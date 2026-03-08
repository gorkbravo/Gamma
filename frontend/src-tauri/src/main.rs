#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::env;
use std::fs::{self, File};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use reqwest::blocking::Client;
use tauri::{AppHandle, Manager, RunEvent, WebviewWindowBuilder};

const API_HOST: &str = "127.0.0.1";
const DEFAULT_API_PORT: u16 = 8000;
const HEALTH_TIMEOUT: Duration = Duration::from_secs(20);
const BUNDLED_BACKEND_NAME: &str = "stratalab-backend";
const LOG_TAIL_BYTES: usize = 2048;

#[derive(Clone, Copy, Eq, PartialEq)]
enum BackendMode {
    Development,
    Bundled,
}

impl BackendMode {
    fn label(self) -> &'static str {
        match self {
            Self::Development => "development",
            Self::Bundled => "packaged",
        }
    }
}

struct BackendLaunch {
    mode: BackendMode,
    executable: PathBuf,
    args: Vec<String>,
    working_dir: PathBuf,
    sample_data_dir: PathBuf,
    cache_dir: PathBuf,
    history_dir: PathBuf,
    log_dir: PathBuf,
    failure_report: PathBuf,
    stdout_log: PathBuf,
    stderr_log: PathBuf,
}

#[derive(Default)]
struct BackendState {
    child: Mutex<Option<Child>>,
}

fn main() {
    let app = tauri::Builder::default()
        .manage(BackendState::default())
        .setup(|app| {
            let app_handle = app.handle().clone();
            thread::spawn(move || {
                if let Err(error) = bootstrap_backend(&app_handle) {
                    let detail = format!("{error}\n\nExpected host: {API_HOST}");
                    update_splash(&app_handle, "Backend startup failed", &detail);
                }
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build StrataLab shell");

    app.run(|app_handle, event| match event {
        RunEvent::Exit => kill_backend(app_handle),
        RunEvent::ExitRequested { .. } => kill_backend(app_handle),
        _ => {}
    });
}

fn bootstrap_backend(app: &AppHandle) -> Result<(), String> {
    let api_port = select_api_port()?;
    let api_base = format!("http://{API_HOST}:{api_port}");
    let health_url = format!("{api_base}/health");
    let launch = resolve_backend_launch(app)?;

    update_splash(
        app,
        &format!("Starting {} backend", launch.mode.label()),
        &format!(
            "Launching {} from {}",
            launch.mode.label(),
            launch.executable.display()
        ),
    );

    let mut child = spawn_backend(&launch, api_port)?;

    update_splash(
        app,
        "Waiting for health",
        &format!("Polling {health_url} before the main window is created."),
    );
    wait_for_health(&mut child, &health_url, &launch)?;

    {
        let state = app.state::<BackendState>();
        *state
            .child
            .lock()
            .map_err(|_| "Backend state lock poisoned".to_string())? = Some(child);
    }

    create_main_window(app, &api_base)?;
    if let Some(splash) = app.get_webview_window("splashscreen") {
        let _ = splash.close();
    }
    Ok(())
}

fn resolve_backend_launch(app: &AppHandle) -> Result<BackendLaunch, String> {
    let runtime_root = app_data_root(app)?;
    let cache_dir = runtime_root.join("cache");
    let history_dir = runtime_root.join("data");
    let log_dir = runtime_root.join("logs");
    fs::create_dir_all(&cache_dir)
        .map_err(|error| format!("Failed to create cache directory {}: {error}", cache_dir.display()))?;
    fs::create_dir_all(&history_dir).map_err(|error| {
        format!(
            "Failed to create history directory {}: {error}",
            history_dir.display()
        )
    })?;
    fs::create_dir_all(&log_dir)
        .map_err(|error| format!("Failed to create log directory {}: {error}", log_dir.display()))?;

    let failure_report = log_dir.join("backend-failure.txt");
    let stdout_log = log_dir.join("backend-stdout.log");
    let stderr_log = log_dir.join("backend-stderr.log");

    if let Some(executable) = bundled_backend_executable(app)? {
        let working_dir = executable
            .parent()
            .ok_or_else(|| format!("Bundled backend path has no parent: {}", executable.display()))?
            .to_path_buf();
        let sample_data_dir = working_dir.join("sample_data");
        return Ok(BackendLaunch {
            mode: BackendMode::Bundled,
            executable,
            args: Vec::new(),
            working_dir,
            sample_data_dir,
            cache_dir,
            history_dir,
            log_dir,
            failure_report,
            stdout_log,
            stderr_log,
        });
    }

    let repo_root = find_repo_root().ok_or_else(|| {
        "Unable to locate the StrataLab repository root. Set STRATALAB_REPO_ROOT if you are running from a non-standard location.".to_string()
    })?;
    let executable = python_path(&repo_root)?;
    Ok(BackendLaunch {
        mode: BackendMode::Development,
        executable,
        args: vec!["-m".into(), "src.api.desktop_entry".into()],
        working_dir: repo_root.clone(),
        sample_data_dir: repo_root.join("sample_data"),
        cache_dir,
        history_dir,
        log_dir,
        failure_report,
        stdout_log,
        stderr_log,
    })
}

fn app_data_root(app: &AppHandle) -> Result<PathBuf, String> {
    let root = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("Failed to resolve the StrataLab app-data directory: {error}"))?
        .join("runtime");
    fs::create_dir_all(&root)
        .map_err(|error| format!("Failed to create app-data directory {}: {error}", root.display()))?;
    Ok(root)
}

fn bundled_backend_executable(app: &AppHandle) -> Result<Option<PathBuf>, String> {
    let resource_dir = match app.path().resource_dir() {
        Ok(path) => path,
        Err(_) => return Ok(None),
    };
    let executable = resource_dir
        .join("backend")
        .join(BUNDLED_BACKEND_NAME)
        .join(executable_name(BUNDLED_BACKEND_NAME));
    if executable.exists() {
        Ok(Some(executable))
    } else {
        Ok(None)
    }
}

fn executable_name(base_name: &str) -> String {
    if cfg!(target_os = "windows") {
        format!("{base_name}.exe")
    } else {
        base_name.to_string()
    }
}

fn spawn_backend(launch: &BackendLaunch, api_port: u16) -> Result<Child, String> {
    let mut command = Command::new(&launch.executable);
    command
        .current_dir(&launch.working_dir)
        .env("STRATALAB_API_PORT", api_port.to_string())
        .env("CACHE_DIR", &launch.cache_dir)
        .env("PORTFOLIO_HISTORY_DIR", &launch.history_dir)
        .env("SAMPLE_DATA_DIR", &launch.sample_data_dir)
        .env("STRATALAB_LOG_DIR", &launch.log_dir)
        .env("STRATALAB_BACKEND_FAILURE_REPORT", &launch.failure_report)
        .env("STRATALAB_APP_DATA_DIR", launch.cache_dir.parent().unwrap_or(&launch.cache_dir));

    for key in ["MOCK_DATA", "LOG_LEVEL", "IB_MARKET_DATA_MODE", "IB_HOST", "IB_PORT", "IB_CLIENT_ID", "IB_ACCOUNT"] {
        if let Ok(value) = env::var(key) {
            command.env(key, value);
        }
    }

    for arg in &launch.args {
        command.arg(arg);
    }

    if launch.mode == BackendMode::Development && cfg!(debug_assertions) {
        command.stdout(Stdio::inherit()).stderr(Stdio::inherit());
    } else {
        let stdout = File::create(&launch.stdout_log).map_err(|error| {
            format!(
                "Failed to create backend stdout log {}: {error}",
                launch.stdout_log.display()
            )
        })?;
        let stderr = File::create(&launch.stderr_log).map_err(|error| {
            format!(
                "Failed to create backend stderr log {}: {error}",
                launch.stderr_log.display()
            )
        })?;
        command.stdout(Stdio::from(stdout)).stderr(Stdio::from(stderr));
    }

    command.spawn().map_err(|error| {
        format!(
            "Failed to start {} backend with {}: {error}",
            launch.mode.label(),
            launch.executable.display()
        )
    })
}

fn wait_for_health(child: &mut Child, health_url: &str, launch: &BackendLaunch) -> Result<(), String> {
    let client = Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(|error| format!("Failed to build health-check client: {error}"))?;
    let deadline = Instant::now() + HEALTH_TIMEOUT;
    let mut last_error = String::from("health endpoint not reachable yet");
    while Instant::now() < deadline {
        if let Some(status) = child
            .try_wait()
            .map_err(|error| format!("Failed to inspect backend process: {error}"))?
        {
            return Err(format!(
                "Backend exited early with status {status}.\n\n{}",
                startup_diagnostics(launch)
            ));
        }
        match client.get(health_url).send() {
            Ok(response) if response.status().is_success() => return Ok(()),
            Ok(response) => {
                last_error = format!("health returned {}", response.status());
            }
            Err(error) => {
                last_error = error.to_string();
            }
        }
        thread::sleep(Duration::from_millis(250));
    }
    let _ = child.kill();
    let _ = child.wait();
    Err(format!(
        "Timed out waiting for backend health. Last error: {last_error}\n\n{}",
        startup_diagnostics(launch)
    ))
}

fn startup_diagnostics(launch: &BackendLaunch) -> String {
    let mut parts = vec![
        format!("Failure report: {}", launch.failure_report.display()),
        format!("stderr log: {}", launch.stderr_log.display()),
        format!("stdout log: {}", launch.stdout_log.display()),
    ];
    if let Some(report) = read_tail(&launch.failure_report) {
        parts.push(format!("Failure report tail:\n{report}"));
    } else if let Some(stderr) = read_tail(&launch.stderr_log) {
        parts.push(format!("stderr tail:\n{stderr}"));
    }
    parts.join("\n")
}

fn read_tail(path: &Path) -> Option<String> {
    let bytes = fs::read(path).ok()?;
    if bytes.is_empty() {
        return None;
    }
    let start = bytes.len().saturating_sub(LOG_TAIL_BYTES);
    let content = String::from_utf8_lossy(&bytes[start..]).trim().to_string();
    if content.is_empty() {
        None
    } else {
        Some(content)
    }
}

fn create_main_window(app: &AppHandle, api_base: &str) -> Result<(), String> {
    if app.get_webview_window("main").is_some() {
        return Ok(());
    }
    let api_base_json = serde_json::to_string(api_base)
        .unwrap_or_else(|_| "\"http://127.0.0.1:8000\"".to_string());
    let init_script = format!("window.__STRATALAB_API_BASE__ = {api_base_json};");
    let window_config = app
        .config()
        .app
        .windows
        .iter()
        .find(|window| window.label == "main")
        .cloned()
        .ok_or_else(|| "Main window config is missing".to_string())?;
    let window = WebviewWindowBuilder::from_config(app, &window_config)
        .map_err(|error| format!("Failed to create main window builder: {error}"))?
        .initialization_script(&init_script)
        .build()
        .map_err(|error| format!("Failed to create main window: {error}"))?;
    window
        .show()
        .map_err(|error| format!("Failed to show main window: {error}"))?;
    Ok(())
}

fn update_splash(app: &AppHandle, headline: &str, detail: &str) {
    if let Some(window) = app.get_webview_window("splashscreen") {
        let headline_json = serde_json::to_string(headline).unwrap_or_else(|_| "\"Status\"".to_string());
        let detail_json = serde_json::to_string(detail).unwrap_or_else(|_| "\"\"".to_string());
        let script = format!(
            "window.__STRATALAB_SET_STATUS__ && window.__STRATALAB_SET_STATUS__({headline_json}, {detail_json});"
        );
        let _ = window.eval(&script);
    }
}

fn find_repo_root() -> Option<PathBuf> {
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Ok(root) = env::var("STRATALAB_REPO_ROOT") {
        candidates.push(PathBuf::from(root));
    }
    if let Ok(current_dir) = env::current_dir() {
        candidates.push(current_dir);
    }
    if let Ok(exe) = env::current_exe() {
        for ancestor in exe.ancestors() {
            candidates.push(ancestor.to_path_buf());
        }
    }
    let manifest_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    candidates.push(manifest_root);

    candidates.into_iter().find(|candidate| is_repo_root(candidate))
}

fn is_repo_root(candidate: &Path) -> bool {
    candidate.join(".venv").exists()
        && candidate.join("pyproject.toml").exists()
        && candidate.join("src").join("api").join("main.py").exists()
}

fn select_api_port() -> Result<u16, String> {
    if let Ok(value) = env::var("STRATALAB_API_PORT") {
        let trimmed = value.trim();
        let port = trimmed
            .parse::<u16>()
            .map_err(|error| format!("Invalid STRATALAB_API_PORT value '{trimmed}': {error}"))?;
        if port == 0 {
            return Err("STRATALAB_API_PORT must be greater than 0.".to_string());
        }
        return Ok(port);
    }
    if TcpListener::bind((API_HOST, DEFAULT_API_PORT)).is_ok() {
        return Ok(DEFAULT_API_PORT);
    }
    let listener = TcpListener::bind((API_HOST, 0))
        .map_err(|error| format!("Unable to reserve a local API port: {error}"))?;
    listener
        .local_addr()
        .map(|address| address.port())
        .map_err(|error| format!("Unable to inspect the reserved API port: {error}"))
}

fn python_path(repo_root: &Path) -> Result<PathBuf, String> {
    let windows_python = repo_root.join(".venv").join("Scripts").join("python.exe");
    if windows_python.exists() {
        return Ok(windows_python);
    }
    let unix_python = repo_root.join(".venv").join("bin").join("python");
    if unix_python.exists() {
        return Ok(unix_python);
    }
    Err(format!(
        "No virtualenv Python found under {}",
        repo_root.join(".venv").display()
    ))
}

fn kill_backend(app: &AppHandle) {
    let state = app.state::<BackendState>();
    let mut guard = match state.child.lock() {
        Ok(guard) => guard,
        Err(_) => return,
    };
    if let Some(mut child) = guard.take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}

impl Drop for BackendState {
    fn drop(&mut self) {
        if let Ok(mut child) = self.child.lock() {
            if let Some(process) = child.as_mut() {
                let _ = process.kill();
            }
        }
    }
}

import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Smoke test del shell de escritorio de release (lo que instala el NSIS), sin instalarlo.
//
// Arranca target/release/gamma-shell.exe con una carpeta de datos temporal. En release el shell
// solo usa el backend empaquetado junto a sus recursos (no recurre al repositorio), así que esto
// prueba el modo instalado: lanzar gamma-backend.exe, esperar /health, cargar la interfaz y
// escribir el marcador de smoke, tras lo cual el shell se cierra solo.
//
// Requiere haber ejecutado antes `npm run tauri:build`.

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(scriptDir, "..");
const releaseDir = path.join(process.env.CARGO_TARGET_DIR ?? path.join(frontendDir, "src-tauri", "target"), "release");
const shellExe = path.join(releaseDir, process.platform === "win32" ? "gamma-shell.exe" : "gamma-shell");

await main();

async function main() {
  if (!existsSync(shellExe)) {
    console.error(`Release shell not found at ${shellExe}. Run npm run tauri:build first.`);
    process.exit(1);
  }
  const root = mkdtempSync(path.join(os.tmpdir(), "gamma-desktop-bundle-"));
  const appDataDir = path.join(root, "app-data");
  const smokeFile = path.join(root, "desktop-smoke.json");
  const child = spawn(shellExe, [], {
    // Fuera del repositorio, como una instalación real.
    cwd: root,
    env: { ...cleanEnvironment(process.env), GAMMA_DESKTOP_SMOKE_FILE: smokeFile, GAMMA_APP_DATA_DIR: appDataDir },
    stdio: "ignore"
  });

  try {
    const payload = await waitForSmokeFile(child, smokeFile, appDataDir);
    if (payload.status !== "ok" || payload.window !== "main" || payload.client !== "tauri") {
      throw new Error(`Unexpected smoke payload: ${JSON.stringify(payload)}`);
    }
    await waitForExit(child, 15000);
    const stdout = safeRead(path.join(appDataDir, "logs", "backend-stdout.log")) + safeRead(path.join(appDataDir, "logs", "backend-stderr.log"));
    if (!/Starting Gamma desktop backend/.test(stdout)) {
      throw new Error(`Backend log does not show the packaged backend starting:\n${stdout.slice(-1500)}`);
    }
    console.log(`Desktop bundle smoke check passed: packaged backend on ${payload.apiBase}, main window loaded.`);
    console.log(`App data written under a temporary folder: ${listTree(appDataDir).join(", ")}`);
  } finally {
    if (child.exitCode === null) {
      child.kill();
      await waitForExit(child, 5000);
    }
    rmSync(root, { force: true, recursive: true });
  }
}

// Sin claves, identidad SEC ni ajustes de Gamma heredados: el resultado no depende del equipo.
function cleanEnvironment(env) {
  const cleaned = {};
  for (const [key, value] of Object.entries(env)) {
    const upper = key.toUpperCase();
    if (/_API_KEY$|_TOKEN$|_SECRET$/.test(upper)) continue;
    if (upper.startsWith("GAMMA_") || upper.startsWith("IB_") || upper === "EDGAR_IDENTITY") continue;
    if (["MOCK_DATA", "BASE_CURRENCY", "CACHE_DIR", "PORTFOLIO_HISTORY_DIR", "SAMPLE_DATA_DIR"].includes(upper)) continue;
    cleaned[key] = value;
  }
  return cleaned;
}

async function waitForSmokeFile(child, filePath, appDataDir) {
  const deadline = Date.now() + 120000;
  while (Date.now() < deadline) {
    if (existsSync(filePath)) {
      try {
        return JSON.parse(readFileSync(filePath, "utf-8"));
      } catch {
        // El shell aún está escribiendo el marcador.
      }
    }
    if (child.exitCode !== null) {
      throw new Error(`Desktop shell exited with code ${child.exitCode} before loading the main window.\n${startupLogs(appDataDir)}`.trim());
    }
    await sleep(500);
  }
  throw new Error(`Timed out waiting for the desktop smoke marker.\n${startupLogs(appDataDir)}`.trim());
}

// Lo que el shell y el backend dejaron al fallar el arranque (el splash no es visible aquí).
function startupLogs(appDataDir) {
  const logDir = path.join(appDataDir, "logs");
  return ["shell-startup-failure.txt", "backend-failure.txt", "backend-stderr.log"]
    .map((name) => {
      const text = safeRead(path.join(logDir, name)).trim();
      return text ? `--- ${name}\n${text.slice(-1500)}` : "";
    })
    .filter(Boolean)
    .join("\n");
}

function listTree(dir) {
  try {
    return readdirSync(dir);
  } catch {
    return [];
  }
}

function safeRead(filePath) {
  try {
    return readFileSync(filePath, "utf-8");
  } catch {
    return "";
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function waitForExit(child, timeoutMs) {
  if (child.exitCode !== null) {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    child.once("exit", resolve);
    setTimeout(resolve, timeoutMs);
  });
}

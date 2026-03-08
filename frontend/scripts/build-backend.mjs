import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(frontendDir, "..");
const pyInstallerRoot = path.join(frontendDir, "src-tauri", ".pyinstaller");
const distPath = path.join(frontendDir, "src-tauri", "resources", "backend");
const workPath = path.join(pyInstallerRoot, "build");
const specPath = pyInstallerRoot;
const appName = "stratalab-backend";
const python = resolvePython();
const dataSeparator = process.platform === "win32" ? ";" : ":";

buildBackend();

function buildBackend() {
  ensurePyInstaller();
  fs.rmSync(distPath, { force: true, recursive: true });
  fs.mkdirSync(distPath, { recursive: true });
  fs.mkdirSync(workPath, { recursive: true });
  fs.mkdirSync(specPath, { recursive: true });

  const args = [
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onedir",
    "--name",
    appName,
    "--distpath",
    distPath,
    "--workpath",
    workPath,
    "--specpath",
    specPath,
    "--paths",
    repoRoot,
    "--add-data",
    `${path.join(repoRoot, "sample_data")}${dataSeparator}sample_data`,
    "--hidden-import",
    "uvicorn.logging",
    "--hidden-import",
    "uvicorn.loops.asyncio",
    "--hidden-import",
    "uvicorn.protocols.http.h11_impl",
    "--hidden-import",
    "uvicorn.protocols.websockets.websockets_impl",
    "--hidden-import",
    "uvicorn.lifespan.on",
    path.join(repoRoot, "src", "api", "desktop_entry.py")
  ];

  const result = spawnSync(python, args, {
    cwd: repoRoot,
    env: { ...process.env },
    stdio: "inherit"
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

function ensurePyInstaller() {
  const result = spawnSync(python, ["-m", "PyInstaller", "--version"], {
    cwd: repoRoot,
    env: { ...process.env },
    encoding: "utf-8"
  });
  if (result.status === 0) {
    return;
  }
  const installHint =
    process.platform === "win32"
      ? `${python} -m pip install pyinstaller`
      : `${python} -m pip install pyinstaller`;
  console.error("PyInstaller is required to package the StrataLab backend.");
  console.error(`Install it with: ${installHint}`);
  process.exit(result.status ?? 1);
}

function resolvePython() {
  if (process.env.STRATALAB_PYTHON) {
    return process.env.STRATALAB_PYTHON;
  }

  const candidates = [
    path.join(repoRoot, ".venv", process.platform === "win32" ? "Scripts" : "bin", process.platform === "win32" ? "python.exe" : "python"),
    process.platform === "win32" ? "python.exe" : "python3",
    "python"
  ];

  for (const candidate of candidates) {
    const result = spawnSync(candidate, ["--version"], {
      cwd: repoRoot,
      env: { ...process.env },
      stdio: "ignore"
    });
    if (result.status === 0) {
      return candidate;
    }
  }

  console.error("Unable to locate a Python interpreter for backend packaging.");
  process.exit(1);
}

import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { ensureCargoTargetDir } from "./tauri-target-dir.mjs";

const [, , ...args] = process.argv;
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(scriptDir, "..");
const manifestPath = path.join(frontendDir, "src-tauri", "Cargo.toml");
const env = { ...process.env };

ensureCargoTargetDir(env, "check");

const child = spawn(process.platform === "win32" ? "cargo.exe" : "cargo", ["check", "--manifest-path", manifestPath, ...args], {
  cwd: frontendDir,
  env,
  stdio: "inherit"
});

child.on("error", (error) => {
  console.error("Failed to launch cargo.", error);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});

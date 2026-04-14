import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(scriptDir, "..");
const tauriDir = path.join(frontendDir, "src-tauri");

export function ensureCargoTargetDir(env, mode) {
  if (env.CARGO_TARGET_DIR) {
    return env.CARGO_TARGET_DIR;
  }

  const targetDir = mode === "check" ? path.join(tauriDir, "target-check") : path.join(tauriDir, "target");
  env.CARGO_TARGET_DIR = targetDir;
  return targetDir;
}

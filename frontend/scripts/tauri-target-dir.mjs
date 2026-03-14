import os from "node:os";
import path from "node:path";

export function ensureCargoTargetDir(env, mode) {
  if (env.CARGO_TARGET_DIR) {
    return env.CARGO_TARGET_DIR;
  }

  const targetSuffix = mode === "build" ? "build" : mode === "check" ? "check" : "dev";
  const targetDir = path.join(os.tmpdir(), `gamma-tauri-${targetSuffix}`);
  env.CARGO_TARGET_DIR = targetDir;
  return targetDir;
}

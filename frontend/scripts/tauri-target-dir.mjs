import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..", "..");

export function ensureCargoTargetDir(env, mode) {
  if (env.CARGO_TARGET_DIR) {
    return env.CARGO_TARGET_DIR;
  }

  const targetSuffix = mode === "build" ? "build" : mode === "check" ? "check" : "dev";
  const targetDir = path.join(repoRoot, "target", `gamma-tauri-${targetSuffix}`);
  env.CARGO_TARGET_DIR = targetDir;
  return targetDir;
}

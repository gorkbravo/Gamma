import { spawn, spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { ensureCargoTargetDir } from "./tauri-target-dir.mjs";

const [, , ...args] = process.argv;

if (args.length === 0) {
  console.error("Usage: node ./scripts/run-tauri.mjs <tauri-args...>");
  process.exit(1);
}

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(scriptDir, "..");
const env = { ...process.env };
if (args[0] === "build" && env.GAMMA_SKIP_BACKEND_PACKAGE !== "true") {
  const packageBackend = spawnSync(process.execPath, [path.join(scriptDir, "build-backend.mjs")], {
    cwd: frontendDir,
    env,
    stdio: "inherit"
  });
  if (packageBackend.status !== 0) {
    process.exit(packageBackend.status ?? 1);
  }
}
if (!env.CARGO_TARGET_DIR) {
  ensureCargoTargetDir(env, args[0] === "build" ? "build" : "dev");
}

const child =
  process.platform === "win32"
    ? spawn(
        "cmd.exe",
        ["/d", "/s", "/c", `npx --no-install tauri ${args.map(quoteForCmd).join(" ")}`],
        {
          cwd: frontendDir,
          env,
          stdio: "inherit"
        }
      )
    : spawn("npx", ["--no-install", "tauri", ...args], {
        cwd: frontendDir,
        env,
        stdio: "inherit"
      });

child.on("error", (error) => {
  console.error("Failed to launch Tauri CLI.", error);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});

function quoteForCmd(value) {
  if (/^[A-Za-z0-9_./:-]+$/.test(value)) {
    return value;
  }
  return `"${value.replace(/"/g, '\\"')}"`;
}

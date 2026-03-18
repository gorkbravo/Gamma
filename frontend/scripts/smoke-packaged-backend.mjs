import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { spawn, spawnSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(scriptDir, "..");
const backendBuildScript = path.join(scriptDir, "build-backend.mjs");
const backendExe = path.join(frontendDir, "src-tauri", "resources", "backend", "gamma-backend", executableName("gamma-backend"));

await main();

async function main() {
  const packageResult = spawnSync(process.execPath, [backendBuildScript], {
    cwd: frontendDir,
    env: { ...process.env },
    stdio: "inherit"
  });
  if (packageResult.status !== 0) {
    process.exit(packageResult.status ?? 1);
  }

  const port = await freePort();
  const tempRoot = mkdtempSync(path.join(os.tmpdir(), "gamma-packaged-backend-"));
  const logDir = path.join(tempRoot, "logs");
  const failureReport = path.join(logDir, "backend-failure.txt");
  const child = spawn(backendExe, [], {
    cwd: path.dirname(backendExe),
    env: {
      ...process.env,
      MOCK_DATA: "true",
      GAMMA_API_PORT: String(port),
      CACHE_DIR: path.join(tempRoot, "cache"),
      PORTFOLIO_HISTORY_DIR: path.join(tempRoot, "data"),
      SAMPLE_DATA_DIR: path.join(path.dirname(backendExe), "sample_data"),
      GAMMA_LOG_DIR: logDir,
      GAMMA_BACKEND_FAILURE_REPORT: failureReport
    },
    stdio: "ignore"
  });

  try {
    await waitForHealth(port, child, failureReport);
    console.log(`Packaged backend smoke check passed on http://127.0.0.1:${port}/health`);
  } finally {
    child.kill();
    await onceExit(child);
    rmSync(tempRoot, { force: true, recursive: true });
  }
}

async function waitForHealth(port, child, failureReport) {
  const deadline = Date.now() + 20000;
  let lastError = "health endpoint not reachable yet";

  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`Packaged backend exited early with code ${child.exitCode}. ${safeRead(failureReport)}`.trim());
    }

    try {
      const response = await fetch(`http://127.0.0.1:${port}/health`);
      if (response.ok) {
        return;
      }
      lastError = `health returned ${response.status}`;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }

    await sleep(250);
  }

  throw new Error(`Timed out waiting for packaged backend health: ${lastError}`);
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

function executableName(baseName) {
  return process.platform === "win32" ? `${baseName}.exe` : baseName;
}

function onceExit(child) {
  if (child.exitCode !== null) {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    child.once("exit", resolve);
    setTimeout(resolve, 5000);
  });
}

async function freePort() {
  const net = await import("node:net");
  return await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 0;
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve(port);
      });
    });
  });
}

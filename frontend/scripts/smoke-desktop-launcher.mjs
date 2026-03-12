import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { spawn, spawnSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(frontendDir, "..");
const markerRoot = mkdtempSync(path.join(os.tmpdir(), "gamma-desktop-smoke-"));
const smokeFile = path.join(markerRoot, "desktop-smoke.json");
const python = resolvePython();

await main();

async function main() {
  const child = spawn(python, ["-m", "src.desktop_launcher"], {
    cwd: repoRoot,
    env: {
      ...process.env,
      MOCK_DATA: "true",
      GAMMA_DESKTOP_SMOKE_FILE: smokeFile
    },
    stdio: "inherit"
  });

  try {
    const payload = await waitForSmokeFile(child, smokeFile);
    if (payload.status !== "ok") {
      throw new Error(`Unexpected smoke payload: ${JSON.stringify(payload)}`);
    }
    if (payload.window !== "main") {
      throw new Error(`Smoke marker came from unexpected window '${payload.window}'.`);
    }
    console.log(`Desktop launcher smoke check passed using ${payload.client} on ${payload.apiBase}`);
    await waitForExit(child);
    if ((child.exitCode ?? 0) !== 0) {
      throw new Error(`Desktop launcher exited with code ${child.exitCode}.`);
    }
  } finally {
    if (child.exitCode === null) {
      child.kill();
      await waitForExit(child);
    }
    rmSync(markerRoot, { force: true, recursive: true });
  }
}

async function waitForSmokeFile(child, filePath) {
  const deadline = Date.now() + 120000;
  let lastError = "desktop smoke file not written yet";

  while (Date.now() < deadline) {
    if (child.exitCode !== null && child.exitCode !== 0) {
      throw new Error(`Desktop launcher exited early with code ${child.exitCode}.`);
    }
    try {
      return JSON.parse(readFileSync(filePath, "utf-8"));
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await sleep(500);
  }

  throw new Error(`Timed out waiting for desktop smoke marker: ${lastError}`);
}

function waitForExit(child) {
  if (child.exitCode !== null) {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    child.once("exit", resolve);
    setTimeout(resolve, 10000);
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function resolvePython() {
  if (process.env.GAMMA_PYTHON) {
    return process.env.GAMMA_PYTHON;
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

  throw new Error("Unable to locate Python for desktop launcher smoke testing.");
}

import { spawn } from "node:child_process";
import process from "node:process";

const DEV_SERVER_URL = process.env.GAMMA_DEV_SERVER_URL ?? "http://127.0.0.1:5173";
const VITE_CLIENT_URL = `${DEV_SERVER_URL.replace(/\/+$/, "")}/@vite/client`;

await main();

async function main() {
  if (await hasHealthyViteServer()) {
    console.log(`Reusing existing Vite dev server at ${DEV_SERVER_URL}`);
    return;
  }

  const child = spawn(npmCommand(), ["run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"], {
    env: { ...process.env },
    stdio: "inherit",
    shell: process.platform === "win32"
  });

  child.on("error", (error) => {
    console.error("Failed to launch the Vite dev server.", error);
    process.exit(1);
  });

  const signalForwarder = (signal) => {
    if (child.exitCode === null) {
      child.kill(signal);
    }
  };
  process.on("SIGINT", signalForwarder);
  process.on("SIGTERM", signalForwarder);

  const exitCode = await new Promise((resolve) => {
    child.on("exit", (code, signal) => {
      if (signal) {
        resolve(1);
        return;
      }
      resolve(code ?? 0);
    });
  });
  process.exit(exitCode);
}

async function hasHealthyViteServer() {
  try {
    const response = await fetch(VITE_CLIENT_URL);
    if (!response.ok) {
      return false;
    }
    const body = await response.text();
    return body.includes("createHotContext") || body.includes("import.meta.hot");
  } catch {
    return false;
  }
}

function npmCommand() {
  return process.platform === "win32" ? "npm.cmd" : "npm";
}

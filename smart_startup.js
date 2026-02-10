#!/usr/bin/env node
/* Smart startup script: tries start, falls back to install, then start again. */
const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const SCRIPT_DIR = path.resolve(__dirname);
process.chdir(SCRIPT_DIR);

const isWin = process.platform === "win32";
const isMac = process.platform === "darwin";
const isLinux = process.platform === "linux";

function log(msg = "") {
  process.stdout.write(`${msg}\n`);
}

function run(cmd, args, opts = {}) {
  const result = spawnSync(cmd, args, {
    stdio: "inherit",
    env: process.env,
    ...opts,
  });
  return result.status ?? 1;
}

function commandExists(cmd) {
  const whichCmd = isWin ? "where" : "which";
  const res = spawnSync(whichCmd, [cmd], { stdio: "ignore" });
  return res.status === 0;
}

function parseArgs(argv) {
  const args = [];
  let i = 0;
  while (i < argv.length) {
    const arg = argv[i];
    if (arg === "--help" || arg === "-h") {
      return { args: ["--help"], help: true };
    }
    args.push(arg);
    i += 1;
  }
  return { args, help: false };
}

function getScriptPath(kind) {
  if (isWin) {
    if (kind === "start") return path.join(SCRIPT_DIR, "start.ps1");
    if (kind === "install") return path.join(SCRIPT_DIR, "install_forge_win.ps1");
  }
  if (kind === "start") return path.join(SCRIPT_DIR, "start.sh");
  if (kind === "install") return path.join(SCRIPT_DIR, "install.sh");
  return "";
}

function runScript(kind, args) {
  const scriptPath = getScriptPath(kind);
  if (!fs.existsSync(scriptPath)) {
    log(`ERROR: Missing ${kind} script: ${scriptPath}`);
    return 1;
  }

  if (scriptPath.endsWith(".ps1")) {
    if (!commandExists("powershell")) {
      log("ERROR: PowerShell not available to run .ps1 script.");
      return 1;
    }
    return run("powershell", ["-ExecutionPolicy", "Bypass", "-File", scriptPath, ...args]);
  }

  if (scriptPath.endsWith(".sh")) {
    if (commandExists("bash")) {
      return run("bash", [scriptPath, ...args]);
    }
    if (commandExists("sh")) {
      return run("sh", [scriptPath, ...args]);
    }
    log("ERROR: No shell available to run .sh script.");
    return 1;
  }

  return 1;
}

function postStart() {
  if (!commandExists("docker")) {
    log("Docker not found in PATH; skipping health checks and migrations.");
    return;
  }

  log("");
  log("=== Post-Start Checks ===");
  run("docker", ["exec", "wfhub-v2-main-api", "alembic", "upgrade", "head"]);
  run("docker", ["exec", "wfhub-v2-main-api", "curl", "-sS", "http://wfhub-v2-forge-api:8001/health"]);
  run("curl", ["-sS", "http://localhost:8002/health/full"]);
}

function main() {
  const { args, help } = parseArgs(process.argv.slice(2));
  if (help) {
    log("Usage: smart_startup.js [OPTIONS]");
    log("");
    log("Options:");
    log("  -w, --workspace NAME   Set the default workspace");
    log("  --no-browser           Don't open browser at end");
    log("  -h, --help             Show this help message");
    return 0;
  }

  log("=== Smart Startup ===");
  log("Attempting to start the stack...");
  let status = runScript("start", args);
  if (status === 0) {
    log("Start succeeded.");
    postStart();
    return 0;
  }

  log("Start failed. Attempting install...");
  status = runScript("install", args);
  if (status !== 0) {
    log("Install failed. Please review the errors above.");
    return status;
  }

  log("Install completed. Starting again...");
  status = runScript("start", args);
  if (status === 0) {
    log("Start succeeded.");
    postStart();
  }
  return status;
}

process.exit(main());

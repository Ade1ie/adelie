#!/usr/bin/env node

/**
 * bin/adelie.js — Adelie CLI entrypoint
 *
 * Thin Node.js wrapper that locates the Python venv
 * and delegates all commands to adelie/cli.py.
 */

const { spawn, execSync } = require("child_process");
const path = require("path");
const fs = require("fs");

// ── Paths ────────────────────────────────────────────────────────────────────
const PKG_ROOT = path.resolve(__dirname, "..");
const VENV_DIR = path.join(PKG_ROOT, ".venv");
const CLI_PY = path.join(PKG_ROOT, "adelie", "cli.py");
const REQUIREMENTS = path.join(PKG_ROOT, "requirements.txt");

const IS_WIN = process.platform === "win32";
const PYTHON_BIN = IS_WIN
  ? path.join(VENV_DIR, "Scripts", "python.exe")
  : path.join(VENV_DIR, "bin", "python");

// ── Helpers ──────────────────────────────────────────────────────────────────

function findSystemPython() {
  const candidates = IS_WIN
    ? ["python", "python3", "py"]
    : ["python3", "python"];
  for (const cmd of candidates) {
    try {
      const ver = execSync(`${cmd} --version 2>&1`, { encoding: "utf-8" }).trim();
      if (ver.includes("Python 3")) return cmd;
    } catch {}
  }
  return null;
}

function ensureVenv() {
  if (fs.existsSync(PYTHON_BIN)) return;

  console.log("[adelie] Setting up Python environment...");
  const sysPython = findSystemPython();
  if (!sysPython) {
    console.error("[adelie] ERROR: Python 3 is required but not found.");
    console.error("         Install from: https://www.python.org/downloads/");
    process.exit(1);
  }

  try {
    execSync(`${sysPython} -m venv "${VENV_DIR}"`, { stdio: "inherit" });
    const pip = IS_WIN
      ? path.join(VENV_DIR, "Scripts", "pip")
      : path.join(VENV_DIR, "bin", "pip");
    const pipEnv = { ...process.env };
    if (IS_WIN) pipEnv.PYTHONUTF8 = "1";
    execSync(`"${pip}" install -r "${REQUIREMENTS}"`, { stdio: "inherit", env: pipEnv });
    console.log("[adelie] Python environment ready.");
  } catch (err) {
    console.error(`[adelie] ERROR: Failed to set up Python environment: ${err.message}`);
    process.exit(1);
  }
}

// ── Main ─────────────────────────────────────────────────────────────────────

ensureVenv();

const child = spawn(PYTHON_BIN, [CLI_PY, ...process.argv.slice(2)], {
  cwd: process.cwd(),
  stdio: "inherit",
  env: {
    ...process.env,
    ADELIE_PKG_ROOT: PKG_ROOT,
    ADELIE_CWD: process.cwd(),
  },
});

child.on("close", (code) => process.exit(code ?? 0));
child.on("error", (err) => {
  console.error(`[adelie] ERROR: Failed to run: ${err.message}`);
  process.exit(1);
});

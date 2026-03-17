#!/usr/bin/env node

/**
 * scripts/postinstall.js — Runs after npm install
 *
 * Creates a Python virtual environment and installs requirements.
 */

const { execSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const PKG_ROOT = path.resolve(__dirname, "..");
const VENV_DIR = path.join(PKG_ROOT, ".venv");
const REQUIREMENTS = path.join(PKG_ROOT, "requirements.txt");
const IS_WIN = process.platform === "win32";
const PYTHON_BIN = IS_WIN
  ? path.join(VENV_DIR, "Scripts", "python.exe")
  : path.join(VENV_DIR, "bin", "python");

if (fs.existsSync(PYTHON_BIN)) {
  console.log("[adelie] Python environment already exists, skipping setup.");
  process.exit(0);
}

// Find system Python 3
const candidates = IS_WIN ? ["python", "python3", "py"] : ["python3", "python"];
let sysPython = null;

for (const cmd of candidates) {
  try {
    const ver = execSync(`${cmd} --version 2>&1`, { encoding: "utf-8" }).trim();
    if (ver.includes("Python 3")) {
      sysPython = cmd;
      break;
    }
  } catch {}
}

if (!sysPython) {
  console.error("[adelie] ERROR: Python 3 is required but not found.");
  console.error("         Install it from: https://www.python.org/downloads/");
  console.error("         After installing Python 3, run: npm rebuild adelie");
  process.exit(1);
}

console.log(`[adelie] Creating Python venv with ${sysPython}...`);

try {
  execSync(`${sysPython} -m venv "${VENV_DIR}"`, { stdio: "inherit" });
  const pip = IS_WIN
    ? path.join(VENV_DIR, "Scripts", "pip")
    : path.join(VENV_DIR, "bin", "pip");
  execSync(`"${pip}" install -q -r "${REQUIREMENTS}"`, { stdio: "inherit" });
  console.log("[adelie] Python environment ready.");
} catch (err) {
  console.error(`[adelie] ERROR: Failed to set up Python environment.`);
  console.error(`         ${err.message}`);
  console.error("         Try manually: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt");
  process.exit(1);
}

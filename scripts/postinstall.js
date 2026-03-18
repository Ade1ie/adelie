#!/usr/bin/env node

/**
 * scripts/postinstall.js — Runs after npm install
 *
 * Creates a Python virtual environment, installs requirements,
 * and shows a welcome screen with initial setup guide.
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

// ── Color helpers ────────────────────────────────────────────────────────────
const c = {
  reset:    "\x1b[0m",
  bold:     "\x1b[1m",
  dim:      "\x1b[2m",
  italic:   "\x1b[3m",
  underline:"\x1b[4m",
  cyan:     "\x1b[36m",
  green:    "\x1b[32m",
  yellow:   "\x1b[33m",
  blue:     "\x1b[34m",
  magenta:  "\x1b[35m",
  white:    "\x1b[97m",
  gray:     "\x1b[90m",
  bgBlue:   "\x1b[44m",
  bgMagenta:"\x1b[45m",
  bgCyan:   "\x1b[46m",
};

function showWelcome() {
  const banner = `
${c.cyan}${c.bold}
    ___       __     ___
   /   | ____/ /__  / (_)__
  / /| |/ __  / _ \\/ / / _ \\
 / ___ / /_/ /  __/ / /  __/
/_/  |_\\__,_/\\___/_/_/\\___/
${c.reset}
${c.bold}${c.white}  Self-Communicating Autonomous AI Loop System${c.reset}
${c.dim}${c.cyan}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${c.reset}
`;

  const info = `
  ${c.green}${c.bold}✔ Installation complete!${c.reset}

  ${c.bold}${c.white}🚀 Quick Start${c.reset}
  ${c.gray}─────────────────────────────────────────${c.reset}

  ${c.yellow}${c.bold}1.${c.reset} ${c.white}Initialize a workspace${c.reset}
     ${c.cyan}$ ${c.bold}adelie init${c.reset}

  ${c.yellow}${c.bold}2.${c.reset} ${c.white}Configure your LLM provider${c.reset}
     ${c.cyan}$ ${c.bold}adelie config --provider gemini --api-key YOUR_KEY${c.reset}
     ${c.dim}or for local Ollama:${c.reset}
     ${c.cyan}$ ${c.bold}adelie config --provider ollama --model gemma3:12b${c.reset}

  ${c.yellow}${c.bold}3.${c.reset} ${c.white}Start the autonomous AI loop${c.reset}
     ${c.cyan}$ ${c.bold}adelie run --goal "Build a REST API"${c.reset}

  ${c.gray}─────────────────────────────────────────${c.reset}

  ${c.bold}${c.white}📖 Useful Commands${c.reset}
  ${c.dim}  adelie status${c.reset}      ${c.gray}— System health check${c.reset}
  ${c.dim}  adelie phase${c.reset}       ${c.gray}— Current project phase${c.reset}
  ${c.dim}  adelie kb${c.reset}          ${c.gray}— Knowledge Base summary${c.reset}
  ${c.dim}  adelie --help${c.reset}      ${c.gray}— Full command reference${c.reset}

  ${c.gray}─────────────────────────────────────────${c.reset}
  ${c.magenta}${c.bold}♥${c.reset}  ${c.dim}GitHub: ${c.underline}https://github.com/Ade1ie/adelie${c.reset}
  ${c.blue}${c.bold}★${c.reset}  ${c.dim}npm:    ${c.underline}https://www.npmjs.com/package/adelie-ai${c.reset}
`;

  console.log(banner);
  console.log(info);
}

// ── Python setup ─────────────────────────────────────────────────────────────

if (fs.existsSync(PYTHON_BIN)) {
  showWelcome();
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
  console.error(`\n  ${c.yellow}${c.bold}⚠  Python 3 is required but not found.${c.reset}`);
  console.error(`  ${c.dim}Install it from: ${c.underline}https://www.python.org/downloads/${c.reset}`);
  console.error(`  ${c.dim}After installing, run: ${c.cyan}npm rebuild adelie-ai${c.reset}\n`);
  process.exit(1);
}

console.log(`\n  ${c.cyan}${c.bold}⏳ Setting up Python environment...${c.reset}`);
console.log(`  ${c.dim}Using: ${sysPython}${c.reset}\n`);

try {
  execSync(`${sysPython} -m venv "${VENV_DIR}"`, { stdio: "inherit" });

  const pip = IS_WIN
    ? path.join(VENV_DIR, "Scripts", "pip")
    : path.join(VENV_DIR, "bin", "pip");

  // Use --encoding utf-8 via env to avoid cp949 issues on Windows
  const pipEnv = { ...process.env };
  if (IS_WIN) {
    pipEnv.PYTHONUTF8 = "1";
  }

  execSync(`"${pip}" install -q -r "${REQUIREMENTS}"`, {
    stdio: "inherit",
    env: pipEnv,
  });

  console.log(`  ${c.green}${c.bold}✔ Python environment ready.${c.reset}\n`);
  showWelcome();
} catch (err) {
  console.error(`\n  ${c.yellow}${c.bold}⚠  Failed to set up Python environment.${c.reset}`);
  console.error(`  ${c.dim}${err.message}${c.reset}`);
  console.error(`  ${c.dim}Try manually:${c.reset}`);
  if (IS_WIN) {
    console.error(`  ${c.cyan}python -m venv .venv && .venv\\Scripts\\pip install -r requirements.txt${c.reset}`);
  } else {
    console.error(`  ${c.cyan}python3 -m venv .venv && .venv/bin/pip install -r requirements.txt${c.reset}`);
  }
  console.error("");
  process.exit(1);
}

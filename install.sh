#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Adelie Installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Ade1ie/adelie/main/install.sh | bash
#
# What it does:
#   1. Detects OS and architecture
#   2. Checks for Python 3.10+ and Node.js 16+
#   3. Installs adelie-ai via npm (global)
#   4. Verifies installation
#
# Environment variables:
#   ADELIE_VERSION  — Install a specific version (default: latest)
#   ADELIE_NO_COLOR — Disable colored output
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────────────────
if [ -z "${ADELIE_NO_COLOR:-}" ] && [ -t 1 ]; then
  BOLD="\033[1m"
  DIM="\033[2m"
  CYAN="\033[36m"
  GREEN="\033[32m"
  YELLOW="\033[33m"
  RED="\033[31m"
  RESET="\033[0m"
else
  BOLD="" DIM="" CYAN="" GREEN="" YELLOW="" RED="" RESET=""
fi

info()  { echo -e "  ${CYAN}${BOLD}▸${RESET} $1"; }
ok()    { echo -e "  ${GREEN}${BOLD}✔${RESET} $1"; }
warn()  { echo -e "  ${YELLOW}${BOLD}⚠${RESET} $1"; }
err()   { echo -e "  ${RED}${BOLD}✕${RESET} $1" >&2; }
die()   { err "$1"; exit 1; }

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}"
echo "     ___       __     ___"
echo "    /   | ____/ /__  / (_)__"
echo "   / /| |/ __  / _ \\/ / / _ \\"
echo "  / ___ / /_/ /  __/ / /  __/"
echo " /_/  |_\\__,_/\\___/_/_/\\___/"
echo -e "${RESET}"
echo -e "  ${BOLD}Adelie Installer${RESET}"
echo -e "  ${DIM}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""

# ── OS Detection ──────────────────────────────────────────────────────────────
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
  Linux*)  OS_NAME="Linux" ;;
  Darwin*) OS_NAME="macOS" ;;
  MINGW*|MSYS*|CYGWIN*) OS_NAME="Windows" ;;
  *)       die "Unsupported OS: $OS" ;;
esac

info "Detected: ${BOLD}${OS_NAME}${RESET} (${ARCH})"

# ── Check Python ──────────────────────────────────────────────────────────────
PYTHON_CMD=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then
    ver=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
    major=$(echo "$ver" | cut -d. -f1)
    minor=$(echo "$ver" | cut -d. -f2)
    if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
      PYTHON_CMD="$cmd"
      break
    fi
  fi
done

if [ -z "$PYTHON_CMD" ]; then
  err "Python 3.10+ is required but not found."
  echo ""
  case "$OS_NAME" in
    macOS)
      echo -e "  ${DIM}Install with Homebrew:${RESET}"
      echo -e "  ${CYAN}brew install python@3.12${RESET}"
      ;;
    Linux)
      echo -e "  ${DIM}Install with your package manager:${RESET}"
      echo -e "  ${CYAN}sudo apt install python3 python3-venv  ${DIM}# Debian/Ubuntu${RESET}"
      echo -e "  ${CYAN}sudo dnf install python3               ${DIM}# Fedora${RESET}"
      ;;
    *)
      echo -e "  ${DIM}Download from: ${CYAN}https://www.python.org/downloads/${RESET}"
      ;;
  esac
  echo ""
  exit 1
fi

ok "Python: $($PYTHON_CMD --version 2>&1)"

# ── Check Node.js ─────────────────────────────────────────────────────────────
if ! command -v node &>/dev/null; then
  err "Node.js 16+ is required but not found."
  echo ""
  case "$OS_NAME" in
    macOS)
      echo -e "  ${DIM}Install with Homebrew:${RESET}"
      echo -e "  ${CYAN}brew install node${RESET}"
      ;;
    Linux)
      echo -e "  ${DIM}Install with nvm (recommended):${RESET}"
      echo -e "  ${CYAN}curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash${RESET}"
      echo -e "  ${CYAN}nvm install --lts${RESET}"
      ;;
    *)
      echo -e "  ${DIM}Download from: ${CYAN}https://nodejs.org/${RESET}"
      ;;
  esac
  echo ""
  exit 1
fi

NODE_VER=$(node --version | grep -oP '\d+' | head -1)
if [ "$NODE_VER" -lt 16 ]; then
  die "Node.js 16+ required, found: $(node --version)"
fi

ok "Node.js: $(node --version)"

# ── Check npm ─────────────────────────────────────────────────────────────────
if ! command -v npm &>/dev/null; then
  die "npm is required but not found. It should come with Node.js."
fi

ok "npm: $(npm --version)"

# ── Install Adelie ────────────────────────────────────────────────────────────
VERSION="${ADELIE_VERSION:-latest}"
echo ""
info "Installing ${BOLD}adelie-ai@${VERSION}${RESET} globally..."
echo ""

if npm install -g "adelie-ai@${VERSION}"; then
  echo ""
  ok "${GREEN}${BOLD}Adelie installed successfully!${RESET}"
else
  echo ""
  err "Installation failed."
  echo ""
  echo -e "  ${DIM}Try with sudo (Linux/macOS):${RESET}"
  echo -e "  ${CYAN}sudo npm install -g adelie-ai@${VERSION}${RESET}"
  echo ""
  echo -e "  ${DIM}Or fix npm permissions:${RESET}"
  echo -e "  ${CYAN}https://docs.npmjs.com/resolving-eacces-permissions-errors${RESET}"
  exit 1
fi

# ── Verify ────────────────────────────────────────────────────────────────────
echo ""
if command -v adelie &>/dev/null; then
  ok "Verified: $(adelie --version 2>&1 || echo 'adelie is on PATH')"
else
  warn "adelie not found on PATH. You may need to restart your terminal."
fi

# ── Next steps ────────────────────────────────────────────────────────────────
echo ""
echo -e "  ${BOLD}🚀 Next Steps${RESET}"
echo -e "  ${DIM}───────────────────────────────${RESET}"
echo -e "  ${CYAN}cd your-project/${RESET}"
echo -e "  ${CYAN}adelie init${RESET}"
echo -e "  ${CYAN}adelie config --provider gemini --api-key YOUR_KEY${RESET}"
echo -e "  ${CYAN}adelie run --goal \"Build something amazing\"${RESET}"
echo ""
echo -e "  ${DIM}Docs: https://github.com/Ade1ie/adelie${RESET}"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Adelie Installer for Windows (PowerShell)
#
# Usage:
#   irm https://raw.githubusercontent.com/Ade1ie/adelie/main/install.ps1 | iex
#
# Environment variables:
#   $env:ADELIE_VERSION  — Install a specific version (default: latest)
# ─────────────────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"

function Write-Banner {
    Write-Host ""
    Write-Host "     ___       __     ___" -ForegroundColor Cyan
    Write-Host "    /   | ____/ /__  / (_)__" -ForegroundColor Cyan
    Write-Host "   / /| |/ __  / _ \/ / / _ \" -ForegroundColor Cyan
    Write-Host "  / ___ / /_/ /  __/ / /  __/" -ForegroundColor Cyan
    Write-Host " /_/  |_\__,_/\___/_/_/\___/" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Adelie Installer" -ForegroundColor White -NoNewline
    Write-Host " (Windows)" -ForegroundColor DarkGray
    Write-Host "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkCyan
    Write-Host ""
}

function Write-Ok($msg)   { Write-Host "  ✔ " -ForegroundColor Green -NoNewline; Write-Host $msg }
function Write-Info($msg)  { Write-Host "  ▸ " -ForegroundColor Cyan -NoNewline; Write-Host $msg }
function Write-Warn($msg)  { Write-Host "  ⚠ " -ForegroundColor Yellow -NoNewline; Write-Host $msg }
function Write-Err($msg)   { Write-Host "  ✕ " -ForegroundColor Red -NoNewline; Write-Host $msg }

Write-Banner

# ── Check Python ──────────────────────────────────────────────────────────────
$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3\.(\d+)") {
            $minor = [int]$Matches[1]
            if ($minor -ge 10) {
                $pythonCmd = $cmd
                break
            }
        }
    } catch {}
}

if (-not $pythonCmd) {
    Write-Err "Python 3.10+ is required but not found."
    Write-Host ""
    Write-Host "  Download from: " -ForegroundColor DarkGray -NoNewline
    Write-Host "https://www.python.org/downloads/" -ForegroundColor Cyan
    Write-Host "  Or use winget:" -ForegroundColor DarkGray
    Write-Host "  winget install Python.Python.3.12" -ForegroundColor Cyan
    Write-Host ""
    exit 1
}

$pyVer = & $pythonCmd --version 2>&1
Write-Ok "Python: $pyVer"

# ── Check Node.js ─────────────────────────────────────────────────────────────
try {
    $nodeVer = & node --version 2>&1
    $nodeMajor = [int]($nodeVer -replace '^v(\d+).*', '$1')
    if ($nodeMajor -lt 16) {
        throw "too old"
    }
    Write-Ok "Node.js: $nodeVer"
} catch {
    Write-Err "Node.js 16+ is required but not found."
    Write-Host ""
    Write-Host "  Download from: " -ForegroundColor DarkGray -NoNewline
    Write-Host "https://nodejs.org/" -ForegroundColor Cyan
    Write-Host "  Or use winget:" -ForegroundColor DarkGray
    Write-Host "  winget install OpenJS.NodeJS.LTS" -ForegroundColor Cyan
    Write-Host ""
    exit 1
}

# ── Check npm ─────────────────────────────────────────────────────────────────
try {
    $npmVer = & npm --version 2>&1
    Write-Ok "npm: $npmVer"
} catch {
    Write-Err "npm is required but not found."
    exit 1
}

# ── Install Adelie ────────────────────────────────────────────────────────────
$version = if ($env:ADELIE_VERSION) { $env:ADELIE_VERSION } else { "latest" }

Write-Host ""
Write-Info "Installing adelie-ai@$version globally..."
Write-Host ""

try {
    & npm install -g "adelie-ai@$version"
    Write-Host ""
    Write-Ok "Adelie installed successfully!"
} catch {
    Write-Host ""
    Write-Err "Installation failed: $_"
    Write-Host ""
    Write-Host "  Try running PowerShell as Administrator." -ForegroundColor DarkGray
    exit 1
}

# ── Verify ────────────────────────────────────────────────────────────────────
Write-Host ""
try {
    $adelieVer = & adelie --version 2>&1
    Write-Ok "Verified: $adelieVer"
} catch {
    Write-Warn "adelie not found on PATH. Restart your terminal."
}

# ── Next steps ────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  🚀 Next Steps" -ForegroundColor White
Write-Host "  ───────────────────────────────" -ForegroundColor DarkGray
Write-Host "  cd your-project\" -ForegroundColor Cyan
Write-Host "  adelie init" -ForegroundColor Cyan
Write-Host "  adelie config --provider gemini --api-key YOUR_KEY" -ForegroundColor Cyan
Write-Host "  adelie run --goal `"Build something amazing`"" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Docs: https://github.com/Ade1ie/adelie" -ForegroundColor DarkGray
Write-Host ""

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PS1_SCRIPT="$ROOT_DIR/setup_tenorclone.ps1"

if ! command -v pwsh >/dev/null 2>&1; then
  echo "PowerShell (pwsh) is required to run this setup on macOS/Linux."
  echo "Install it first:"
  echo "  brew install --cask powershell    # macOS with Homebrew"
  echo "  or use your distro's package manager on Linux"
  exit 1
fi

if [ ! -f "$PS1_SCRIPT" ]; then
  echo "Could not find setup_tenorclone.ps1 in: $ROOT_DIR"
  exit 1
fi

echo "Running setup_tenorclone.ps1 with PowerShell Core..."
exec pwsh -NoProfile -ExecutionPolicy Bypass -File "$PS1_SCRIPT"

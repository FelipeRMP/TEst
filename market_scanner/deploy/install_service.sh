#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/home/scanner/TEst/market_scanner"
SERVICE_SOURCE="${PROJECT_ROOT}/deploy/market-scanner.service"
SERVICE_TARGET="/etc/systemd/system/market-scanner.service"
VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
WORKER_SCRIPT="${PROJECT_ROOT}/backend/workers/scan_worker.py"

require_path() {
  local path="$1"
  local label="$2"

  if [[ ! -e "${path}" ]]; then
    echo "Error: ${label} not found at ${path}" >&2
    exit 1
  fi
}

echo "Running market-scanner service preflight checks..."
require_path "${PROJECT_ROOT}" "project root"
require_path "${SERVICE_SOURCE}" "service file"
require_path "${VENV_PYTHON}" "virtualenv python"
require_path "${WORKER_SCRIPT}" "worker script"

echo "Preflight checks passed."
echo "Installing market-scanner.service..."
sudo cp "${SERVICE_SOURCE}" "${SERVICE_TARGET}"
sudo systemctl daemon-reload
sudo systemctl enable market-scanner
sudo systemctl restart market-scanner

echo "Service installed and restarted."
echo "Useful commands:"
echo "  sudo systemctl status market-scanner"
echo "  sudo journalctl -u market-scanner -n 50 --no-pager"
echo "  sudo journalctl -u market-scanner -f"

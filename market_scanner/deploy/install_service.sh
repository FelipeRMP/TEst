#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/home/scanner/TEst/market_scanner"
WORKER_SERVICE_SOURCE="${PROJECT_ROOT}/deploy/market-scanner.service"
API_SERVICE_SOURCE="${PROJECT_ROOT}/deploy/market-scanner-api.service"
FRONTEND_SERVICE_SOURCE="${PROJECT_ROOT}/deploy/market-scanner-frontend.service"
WORKER_SERVICE_TARGET="/etc/systemd/system/market-scanner.service"
API_SERVICE_TARGET="/etc/systemd/system/market-scanner-api.service"
FRONTEND_SERVICE_TARGET="/etc/systemd/system/market-scanner-frontend.service"
VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
WORKER_SCRIPT="${PROJECT_ROOT}/backend/workers/scan_worker.py"
API_MODULE="${PROJECT_ROOT}/backend/app/api.py"
FRONTEND_DIST_DIR="${PROJECT_ROOT}/frontend/dist"

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
require_path "${WORKER_SERVICE_SOURCE}" "worker service file"
require_path "${API_SERVICE_SOURCE}" "api service file"
require_path "${FRONTEND_SERVICE_SOURCE}" "frontend service file"
require_path "${VENV_PYTHON}" "virtualenv python"
require_path "${WORKER_SCRIPT}" "worker script"
require_path "${API_MODULE}" "backend api module"
require_path "${FRONTEND_DIST_DIR}" "frontend dist directory"

echo "Preflight checks passed."
echo "Installing systemd service files..."
sudo cp "${WORKER_SERVICE_SOURCE}" "${WORKER_SERVICE_TARGET}"
sudo cp "${API_SERVICE_SOURCE}" "${API_SERVICE_TARGET}"
sudo cp "${FRONTEND_SERVICE_SOURCE}" "${FRONTEND_SERVICE_TARGET}"
sudo systemctl daemon-reload
sudo systemctl enable market-scanner
sudo systemctl enable market-scanner-api
sudo systemctl enable market-scanner-frontend
sudo systemctl restart market-scanner
sudo systemctl restart market-scanner-api
sudo systemctl restart market-scanner-frontend

echo "Services installed and restarted."
echo "Useful commands:"
echo "  sudo systemctl status market-scanner"
echo "  sudo systemctl status market-scanner-api"
echo "  sudo systemctl status market-scanner-frontend"
echo "  sudo journalctl -u market-scanner -n 50 --no-pager"
echo "  sudo journalctl -u market-scanner-api -n 50 --no-pager"
echo "  sudo journalctl -u market-scanner-frontend -n 50 --no-pager"
echo "  sudo journalctl -u market-scanner -f"
echo "  sudo journalctl -u market-scanner-api -f"
echo "  sudo journalctl -u market-scanner-frontend -f"

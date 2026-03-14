#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SERVICE_SOURCE="${PROJECT_ROOT}/deploy/market-scanner.service"
SERVICE_TARGET="/etc/systemd/system/market-scanner.service"

echo "Installing market-scanner.service..."
sudo cp "${SERVICE_SOURCE}" "${SERVICE_TARGET}"
sudo systemctl daemon-reload
sudo systemctl enable market-scanner
sudo systemctl start market-scanner
sudo systemctl status market-scanner --no-pager

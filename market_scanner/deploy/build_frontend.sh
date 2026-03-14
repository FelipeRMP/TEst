#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/home/scanner/TEst/market_scanner"
FRONTEND_DIR="${PROJECT_ROOT}/frontend"
PACKAGE_JSON="${FRONTEND_DIR}/package.json"

require_path() {
  local path="$1"
  local label="$2"

  if [[ ! -e "${path}" ]]; then
    echo "Error: ${label} not found at ${path}" >&2
    exit 1
  fi
}

require_path "${PROJECT_ROOT}" "project root"
require_path "${FRONTEND_DIR}" "frontend directory"
require_path "${PACKAGE_JSON}" "frontend package.json"

if ! command -v npm >/dev/null 2>&1; then
  echo "Error: npm is not installed or not on PATH" >&2
  exit 1
fi

cd "${FRONTEND_DIR}"
echo "Installing frontend dependencies..."
npm install
echo "Building frontend..."
npm run build

if [[ ! -d "${FRONTEND_DIR}/dist" ]]; then
  echo "Error: frontend dist directory was not created" >&2
  exit 1
fi

echo "Frontend build completed at ${FRONTEND_DIR}/dist"

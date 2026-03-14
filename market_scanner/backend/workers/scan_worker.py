from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if __package__ in {None, ""}:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.schemas import ScanRequest
from backend.app.services.scanner_service import ScannerService

DEFAULT_SCAN_INTERVAL_SECONDS = 60
DEFAULT_SCAN_LIMIT = 300
DEFAULT_MIN_LIQUIDITY = 0.0
DEFAULT_MIN_EV = 0.01
DEFAULT_BANKROLL_AMOUNT = 1000.0


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _build_request() -> ScanRequest:
    return ScanRequest(
        limit=_env_int("SCAN_LIMIT", DEFAULT_SCAN_LIMIT),
        min_liquidity=_env_float("MIN_LIQUIDITY", DEFAULT_MIN_LIQUIDITY),
        min_ev=_env_float("MIN_EV", DEFAULT_MIN_EV),
        bankroll_amount=_env_float("BANKROLL_AMOUNT", DEFAULT_BANKROLL_AMOUNT),
    )


async def run_single_scan_from_env(service: ScannerService | None = None) -> int:
    scanner_service = service or ScannerService()
    request = _build_request()
    started_at = datetime.now(timezone.utc)
    print(
        f"[scan_worker] scan started at={started_at.strftime('%Y-%m-%dT%H:%M:%SZ')} "
        f"limit={request.limit} min_liquidity={request.min_liquidity:.2f} "
        f"min_ev={request.min_ev:.4f} bankroll={request.bankroll_amount:.2f}"
    )
    cached = await scanner_service.run_scan(request)
    finished_at = datetime.now(timezone.utc)
    opportunity_count = len(cached.opportunities)
    print(
        f"[scan_worker] scan finished at={finished_at.strftime('%Y-%m-%dT%H:%M:%SZ')} "
        f"opportunities={opportunity_count}"
    )
    return opportunity_count


async def run_worker() -> None:
    service = ScannerService()
    interval_seconds = max(5, _env_int("SCAN_INTERVAL_SECONDS", DEFAULT_SCAN_INTERVAL_SECONDS))
    while True:
        try:
            await run_single_scan_from_env(service)
        except Exception as exc:
            print(f"[scan_worker] scan error: {exc}")
        await asyncio.sleep(interval_seconds)


def main() -> None:
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        print("[scan_worker] stopped")


if __name__ == "__main__":
    main()

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .schemas import OpportunitiesResponse, ScanRequest, ScanResponse
from .services.scanner_service import ScannerService

app = FastAPI(title="Market Scanner API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

scanner_service = ScannerService()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/scan", response_model=ScanResponse)
async def scan(request: ScanRequest) -> ScanResponse:
    cached = await scanner_service.run_scan(request)
    return ScanResponse(
        opportunities=cached.opportunities,
        count=len(cached.opportunities),
        scanned_at=cached.scanned_at,
        params=cached.params,
    )


@app.get("/opportunities", response_model=OpportunitiesResponse)
async def get_opportunities() -> OpportunitiesResponse:
    cached = scanner_service.get_cached()
    if cached is None:
        return OpportunitiesResponse(opportunities=[], count=0, last_scan_at=None)

    return OpportunitiesResponse(
        opportunities=cached.opportunities,
        count=len(cached.opportunities),
        last_scan_at=cached.scanned_at,
    )

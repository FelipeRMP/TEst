# Market Scanner

This project now includes the original Python scanner logic, a FastAPI backend, and a React + Vite frontend dashboard.

## Project Layout

```text
market_scanner/
    backend/
        app/
            api.py
            schemas.py
            services/
                scanner_service.py
        requirements.txt
    frontend/
        src/
            App.tsx
            api.ts
            components/
            main.tsx
            styles.css
            types.ts
        index.html
        package.json
        tsconfig.json
        vite.config.ts
    src/
        config.py
        models.py
        odds_normalizer.py
        scanner.py
        ingestion/
            polymarket_client.py
        matching/
            event_matcher.py
        analysis/
            consensus_model.py
            arbitrage_detector.py
        main.py
```

## Python Setup

From [market_scanner](C:/Users/redfy/Desktop/codex_root/market_scanner):

```bash
python -m pip install -r requirements.txt
python -m pip install -r backend/requirements.txt
```

## Run The CLI Scanner

From [market_scanner](C:/Users/redfy/Desktop/codex_root/market_scanner):

```bash
python src/main.py --limit 50 --json
```

## Run The FastAPI Backend

From [market_scanner](C:/Users/redfy/Desktop/codex_root/market_scanner):

```bash
python -m uvicorn backend.app.api:app --reload
```

The API will be available at [http://localhost:8000](http://localhost:8000).

Available endpoints:

- `GET /health`
- `POST /scan`
- `GET /opportunities`

## One-Click Launcher

Double-click [start_market_scanner.bat](C:/Users/redfy/Desktop/codex_root/market_scanner/start_market_scanner.bat) from File Explorer, or run:

```bash
.\start_market_scanner.bat
```

It starts:

- The FastAPI backend on `http://localhost:8000`
- The Vite frontend on `http://localhost:5173`

## Run The Frontend

From [frontend](C:/Users/redfy/Desktop/codex_root/market_scanner/frontend):

```bash
npm install
npm run dev
```

If PowerShell blocks `npm`, use:

```bash
npm.cmd install
npm.cmd run dev
```

The dashboard will be available at [http://localhost:5173](http://localhost:5173).

If the API is not on `http://localhost:8000`, set `VITE_API_BASE_URL` before starting Vite.

PowerShell example:

```bash
$env:VITE_API_BASE_URL="http://localhost:8000"
npm run dev
```

## Dashboard Features

- Run scans from the UI
- Review opportunities in a sortable table
- Filter by platform, arbitrage-only flag, minimum EV, and minimum liquidity
- Open a details modal for each opportunity
- Inspect implied probability, consensus probability, EV, liquidity, arbitrage flag, confidence, and bankroll sizing

## Data Sources

The scanner now pulls read-only market data from:

- Polymarket
- Kalshi

Consensus is now cross-platform when comparable events are matched across those sources.

Kalshi notes:

- The current connector uses Kalshi's public Trade API for open events and market data.
- No API key is required for the current read-only scan flow.

## Bankroll Sizing

The `POST /scan` endpoint now accepts `bankroll_amount`.

The backend computes:

- `recommended_bankroll_fraction`
- `recommended_position_size`
- `risk_level`

These use a conservative Kelly-style sizing rule that scales position sizes down based on confidence and liquidity.

## Notes

- The backend reuses the existing scanner flow in [scanner.py](C:/Users/redfy/Desktop/codex_root/market_scanner/src/scanner.py).
- The current MVP still scans Polymarket only, but the API and UI are set up so additional sources can be added later.

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

## Run Tests

From [market_scanner](C:/Users/redfy/Desktop/codex_root/market_scanner):

```bash
pytest -q
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
- `GET /collection-stats`

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

For a clean reproducible frontend setup, install dependencies from scratch inside `frontend/` instead of relying on a checked-in `node_modules` directory.

The dashboard will be available at [http://localhost:5173](http://localhost:5173).

If the API is not on `http://localhost:8000`, set `VITE_API_BASE_URL` before starting Vite.

PowerShell example:

```bash
$env:VITE_API_BASE_URL="http://localhost:8000"
npm run dev
```

## Dashboard Features

- `Trade Ideas` tab for simplified trading ideas
- `Data Collection` tab for logging and paper-trading research metrics
- Run scans from the UI
- Filter by platform, near risk-free flag, minimum profit potential, and minimum liquidity
- Open a details modal for each opportunity
- Inspect current odds, market average odds, best bid/ask, spread, liquidity, movement, related signals, and bankroll sizing

## Data Sources

The scanner now pulls read-only market data from:

- Polymarket
- Kalshi

Consensus is now cross-platform when comparable events are matched across those sources.

Kalshi notes:

- The current connector uses Kalshi's public Trade API for open events and market data.
- No API key is required for the current read-only scan flow.

## Improved EV Math

Positive-EV opportunities now use a true expected value calculation rather than the earlier simple edge approximation.

For a YES-position style contract:

```text
p = consensus probability
q = 1 - p
price = market probability
payout_multiple = (1 / price) - 1
EV = (p * payout_multiple) - q
```

The existing edge-style metric is still preserved separately for compatibility.

## Historical Database

Each scan now writes normalized probabilities to a SQLite history database at:

`market_history.sqlite3`

Stored fields include:

- timestamp
- platform
- event_id
- market_id
- outcome
- probability
- liquidity

This history powers movement and volatility analysis.

## Canonical Runtime Storage

Runtime analytics and monitoring now prefer:

- `data/trading_data.db`

This SQLite database is the canonical source of truth for:

- signal rows
- raw price snapshots
- scan batches
- simulated trades
- generated research labels

CSV files in `data/` are still written as fallback/debug artifacts, but monitoring and research scripts prefer SQLite first.

## Scan Batches

Every scan now gets a real `scan_id`.

That batch ID is attached to:

- price snapshots written during the scan
- signals emitted during the scan
- scan batch metadata in the `scan_batches` table

Each batch records:

- scan start time
- scan finish time
- scan duration
- market count
- price snapshot count
- detected opportunity count
- emitted signal count
- status / error message

## Signal Logging

Every finalized opportunity returned by the backend is now logged for later analysis.

Files written:

- `data/signal_log.csv`
- `data/trading_data.db` (`signals` table)

Logged fields include:

- signal_id
- scan_id
- scan_timestamp
- timestamp
- signal_family
- opportunity_type
- event_id
- event_title
- platform
- market_id
- side
- market_price
- consensus_probability
- expected_value
- signal_strength
- liquidity
- suggested_bankroll_percent
- suggested_amount
- best_bid
- best_ask
- bid_size
- ask_size
- spread
- spread_percent

Logging is best-effort and will never stop the scanner if the file or database write fails.

Near-identical signals are also deduplicated before they are logged. A repeated signal family is only re-emitted quickly if market price, consensus, EV, or signal strength changed materially.

## Market Price Logging

Each scan also records fetched market prices for paper-trading analysis.

Files written:

- `data/price_history.csv`
- `data/trading_data.db` (`price_history` table)

Each row includes:

- scan_id
- scan_timestamp
- timestamp
- platform
- market_id
- event_id
- price
- liquidity

The logger writes UTC timestamps and creates the `data/` folder automatically if it does not exist.

## Paper Trading Simulator

Run the simulator from [market_scanner](C:/Users/redfy/Desktop/codex_root/market_scanner):

```bash
python backend/simulate_trades.py
```

It loads:

- `data/trading_data.db` first
- `data/signal_log.csv` / `data/price_history.csv` only as fallback

Default paper-trading rules:

- enter using the logged executable order-book price when available
- exit after 24 hours or when price reaches the logged consensus probability

Simulator notes:

- BUY-style entries use `best_ask` when it is available
- SELL-style entries use `best_bid` when it is available
- if a logged spread exceeds 15%, simulated pnl is reduced to reflect hard-to-capture edge

Reported metrics:

- total trades
- win rate
- average profit
- average expected value
- total pnl
- max drawdown
- average holding time
- average spread
- average liquidity at entry

Simulated trades are also written to `data/trading_data.db` in the `simulated_trades` table.

Each simulator execution now gets its own `run_id`, so a fresh run can be identified cleanly without silently mixing results.

## Label Generation

To create research-ready labels from the collected SQLite history:

```bash
python backend/generate_labels.py
```

This generates or refreshes `signal_labels` in `data/trading_data.db` using canonical normalized market IDs.

Current labels:

- `future_return_5m`
- `future_return_1h`
- `future_return_24h`
- `hit_consensus_within_24h`

Label definitions:

- `future_return_*` = future market price minus the logged entry price at the first snapshot on or after the horizon
- `hit_consensus_within_24h` = whether the logged market price reached or exceeded the logged consensus probability within 24 hours

The script is safe to rerun because it upserts labels by `signal_id`.

## Continuous Data Collection Worker

Run the background worker from [market_scanner](C:/Users/redfy/Desktop/codex_root/market_scanner):

```bash
python backend/workers/scan_worker.py
```

This worker runs the existing backend scan flow on a loop and lets the normal signal / price loggers capture data over time.

Environment variables:

- `SCAN_INTERVAL_SECONDS` default `60`
- `SCAN_LIMIT` default `300`
- `MIN_LIQUIDITY` default `0`
- `MIN_EV` default `0.01`
- `BANKROLL_AMOUNT` default `1000`

Example PowerShell:

```bash
$env:SCAN_INTERVAL_SECONDS="60"
$env:SCAN_LIMIT="300"
$env:MIN_LIQUIDITY="0"
$env:MIN_EV="0.01"
$env:BANKROLL_AMOUNT="1000"
python backend/workers/scan_worker.py
```

Example shell environment values:

```bash
SCAN_INTERVAL_SECONDS=60
SCAN_LIMIT=300
MIN_LIQUIDITY=0
MIN_EV=0.01
BANKROLL_AMOUNT=1000
```

The worker:

- runs scans continuously on the configured interval
- logs signals and price snapshots on every loop
- prints concise scan progress to the console
- catches errors and continues running

For a simple server deployment, keep the worker running under a process manager or a long-lived terminal session.

## Linux System Service

For Ubuntu on Azure, you can run the worker as a `systemd` service so it starts on boot and restarts automatically after failures.

Service template:

- [market-scanner.service](C:/Users/redfy/Desktop/codex_root/market_scanner/deploy/market-scanner.service)
- [market-scanner-api.service](C:/Users/redfy/Desktop/codex_root/market_scanner/deploy/market-scanner-api.service)
- [market-scanner-frontend.service](C:/Users/redfy/Desktop/codex_root/market_scanner/deploy/market-scanner-frontend.service)

Helpers:

- [install_service.sh](C:/Users/redfy/Desktop/codex_root/market_scanner/deploy/install_service.sh)
- [build_frontend.sh](C:/Users/redfy/Desktop/codex_root/market_scanner/deploy/build_frontend.sh)

Headless deployment steps for the VM at `/home/scanner/TEst/market_scanner`:

1. Build the frontend once:

```bash
cd /home/scanner/TEst/market_scanner
bash deploy/build_frontend.sh
```

2. Install and enable all three services:

```bash
cd /home/scanner/TEst/market_scanner
sudo cp deploy/market-scanner.service /etc/systemd/system/
sudo cp deploy/market-scanner-api.service /etc/systemd/system/
sudo cp deploy/market-scanner-frontend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable market-scanner
sudo systemctl enable market-scanner-api
sudo systemctl enable market-scanner-frontend
sudo systemctl restart market-scanner
sudo systemctl restart market-scanner-api
sudo systemctl restart market-scanner-frontend
sudo systemctl status market-scanner
sudo systemctl status market-scanner-api
sudo systemctl status market-scanner-frontend
sudo journalctl -u market-scanner -f
sudo journalctl -u market-scanner-api -f
sudo journalctl -u market-scanner-frontend -f
```

The service uses the project virtualenv Python at:

```bash
/home/scanner/TEst/market_scanner/.venv/bin/python
```

If you need different paths or environment values, edit the unit file before enabling it.

Azure inbound ports that must be open:

- `22` for SSH
- `8000` for the FastAPI API
- `5173` for the static frontend

The frontend is served from `frontend/dist` via a lightweight Python static server, so no `npm run dev` terminal needs to stay open on your PC.

### Troubleshooting

If the service fails to start, first confirm that both the worker path and virtualenv path match the deployed project root:

```bash
/home/scanner/TEst/market_scanner
```

Useful commands:

```bash
sudo systemctl daemon-reload
sudo systemctl enable market-scanner
sudo systemctl enable market-scanner-api
sudo systemctl enable market-scanner-frontend
sudo systemctl restart market-scanner
sudo systemctl restart market-scanner-api
sudo systemctl restart market-scanner-frontend
sudo systemctl status market-scanner
sudo systemctl status market-scanner-api
sudo systemctl status market-scanner-frontend
sudo journalctl -u market-scanner -n 50 --no-pager
sudo journalctl -u market-scanner-api -n 50 --no-pager
sudo journalctl -u market-scanner-frontend -n 50 --no-pager
sudo journalctl -u market-scanner -f
sudo journalctl -u market-scanner-api -f
sudo journalctl -u market-scanner-frontend -f
```

## Movement Signals

The scanner now computes:

- `price_change_5m`
- `price_change_30m`
- `price_change_2h`
- `price_change_24h`
- `volatility_5m`
- `volatility_30m`
- `volatility_2h`

Movement labels include:

- `rapid_up`
- `rapid_down`
- `stale_market`
- `lagging_market`
- `stable`

These signals are exposed in the API and shown in the dashboard.

## Bankroll Sizing

The `POST /scan` endpoint now accepts `bankroll_amount`.

The backend computes:

- `recommended_bankroll_fraction`
- `recommended_position_size`
- `risk_level`

These use a conservative fractional Kelly-style sizing rule.

In practice, the recommendation is reduced when:

- volatility is elevated
- liquidity is low
- movement signals lower confidence

The dashboard keeps showing bankroll percentages and dollar-size recommendations exactly as before, now with stronger math behind them.

## Notes

- The backend reuses the existing scanner flow in [scanner.py](C:/Users/redfy/Desktop/codex_root/market_scanner/src/scanner.py).
- The scanner remains runnable through the same CLI, FastAPI endpoints, and frontend launcher.

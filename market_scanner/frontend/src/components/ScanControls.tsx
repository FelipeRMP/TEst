import type { ScanRequest } from "../types";

type ScanControlsProps = {
  value: ScanRequest;
  loading: boolean;
  onChange: (nextValue: ScanRequest) => void;
  onScan: () => void;
  lastScanAt: string | null;
};

export function ScanControls({
  value,
  loading,
  onChange,
  onScan,
  lastScanAt
}: ScanControlsProps) {
  return (
    <section className="panel controls-panel">
      <div className="controls-header">
        <div>
          <h2>Run a Market Scan</h2>
          <p>Refresh the dashboard with the latest prices and trading signals.</p>
        </div>
        <button className="primary-button" onClick={onScan} disabled={loading}>
          {loading ? "Scanning..." : "Run Scan"}
        </button>
      </div>
      <div className="controls-grid">
        <label>
          <span>Markets To Check</span>
          <input
            type="number"
            min={1}
            max={500}
            value={value.limit}
            onChange={(event) =>
              onChange({ ...value, limit: Number(event.target.value) || 1 })
            }
          />
        </label>
        <label>
          <span>Minimum Market Depth</span>
          <input
            type="number"
            min={0}
            step="100"
            value={value.min_liquidity}
            onChange={(event) =>
              onChange({ ...value, min_liquidity: Number(event.target.value) || 0 })
            }
          />
        </label>
        <label>
          <span>Minimum Profit Potential</span>
          <input
            type="number"
            min={0}
            step="0.01"
            value={value.min_ev}
            onChange={(event) =>
              onChange({ ...value, min_ev: Number(event.target.value) || 0 })
            }
          />
        </label>
        <label>
          <span
            title="This is used to estimate suggested position sizes with conservative bankroll management."
          >
            Total Bankroll
          </span>
          <input
            type="number"
            min={0}
            step="100"
            value={value.bankroll_amount}
            onChange={(event) =>
              onChange({ ...value, bankroll_amount: Number(event.target.value) || 0 })
            }
          />
        </label>
        <div className="status-chip">
          <span className="status-label">Last Update</span>
          <strong>{lastScanAt ? new Date(lastScanAt).toLocaleString() : "Not run yet"}</strong>
        </div>
      </div>
    </section>
  );
}

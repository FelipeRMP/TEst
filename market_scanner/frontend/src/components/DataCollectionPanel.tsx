import type { CollectionStats } from "../types";

type DataCollectionPanelProps = {
  stats: CollectionStats | null;
  loading: boolean;
  error: string | null;
};

function formatPercent(value: number | null | undefined) {
  if (value == null) {
    return "N/A";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function formatCurrency(value: number | null | undefined) {
  if (value == null) {
    return "N/A";
  }
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2
  }).format(value);
}

export function DataCollectionPanel({ stats, loading, error }: DataCollectionPanelProps) {
  if (error) {
    return (
      <section className="panel state-panel error-panel">
        <h3>Data collection stats are unavailable</h3>
        <p>{error}</p>
      </section>
    );
  }

  if (loading && !stats) {
    return (
      <section className="panel state-panel">
        <h3>Loading research metrics</h3>
        <p>Gathering signal counts, price snapshots, and simulator results.</p>
      </section>
    );
  }

  if (!stats) {
    return (
      <section className="panel state-panel">
        <h3>No collection data yet</h3>
        <p>Run a scan or start the background worker to begin logging signals and prices.</p>
      </section>
    );
  }

  return (
    <div className="collection-layout">
      <section className="metrics-row">
        <div className="metric-card">
          <span className="metric-label">Signals Logged</span>
          <strong className="metric-value">{stats.total_signals_logged}</strong>
          <span className="metric-helper">Total trading ideas recorded to the experiment log</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Price Snapshots</span>
          <strong className="metric-value">{stats.total_price_snapshots_logged}</strong>
          <span className="metric-helper">Order-price observations captured during scans</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Simulator Trades</span>
          <strong className="metric-value">{stats.simulator_trade_count}</strong>
          <span className="metric-helper">Paper trades built from the logged signals</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Realized PnL</span>
          <strong className="metric-value">{formatCurrency(stats.simulated_realized_pnl)}</strong>
          <span className="metric-helper">Simulator profit after applying the current exit rules</span>
        </div>
      </section>

      <section className="panel collection-summary-panel">
        <div className="panel-heading">
          <div>
            <h3>Research Summary</h3>
            <p>This tab helps you monitor data collection quality and paper-trading performance.</p>
          </div>
        </div>
        <div className="modal-grid">
          <div className="detail-block">
            <span>Latest Scan Timestamp</span>
            <strong>
              {stats.latest_scan_timestamp
                ? new Date(stats.latest_scan_timestamp).toLocaleString()
                : "No scans yet"}
            </strong>
          </div>
          <div className="detail-block">
            <span>Average EV</span>
            <strong>{formatPercent(stats.average_ev)}</strong>
          </div>
          <div className="detail-block">
            <span>Win Rate</span>
            <strong>{formatPercent(stats.win_rate)}</strong>
          </div>
        </div>
      </section>

      <section className="panel collection-summary-panel">
        <div className="panel-heading">
          <div>
            <h3>Recent Scan Activity</h3>
            <p>Recent scan batches grouped by minute for easy monitoring.</p>
          </div>
        </div>
        <div className="activity-list">
          {stats.recent_scan_activity.length === 0 ? (
            <p>No recent activity yet.</p>
          ) : (
            stats.recent_scan_activity.map((activity) => (
              <div key={activity.timestamp} className="activity-row">
                <strong>{new Date(activity.timestamp).toLocaleString()}</strong>
                <span>{activity.signal_count} signals</span>
                <span>{activity.price_snapshot_count} price snapshots</span>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}

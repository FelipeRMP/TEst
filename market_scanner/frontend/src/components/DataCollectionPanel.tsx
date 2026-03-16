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

function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "N/A";
  }
  return new Date(value).toLocaleString();
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
          <span className="metric-label">Scan Batches</span>
          <strong className="metric-value">{stats.total_scan_batches}</strong>
          <span className="metric-helper">Completed scan runs recorded in SQLite</span>
        </div>
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
          <span className="metric-label">Latest Signal Time</span>
          <strong className="metric-value metric-value-small">
            {formatDateTime(stats.latest_signal_timestamp)}
          </strong>
          <span className="metric-helper">Most recent signal row written by the scanner</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Simulator Trades</span>
          <strong className="metric-value">{stats.simulator_trade_count}</strong>
          <span className="metric-helper">Paper trades built from the logged signals</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Simulated PnL</span>
          <strong className="metric-value">{formatCurrency(stats.simulator_total_pnl)}</strong>
          <span className="metric-helper">Simulator profit after applying the current exit rules</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Win Rate</span>
          <strong className="metric-value">{formatPercent(stats.simulator_win_rate)}</strong>
          <span className="metric-helper">Share of simulator trades with positive realized pnl</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Average EV</span>
          <strong className="metric-value">{formatPercent(stats.average_expected_value)}</strong>
          <span className="metric-helper">Average logged expected value across all saved signals</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Signals in Last 24h</span>
          <strong className="metric-value">{stats.recent_signal_count_24h}</strong>
          <span className="metric-helper">Recent signal activity for monitoring collection health</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Unique Markets</span>
          <strong className="metric-value">{stats.unique_markets_scanned}</strong>
          <span className="metric-helper">Distinct canonical market IDs seen in stored snapshots</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Unique Events</span>
          <strong className="metric-value">{stats.unique_events_signaled}</strong>
          <span className="metric-helper">Distinct event IDs represented in logged signals</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Malformed IDs</span>
          <strong className="metric-value">{stats.malformed_id_count}</strong>
          <span className="metric-helper">Signals with duplicated YES/NO suffixes still present in storage</span>
        </div>
      </section>

      <section className="panel collection-summary-panel">
        <div className="panel-heading">
          <div>
            <h3>System Status</h3>
            <p>This tab tracks worker freshness and whether the collection pipeline looks healthy.</p>
          </div>
        </div>
        <div className="modal-grid">
          <div className="detail-block">
            <span>Worker Expected Interval</span>
            <strong>{stats.expected_scan_interval_seconds}s</strong>
          </div>
          <div className="detail-block">
            <span>Last Observed Scan</span>
            <strong>{formatDateTime(stats.latest_scan_timestamp)}</strong>
          </div>
          <div className="detail-block">
            <span>Latest Scan Duration</span>
            <strong>{stats.latest_scan_duration_seconds.toFixed(1)}s</strong>
          </div>
          <div className="detail-block">
            <span>Latest Price Time</span>
            <strong>{formatDateTime(stats.latest_price_timestamp)}</strong>
          </div>
          <div className="detail-block">
            <span>Data Freshness</span>
            <strong className={`freshness-${stats.data_freshness_status}`}>
              {stats.data_freshness_status}
            </strong>
          </div>
          <div className="detail-block">
            <span>Price Snapshots in Last 24h</span>
            <strong>{stats.recent_price_snapshot_count_24h}</strong>
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
              <div key={activity.scan_id} className="activity-row">
                <strong>{new Date(activity.timestamp).toLocaleString()}</strong>
                <span>{activity.signal_count} signals</span>
                <span>{activity.price_snapshot_count} price snapshots</span>
                <span>{activity.status}</span>
              </div>
            ))
          )}
        </div>
      </section>

      <section className="panel collection-summary-panel">
        <div className="panel-heading">
          <div>
            <h3>Top Repeated Signal Families</h3>
            <p>Useful for spotting over-represented ideas in the collected dataset.</p>
          </div>
        </div>
        <div className="activity-list">
          {stats.top_repeated_signal_families.length === 0 ? (
            <p>No repeated signal families yet.</p>
          ) : (
            stats.top_repeated_signal_families.map((family) => (
              <div key={family.signal_family} className="activity-row">
                <strong>{family.event_title || family.signal_family}</strong>
                <span>{family.count} logged signals</span>
                <span>Last seen {formatDateTime(family.last_seen)}</span>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}

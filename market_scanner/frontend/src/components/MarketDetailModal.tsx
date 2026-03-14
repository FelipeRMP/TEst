import type { Opportunity } from "../types";

type MarketDetailModalProps = {
  opportunity: Opportunity | null;
  onClose: () => void;
};

function formatPercent(value: number | null | undefined) {
  if (value == null) {
    return "N/A";
  }
  return `${(value * 100).toFixed(2)}%`;
}

function formatNumber(value: number | null | undefined) {
  if (value == null) {
    return "N/A";
  }
  return new Intl.NumberFormat().format(Math.round(value));
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

export function MarketDetailModal({ opportunity, onClose }: MarketDetailModalProps) {
  if (!opportunity) {
    return null;
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" onClick={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h3>{opportunity.event}</h3>
            <p>{opportunity.opportunity_type.replace(/_/g, " ")}</p>
          </div>
          <button className="ghost-button" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="modal-grid">
          <div className="detail-block">
            <span title="Estimated Profit Potential shows the projected return if the broader market view is right.">
              Estimated Profit Potential
            </span>
            <strong>{formatPercent(opportunity.expected_value)}</strong>
          </div>
          <div className="detail-block">
            <span title="Price Edge compares this market's price with the scanner's fair-price estimate.">
              Price Edge
            </span>
            <strong>{formatPercent(opportunity.net_edge)}</strong>
          </div>
          <div className="detail-block">
            <span title="Signal Strength reflects how trustworthy the match and pricing signal appear to be.">
              Signal Strength
            </span>
            <strong>{formatPercent(opportunity.confidence)}</strong>
          </div>
          <div className="detail-block">
            <span title="This is the rough size that looks tradable based on available market depth.">
              Tradable Size
            </span>
            <strong>{formatNumber(opportunity.max_executable_size)}</strong>
          </div>
          <div className="detail-block">
            <span title="This is the share of your bankroll the system suggests risking on this trade.">
              Suggested Bankroll Share
            </span>
            <strong>{formatPercent(opportunity.recommended_bankroll_fraction)}</strong>
          </div>
          <div className="detail-block">
            <span title="This is the estimated dollar amount to risk based on your bankroll setting.">
              Suggested Amount
            </span>
            <strong>{formatCurrency(opportunity.recommended_position_size)}</strong>
          </div>
          <div className="detail-block">
            <span title="Risk Level summarizes uncertainty, liquidity limits, and market stability.">
              Risk Level
            </span>
            <strong>{opportunity.risk_level}</strong>
          </div>
          <div className="detail-block">
            <span>5m Change</span>
            <strong>{formatPercent(opportunity.price_change_5m)}</strong>
          </div>
          <div className="detail-block">
            <span>30m Change</span>
            <strong>{formatPercent(opportunity.price_change_30m)}</strong>
          </div>
          <div className="detail-block">
            <span>Movement Signal</span>
            <strong>{opportunity.movement_signal}</strong>
          </div>
          <div className="detail-block">
            <span>Volatility 30m</span>
            <strong>{formatPercent(opportunity.volatility_30m)}</strong>
          </div>
          <div className="detail-block">
            <span>Best Bid</span>
            <strong>{opportunity.best_bid == null ? "N/A" : opportunity.best_bid.toFixed(3)}</strong>
          </div>
          <div className="detail-block">
            <span>Best Ask</span>
            <strong>{opportunity.best_ask == null ? "N/A" : opportunity.best_ask.toFixed(3)}</strong>
          </div>
          <div className="detail-block">
            <span>Spread</span>
            <strong>{opportunity.spread == null ? "N/A" : opportunity.spread.toFixed(3)}</strong>
          </div>
          <div className="detail-block">
            <span>Spread Percent</span>
            <strong>{formatPercent(opportunity.spread_percent)}</strong>
          </div>
          <div className="detail-block">
            <span>Related Signals</span>
            <strong>{opportunity.related_signal_count}</strong>
          </div>
        </div>

        <div className="detail-section">
          <h4>Why This Opportunity Stands Out</h4>
          <p>{opportunity.suggested_trade_strategy}</p>
          <p>
            In plain English: this signal appears because this market price differs from the
            broader market view or from a matching market on another platform.
          </p>
          <p>
            Flag summary: movement signal is <strong>{opportunity.movement_signal}</strong>, and
            this family currently has <strong>{opportunity.related_signal_count}</strong> related
            signal{opportunity.related_signal_count === 1 ? "" : "s"}.
          </p>
          <p
            className="tooltip-copy"
            title="This recommendation uses conservative bankroll management to limit risk. It does not assume you should bet your full edge."
          >
            This recommendation uses conservative bankroll management to limit risk.
          </p>
        </div>

        <div className="detail-section">
          <h4>Market Details</h4>
          <div className="legs-list">
            {opportunity.legs.map((leg) => (
              <div key={`${leg.platform}-${leg.market_id}-${leg.outcome}`} className="leg-card">
                <div className="leg-title">
                  <strong>{leg.market_title}</strong>
                  <span>{`${leg.platform} | ${leg.market_id}`}</span>
                </div>
                <div className="leg-metrics">
                  <span>Outcome: {leg.outcome}</span>
                  <span>Price: {leg.price.toFixed(3)}</span>
                  <span>Current market odds: {formatPercent(leg.implied_probability)}</span>
                  <span>Market average odds: {formatPercent(leg.consensus_probability)}</span>
                  <span>Best bid: {leg.best_bid == null ? "N/A" : leg.best_bid.toFixed(3)}</span>
                  <span>Best ask: {leg.best_ask == null ? "N/A" : leg.best_ask.toFixed(3)}</span>
                  <span>Spread: {leg.spread == null ? "N/A" : leg.spread.toFixed(3)}</span>
                  <span>Spread %: {formatPercent(leg.spread_percent)}</span>
                  <span>Liquidity: {formatNumber(leg.liquidity)}</span>
                  <span>Volume 24h: {formatNumber(leg.volume_24h)}</span>
                </div>
                {leg.description ? <p>{leg.description}</p> : null}
                {leg.resolution_criteria ? (
                  <div className="criteria-box">
                    <span>Resolution</span>
                    <p>{leg.resolution_criteria}</p>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>

        <div className="detail-section">
          <h4>Signal Breakdown</h4>
          <p>
            Use this section as a quick explanation of how confident the system is, how risky the
            setup looks, and whether the price deserves a second look.
          </p>
          <pre className="risk-box">{JSON.stringify(opportunity.risk, null, 2)}</pre>
        </div>
      </div>
    </div>
  );
}

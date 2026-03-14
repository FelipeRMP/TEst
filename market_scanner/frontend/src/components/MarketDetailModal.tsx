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
            <span>Expected Value</span>
            <strong>{formatPercent(opportunity.expected_value)}</strong>
          </div>
          <div className="detail-block">
            <span>Net Edge</span>
            <strong>{formatPercent(opportunity.net_edge)}</strong>
          </div>
          <div className="detail-block">
            <span>Confidence</span>
            <strong>{formatPercent(opportunity.confidence)}</strong>
          </div>
          <div className="detail-block">
            <span>Max Executable Size</span>
            <strong>{formatNumber(opportunity.max_executable_size)}</strong>
          </div>
          <div className="detail-block">
            <span>Recommended Investment</span>
            <strong>{formatPercent(opportunity.recommended_bankroll_fraction)}</strong>
          </div>
          <div className="detail-block">
            <span>Recommended Position</span>
            <strong>{formatCurrency(opportunity.recommended_position_size)}</strong>
          </div>
          <div className="detail-block">
            <span>Risk Level</span>
            <strong>{opportunity.risk_level}</strong>
          </div>
        </div>

        <div className="detail-section">
          <h4>Suggested Trade</h4>
          <p>{opportunity.suggested_trade_strategy}</p>
          <p className="tooltip-copy" title="This is a suggested position size based on expected value and model confidence using a conservative Kelly-based strategy.">
            Suggested bankroll sizing uses a conservative Kelly-based rule.
          </p>
        </div>

        <div className="detail-section">
          <h4>Market Legs</h4>
          <div className="legs-list">
            {opportunity.legs.map((leg) => (
              <div key={`${leg.platform}-${leg.market_id}-${leg.outcome}`} className="leg-card">
                <div className="leg-title">
                  <strong>{leg.market_title}</strong>
                  <span>
                    {leg.platform} • {leg.market_id}
                  </span>
                </div>
                <div className="leg-metrics">
                  <span>Outcome: {leg.outcome}</span>
                  <span>Price: {leg.price.toFixed(3)}</span>
                  <span>Implied: {formatPercent(leg.implied_probability)}</span>
                  <span>Consensus: {formatPercent(leg.consensus_probability)}</span>
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
          <h4>Risk Summary</h4>
          <pre className="risk-box">{JSON.stringify(opportunity.risk, null, 2)}</pre>
        </div>
      </div>
    </div>
  );
}

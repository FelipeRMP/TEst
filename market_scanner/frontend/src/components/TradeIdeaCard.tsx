import type { Opportunity } from "../types";

type TradeIdeaCardProps = {
  opportunity: Opportunity;
  onSelect: (opportunity: Opportunity) => void;
};

function formatPercent(value: number | null | undefined) {
  if (value == null) {
    return "N/A";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function actionLabel(opportunity: Opportunity) {
  const primaryLeg = opportunity.legs[0];
  const outcome = primaryLeg?.outcome ?? "YES";
  return `Buy ${outcome}`;
}

export function TradeIdeaCard({ opportunity, onSelect }: TradeIdeaCardProps) {
  return (
    <button className="trade-idea-card" onClick={() => onSelect(opportunity)}>
      <div className="trade-idea-header">
        <div>
          <span className="trade-idea-platform">{opportunity.platform}</span>
          <h3>{opportunity.event}</h3>
        </div>
        <span className={`pill pill-risk risk-${opportunity.risk_level.toLowerCase()}`}>
          {opportunity.risk_level} risk
        </span>
      </div>

      <p className="trade-idea-copy">
        Invest {formatPercent(opportunity.recommended_bankroll_fraction)} of your bankroll in{" "}
        {actionLabel(opportunity)} for an estimated {formatPercent(opportunity.expected_value)} profit
        potential with {formatPercent(opportunity.confidence)} signal strength.
      </p>

      <div className="trade-idea-summary">
        <span>Suggested amount: ${opportunity.recommended_position_size.toFixed(2)}</span>
        <span>Related signals: {opportunity.related_signal_count}</span>
      </div>
    </button>
  );
}

import type { Opportunity, SortKey } from "../types";

type OpportunityTableProps = {
  opportunities: Opportunity[];
  sortKey: SortKey;
  sortDirection: "asc" | "desc";
  onSort: (key: SortKey) => void;
  onSelect: (opportunity: Opportunity) => void;
};

const columns: Array<{ key: SortKey; label: string }> = [
  { key: "event", label: "Event" },
  { key: "platform", label: "Platform" },
  { key: "implied_probability", label: "Implied %" },
  { key: "consensus_probability", label: "Consensus %" },
  { key: "expected_value", label: "EV" },
  { key: "recommended_bankroll_fraction", label: "Invest %" },
  { key: "recommended_position_size", label: "Position $" },
  { key: "liquidity", label: "Liquidity" },
  { key: "confidence", label: "Confidence" }
];

function formatPercent(value: number | null | undefined) {
  if (value == null) {
    return "N/A";
  }
  return `${(value * 100).toFixed(1)}%`;
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
    maximumFractionDigits: 0
  }).format(value);
}

export function OpportunityTable({
  opportunities,
  sortKey,
  sortDirection,
  onSort,
  onSelect
}: OpportunityTableProps) {
  return (
    <section className="panel table-panel">
      <div className="panel-heading">
        <div>
          <h3>Detected Opportunities</h3>
          <p>{opportunities.length} rows after filtering</p>
        </div>
        <p className="tooltip-copy">
          Click any row to inspect market details.
        </p>
      </div>
      <p
        className="tooltip-copy"
        title="This is a suggested position size based on expected value and model confidence using a conservative Kelly-based strategy."
      >
        Suggested investment sizes use a conservative Kelly-style bankroll rule.
      </p>
      <div className="table-wrap">
        <table className="opportunity-table">
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column.key}>
                  <button className="sort-button" onClick={() => onSort(column.key)}>
                    {column.label}
                    {sortKey === column.key ? (
                      <span>{sortDirection === "asc" ? " ^" : " v"}</span>
                    ) : null}
                  </button>
                </th>
              ))}
              <th>Flags</th>
            </tr>
          </thead>
          <tbody>
            {opportunities.map((opportunity) => (
              <tr key={opportunity.opportunity_id} onClick={() => onSelect(opportunity)}>
                <td>
                  <div className="event-cell">
                    <strong>{opportunity.event}</strong>
                    <span>{opportunity.market}</span>
                  </div>
                </td>
                <td>{opportunity.platforms.join(", ")}</td>
                <td>{formatPercent(opportunity.implied_probability)}</td>
                <td>{formatPercent(opportunity.consensus_probability)}</td>
                <td className={opportunity.expected_value > 0 ? "positive" : ""}>
                  {formatPercent(opportunity.expected_value)}
                </td>
                <td>{formatPercent(opportunity.recommended_bankroll_fraction)}</td>
                <td>{formatCurrency(opportunity.recommended_position_size)}</td>
                <td>{formatNumber(opportunity.liquidity)}</td>
                <td>{formatPercent(opportunity.confidence)}</td>
                <td>
                  <div className="flags-cell">
                    {opportunity.arbitrage_flag ? (
                      <span className="pill pill-arb">Arb</span>
                    ) : (
                      <span className="pill">EV</span>
                    )}
                    <span className="pill pill-risk">
                      {String(opportunity.risk.overall ?? "unknown")}
                    </span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

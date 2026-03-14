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
  { key: "implied_probability", label: "Current Market Odds" },
  { key: "consensus_probability", label: "Market Average Odds" },
  { key: "expected_value", label: "Estimated Profit Potential" },
  { key: "price_change_5m", label: "5m Change" },
  { key: "price_change_30m", label: "30m Change" },
  { key: "volatility_30m", label: "Price Choppiness" },
  { key: "recommended_bankroll_fraction", label: "Suggested Bankroll %" },
  { key: "recommended_position_size", label: "Suggested Amount" },
  { key: "liquidity", label: "Liquidity" },
  { key: "confidence", label: "Signal Strength" }
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

function movementClass(value: number) {
  if (value > 0.01) {
    return "movement-up";
  }
  if (value < -0.01) {
    return "movement-down";
  }
  return "movement-flat";
}

function movementSignalClass(signal: string) {
  if (signal === "lagging_market") {
    return "pill pill-warning";
  }
  if (signal === "rapid_up" || signal === "rapid_down") {
    return "pill pill-arb";
  }
  return "pill";
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
          <h3>Trading Opportunities</h3>
          <p>{opportunities.length} results after filtering</p>
        </div>
        <p className="tooltip-copy">
          Click any row to see why the signal was flagged.
        </p>
      </div>
      <p
        className="tooltip-copy"
        title="This recommendation uses conservative bankroll management to limit risk. It blends estimated profit potential, confidence, and liquidity into a smaller suggested position size."
      >
        Suggested amounts use conservative bankroll management to help limit risk.
      </p>
      <p
        className="tooltip-copy"
        title="Estimated Profit Potential compares the market price with the scanner's broader market view. Higher values suggest the market may be underpricing this outcome."
      >
        Estimated Profit Potential shows how attractive the trade looks if the broader market view is correct.
      </p>
      <p
        className="tooltip-copy"
        title="Signal Strength combines how confident the system is that the markets describe the same event with how much agreement exists across sources."
      >
        Signal Strength tells you how much trust to place in the pricing signal.
      </p>
      <p
        className="tooltip-copy"
        title="Green indicates upward movement, red indicates downward movement, and yellow highlights lagging markets relative to peers."
      >
        Movement colors: green up, red down, yellow lagging.
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
              <th>Quick Tags</th>
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
                <td className={movementClass(opportunity.price_change_5m)}>
                  {formatPercent(opportunity.price_change_5m)}
                </td>
                <td className={movementClass(opportunity.price_change_30m)}>
                  {formatPercent(opportunity.price_change_30m)}
                </td>
                <td>{formatPercent(opportunity.volatility_30m)}</td>
                <td>{formatPercent(opportunity.recommended_bankroll_fraction)}</td>
                <td>{formatCurrency(opportunity.recommended_position_size)}</td>
                <td>{formatNumber(opportunity.liquidity)}</td>
                <td>{formatPercent(opportunity.confidence)}</td>
                <td>
                  <div className="flags-cell">
                    {opportunity.arbitrage_flag ? (
                      <span className="pill pill-arb">Low-Risk Gap</span>
                    ) : (
                      <span className="pill">Profit Signal</span>
                    )}
                    <span className={movementSignalClass(opportunity.movement_signal)}>
                      {opportunity.movement_signal}
                    </span>
                    {opportunity.risk.suspicious_ev === "true" ? (
                      <span className="pill pill-warning">Check Price</span>
                    ) : null}
                    <span className="pill pill-risk">
                      {String(opportunity.risk.overall ?? "unknown")} risk
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

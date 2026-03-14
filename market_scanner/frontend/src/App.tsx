import { useEffect, useMemo, useState } from "react";
import { fetchOpportunities, runScan } from "./api";
import { FiltersPanel } from "./components/FiltersPanel";
import { MarketDetailModal } from "./components/MarketDetailModal";
import { OpportunityCard } from "./components/OpportunityCard";
import { OpportunityTable } from "./components/OpportunityTable";
import { ScanControls } from "./components/ScanControls";
import type {
  FiltersState,
  Opportunity,
  OpportunitiesResponse,
  ScanRequest,
  SortKey
} from "./types";

const defaultScanRequest: ScanRequest = {
  limit: 50,
  min_liquidity: 100,
  min_ev: 0.02,
  bankroll_amount: 1000
};

const defaultFilters: FiltersState = {
  platform: "",
  arbitrageOnly: false,
  minEv: 0,
  minLiquidity: 0
};

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function App() {
  const [scanRequest, setScanRequest] = useState<ScanRequest>(defaultScanRequest);
  const [filters, setFilters] = useState<FiltersState>(defaultFilters);
  const [sortKey, setSortKey] = useState<SortKey>("expected_value");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [lastScanAt, setLastScanAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedOpportunity, setSelectedOpportunity] = useState<Opportunity | null>(null);

  useEffect(() => {
    void loadExisting();
  }, []);

  async function loadExisting() {
    setLoading(true);
    setError(null);
    try {
      const response: OpportunitiesResponse = await fetchOpportunities();
      setOpportunities(response.opportunities);
      setLastScanAt(response.last_scan_at);
    } catch (caughtError) {
      const message =
        caughtError instanceof Error ? caughtError.message : "Failed to load opportunities.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  async function handleRunScan() {
    setLoading(true);
    setError(null);
    try {
      const response = await runScan(scanRequest);
      setOpportunities(response.opportunities);
      setLastScanAt(response.scanned_at);
    } catch (caughtError) {
      const message =
        caughtError instanceof Error ? caughtError.message : "Failed to run scan.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  function handleSort(nextKey: SortKey) {
    if (nextKey === sortKey) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(nextKey);
    setSortDirection("desc");
  }

  const platformOptions = useMemo(() => {
    return Array.from(new Set(opportunities.flatMap((item) => item.platforms))).sort();
  }, [opportunities]);

  const filteredOpportunities = useMemo(() => {
    const items = opportunities.filter((item) => {
      if (filters.platform && !item.platforms.includes(filters.platform)) {
        return false;
      }
      if (filters.arbitrageOnly && !item.arbitrage_flag) {
        return false;
      }
      if (item.expected_value < filters.minEv) {
        return false;
      }
      if (item.liquidity < filters.minLiquidity) {
        return false;
      }
      return true;
    });

    return [...items].sort((left, right) => {
      const leftValue = left[sortKey] ?? 0;
      const rightValue = right[sortKey] ?? 0;

      if (typeof leftValue === "string" && typeof rightValue === "string") {
        const comparison = leftValue.localeCompare(rightValue);
        return sortDirection === "asc" ? comparison : -comparison;
      }

      const numericLeft = typeof leftValue === "number" ? leftValue : 0;
      const numericRight = typeof rightValue === "number" ? rightValue : 0;
      return sortDirection === "asc" ? numericLeft - numericRight : numericRight - numericLeft;
    });
  }, [filters, opportunities, sortDirection, sortKey]);

  const summary = useMemo(() => {
    const arbitrageCount = filteredOpportunities.filter((item) => item.arbitrage_flag).length;
    const bestEv = filteredOpportunities[0]?.expected_value ?? 0;
    const averageConfidence =
      filteredOpportunities.length > 0
        ? filteredOpportunities.reduce((sum, item) => sum + item.confidence, 0) /
          filteredOpportunities.length
        : 0;

    return {
      total: filteredOpportunities.length,
      arbitrageCount,
      bestEv,
      averageConfidence
    };
  }, [filteredOpportunities]);

  return (
    <div className="app-shell">
      <header className="hero">
        <div>
          <span className="eyebrow">Market Intelligence Dashboard</span>
          <h1>Market Scanner</h1>
          <p>
            Run live scans, compare implied and consensus probabilities, and inspect
            arbitrage or positive-EV opportunities from the existing Python backend.
          </p>
        </div>
      </header>

      <ScanControls
        value={scanRequest}
        loading={loading}
        onChange={setScanRequest}
        onScan={handleRunScan}
        lastScanAt={lastScanAt}
      />

      <section className="metrics-row">
        <OpportunityCard
          title="Filtered Opportunities"
          value={String(summary.total)}
          helper="Rows matching the current filters"
        />
        <OpportunityCard
          title="Arbitrage Flags"
          value={String(summary.arbitrageCount)}
          helper="Cross-market opportunities in the visible set"
        />
        <OpportunityCard
          title="Best EV"
          value={formatPercent(summary.bestEv)}
          helper="Highest expected value after filtering"
        />
        <OpportunityCard
          title="Average Confidence"
          value={formatPercent(summary.averageConfidence)}
          helper="Mean of match and model confidence"
        />
      </section>

      <FiltersPanel
        filters={filters}
        platforms={platformOptions}
        onChange={setFilters}
      />

      {error ? (
        <section className="panel state-panel error-panel">
          <h3>Something went wrong</h3>
          <p>{error}</p>
        </section>
      ) : null}

      {!error && loading ? (
        <section className="panel state-panel">
          <h3>Loading opportunities</h3>
          <p>The backend is fetching live markets and recomputing scanner output.</p>
        </section>
      ) : null}

      {!error && !loading && filteredOpportunities.length === 0 ? (
        <section className="panel state-panel">
          <h3>No opportunities yet</h3>
          <p>Run a scan or relax the filters to populate the dashboard.</p>
        </section>
      ) : null}

      {!error && !loading && filteredOpportunities.length > 0 ? (
        <OpportunityTable
          opportunities={filteredOpportunities}
          sortKey={sortKey}
          sortDirection={sortDirection}
          onSort={handleSort}
          onSelect={setSelectedOpportunity}
        />
      ) : null}

      <MarketDetailModal
        opportunity={selectedOpportunity}
        onClose={() => setSelectedOpportunity(null)}
      />
    </div>
  );
}

export default App;

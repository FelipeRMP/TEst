import { useEffect, useMemo, useState } from "react";
import { fetchCollectionStats, fetchOpportunities, runScan } from "./api";
import { DataCollectionPanel } from "./components/DataCollectionPanel";
import { FiltersPanel } from "./components/FiltersPanel";
import { MarketDetailModal } from "./components/MarketDetailModal";
import { OpportunityCard } from "./components/OpportunityCard";
import { ScanControls } from "./components/ScanControls";
import { TradeIdeaCard } from "./components/TradeIdeaCard";
import type {
  CollectionStats,
  FiltersState,
  Opportunity,
  OpportunitiesResponse,
  ScanRequest
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

type TabKey = "trade-ideas" | "data-collection";

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function App() {
  const [activeTab, setActiveTab] = useState<TabKey>("trade-ideas");
  const [scanRequest, setScanRequest] = useState<ScanRequest>(defaultScanRequest);
  const [filters, setFilters] = useState<FiltersState>(defaultFilters);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [lastScanAt, setLastScanAt] = useState<string | null>(null);
  const [collectionStats, setCollectionStats] = useState<CollectionStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingStats, setLoadingStats] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statsError, setStatsError] = useState<string | null>(null);
  const [selectedOpportunity, setSelectedOpportunity] = useState<Opportunity | null>(null);

  useEffect(() => {
    void Promise.all([loadExisting(), loadCollectionStats()]);
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

  async function loadCollectionStats() {
    setLoadingStats(true);
    setStatsError(null);
    try {
      const response = await fetchCollectionStats();
      setCollectionStats(response);
    } catch (caughtError) {
      const message =
        caughtError instanceof Error ? caughtError.message : "Failed to load collection stats.";
      setStatsError(message);
    } finally {
      setLoadingStats(false);
    }
  }

  async function handleRunScan() {
    setLoading(true);
    setError(null);
    try {
      const response = await runScan(scanRequest);
      setOpportunities(response.opportunities);
      setLastScanAt(response.scanned_at);
      await loadCollectionStats();
    } catch (caughtError) {
      const message =
        caughtError instanceof Error ? caughtError.message : "Failed to run scan.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  const platformOptions = useMemo(() => {
    return Array.from(new Set(opportunities.flatMap((item) => item.platforms))).sort();
  }, [opportunities]);

  const filteredOpportunities = useMemo(() => {
    return opportunities.filter((item) => {
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
  }, [filters, opportunities]);

  const summary = useMemo(() => {
    const arbitrageCount = filteredOpportunities.filter((item) => item.arbitrage_flag).length;
    const bestEv = Math.max(0, ...filteredOpportunities.map((item) => item.expected_value));
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
            Track simple trade ideas on one tab, and monitor signal logging plus paper-trading
            research on the other.
          </p>
        </div>
      </header>

      <div className="tab-strip">
        <button
          className={`tab-button ${activeTab === "trade-ideas" ? "tab-button-active" : ""}`}
          onClick={() => setActiveTab("trade-ideas")}
        >
          Trade Ideas
        </button>
        <button
          className={`tab-button ${activeTab === "data-collection" ? "tab-button-active" : ""}`}
          onClick={() => setActiveTab("data-collection")}
        >
          Data Collection
        </button>
      </div>

      {activeTab === "trade-ideas" ? (
        <>
          <ScanControls
            value={scanRequest}
            loading={loading}
            onChange={setScanRequest}
            onScan={handleRunScan}
            lastScanAt={lastScanAt}
          />

          <section className="metrics-row">
            <OpportunityCard
              title="Visible Opportunities"
              value={String(summary.total)}
              helper="Simple trade ideas that match your current filters"
            />
            <OpportunityCard
              title="Near Risk-Free Setups"
              value={String(summary.arbitrageCount)}
              helper="Possible buy-both-sides opportunities in the visible list"
            />
            <OpportunityCard
              title="Best Profit Potential"
              value={formatPercent(summary.bestEv)}
              helper="The strongest estimated profit potential in the current view"
            />
            <OpportunityCard
              title="Average Signal Strength"
              value={formatPercent(summary.averageConfidence)}
              helper="A quick trust score across the visible trade ideas"
            />
          </section>

          <FiltersPanel filters={filters} platforms={platformOptions} onChange={setFilters} />

          {error ? (
            <section className="panel state-panel error-panel">
              <h3>We couldn't load trade ideas</h3>
              <p>{error}</p>
            </section>
          ) : null}

          {!error && loading ? (
            <section className="panel state-panel">
              <h3>Scanning live markets</h3>
              <p>The backend is gathering fresh prices and turning them into simple trade ideas.</p>
            </section>
          ) : null}

          {!error && !loading && filteredOpportunities.length === 0 ? (
            <section className="panel state-panel">
              <h3>No trade ideas found yet</h3>
              <p>Run a scan or loosen the filters to see more results.</p>
            </section>
          ) : null}

          {!error && !loading && filteredOpportunities.length > 0 ? (
            <section className="trade-ideas-grid">
              {filteredOpportunities.map((opportunity) => (
                <TradeIdeaCard
                  key={opportunity.opportunity_id}
                  opportunity={opportunity}
                  onSelect={setSelectedOpportunity}
                />
              ))}
            </section>
          ) : null}
        </>
      ) : (
        <DataCollectionPanel
          stats={collectionStats}
          loading={loadingStats}
          error={statsError}
        />
      )}

      <MarketDetailModal
        opportunity={selectedOpportunity}
        onClose={() => setSelectedOpportunity(null)}
      />
    </div>
  );
}

export default App;

import type { FiltersState } from "../types";

type FiltersPanelProps = {
  filters: FiltersState;
  platforms: string[];
  onChange: (nextFilters: FiltersState) => void;
};

export function FiltersPanel({ filters, platforms, onChange }: FiltersPanelProps) {
  return (
    <section className="panel filters-panel">
      <div className="panel-heading">
        <h3>Refine Results</h3>
        <p>Narrow the current list without running a new scan.</p>
      </div>
      <div className="filters-grid">
        <label>
          <span>Platform</span>
          <select
            value={filters.platform}
            onChange={(event) =>
              onChange({ ...filters, platform: event.target.value })
            }
          >
            <option value="">All platforms</option>
            {platforms.map((platform) => (
              <option key={platform} value={platform}>
                {platform}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Minimum Profit Potential</span>
          <input
            type="number"
            step="0.01"
            min={0}
            value={filters.minEv}
            onChange={(event) =>
              onChange({ ...filters, minEv: Number(event.target.value) || 0 })
            }
          />
        </label>
        <label>
          <span>Minimum Market Depth</span>
          <input
            type="number"
            step="100"
            min={0}
            value={filters.minLiquidity}
            onChange={(event) =>
              onChange({
                ...filters,
                minLiquidity: Number(event.target.value) || 0
              })
            }
          />
        </label>
        <label className="checkbox-field">
          <span>Only Near Risk-Free Setups</span>
          <input
            type="checkbox"
            checked={filters.arbitrageOnly}
            onChange={(event) =>
              onChange({ ...filters, arbitrageOnly: event.target.checked })
            }
          />
        </label>
      </div>
    </section>
  );
}

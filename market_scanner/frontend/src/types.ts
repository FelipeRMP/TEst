export type OpportunityLeg = {
  platform: string;
  market_id: string;
  market_title: string;
  outcome: string;
  price: number;
  implied_probability: number;
  consensus_probability: number | null;
  liquidity: number;
  volume_24h: number;
  spread_bps: number | null;
  description: string | null;
  resolution_criteria: string | null;
};

export type Opportunity = {
  opportunity_id: string;
  event_id: string;
  event: string;
  market: string;
  platform: string;
  platforms: string[];
  implied_probability: number;
  consensus_probability: number | null;
  expected_value: number;
  liquidity: number;
  arbitrage_flag: boolean;
  confidence: number;
  opportunity_type: string;
  net_edge: number;
  max_executable_size: number | null;
  recommended_bankroll_fraction: number;
  recommended_position_size: number;
  risk_level: string;
  risk: Record<string, string | number>;
  suggested_trade_strategy: string;
  legs: OpportunityLeg[];
};

export type ScanRequest = {
  limit: number;
  min_liquidity: number;
  min_ev: number;
  bankroll_amount: number;
};

export type OpportunitiesResponse = {
  opportunities: Opportunity[];
  count: number;
  last_scan_at: string | null;
};

export type ScanResponse = {
  opportunities: Opportunity[];
  count: number;
  scanned_at: string;
  params: ScanRequest;
};

export type FiltersState = {
  platform: string;
  arbitrageOnly: boolean;
  minEv: number;
  minLiquidity: number;
};

export type SortKey =
  | "event"
  | "platform"
  | "expected_value"
  | "consensus_probability"
  | "implied_probability"
  | "liquidity"
  | "confidence"
  | "recommended_bankroll_fraction"
  | "recommended_position_size";

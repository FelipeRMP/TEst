export type OpportunityLeg = {
  platform: string;
  market_id: string;
  market_title: string;
  outcome: string;
  price: number;
  implied_probability: number;
  best_bid: number | null;
  best_ask: number | null;
  bid_size: number | null;
  ask_size: number | null;
  spread: number | null;
  spread_percent: number | null;
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
  best_bid: number | null;
  best_ask: number | null;
  spread: number | null;
  spread_percent: number | null;
  consensus_probability: number | null;
  expected_value: number;
  liquidity: number;
  arbitrage_flag: boolean;
  confidence: number;
  related_signal_count: number;
  opportunity_type: string;
  net_edge: number;
  max_executable_size: number | null;
  recommended_bankroll_fraction: number;
  recommended_position_size: number;
  risk_level: string;
  price_change_5m: number;
  price_change_30m: number;
  price_change_2h: number;
  price_change_24h: number;
  movement_signal: string;
  movement_confidence: number;
  volatility_5m: number;
  volatility_30m: number;
  volatility_2h: number;
  consensus_variance: number;
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

export type RecentScanActivity = {
  scan_id: string;
  timestamp: string;
  signal_count: number;
  price_snapshot_count: number;
  status: string;
  duration_seconds: number;
};

export type RepeatedSignalFamily = {
  signal_family: string;
  event_title: string;
  count: number;
  last_seen: string | null;
};

export type CollectionStats = {
  total_signals_logged: number;
  total_price_snapshots_logged: number;
  latest_signal_timestamp: string | null;
  latest_price_timestamp: string | null;
  latest_scan_timestamp: string | null;
  total_scan_batches: number;
  latest_scan_batch_timestamp: string | null;
  latest_scan_duration_seconds: number;
  unique_markets_scanned: number;
  unique_events_signaled: number;
  malformed_id_count: number;
  simulator_trade_count: number;
  simulator_total_pnl: number;
  simulated_realized_pnl: number;
  simulator_win_rate: number | null;
  average_expected_value: number;
  average_ev: number;
  recent_signal_count_24h: number;
  recent_price_snapshot_count_24h: number;
  expected_scan_interval_seconds: number;
  data_freshness_status: string;
  win_rate: number | null;
  recent_scan_activity: RecentScanActivity[];
  top_repeated_signal_families: RepeatedSignalFamily[];
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
  | "recommended_position_size"
  | "price_change_5m"
  | "price_change_30m"
  | "volatility_30m";

# Automated Market Intelligence System Design

## Goal

Build a system that continuously scans prediction markets and betting platforms, normalizes prices into comparable probabilities, matches equivalent events across platforms, estimates a fair consensus probability, and ranks actionable opportunities such as arbitrage, positive expected value bets, and stale or illiquid mispricings.

## 1. High-Level Architecture

```text
                +----------------------+
                | Platform Connectors  |
                | Polymarket, books,   |
                | exchanges, APIs      |
                +----------+-----------+
                           |
                           v
                +----------------------+
                | Ingestion Pipeline   |
                | polling, streaming,  |
                | retries, validation  |
                +----------+-----------+
                           |
                           v
                +----------------------+
                | Normalization Layer  |
                | odds -> probability  |
                | liquidity/spread     |
                | outcome canonicality |
                +----------+-----------+
                           |
                           v
                +----------------------+
                | Event Matching       |
                | NLP + fuzzy matching |
                | resolution alignment |
                +----------+-----------+
                           |
                           v
                +----------------------+
                | Consensus Engine     |
                | source weighting     |
                | fair probability     |
                +----------+-----------+
                           |
                           v
                +----------------------+
                | Opportunity Engine   |
                | arb, EV, stale       |
                | inefficiency flags   |
                +----------+-----------+
                           |
                           v
                +----------------------+
                | Ranking + Output     |
                | score, risk, action  |
                | API/UI/alerts        |
                +----------------------+
```

## 2. Core Components

### A. Data Connectors

Each connector standardizes raw market data into a shared schema.

Supported source types:

- Prediction markets: Polymarket, Kalshi, Manifold
- Sportsbooks: DraftKings, FanDuel, Bet365
- Exchanges: Betfair, Matchbook

Connector responsibilities:

- Pull market metadata
- Pull prices and order book snapshots where available
- Capture timestamps, liquidity, spread, and volume
- Track platform-specific resolution rules
- Detect suspensions, market halts, and stale quotes

Recommended pattern:

- Streaming/websocket where available
- Polling fallback for REST-only sources
- Idempotent upserts into raw tables

### B. Normalization Layer

Normalize all source formats to a unified event/outcome representation.

#### Canonical market fields

```json
{
  "platform": "polymarket",
  "market_id": "0xabc123",
  "event_title": "Will Candidate A win the election?",
  "outcome_label": "YES",
  "raw_price": 0.61,
  "price_type": "decimal_probability",
  "implied_probability": 0.61,
  "bid": 0.60,
  "ask": 0.62,
  "spread_bps": 200,
  "volume_24h": 185000,
  "liquidity": 420000,
  "last_updated_at": "2026-03-14T10:30:00Z",
  "resolution_criteria": "Resolves YES if Candidate A is officially certified as winner.",
  "market_status": "open"
}
```

#### Odds normalization

Convert every quoted price into an implied probability.

Examples:

- Decimal odds: `p = 1 / decimal_odds`
- Fractional odds `a/b`: `p = b / (a + b)`
- American odds:
  - Positive `+x`: `p = 100 / (x + 100)`
  - Negative `-x`: `p = x / (x + 100)` using absolute value of `x`
- Prediction market YES share: `p = price`
- Exchange back/lay:
  - Back implied probability from best back price
  - Lay implied probability from best lay price
  - Midpoint or executable side chosen depending on strategy simulation

#### Margin handling

Sportsbooks often include vig.

For mutually exclusive outcomes:

1. Convert each outcome to raw implied probability
2. Sum raw probabilities
3. Normalize each as:
   `p_fair_i = p_raw_i / sum(p_raw_all)`

Store both:

- `implied_probability_raw`
- `implied_probability_no_vig`

### C. Event and Outcome Canonicalization

Canonical entity model:

- `CanonicalEvent`
- `CanonicalOutcome`
- `SourceMarket`
- `SourceOutcome`

Example:

```json
{
  "canonical_event_id": "election_us_2028_president_winner",
  "event_type": "politics",
  "entities": ["Candidate A", "Candidate B"],
  "start_time": null,
  "resolution_time": "2028-11-08T05:00:00Z",
  "canonical_question": "Will Candidate A win the 2028 U.S. presidential election?",
  "canonical_outcomes": [
    {"outcome_id": "yes_candidate_a", "label": "YES"},
    {"outcome_id": "no_candidate_a", "label": "NO"}
  ]
}
```

Canonicalization tasks:

- Normalize names, teams, leagues, dates, venues, tickers, candidates
- Map synonyms: "win", "be elected", "take office"
- Convert all binary markets to YES/NO framing
- Convert multi-way markets into comparable derived probabilities when possible

## 3. Market Matching

The system must determine when two markets refer to the same real-world event and comparable outcomes.

### Matching Pipeline

#### Step 1: Blocking

Reduce candidate pairs before expensive NLP.

Blocking keys:

- Event date/time window
- Sport/league/category
- Named entities extracted from titles
- Market type: moneyline, spread, total, election winner, macro event

#### Step 2: Similarity Features

Build pairwise similarity features from:

- Title embeddings
- Outcome label embeddings
- Fuzzy string similarity
- Named entity overlap
- Time proximity
- Numeric constraint overlap
- Resolution criteria similarity
- Platform taxonomy match

Useful models:

- Sentence embeddings for titles and criteria
- Named entity recognition for teams, candidates, asset names
- Rule-based parsers for dates, thresholds, and comparators

#### Step 3: Resolution Alignment

Two markets with similar text may still resolve differently.

Examples:

- "Will X be elected?" vs "Will X take office?"
- "Will BTC exceed $100k in 2026?" vs "Will BTC close above $100k on Dec 31?"

Resolution alignment checks:

- Same reference entity
- Same threshold
- Same observation window
- Same resolution source if material
- Same notion of occurrence: intraday touch, close, official result, settlement source

#### Step 4: Match Scoring

Produce:

- `match_score` from 0 to 1
- `resolution_compatibility_score` from 0 to 1
- `outcome_mapping_confidence` from 0 to 1

Final match confidence:

`final_match_confidence = 0.5 * semantic_score + 0.3 * criteria_score + 0.2 * outcome_alignment_score`

Only promote to canonical equivalence above threshold, for example `0.85`.

#### Step 5: Human Review Queue

Low-confidence but high-value matches should be queued for review.

Examples:

- Large apparent arbitrage with `match_confidence < 0.9`
- High liquidity event with conflicting resolution wording

## 4. Probability Modeling

The system should estimate a fair probability for each canonical outcome.

### Consensus Probability

Use a weighted aggregation across sources.

Base weighting inputs:

- Liquidity depth
- Recent volume
- Tightness of spread
- Source reliability
- Freshness of quote
- Historical sharpness of platform for that market category

Suggested source weight:

`w_i = reliability_i * log(1 + liquidity_i) * freshness_decay_i * spread_penalty_i`

Where:

- `freshness_decay_i = exp(-lambda * age_seconds)`
- `spread_penalty_i = 1 / (1 + normalized_spread)`

Consensus probability:

`p_consensus = sum(w_i * p_i) / sum(w_i)`

### Robustness Controls

To avoid consensus distortion:

- Downweight illiquid or wide-spread markets
- Cap single-source contribution
- Use median or Huber-robust averaging when dispersion is high
- Exclude markets flagged stale or suspended

### Model Confidence

Confidence should increase when:

- Many independent platforms agree
- Liquidity is high
- Quotes are recent
- Match confidence is high
- Resolution criteria are well aligned

Example confidence score:

`model_confidence = f(source_count, effective_liquidity, variance_inverse, match_confidence_mean, criteria_alignment_mean)`

## 5. Opportunity Detection

### A. Cross-Platform Arbitrage

Applies when complementary positions across platforms guarantee positive payoff after fees.

#### Binary event example

For the same event:

- Buy YES on platform A at price `p_yes_A`
- Buy NO on platform B at price `p_no_B`

Arbitrage exists if:

`p_yes_A + p_no_B + fees + slippage < 1`

Profit per $1 notional approximately:

`arb_margin = 1 - total_cost`

#### Sportsbook/exchange multi-outcome example

For `n` mutually exclusive outcomes:

Arbitrage exists if:

`sum(1 / best_decimal_odds_i) < 1`

Store:

- gross arbitrage margin
- net arbitrage margin after fees
- executable size based on minimum available depth across legs

### B. Positive Expected Value

Compare platform price to consensus fair probability.

For a YES contract priced at `p_market` and consensus `p_consensus`:

`EV_per_$1 = p_consensus - p_market - fees - slippage_adjustment`

For sportsbook odds, expected value can be computed from payout structure:

`EV = p_consensus * profit_if_win - (1 - p_consensus) * stake`

Flag if:

- `EV > threshold`
- quote is recent
- minimum liquidity threshold met
- model confidence above threshold

### C. Inefficiency Detection

Identify mispricings caused by weak market quality.

Signals:

- Low liquidity relative to peer markets
- Wide spread
- Quote age much older than peer quotes
- Large move in related markets not yet reflected
- Sudden external news and lagging adjustment
- Order book imbalance

Example stale-market score:

`staleness_score = age_zscore + peer_move_divergence + spread_zscore`

## 6. Ranking Framework

Each opportunity gets a final score for prioritization.

### Inputs

- Expected value
- Net arbitrage margin
- Executable liquidity
- Number of legs
- Estimated slippage
- Match confidence
- Model confidence
- Resolution risk
- Operational risk

### Suggested ranking formula

```text
opportunity_score =
  0.35 * normalized_ev +
  0.20 * normalized_liquidity +
  0.15 * execution_feasibility +
  0.15 * model_confidence +
  0.10 * match_confidence -
  0.05 * risk_penalty
```

Where `risk_penalty` includes:

- ambiguous resolution
- low depth
- high spread
- many-leg execution risk
- platform-specific counterparty or settlement concerns

### Execution Feasibility

Estimate how likely the trade can be executed at shown prices.

Factors:

- order book depth at best price
- need to leg into multiple platforms
- withdrawal/deposit latency
- platform limits
- KYC/account restrictions
- API or automation support

## 7. Data Model

### Tables

#### `raw_market_snapshots`

- `snapshot_id`
- `platform`
- `market_id`
- `raw_payload`
- `captured_at`

#### `normalized_markets`

- `platform`
- `market_id`
- `canonical_event_id` nullable
- `canonical_outcome_id` nullable
- `event_title`
- `outcome_label`
- `implied_probability_raw`
- `implied_probability_no_vig`
- `bid`
- `ask`
- `mid`
- `spread_bps`
- `volume_24h`
- `liquidity`
- `fees_estimate`
- `last_trade_at`
- `last_updated_at`
- `market_status`
- `resolution_criteria_hash`

#### `event_matches`

- `platform_a`
- `market_id_a`
- `platform_b`
- `market_id_b`
- `semantic_score`
- `criteria_score`
- `outcome_alignment_score`
- `final_match_confidence`
- `match_status`

#### `consensus_probabilities`

- `canonical_event_id`
- `canonical_outcome_id`
- `consensus_probability`
- `dispersion`
- `effective_liquidity`
- `source_count`
- `model_confidence`
- `computed_at`

#### `opportunities`

- `opportunity_id`
- `opportunity_type`
- `canonical_event_id`
- `canonical_outcome_id`
- `platforms`
- `gross_edge`
- `net_edge`
- `expected_value`
- `max_executable_size`
- `match_confidence`
- `model_confidence`
- `risk_score`
- `execution_feasibility`
- `suggested_strategy`
- `created_at`

## 8. Processing Flow

### Real-Time Loop

1. Ingest latest market data
2. Normalize into implied probabilities and market quality metrics
3. Match or rematch markets to canonical events
4. Recompute consensus probabilities
5. Run opportunity detectors
6. Rank and publish results
7. Trigger alerts for high-score opportunities

### Batch Jobs

- Re-train matching model
- Recompute platform reliability scores
- Backtest EV and arbitrage signals
- Refresh entity dictionaries and synonym maps

## 9. Suggested Technology Stack

### Ingestion

- Python or TypeScript connectors
- Kafka or Redpanda for event streaming
- Airbyte only if source coverage matters more than latency

### Storage

- Postgres for normalized transactional data
- Redis for hot snapshots and low-latency ranking
- S3 or object store for raw payload archive

### Modeling

- Python for matching and probability modeling
- `sentence-transformers` or an embeddings service for semantic similarity
- LightGBM or logistic regression for supervised match scoring

### Serving

- FastAPI or Node API for query access
- Websocket push for live opportunity feeds
- Optional dashboard in React

## 10. Risk Controls

This system should explicitly surface non-price risks.

Risk dimensions:

- Resolution mismatch risk
- Execution slippage risk
- Liquidity exhaustion risk
- Counterparty/platform risk
- Suspension/cancellation risk
- News latency risk

Recommended hard filters:

- Reject opportunities with low resolution compatibility
- Reject stale quotes older than configured threshold
- Require minimum executable size
- Adjust EV for fees and expected slippage

## 11. Structured Output Contract

The output should be machine-readable and also usable in a UI.

### Example output

```json
[
  {
    "event": "Will Candidate A win the 2028 U.S. presidential election?",
    "canonical_event_id": "election_us_2028_president_winner",
    "opportunity_type": "cross_platform_arbitrage",
    "platforms": [
      {
        "platform": "polymarket",
        "market_id": "0xabc123",
        "outcome": "YES",
        "price": 0.61,
        "implied_probability": 0.61,
        "liquidity": 420000,
        "spread_bps": 200
      },
      {
        "platform": "kalshi",
        "market_id": "KX123",
        "outcome": "NO",
        "price": 0.35,
        "implied_probability": 0.35,
        "liquidity": 310000,
        "spread_bps": 150
      }
    ],
    "consensus_probability": 0.58,
    "expected_value": 0.04,
    "net_edge": 0.03,
    "max_executable_size": 12000,
    "risk": {
      "overall": "medium",
      "match_confidence": 0.95,
      "model_confidence": 0.88,
      "resolution_risk": 0.08,
      "execution_risk": 0.22
    },
    "suggested_trade_strategy": "Buy YES on Polymarket and buy NO on Kalshi up to the minimum displayed depth after fees."
  }
]
```

### Minimum output fields

- `event`
- `opportunity_type`
- `platforms`
- `prices`
- `implied_probabilities`
- `consensus_probability`
- `expected_value`
- `risk`
- `suggested_trade_strategy`

## 12. Recommended MVP

Start with a narrow but robust slice:

### Scope

- 2 prediction markets
- 2 sportsbooks or exchanges
- Binary markets only
- One vertical first: politics, crypto, or major sports moneylines

### MVP Features

- Connector framework
- Odds normalization
- Binary market matcher
- Weighted consensus probability
- Arbitrage and EV detector
- Ranked JSON feed and alerting

### Defer Until Later

- Full multi-outcome decomposition
- Deep order book simulation
- Online learning for source reliability
- Automatic trade execution

## 13. Pseudocode

```python
while True:
    snapshots = ingest_all_sources()
    normalized = [normalize_market(s) for s in snapshots]

    for market in normalized:
        candidates = generate_match_candidates(market)
        match = resolve_best_match(market, candidates)
        attach_canonical_event(market, match)

    canonical_groups = group_by_canonical_event(normalized)

    consensus_map = {}
    for group in canonical_groups:
        consensus_map[group.id] = compute_consensus(group.markets)

    opportunities = []
    for group in canonical_groups:
        opportunities.extend(find_arbitrage(group))
        opportunities.extend(find_positive_ev(group, consensus_map[group.id]))
        opportunities.extend(find_inefficiencies(group))

    ranked = rank_opportunities(opportunities)
    publish(ranked)
    sleep(refresh_interval)
```

## 14. Success Metrics

- Match precision and recall
- Net realized EV versus predicted EV
- Share of alerted opportunities still executable after detection
- Mean detection latency
- False-positive arbitrage rate
- Profit adjusted for slippage and fees

## 15. Implementation Notes

- Treat resolution criteria as first-class data, not just market titles.
- Keep executable and displayed price separate.
- Build auditability into every score so each opportunity can be explained.
- Preserve raw payloads for dispute analysis and model retraining.
- Separate signal generation from auto-execution to reduce risk.


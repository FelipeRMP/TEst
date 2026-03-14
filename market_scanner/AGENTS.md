# AGENTS.md

## Project rules
- Preserve the current architecture unless a refactor is required to fix correctness.
- Do not fabricate assumptions about market-price units; trace them to source code and API responses.
- Treat exact confidence = 1.0 as suspicious unless derived from a provable deterministic rule.
- Grouped markets must represent the same underlying event and outcome.
- Frontend labels must match backend entities exactly.
- Prices must always represent probabilities in the range [0,1].
- Expected value calculations must use consistent units.
- EV > 300% should be flagged as suspicious.
- Grouped markets must represent the same event.
- UI labels must match backend event data exactly.

## Validation requirements
Before finishing:
- Run tests
- Run typecheck
- Run lint
- Add tests for price normalization and EV formatting
- Add a regression test for mismatched grouped events
- Add a regression test for stale-market penalty behavior

## Output requirements
Summarize:
1. root cause
2. fix
3. files changed
4. validation performed
5. remaining risks
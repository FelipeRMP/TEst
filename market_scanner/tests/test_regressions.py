from __future__ import annotations

import sys
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from backend import simulate_trades
from backend.utils import collection_stats, price_logger
from backend.utils.market_ids import normalize_market_id
from backend.utils import signal_logger


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.arbitrage_detector import OpportunityDetector
from src.analysis.bankroll_allocator import BankrollAllocator
from src.analysis.consensus_model import ConsensusModel
from src.analysis.movement_detector import MovementDetector, MovementMetrics
from src.matching.event_matcher import EventMatcher
from src.models import Event, Market, Outcome
from src.scanner import _sanitize_market
from src.storage.price_history_store import PriceHistoryPoint


def make_market(
    *,
    market_id: str,
    title: str,
    platform: str = "polymarket",
    probability: float = 0.5,
    description: str | None = None,
    liquidity: float = 1_000.0,
    end_date: datetime | None = None,
) -> Market:
    return Market(
        platform=platform,
        market_id=market_id,
        event_title=title,
        description=description,
        liquidity=liquidity,
        end_date=end_date,
        outcomes=[
            Outcome(label="YES", price=probability, implied_probability=probability),
            Outcome(label="NO", price=1.0 - probability, implied_probability=1.0 - probability),
        ],
    )


class PriceNormalizationTests(unittest.TestCase):
    def test_probability_prices_remain_in_decimal_units(self) -> None:
        samples = [0.001, 0.01, 0.25, 0.50, 0.99]

        for index, sample in enumerate(samples, start=1):
            market = Market(
                platform="polymarket",
                market_id=f"m-{index}",
                event_title=f"Market {index}",
                liquidity=100.0,
                outcomes=[Outcome(label="YES", price=sample, implied_probability=sample)],
            )

            sanitized = _sanitize_market(market)

            self.assertIsNotNone(sanitized)
            outcome = sanitized.outcomes[0]
            self.assertAlmostEqual(outcome.price or 0.0, sample, places=6)
            self.assertAlmostEqual(outcome.implied_probability or 0.0, sample, places=6)
            self.assertGreaterEqual(outcome.implied_probability or 0.0, 0.0)
            self.assertLessEqual(outcome.implied_probability or 0.0, 1.0)

    def test_invalid_probability_is_rejected(self) -> None:
        market = Market(
            platform="polymarket",
            market_id="invalid",
            event_title="Invalid Market",
            liquidity=100.0,
            outcomes=[Outcome(label="YES", price=1.5, implied_probability=None)],
        )

        self.assertIsNone(_sanitize_market(market))


class ExpectedValueTests(unittest.TestCase):
    def test_true_expected_value_uses_decimal_units(self) -> None:
        detector = OpportunityDetector(fee_bps=0, min_ev=0.0)

        ev = detector._true_expected_value(0.60, 0.50)

        self.assertAlmostEqual(ev, 0.10, places=6)
        self.assertLess(ev, 1.0)

    def test_true_expected_value_known_case(self) -> None:
        detector = OpportunityDetector(fee_bps=0, min_ev=0.0)

        ev = detector._true_expected_value(0.25, 0.20)

        self.assertAlmostEqual(ev, 0.05, places=6)

    def test_expected_value_does_not_show_percent_scaling_bug(self) -> None:
        detector = OpportunityDetector(fee_bps=50, min_ev=0.0)

        ev_after_fees = detector._true_expected_value(0.55, 0.50) - detector.fee_rate

        self.assertAlmostEqual(ev_after_fees, 0.045, places=6)
        self.assertLess(ev_after_fees, 1.0)

    def test_entry_price_uses_best_ask_when_available(self) -> None:
        detector = OpportunityDetector(fee_bps=0, min_ev=0.0)
        outcome = Outcome(
            label="YES",
            price=0.50,
            implied_probability=0.50,
            best_bid=0.48,
            best_ask=0.52,
        )

        self.assertAlmostEqual(detector._entry_price(outcome, "BUY") or 0.0, 0.52, places=6)


class MarketGroupingTests(unittest.TestCase):
    def test_different_teams_do_not_group(self) -> None:
        matcher = EventMatcher()
        end_date = datetime(2026, 6, 30, tzinfo=timezone.utc)
        markets = [
            make_market(
                market_id="rangers",
                title="Will the New York Rangers win the 2026 NHL Stanley Cup?",
                description="This market resolves Yes if the New York Rangers win the 2026 NHL Stanley Cup.",
                end_date=end_date,
            ),
            make_market(
                market_id="islanders",
                title="Will the New York Islanders win the 2026 NHL Stanley Cup?",
                description="This market resolves Yes if the New York Islanders win the 2026 NHL Stanley Cup.",
                end_date=end_date,
            ),
        ]

        events = matcher.group_markets(markets)

        self.assertEqual(len(events), 2)
        self.assertTrue(all(len(event.markets) == 1 for event in events))

    def test_similar_same_event_wording_groups(self) -> None:
        matcher = EventMatcher()
        end_date = datetime(2026, 11, 3, tzinfo=timezone.utc)
        markets = [
            make_market(
                market_id="pm",
                platform="polymarket",
                title="Will Donald Trump win the 2026 election?",
                description="Resolves Yes if Donald Trump wins the 2026 election.",
                end_date=end_date,
            ),
            make_market(
                market_id="kalshi",
                platform="kalshi",
                title="Will Donald Trump win the 2026 election",
                description="Donald Trump",
                end_date=end_date,
            ),
        ]

        events = matcher.group_markets(markets)

        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].markets), 2)

    def test_donald_and_ivanka_2028_markets_do_not_group(self) -> None:
        matcher = EventMatcher()
        end_date = datetime(2028, 11, 7, tzinfo=timezone.utc)
        markets = [
            make_market(
                market_id="561243",
                title="Will Donald Trump win the 2028 US Presidential Election?",
                description="Resolves Yes if Donald Trump wins the 2028 US Presidential Election.",
                end_date=end_date,
            ),
            make_market(
                market_id="561255",
                title="Will Ivanka Trump win the 2028 US Presidential Election?",
                description="Resolves Yes if Ivanka Trump wins the 2028 US Presidential Election.",
                end_date=end_date,
            ),
        ]

        events = matcher.group_markets(markets)

        self.assertEqual(len(events), 2)
        self.assertTrue(all(len(event.markets) == 1 for event in events))

    def test_opposite_party_control_markets_do_not_group(self) -> None:
        matcher = EventMatcher()
        end_date = datetime(2026, 11, 3, tzinfo=timezone.utc)
        markets = [
            make_market(
                market_id="562793",
                title="Will the Democratic Party control the Senate after the 2026 Midterm elections?",
                description="Resolves Yes if Democrats control the Senate after the 2026 midterms.",
                end_date=end_date,
            ),
            make_market(
                market_id="562794",
                title="Will the Republican Party control the Senate after the 2026 Midterm elections?",
                description="Resolves Yes if Republicans control the Senate after the 2026 midterms.",
                end_date=end_date,
            ),
        ]

        events = matcher.group_markets(markets)

        self.assertEqual(len(events), 2)

    def test_balance_of_power_variants_do_not_group(self) -> None:
        matcher = EventMatcher()
        end_date = datetime(2026, 11, 3, tzinfo=timezone.utc)
        markets = [
            make_market(
                market_id="562828",
                title="2026 Balance of Power: D Senate, D House",
                description="Resolves based on 2026 congressional control.",
                end_date=end_date,
            ),
            make_market(
                market_id="562829",
                title="2026 Balance of Power: D Senate, R House",
                description="Resolves based on 2026 congressional control.",
                end_date=end_date,
            ),
            make_market(
                market_id="562830",
                title="2026 Balance of Power: R Senate, D House",
                description="Resolves based on 2026 congressional control.",
                end_date=end_date,
            ),
        ]

        events = matcher.group_markets(markets)

        self.assertEqual(len(events), 3)


class ConfidenceCalibrationTests(unittest.TestCase):
    def test_model_confidence_stays_below_one(self) -> None:
        model = ConsensusModel()
        end_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
        markets = [
            make_market(
                market_id=f"m-{index}",
                title="Will Alice win the election?",
                platform="polymarket" if index % 2 == 0 else "kalshi",
                probability=0.61,
                liquidity=100_000.0,
                end_date=end_date,
            )
            for index in range(10)
        ]
        event = Event(
            event_id="alice-election",
            title="Will Alice win the election?",
            match_confidence=0.95,
            markets=markets,
        )

        consensus = model.compute([event])["alice-election"]

        self.assertGreater(consensus.model_confidence, 0.0)
        self.assertLess(consensus.model_confidence, 1.0)
        self.assertNotEqual(consensus.model_confidence, 1.0)

    def test_confidence_drops_with_disagreement(self) -> None:
        model = ConsensusModel()
        end_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
        aligned = Event(
            event_id="aligned",
            title="Aligned",
            markets=[
                make_market(market_id="a1", title="Aligned", probability=0.60, liquidity=10_000.0, end_date=end_date),
                make_market(market_id="a2", title="Aligned", probability=0.60, liquidity=10_000.0, end_date=end_date),
            ],
        )
        disputed = Event(
            event_id="disputed",
            title="Disputed",
            markets=[
                make_market(market_id="d1", title="Disputed", probability=0.15, liquidity=10_000.0, end_date=end_date),
                make_market(market_id="d2", title="Disputed", probability=0.85, liquidity=10_000.0, end_date=end_date),
            ],
        )

        results = model.compute([aligned, disputed])

        self.assertGreater(results["aligned"].model_confidence, results["disputed"].model_confidence)


class StaleMarketTests(unittest.TestCase):
    def test_zero_movement_triggers_stale_signal(self) -> None:
        metrics = MovementMetrics(
            price_change_5m=0.0,
            price_change_30m=0.0,
            price_change_2h=0.0,
        )

        signal, confidence = MovementDetector._movement_signal(metrics)

        self.assertEqual(signal, "stale_market")
        self.assertGreaterEqual(confidence, 0.0)
        self.assertLessEqual(confidence, 0.1)

    def test_stale_signal_reduces_bankroll_recommendation(self) -> None:
        allocator = BankrollAllocator()

        stable = allocator.recommend(
            expected_value=0.20,
            consensus_probability=0.60,
            confidence=0.70,
            liquidity=10_000.0,
            bankroll_amount=1_000.0,
            implied_probability=0.50,
            volatility_30m=0.0,
            movement_confidence=0.0,
            movement_signal="stable",
        )
        stale = allocator.recommend(
            expected_value=0.20,
            consensus_probability=0.60,
            confidence=0.70,
            liquidity=10_000.0,
            bankroll_amount=1_000.0,
            implied_probability=0.50,
            volatility_30m=0.0,
            movement_confidence=0.0,
            movement_signal="stale_market",
        )

        self.assertGreater(stable.recommended_bankroll_fraction, stale.recommended_bankroll_fraction)
        self.assertIn(stale.risk_level, {"medium", "high"})

    def test_price_change_and_volatility_use_history_windows(self) -> None:
        now = datetime.now(timezone.utc)
        history = [
            PriceHistoryPoint(
                timestamp=now - timedelta(minutes=40),
                scan_id="scan-1",
                platform="polymarket",
                event_id="event-1",
                market_id="market-1",
                outcome="YES",
                probability=0.40,
                liquidity=100.0,
            ),
            PriceHistoryPoint(
                timestamp=now - timedelta(minutes=10),
                scan_id="scan-1",
                platform="polymarket",
                event_id="event-1",
                market_id="market-1",
                outcome="YES",
                probability=0.40,
                liquidity=100.0,
            ),
            PriceHistoryPoint(
                timestamp=now,
                scan_id="scan-1",
                platform="polymarket",
                event_id="event-1",
                market_id="market-1",
                outcome="YES",
                probability=0.40,
                liquidity=100.0,
            ),
        ]

        self.assertEqual(MovementDetector._price_change(history, timedelta(minutes=30)), 0.0)
        self.assertEqual(MovementDetector._volatility(history, timedelta(minutes=30)), 0.0)


class LoggingNormalizationTests(unittest.TestCase):
    def test_market_id_normalization_is_consistent(self) -> None:
        normalized_ids = [
            normalize_market_id("kalshi", "POWER-28-DH-DS-RP", "YES"),
            normalize_market_id("kalshi", "kalshi:POWER-28-DH-DS-RP:YES", "YES"),
            normalize_market_id("kalshi", "POWER-28-DH-DS-RP:YES", "YES"),
            normalize_market_id("kalshi", "kalshi:POWER-28-DH-DS-RP:YES:YES", "YES"),
            normalize_market_id("polymarket", "561255", "YES"),
            normalize_market_id("polymarket", "polymarket:561255:YES:YES", "YES"),
        ]

        self.assertEqual(normalized_ids[0], "kalshi:POWER-28-DH-DS-RP:YES")
        self.assertEqual(normalized_ids[1], "kalshi:POWER-28-DH-DS-RP:YES")
        self.assertEqual(normalized_ids[2], "kalshi:POWER-28-DH-DS-RP:YES")
        self.assertEqual(normalized_ids[3], "kalshi:POWER-28-DH-DS-RP:YES")
        self.assertEqual(normalized_ids[4], "polymarket:561255:YES")
        self.assertEqual(normalized_ids[5], "polymarket:561255:YES")
        self.assertTrue(all(not item.endswith("YES:YES") for item in normalized_ids))
        self.assertTrue(all(not item.endswith("NO:NO") for item in normalized_ids))

    def test_signal_row_includes_orderbook_fields_without_duplicate_market_id(self) -> None:
        opportunity = SimpleNamespace(
            event_id="event-1",
            event="Example Event",
            consensus_probability=0.61,
            expected_value=0.08,
            confidence=0.72,
            liquidity=1500.0,
            recommended_bankroll_fraction=0.024,
            recommended_position_size=24.0,
            market="kalshi:POWER-28-DH-DS-RP:YES",
            legs=[
                SimpleNamespace(
                    platform="kalshi",
                    market_id="kalshi:POWER-28-DH-DS-RP:YES",
                    outcome="YES",
                    price=0.04,
                    best_bid=0.03,
                    best_ask=0.04,
                    bid_size=150.0,
                    ask_size=120.0,
                    spread=0.01,
                    spread_percent=0.285714,
                    consensus_probability=0.61,
                )
            ],
        )

        scan_time = datetime(2026, 3, 14, 18, 2, 10, tzinfo=timezone.utc)
        row = signal_logger._build_signal_row(opportunity, scan_id="scan-1", scan_timestamp=scan_time)

        self.assertEqual(row["market_id"], "kalshi:POWER-28-DH-DS-RP:YES")
        self.assertEqual(row["scan_id"], "scan-1")
        self.assertEqual(row["scan_timestamp"], "2026-03-14T18:02:10Z")
        self.assertIn("best_bid", row)
        self.assertIn("best_ask", row)
        self.assertIn("bid_size", row)
        self.assertIn("ask_size", row)
        self.assertIn("spread", row)
        self.assertIn("spread_percent", row)
        self.assertAlmostEqual(row["best_ask"], 0.04, places=6)

    def test_price_rows_include_scan_id(self) -> None:
        market = make_market(market_id="561255", title="Example market")
        rows = price_logger._build_price_rows(
            market,
            scan_id="scan-1",
            scan_timestamp=datetime(2026, 3, 14, 18, 2, 10, tzinfo=timezone.utc),
        )

        self.assertTrue(rows)
        self.assertTrue(all(row["scan_id"] == "scan-1" for row in rows))
        self.assertTrue(all(row["scan_timestamp"] == "2026-03-14T18:02:10Z" for row in rows))

    def test_simulator_loads_normalized_signal_rows(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            temp_path = Path(temp_dir)
            original_signal_path = simulate_trades.SIGNAL_LOG_PATH
            try:
                simulate_trades.SIGNAL_LOG_PATH = temp_path / "signal_log.csv"
                simulate_trades.SIGNAL_LOG_PATH.write_text(
                    (
                        "signal_id,scan_id,scan_timestamp,timestamp,signal_family,opportunity_type,event_id,event_title,platform,market_id,side,market_price,"
                        "consensus_probability,expected_value,signal_strength,liquidity,"
                        "suggested_bankroll_percent,suggested_amount,best_bid,best_ask,"
                        "bid_size,ask_size,spread,spread_percent\n"
                        "sig-1,scan-1,2026-03-14T18:02:10Z,2026-03-14T18:02:10Z,event-1|kalshi:POWER-28-DH-DS-RP:YES|signal,signal,event-1,Republican Sweep,kalshi,"
                        "kalshi:POWER-28-DH-DS-RP:YES,YES,0.04,0.136,0.071,0.26,1200,0.02,2,"
                        "0.03,0.04,100,90,0.01,0.285714\n"
                    ),
                    encoding="utf-8",
                )

                signals = simulate_trades.load_signals()

                self.assertEqual(len(signals), 1)
                self.assertEqual(signals[0].market_id, "kalshi:POWER-28-DH-DS-RP:YES")
                self.assertAlmostEqual(signals[0].best_bid or 0.0, 0.03, places=6)
                self.assertAlmostEqual(signals[0].best_ask or 0.0, 0.04, places=6)
            finally:
                simulate_trades.SIGNAL_LOG_PATH = original_signal_path

    def test_simulator_entry_price_uses_best_bid_and_ask(self) -> None:
        buy_signal = simulate_trades.SignalRow(
            signal_id="sig-1",
            scan_id="scan-1",
            timestamp=datetime.now(timezone.utc),
            event_id="event-1",
            event_title="Example",
            platform="kalshi",
            market_id="kalshi:POWER-28-DH-DS-RP:YES",
            side="BUY",
            market_price=0.04,
            consensus_probability=0.10,
            expected_value=0.02,
            signal_strength=0.5,
            liquidity=1000.0,
            suggested_bankroll_percent=0.02,
            suggested_amount=10.0,
            best_bid=0.03,
            best_ask=0.05,
            spread=0.02,
            spread_percent=0.5,
        )
        sell_signal = simulate_trades.SignalRow(
            signal_id="sig-2",
            scan_id="scan-1",
            timestamp=datetime.now(timezone.utc),
            event_id="event-1",
            event_title="Example",
            platform="kalshi",
            market_id="kalshi:POWER-28-DH-DS-RP:YES",
            side="SELL",
            market_price=0.04,
            consensus_probability=0.10,
            expected_value=0.02,
            signal_strength=0.5,
            liquidity=1000.0,
            suggested_bankroll_percent=0.02,
            suggested_amount=10.0,
            best_bid=0.03,
            best_ask=0.05,
            spread=0.02,
            spread_percent=0.5,
        )

        self.assertAlmostEqual(simulate_trades._entry_price(buy_signal), 0.05, places=6)
        self.assertAlmostEqual(simulate_trades._entry_price(sell_signal), 0.03, places=6)

    def test_deduplication_suppresses_near_identical_signals(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            temp_path = Path(temp_dir)
            original_signal_path = signal_logger.SIGNAL_LOG_PATH
            original_sqlite_path = signal_logger.SQLITE_PATH
            original_data_dir = signal_logger.DATA_DIR
            try:
                signal_logger.SIGNAL_LOG_PATH = temp_path / "signal_log.csv"
                signal_logger.SQLITE_PATH = temp_path / "trading_data.db"
                signal_logger.DATA_DIR = temp_path

                opportunity = SimpleNamespace(
                    event_id="event-1",
                    event="Example Event",
                    opportunity_type="positive_ev",
                    consensus_probability=0.61,
                    expected_value=0.08,
                    confidence=0.72,
                    liquidity=1500.0,
                    recommended_bankroll_fraction=0.024,
                    recommended_position_size=24.0,
                    market="kalshi:POWER-28-DH-DS-RP:YES",
                    legs=[
                        SimpleNamespace(
                            platform="kalshi",
                            market_id="kalshi:POWER-28-DH-DS-RP:YES",
                            outcome="YES",
                            price=0.04,
                            best_bid=0.03,
                            best_ask=0.04,
                            bid_size=150.0,
                            ask_size=120.0,
                            spread=0.01,
                            spread_percent=0.285714,
                            consensus_probability=0.61,
                        )
                    ],
                )
                first = signal_logger._build_signal_row(
                    opportunity,
                    scan_id="scan-1",
                    scan_timestamp=datetime(2026, 3, 14, 18, 2, 10, tzinfo=timezone.utc),
                )
                second = signal_logger._build_signal_row(
                    opportunity,
                    scan_id="scan-2",
                    scan_timestamp=datetime(2026, 3, 14, 18, 3, 10, tzinfo=timezone.utc),
                )

                self.assertTrue(signal_logger._write_signal_row(first))
                self.assertFalse(signal_logger._write_signal_row(second))
            finally:
                signal_logger.SIGNAL_LOG_PATH = original_signal_path
                signal_logger.SQLITE_PATH = original_sqlite_path
                signal_logger.DATA_DIR = original_data_dir

    def test_collection_stats_reads_sqlite_scan_batches(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            temp_path = Path(temp_dir)
            original_sqlite_path = collection_stats.SQLITE_PATH
            original_signal_path = collection_stats.SIGNAL_LOG_PATH
            original_price_path = collection_stats.PRICE_LOG_PATH
            try:
                collection_stats.SQLITE_PATH = temp_path / "trading_data.db"
                collection_stats.SIGNAL_LOG_PATH = temp_path / "signal_log.csv"
                collection_stats.PRICE_LOG_PATH = temp_path / "price_history.csv"
                with sqlite3.connect(collection_stats.SQLITE_PATH) as connection:
                    connection.execute(
                        """
                        CREATE TABLE signals(
                            signal_id TEXT,
                            scan_id TEXT,
                            scan_timestamp TEXT,
                            timestamp TEXT,
                            signal_family TEXT,
                            opportunity_type TEXT,
                            event_id TEXT,
                            event_title TEXT,
                            platform TEXT,
                            market_id TEXT,
                            side TEXT,
                            market_price REAL,
                            consensus_probability REAL,
                            expected_value REAL,
                            signal_strength REAL,
                            liquidity REAL,
                            suggested_bankroll_percent REAL,
                            suggested_amount REAL,
                            best_bid REAL,
                            best_ask REAL,
                            bid_size REAL,
                            ask_size REAL,
                            spread REAL,
                            spread_percent REAL
                        )
                        """
                    )
                    connection.execute(
                        """
                        CREATE TABLE price_history(
                            scan_id TEXT,
                            scan_timestamp TEXT,
                            timestamp TEXT,
                            platform TEXT,
                            market_id TEXT,
                            event_id TEXT,
                            price REAL,
                            liquidity REAL
                        )
                        """
                    )
                    connection.execute(
                        """
                        CREATE TABLE scan_batches(
                            scan_id TEXT PRIMARY KEY,
                            scan_timestamp TEXT,
                            started_at TEXT,
                            finished_at TEXT,
                            status TEXT,
                            limit_value INTEGER,
                            min_liquidity REAL,
                            min_ev REAL,
                            bankroll_amount REAL,
                            market_count INTEGER,
                            price_snapshot_count INTEGER,
                            detected_opportunity_count INTEGER,
                            emitted_signal_count INTEGER,
                            duration_seconds REAL,
                            error_message TEXT
                        )
                        """
                    )
                    connection.execute(
                        """
                        CREATE TABLE simulated_trades(
                            run_id TEXT,
                            run_timestamp TEXT,
                            signal_id TEXT,
                            scan_id TEXT,
                            entered_at TEXT,
                            exited_at TEXT,
                            market_id TEXT,
                            side TEXT,
                            stake REAL,
                            entry_price REAL,
                            exit_price REAL,
                            expected_value REAL,
                            pnl REAL,
                            holding_hours REAL,
                            spread_percent REAL,
                            liquidity_at_entry REAL
                        )
                        """
                    )
                    connection.execute(
                        """
                        INSERT INTO signals VALUES(
                            'sig-1','scan-1','2026-03-14T18:02:10Z','2026-03-14T18:02:10Z',
                            'event-1|polymarket:561255:YES|positive_ev','positive_ev','event-1','Example Event',
                            'polymarket','polymarket:561255:YES','YES',0.12,0.2,0.05,0.7,1000,0.02,20,0.11,0.12,10,10,0.01,0.08
                        )
                        """
                    )
                    connection.execute(
                        """
                        INSERT INTO price_history VALUES(
                            'scan-1','2026-03-14T18:02:10Z','2026-03-14T18:02:10Z',
                            'polymarket','polymarket:561255:YES','event-1',0.12,1000
                        )
                        """
                    )
                    connection.execute(
                        """
                        INSERT INTO scan_batches VALUES(
                            'scan-1','2026-03-14T18:02:10Z','2026-03-14T18:02:10Z','2026-03-14T18:02:12Z',
                            'completed',300,0,0.01,1000,20,40,1,1,2.0,''
                        )
                        """
                    )
                    connection.execute(
                        """
                        INSERT INTO simulated_trades VALUES(
                            'run-1','2026-03-14T19:00:00Z','sig-1','scan-1','2026-03-14T18:02:10Z',
                            '2026-03-14T19:00:00Z','polymarket:561255:YES','YES',20,0.12,0.16,0.05,0.8,1.0,0.08,1000
                        )
                        """
                    )
                    connection.commit()

                stats = collection_stats.load_collection_stats()

                self.assertEqual(stats["total_scan_batches"], 1)
                self.assertEqual(stats["unique_markets_scanned"], 1)
                self.assertEqual(stats["unique_events_signaled"], 1)
                self.assertEqual(len(stats["recent_scan_activity"]), 1)
                self.assertEqual(stats["recent_scan_activity"][0]["scan_id"], "scan-1")
            finally:
                collection_stats.SQLITE_PATH = original_sqlite_path
                collection_stats.SIGNAL_LOG_PATH = original_signal_path
                collection_stats.PRICE_LOG_PATH = original_price_path


if __name__ == "__main__":
    unittest.main()

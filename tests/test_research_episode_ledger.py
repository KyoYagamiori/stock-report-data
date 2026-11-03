from copy import deepcopy
from datetime import datetime
import unittest

from research_system.ledger import normalize_signal, upsert, evaluate_episode, summarize

NOW = datetime.fromisoformat("2026-11-10T16:00:00+08:00")
CALENDAR = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10", "2026-11-11"]


def signal(**updates):
    row = {"code": "600000", "roles": ["technical"], "method_version": "fixture_v2", "strategy": "trend_pullback",
           "first_issued_at": "2026-11-02T21:00:00+08:00", "valid_until": "2026-11-11T15:00:00+08:00",
           "entry_rule": "next_daily_open", "invalidation_price": 9}
    row.update(updates)
    return normalize_signal(row, "2026-11-02T21:01:00+08:00", {"file": "fixture", "sha256": "a" * 64}, NOW)


def tape():
    return {day: {"600000": {"open": 10, "high": 12, "low": 9.5, "close": 11,
                            "previous_close": 10, "volume": 1000, "basis_change": False}} for day in CALENDAR}


class EpisodeTests(unittest.TestCase):
    def test_repeated_reports_merge_roles_without_resetting_window_or_count(self):
        episodes, ep = {}, signal()
        self.assertTrue(upsert(episodes, ep))
        again = signal(roles=["comprehensive"])
        self.assertFalse(upsert(episodes, again))
        self.assertEqual(1, len(episodes))
        self.assertEqual(["comprehensive", "technical"], episodes[ep["signal_id"]]["roles"])
        self.assertEqual("2026-11-02T21:00:00+08:00", ep["first_issued_at"])

    def test_mutating_invalidation_under_same_episode_is_rejected(self):
        ep = signal()
        changed = deepcopy(ep)
        changed["invalidation_price"] = 8
        with self.assertRaisesRegex(ValueError, "reset_original"):
            upsert({ep["signal_id"]: ep}, changed)

    def test_late_publication_cannot_buy_at_an_earlier_open(self):
        ep = signal()
        ep["available_at"] = "2026-11-03T12:40:00+08:00"
        evaluate_episode(ep, tape(), CALENDAR, NOW)
        self.assertEqual("2026-11-04", ep["entry"]["date"])
        self.assertEqual("2026-11-09", ep["outcomes"]["t_plus_3"]["exit_date"])

    def test_t_plus_3_counts_sessions_not_calendar_days_and_costs_once(self):
        ep = signal()
        evaluate_episode(ep, tape(), CALENDAR, NOW, 20)
        result = ep["outcomes"]["t_plus_3"]
        self.assertEqual("2026-11-03", ep["entry"]["date"])
        self.assertEqual("2026-11-06", result["exit_date"])
        self.assertAlmostEqual(9.8, result["net_return_pct"])
        self.assertAlmostEqual(-5, result["mae_pct"])

    def test_unmatured_future_label_is_not_counted(self):
        ep = signal()
        evaluate_episode(ep, tape(), CALENDAR, datetime.fromisoformat("2026-11-04T14:00:00+08:00"))
        self.assertEqual({}, ep["outcomes"])

    def test_missing_or_corporate_action_bar_never_becomes_a_return(self):
        for kind in ("missing", "basis"):
            ep, data = signal(), tape()
            if kind == "missing": del data["2026-11-05"]
            else: data["2026-11-05"]["600000"]["basis_change"] = True
            evaluate_episode(ep, data, CALENDAR, NOW)
            self.assertNotIn("t_plus_3", ep["outcomes"])
            self.assertIn("t_plus_3", ep["outcome_gaps"])

    def test_limit_up_and_already_invalid_entries_are_not_filled(self):
        for price, expected in ((11, "unfilled_entry"), (8, "invalid_before_entry")):
            ep, data = signal(), tape()
            data["2026-11-03"]["600000"]["open"] = price
            evaluate_episode(ep, data, CALENDAR, NOW)
            self.assertEqual(expected, ep["state"])
            self.assertNotIn("entry", ep)

    def test_observation_cards_do_not_inflate_win_rate(self):
        ep = signal(entry_rule="observation_only")
        evaluate_episode(ep, tape(), CALENDAR, NOW)
        stats = summarize({ep["signal_id"]: ep})["role_results"]["technical"]
        self.assertEqual(0, stats["t_plus_3_matured"])
        self.assertIsNone(stats["positive_return_fraction"])
        self.assertEqual(1, stats["observation_only_excluded_from_returns"])

    def test_intraday_trigger_without_execution_evidence_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "intraday_trigger"):
            signal(entry_rule="intraday_cross_above")

    def test_naive_future_or_boolean_prices_are_rejected(self):
        for changes in ({"first_issued_at": "2026-11-02T21:00:00"}, {"invalidation_price": True},
                        {"first_issued_at": "2027-01-01T21:00:00+08:00"}):
            with self.assertRaises(ValueError): signal(**changes)


if __name__ == "__main__":
    unittest.main()

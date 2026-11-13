from copy import deepcopy
from datetime import date, timedelta
import unittest

from market_screen.vcp import analyze, feature_values, observe, prepare, swings
from market_screen.early import build
from market_screen.early_runtime import update_observations


def vcp_bars():
    anchors = [(0, 70), (40, 95), (50, 110), (60, 90), (70, 112), (80, 105),
               (90, 113), (97, 109), (102, 112.5), (103, 112.8)]
    rows = []
    for i in range(104):
        a, z = next((a, z) for a, z in zip(anchors, anchors[1:]) if a[0] <= i <= z[0])
        price = a[1] + (z[1] - a[1]) * (i - a[0]) / (z[0] - a[0])
        rows.append({"day": (date(2020, 1, 1) + timedelta(days=i)).isoformat(),
                     "open": price, "close": price, "high": price+.2, "low": price-.2,
                     "volume": 300 if i >= 98 else 1000})
    return rows


class VCPShadowTests(unittest.TestCase):
    def test_missing_completed_session_reports_the_date_instead_of_empty_reason(self):
        from market_screen.completed_source import load_completed_records
        from tests.test_boll_early import NOW
        from pathlib import Path
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "output/boll/latest/manifest.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"latest_screen": {"market_date": "2026-10-13"}}))
            records, source, _ = load_completed_records(root, "2026-10-14", NOW)
            self.assertFalse(records)
            self.assertFalse(source["accepted"])
            self.assertEqual(["completed_store_missing_for_market_date:2026-10-14"], source["reasons"])

    def test_shadow_watchlist_neither_reorders_boll_nor_requires_boll_setup(self):
        from tests.test_boll_early import record, quote, DATES, NOW, CONFIG
        original = build([record()], DATES, NOW, CONFIG, {"600000": quote()})
        r = record()
        r["indicators"]["early_state"]["vcp_next_session"] = {**prepare(vcp_bars()[:-1]),
            "base_asof": DATES["market_date"], "pivot": 10.1, "invalidation_below": 9.8, "atr20": 1., "origin": "2026-10-10"}
        enriched = build([r], DATES, NOW, CONFIG, {"600000": quote()})
        self.assertEqual([x["code"] for x in original["shortlist"]], [x["code"] for x in enriched["shortlist"]])
        self.assertEqual("600000", enriched["vcp_shadow"]["watchlist"][0]["code"])
        # A VCP observation survives when the four early BOLL pools are empty.
        from unittest.mock import patch
        with patch("market_screen.early.classify", return_value=([], "no_early_setup", .1)):
            independent = build([r], DATES, NOW, CONFIG, {"600000": quote()})
        self.assertFalse(independent["shortlist"])
        self.assertEqual(1, independent["vcp_shadow"]["eligible_count"])

    def test_original_vcp_pivot_and_expiry_cannot_reset_on_later_reports(self):
        from tests.test_boll_early import record, quote, DATES, NOW, CONFIG
        data = build([record()], DATES, NOW, CONFIG, {"600000": quote()})
        observation = {**analyze(vcp_bars()), "origin": "2026-10-10"}
        row = {"code": "600000", "vcp_shadow": observation}
        data["vcp_shadow"]["watchlist"] = [row]
        calendar = ["2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21"]
        state = update_observations(data, {}, calendar, NOW)
        first = deepcopy(next(iter(state["vcp_episodes"].values())))
        row["vcp_shadow"]["pivot"] += 2
        update_observations(data, state, calendar, NOW + timedelta(hours=1))
        second = next(iter(state["vcp_episodes"].values()))
        self.assertEqual(first["original_pivot"], second["original_pivot"])
        self.assertEqual(first["valid_until"], second["valid_until"])
        update_observations(data, state, calendar, NOW + timedelta(days=8))
        self.assertFalse(data["vcp_shadow"]["watchlist"])

    def test_confirmed_swings_contract_with_rising_lows_and_dry_volume(self):
        rows = vcp_bars()
        result = analyze(rows)
        self.assertTrue(result["matched"], result)
        self.assertGreaterEqual(result["contraction_count"], 2)
        self.assertEqual("near_pivot", result["stage"])
        self.assertAlmostEqual(113.2, result["pivot"])
        for point in swings(rows[:-1]):
            self.assertGreater(point["known_on"], point["day"])
            self.assertLessEqual(point["known_on"], rows[-2]["day"])
        self.assertFalse(result["entry_qualified"])

    def test_current_session_cannot_rewrite_preexisting_pivot_or_contractions(self):
        rows = vcp_bars()
        old = analyze(rows)
        rows[-1].update(high=500., low=1.)
        new = analyze(rows)
        for key in ("pivot", "origin", "contraction_depths_pct", "confirmed_swings"):
            self.assertEqual(old[key], new[key])

    def test_intraday_volume_is_not_compared_with_full_day_or_called_confirmed(self):
        rows = vcp_bars()
        state = prepare(rows[:-1])
        current = {**rows[-1], "close": state["pivot"]+.1, "volume": 999999}
        intraday = observe(state, current, completed=False)
        self.assertEqual("breakout_provisional", intraday["stage"])
        self.assertIsNone(intraday["completed_volume_ratio"])
        self.assertEqual("not_supplied", intraday["same_time_volume_confirmation"])
        daily = observe(state, current, completed=True)
        self.assertEqual("breakout_close_volume_confirmed", daily["stage"])

    def test_extension_and_failed_base_are_separate_from_a_new_entry(self):
        rows = vcp_bars()
        state = prepare(rows[:-1])
        high = observe(state, {**rows[-1], "close": state["pivot"] + 2*state["atr20"]})
        self.assertEqual("extended_do_not_chase", high["stage"])
        low = observe(state, {**rows[-1], "close": state["invalidation_below"]-.1})
        self.assertEqual("invalidated", low["stage"])

    def test_price_squeeze_without_volume_dry_up_is_not_vcp_match(self):
        rows = vcp_bars()
        for row in rows[-6:]:
            row["volume"] = 2000
        result = analyze(rows)
        self.assertFalse(result["matched"])
        self.assertFalse(result["checks"]["volume_dry"])

    def test_short_history_missing_fields_and_temporal_order(self):
        result = analyze(vcp_bars()[:30])
        self.assertFalse(result["available"])
        self.assertEqual(0, feature_values(result)["vcp_evaluable"])
        rows = vcp_bars()
        with self.assertRaises(ValueError): prepare(list(reversed(rows)))
        with self.assertRaises(ValueError): observe(prepare(rows), rows[-1])

if __name__ == "__main__":
    unittest.main()

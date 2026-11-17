from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import unittest

from research_system.vcp_trigger_training import trigger_labels


def fixture():
    config = json.loads((Path(__file__).resolve().parents[1] / "config/vcp_trigger_training.json").read_bytes())
    calendar = [(date(2020, 1, 2) + timedelta(days=i)).isoformat() for i in range(15)]
    raw = {d: {"day": d, "open": 9.8, "close": 9.8, "high": 10.4, "low": 9.5,
        "preclose": 9.8, "volume": 80, "tradestatus": "1", "isST": "unknown", "factor": 1.} for d in calendar}
    state = {"matched": True, "base_asof": "2020-01-01", "origin": "2019-12-20", "pivot": 10.,
        "invalidation_below": 9., "atr20": 1., "reference_volume": 100.}
    return config, calendar, raw, state, {d: {"open": 10., "close": 10.} for d in calendar}


class VcpTriggerTrainingTests(unittest.TestCase):
    def calculate(self, config, calendar, raw, state, benchmark):
        return trigger_labels(calendar[0], state, raw, deepcopy(raw), calendar, benchmark, config)

    def test_waits_for_volume_close_then_next_open_and_t_plus_one_exit(self):
        config, calendar, raw, state, benchmark = fixture()
        raw[calendar[0]]["close"] = 10.2  # High/close alone never establishes volume confirmation.
        raw[calendar[1]].update(close=10.2, volume=180)
        raw[calendar[2]].update(open=10.2, close=10.3, high=10.4)
        targets, audit = self.calculate(config, calendar, raw, state, benchmark)
        self.assertEqual(calendar[1], audit["confirmation_date"])
        self.assertEqual(calendar[2], audit["entry_date"])
        self.assertEqual(calendar[3], audit["execution"]["scheduled_exit_dates"][1])
        self.assertEqual(calendar[7], audit["execution"]["scheduled_exit_dates"][5])
        self.assertTrue(all(h in targets for h in (1, 3, 5)))
        self.assertFalse(audit["actual_trade"])

    def test_expired_window_cannot_be_reset_by_later_confirmation(self):
        config, calendar, raw, state, benchmark = fixture()
        raw[calendar[3]].update(close=10.2, volume=200)
        targets, audit = self.calculate(config, calendar, raw, state, benchmark)
        self.assertEqual("expired_without_confirmation", audit["state"])
        self.assertEqual(calendar[2], audit["label_end_date"])
        self.assertEqual({1: 0., 3: 0., 5: 0.}, targets)
        self.assertNotIn("entry_date", audit)

    def test_first_invalidation_or_extension_stops_waiting(self):
        for close, expected in ((8.9, "invalidated_before_entry"), (10.6, "extended_before_entry")):
            config, calendar, raw, state, benchmark = fixture()
            raw[calendar[0]]["close"] = close
            raw[calendar[1]].update(close=10.2, volume=200)
            targets, audit = self.calculate(config, calendar, raw, state, benchmark)
            self.assertEqual(expected, audit["state"])
            self.assertEqual(0., targets[3])
            self.assertNotIn("entry_date", audit)

    def test_confirmation_does_not_authorize_chasing_a_next_open_gap(self):
        for opened, expected in ((10.6, "entry_gap_extended_skip"), (9.7, "entry_gap_failed_skip")):
            config, calendar, raw, state, benchmark = fixture()
            raw[calendar[0]].update(close=10.2, volume=200)
            raw[calendar[1]].update(open=opened, high=11., low=9.)
            target, audit = self.calculate(config, calendar, raw, state, benchmark)
            self.assertEqual(expected, audit["state"])
            self.assertEqual(0., target[3])

    def test_missing_observation_or_entry_is_unresolved_not_zero(self):
        config, calendar, raw, state, benchmark = fixture()
        del raw[calendar[1]]
        target, audit = self.calculate(config, calendar, raw, state, benchmark)
        self.assertIsNone(target)
        self.assertEqual("unresolved_observation_data", audit["state"])
        raw[calendar[0]].update(close=10.2, volume=200)
        target, audit = self.calculate(config, calendar, raw, state, benchmark)
        self.assertIsNone(target)
        self.assertEqual("unresolved_entry_data", audit["state"])

    def test_missing_exit_is_retained_as_censored(self):
        config, calendar, raw, state, benchmark = fixture()
        raw[calendar[0]].update(close=10.2, volume=200)
        raw[calendar[1]].update(open=10.2)
        del raw[calendar[4]]
        target, audit = self.calculate(config, calendar, raw, state, benchmark)
        self.assertIsNone(target)
        self.assertEqual("censored_exit", audit["state"])

    def test_only_prior_frozen_structure_can_be_used(self):
        config, calendar, raw, state, benchmark = fixture()
        state["base_asof"] = calendar[0]
        with self.assertRaisesRegex(ValueError, "known_frozen_prior_session"):
            self.calculate(config, calendar, raw, state, benchmark)


if __name__ == "__main__":
    unittest.main()

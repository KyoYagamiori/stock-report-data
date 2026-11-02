from datetime import datetime
import unittest

from report_support.delivery import assess_delivery
from tests.test_report_index import report


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.fromisoformat("2026-11-02T13:10:00+08:00")
        self.last = {"id": "noon-run", "recorded_status": "no_update", "scheduled_for": "2026-11-02T04:40:00Z"}
        self.old_result = {"run_id": "early-run", "scheduled_for": "2026-11-02T01:00:00Z",
                           "content_text": report(label="早报"), "chat_ref": {"id": "main", "type": "chatgpt"}}

    def check(self, last=None, result=None, **kwargs):
        return assess_delivery({"run_details": {"last_run": last or self.last, "latest_result": result or self.old_result}},
                               "2026-11-02", "noon", moment=kwargs.get("moment", self.now))

    def test_november2_no_update_does_not_mistake_early_report_for_noon(self):
        self.assertEqual("recover_same_cycle", self.check()["action"])

    def test_matching_complete_chat_result_is_not_resent(self):
        result = {**self.old_result, "run_id": "noon-run", "scheduled_for": self.last["scheduled_for"], "content_text": report()}
        out = self.check(last={**self.last, "recorded_status": "completed"}, result=result)
        self.assertEqual("recorded_result_present", out["action"])
        self.assertEqual("unknown", out["device_delivery"])

    def test_in_progress_does_not_start_concurrent_duplicate(self):
        self.assertEqual("wait_for_active_run", self.check(last={**self.last, "recorded_status": "in_progress"})["action"])

    def test_summary_failure_or_missing_chat_result_requires_recovery(self):
        for changes in ({"content_text": "Archive uploaded."}, {"is_failure_message": True}, {"chat_ref": None}):
            result = {**self.old_result, "scheduled_for": self.last["scheduled_for"], "content_text": report(), **changes}
            self.assertEqual("recover_same_cycle", self.check(result=result)["action"])

    def test_tool_truncation_is_not_treated_as_delivery_failure(self):
        result = {**self.old_result, "scheduled_for": self.last["scheduled_for"], "content_text": report()[:120], "content_truncated": True}
        self.assertEqual("recorded_result_present", self.check(result=result)["action"])

    def test_truncated_wrong_cycle_title_cannot_count_as_noon_delivery(self):
        result = {**self.old_result, "scheduled_for": self.last["scheduled_for"], "content_truncated": True}
        self.assertEqual("recover_same_cycle", self.check(result=result)["action"])

    def test_future_and_prior_day_are_not_backfilled(self):
        self.assertEqual("not_due", self.check(moment=self.now.replace(hour=12))["action"])
        self.assertEqual("do_not_backfill", self.check(moment=self.now.replace(day=3))["action"])

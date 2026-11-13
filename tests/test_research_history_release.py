from copy import deepcopy
from datetime import date,datetime,timedelta
import json
from pathlib import Path
import tempfile
import unittest

from research_system.history_release import check_forward,check_performance,load_evidence
from research_system.history_source import TZ,canonical,digest,write


POLICY={"minimum_net_excess_pct":0,"minimum_improvement_interval_lower_pct":0,
        "required_round_trip_cost_bps":[20,40],"minimum_rolling_positive_improvement_fraction":.6,
        "minimum_forward_sessions":60,"minimum_matured_signals":100,"minimum_matured_signal_dates":30,
        "operational_forward_sessions":20}


def forward(n=60):
    rows=[]
    for i in range(n):
        day=date(2020,1,2)+timedelta(days=i)
        rows.append({"date":day.isoformat(),"prediction_registered_at":day.isoformat()+"T16:00:00+08:00",
                     "features_known_at":day.isoformat()+"T15:30:00+08:00",
                     "entry_at":(day+timedelta(days=1)).isoformat()+"T09:30:00+08:00",
                     "outcome_known_at":(day+timedelta(days=5)).isoformat()+"T16:00:00+08:00",
                     "matured_signals":2,"net_excess_pct":1.,"baseline_net_excess_pct":0.})
    return {"model_frozen_at":"2020-01-01T16:00:00+08:00","daily_results":rows,
            "previously_inspected_dates_used":False,"unresolved_exit_count":0}


class ReleaseGateTests(unittest.TestCase):
    def test_twenty_sessions_can_pass_operations_but_not_model_evidence(self):
        out=check_forward(forward(20),POLICY,datetime(2026,1,1,tzinfo=TZ))
        self.assertTrue(out["operations_20_sessions_met"])
        self.assertEqual("failed",out["state"])

    def test_frozen_registered_predictions_and_sufficient_maturity_are_required(self):
        data=forward()
        self.assertEqual("passed",check_forward(data,POLICY,datetime(2026,1,1,tzinfo=TZ))["state"])
        data["previously_inspected_dates_used"]=True
        self.assertEqual("failed",check_forward(data,POLICY,datetime(2026,1,1,tzinfo=TZ))["state"])
        data=forward()
        data["daily_results"][0]["prediction_registered_at"]=data["daily_results"][0]["outcome_known_at"]
        with self.assertRaises(ValueError):check_forward(data,POLICY,datetime(2026,1,1,tzinfo=TZ))

    def test_prediction_after_entry_or_duplicate_day_cannot_qualify(self):
        data=forward()
        data["daily_results"][0]["prediction_registered_at"]=data["daily_results"][0]["entry_at"]
        with self.assertRaises(ValueError):check_forward(data,POLICY,datetime(2026,1,1,tzinfo=TZ))
        data=forward()
        data["daily_results"].append(data["daily_results"][-1])
        with self.assertRaises(ValueError):check_forward(data,POLICY,datetime(2026,1,1,tzinfo=TZ))

    def test_positive_average_is_insufficient_when_stressed_costs_fail(self):
        result={"selected_model":"ridge","development_comparison":{"ridge":{"diagnostics":{
            "round_trip_cost_bps_sensitivity":{"20":{"date_balanced_mean_net_excess_pct":.05},"40":{"date_balanced_mean_net_excess_pct":-.15}}}}},
            "out_of_fold_daily_results":{"ridge":[{"net_excess_pct":.05,"paired_improvement_pct":.05} for _ in range(30)]},
            "rolling_folds":[{"models":{"ridge":{"paired_early_rule_improvement_pct":.05}}} for _ in range(6)]}
        out=check_performance(result,POLICY)
        self.assertEqual("failed",out["state"])
        self.assertFalse(out["checks"]["positive_at_all_required_costs"])

    def test_evidence_flags_without_bound_sources_and_other_model_evidence_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            path=root/"output/research/release_evidence/review.json"
            data={"candidate_sha256":"a"*64,"passed":True}
            write(path,data)
            ref={"file":path.relative_to(root).as_posix(),"sha256":digest(path.read_bytes())}
            with self.assertRaisesRegex(ValueError,"no_source"):load_evidence(root,{"test":ref},"test","a"*64)
            with self.assertRaisesRegex(ValueError,"another_model"):load_evidence(root,{"test":ref},"test","b"*64)
            path.write_bytes(path.read_bytes()+b"tampered")
            with self.assertRaisesRegex(ValueError,"hash_invalid"):load_evidence(root,{"test":ref},"test","a"*64)


if __name__=="__main__":unittest.main()

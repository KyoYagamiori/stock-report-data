"""Expand the fixed historical VCP cohort without changing its trigger contract."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from functools import partial
import gzip
import json
from pathlib import Path
import statistics
from tempfile import TemporaryDirectory

from market_screen import vcp
from .daily_model import immutable
from .daily_model_data import checked
from .history_dataset import causal_adjust, normalize, points_for
from .history_qlib import FIELDS, QlibRelease
from .history_source import TZ, canonical, digest, select_cohort, write
from .vcp_training import FEATURES, STAGES, context, features_for, temporal_split, train
from .vcp_trigger_training import trigger_labels

BASELINE = "output/history_pilot/vcp_triggered"
OUTPUT = "output/history_pilot/vcp_triggered_cohort"
LATEST = "output/research/latest/vcp_cohort_training_status.json"


def additional_codes(members, baseline, seed, blocks):
    if len(baseline) != 512 or select_cohort(members, 512, seed) != baseline:
        raise ValueError("expanded_vcp_original_membership_mismatch")
    selected = []
    remaining = {row["code"]: row for row in members}
    for code in baseline:
        del remaining[code]
    for _ in range(blocks):
        block = select_cohort(remaining.values(), 512, seed)
        selected.extend(block)
        for code in block:
            del remaining[code]
    return selected


def source_metadata(release, source, calendar):
    config = source["config"]
    origin, first, last = config["cohort_date"], calendar[0], calendar[-1]
    actual = [day for day in release.calendar if first <= day <= last]
    if actual != calendar or origin not in actual:
        raise ValueError("expanded_vcp_release_calendar_mismatch")
    selected = release.cohort_selector(release.query({"method": "query_all_stock", "kwargs": {"day": origin}}))
    wanted = {code.replace(".", "").upper(): code for code in selected}
    intervals = dict()
    for symbol, start, end in release.intervals:
        if symbol in wanted and start <= origin <= end:
            code = wanted[symbol]
            if code in intervals:
                raise ValueError("expanded_vcp_ambiguous_listing_interval:" + code)
            intervals[code] = (start, end)
    if set(intervals) != set(selected):
        raise ValueError("expanded_vcp_missing_listing_interval")
    return selected, intervals


def stock_samples(code, source_rows, source_sha, listing, cohort_day, calendar, benchmark, contract):
    last = contract["exclude_reviewed_from"]
    raw = normalize([row for row in source_rows if listing[0] <= row["date"] <= listing[1]
                     and row["date"] < last], allow_unknown_status=True)
    if not raw or any(row["code"] != code or row["day"] not in calendar for row in raw):
        raise ValueError("expanded_vcp_stock_identity_or_calendar:" + code)
    adjusted = causal_adjust(raw)
    points = points_for(adjusted)
    raw_map = {row["day"]: row for row in raw}
    adjusted_map = {row["day"]: row for row in adjusted}
    indices = {row["day"]: i for i, row in enumerate(raw)}
    counts, seen, rows, audits = Counter(), set(), [], []
    for i in range(159, len(raw)):
        bar = raw[i]
        day = bar["day"]
        if (day < cohort_day or bar["tradestatus"] != "1" or bar["isST"] not in {"0", "unknown"}
                or bar["volume"] <= 0 or bar["high"] == bar["low"]):
            counts["ineligible_bar"] += 1
            continue
        counts["evaluated_stock_days"] += 1
        observation = vcp.analyze(adjusted[i - 120:i + 1])
        if not observation.get("matched") or observation["stage"] not in STAGES:
            continue
        if statistics.median(row["amount"] for row in raw[i - 19:i + 1]) < contract["minimum_turnover_cny"]:
            counts["low_liquidity_proxy"] += 1
            continue
        origin = observation["origin"]
        if origin in seen:
            counts["repeated_origin_suppressed"] += 1
            continue
        seen.add(origin)
        features = features_for(points[i], observation, i - indices[origin])
        values, audit = trigger_labels(day, observation, raw_map, adjusted_map, calendar, benchmark, contract)
        audit.update(code=code, origin=origin, source_sha256=source_sha)
        audit_hash = digest(canonical(audit))
        audits.append({"sha256": audit_hash, "evidence": audit})
        if values is None:
            continue
        if not day <= audit["label_end_date"] < last:
            raise ValueError("expanded_vcp_sealed_label_leakage")
        rows.append({"date": day, "code": code.split(".")[1], "origin": origin,
                     "stage": observation["stage"], "features": features,
                     "targets_provider_benchmark_net_proxy_pct": {str(h): values[h] for h in contract["horizons_sessions"]},
                     "label_end_date": audit["label_end_date"], "execution_state": audit["state"],
                     "execution_audit_sha256": audit_hash, "source_sha256": source_sha})
    return rows, audits, {"pre_cutoff_bars": len(raw), **counts}


def scan_stock(release, source_config, intervals, calendar, benchmark, contract, code):
    listing = intervals[code]
    source_rows = release.query({"method": "query_history_k_data_plus", "kwargs": {
        "code": code, "start_date": source_config["history_start"], "end_date": calendar[-1],
        "adjustflag": "3", "frequency": "d"}})
    symbol = code.replace(".", "")
    fields = {field: digest(release.binary[(symbol, field)]) for field in FIELDS}
    source_sha = digest(canonical(source_rows))
    rows, audits, counts = stock_samples(code, source_rows, source_sha, listing, source_config["cohort_date"],
                                         calendar, benchmark, contract)
    return code, rows, audits, {"listing_interval": listing, "members_sha256": fields,
                                "normalized_rows_sha256": source_sha, "source_rows": len(source_rows),
                                **counts}


_scan_stock = None


def init_worker(*args):
    global _scan_stock
    _scan_stock = partial(scan_stock, *args)


def scan_code(code):
    return _scan_stock(code)


def summarize_coverage(rows, audits, code_count):
    return {"codes": code_count, "unique_origins": len(audits), "resolved_rows": len(rows),
            "unresolved_origins": len(audits) - len(rows),
            "states": dict(Counter(audit["evidence"]["state"] for audit in audits)),
            "stages": dict(Counter(row["stage"] for row in rows))}


def load_json(root, ref, prefix=BASELINE):
    raw = checked(root, ref, prefix)
    return json.loads(gzip.decompress(raw) if ref["file"].endswith(".gz") else raw)


def frozen_gzip(root, path, payload):
    raw = gzip.compress(canonical(payload), mtime=0)
    if path.exists() and path.read_bytes() != raw:
        raise ValueError("expanded_vcp_frozen_evidence_cannot_be_replaced")
    path.write_bytes(raw)
    return {"file": path.relative_to(root).as_posix(), "sha256": digest(raw)}


def run(root, archive, workers):
    import lightgbm
    import numpy

    root = Path(root).resolve()
    config = json.loads((root / "config/vcp_cohort_training.json").read_bytes())
    original = load_json(root, config["baseline_status"])
    registration = load_json(root, config["baseline_registration"])
    contract = registration["config"]
    if (contract["version"] != original["version"] or contract["source_manifest"] != original["source_manifest"]
            or registration["independent_final_test"] or original["automatic_activation"]
            or config["additional_512_code_blocks"] != 2 or contract["exclude_reviewed_from"] != "2026-01-20"):
        raise ValueError("expanded_vcp_requires_frozen_research_contract")
    paths = ("research_system/vcp_cohort_training.py", "research_system/history_qlib.py",
             "research_system/history_source.py", *registration["code_sha256"])
    hashes = {path: digest((root / path).read_bytes()) for path in paths}
    if any(hashes[path] != sha for path, sha in registration["code_sha256"].items()):
        raise ValueError("expanded_vcp_trigger_implementation_changed")
    identity = {"config": config, "trigger_contract": contract, "code_sha256": hashes,
                "runtime": {"numpy": numpy.__version__, "lightgbm": lightgbm.__version__},
                "independent_final_test": False}
    directory = root / OUTPUT / digest(canonical(identity))[:24]
    status_path = directory / "status.json"
    if status_path.exists():
        status = json.loads(status_path.read_bytes())
        for key in ("added_dataset", "added_audits", "source_receipt", "models", "result"):
            checked(root, status[key], OUTPUT)
        write(root / LATEST, status)
        return status
    immutable(root, directory / "registration.json", identity)

    ref = contract["source_manifest"]
    source, calendar, benchmark = context(str(root), ref["file"], ref["sha256"], contract["exclude_reviewed_from"])
    source_config = source["config"]
    original_rows = load_json(root, original["dataset"])["rows"]
    original_audits = load_json(root, original["audits"])
    selector = partial(additional_codes, baseline=source["selected_codes"], seed=source_config["seed"],
                       blocks=config["additional_512_code_blocks"])
    added_rows, added_audits, receipts = [], [], {}
    with TemporaryDirectory(prefix="vcp-cohort-source-") as scratch:
        with QlibRelease(scratch, source_config, archive=archive, cohort_selector=selector) as release:
            codes, intervals = source_metadata(release, source, calendar)
            receipt = json.loads((Path(scratch) / release.provenance["extraction_receipt_file"]).read_bytes())
            with ProcessPoolExecutor(max_workers=workers, initializer=init_worker,
                                     initargs=(release, source_config, intervals, calendar, benchmark, contract)) as executor:
                for code, rows, audits, stock_receipt in executor.map(scan_code, codes, chunksize=4):
                    added_rows.extend(rows)
                    added_audits.extend(audits)
                    receipts[code] = stock_receipt
                    if len(receipts) % 128 == 0:
                        print({"additional_codes_built": len(receipts), "additional_origins": len(added_audits)}, flush=True)
    added_rows.sort(key=lambda row: (row["date"], row["code"]))
    evidence = summarize_coverage(added_rows, added_audits, len(codes))
    coverage = {"original_cohort": summarize_coverage(original_rows, original_audits, len(source["selected_codes"])),
                "additional_cohort": evidence, "combined_codes": len(source["selected_codes"]) + len(codes),
                "combined_origins": len(original_audits) + len(added_audits),
                "combined_resolved_rows": len(original_rows) + len(added_rows),
                "combined_entry_price_proxies": sum(r["execution_state"] == "filled_daily_proxy"
                                                    for r in original_rows + added_rows)}
    print(coverage, flush=True)
    source_ref = frozen_gzip(root, directory / "added_source_receipt.json.gz", {
        "archive_url": receipt["archive_url"], "archive_sha256": receipt["archive_sha256"],
        "archive_size_bytes": receipt["archive_size_bytes"], "manifest_sha256": receipt["manifest_sha256"],
        "metadata_members": {name: member["sha256"] for name, member in receipt["captured_members"].items()
                             if not name.startswith("features/")},
        "source_history": ref, "cohort_date": source_config["cohort_date"],
        "data_window_end": calendar[-1], "selected_codes": codes, "stocks": receipts,
        "evaluated_stock_days": sum(r.get("evaluated_stock_days", 0) for r in receipts.values()),
        "pre_cutoff_bars": sum(r["pre_cutoff_bars"] for r in receipts.values())})
    dataset_ref = frozen_gzip(root, directory / "added_dataset.json.gz", {
        "rows": added_rows, "feature_names": FEATURES, "source": source_ref, "baseline_dataset": original["dataset"]})
    audits_ref = frozen_gzip(root, directory / "added_audits.json.gz", added_audits)
    all_rows = sorted(original_rows + added_rows, key=lambda row: (row["date"], row["code"]))
    training_calendar = [day for day in calendar if day >= source_config["cohort_date"]]
    training_rows, validation_rows = temporal_split(all_rows, training_calendar, len(training_calendar), contract)
    result = train(all_rows, training_calendar, contract)
    result["entry_price_proxy_rows"] = {
        "training": sum(row["execution_state"] == "filled_daily_proxy" for row in training_rows),
        "validation": sum(row["execution_state"] == "filled_daily_proxy" for row in validation_rows)}
    model_ref = frozen_gzip(root, directory / "models.json.gz", {
        "version": config["version"], "models": result.pop("models"), "feature_names": FEATURES,
        "baseline_dataset": original["dataset"], "added_dataset": dataset_ref,
        "score_meaning": "uncalibrated_ranking_on_price_proxy_labels", "automatic_activation": False})
    result_ref = frozen_gzip(root, directory / "result.json.gz", {
        **result, "coverage": coverage, "models": model_ref, "independent_final_test": False})
    status = {"version": config["version"], "experiment_id": directory.name, "generated_at": datetime.now(TZ).isoformat(),
              "status": "trained_expanded_research_candidate", "baseline": config["baseline_status"],
              "source_receipt": source_ref, "added_dataset": dataset_ref, "added_audits": audits_ref,
              "models": model_ref, "result": result_ref, "coverage": coverage,
              **{key: result[key] for key in ("training_rows", "validation_rows", "training_label_end",
                                            "validation_label_end", "entry_price_proxy_rows", "horizons")},
              "independent_final_test": False, "automatic_activation": False, "automatic_trading": False,
              "limitations": ["reused_historical_period", "fixed_origin_cohort_not_full_market",
                              "price_proxies_missing_independent_official_benchmark_st_actions_and_fills",
                              "causally_adjusted_historical_features_not_live_raw_features"]}
    immutable(root, status_path, status)
    write(root / LATEST, status)
    return status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error("--workers must be between 1 and 8")
    result = run(args.root, args.archive, args.workers)
    print(json.dumps({"status": result["status"], "experiment_id": result["experiment_id"],
                      "coverage": result["coverage"], "entry_price_proxy_rows": result["entry_price_proxy_rows"]},
                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

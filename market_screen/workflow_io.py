"""Small CI checkouts and bounded publication with semantic pointer merges."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path, PurePosixPath
import subprocess


def archive_directory(path):
    """Only data directories, never shell patterns supplied by a manifest."""
    value = PurePosixPath(str(path))
    if value.is_absolute() or ".." in value.parts:
        raise ValueError("unsafe_input_reference")
    allowed = str(value).startswith(("output/boll/archive/", "output/archive/"))
    if not allowed or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/_.-" for c in str(value)):
        raise ValueError("input_reference_outside_archives")
    return "/" + str(value.parent) + "/"


def hydrate_inputs(root, phase="noon"):
    """Download only referenced completed/membership/noon evidence, not all history."""
    from .runner import TZ, resolve_dates
    root = Path(root).resolve()
    now = datetime.now(TZ)
    noon_clock = now.replace(hour=11, minute=40)
    dates = resolve_dates(root, noon_clock if phase in {"noon", "replay"} else now, "noon" if phase in {"noon", "replay"} else "early")
    path = root / "output/boll/latest/manifest.json"
    manifest = json.loads(path.read_text()) if path.exists() else {}
    patterns = set()
    for key in ("latest_screen", "latest_complete_screen"):
        pointer = manifest.get(key, {})
        if pointer.get("market_date") == dates["market_date"]:
            patterns.add(archive_directory(pointer["selected_file"]))
    for key, field, date_key in (("latest_universe", "universe_file", "report_date"),
                                 ("latest_noon_overlay", "selected_file", "market_date")):
        pointer = manifest.get(key, {})
        if pointer.get(date_key) == dates["report_date"]:
            patterns.add(archive_directory(pointer[field]))
    report_manifest = root / "output/latest/manifest.json"
    if report_manifest.exists():
        data = json.loads(report_manifest.read_text())
        for pointer in data.get("snapshots", {}).values():
            if pointer and pointer.get("selected_file"):
                patterns.add(archive_directory(pointer["selected_file"]))
    sparse = subprocess.run(["git", "config", "--bool", "core.sparseCheckout"], cwd=root, text=True, capture_output=True)
    if sparse.stdout.strip() == "true" and patterns:
        subprocess.run(["git", "sparse-checkout", "add", "--stdin"], input="\n".join(sorted(patterns)) + "\n", text=True, cwd=root, check=True)
    return sorted(patterns)


def merge_boll_manifest(remote, incoming):
    merged = deepcopy(remote)
    for key, value in incoming.items():
        if key == "schema_version" or key not in merged:
            merged[key] = deepcopy(value)
            continue
        if key not in {"latest_screen", "latest_complete_screen", "latest_overlay", "latest_noon_overlay", "latest_universe", "last_attempt"}:
            continue
        old = merged[key]
        if key == "latest_complete_screen" and not value.get("technical_screen_complete"):
            continue
        if key == "latest_universe" and not value.get("accepted"):
            continue
        if key == "latest_universe":
            rank = lambda p: (p.get("report_date", ""), p.get("published_at", ""))
        elif key in {"latest_screen", "latest_complete_screen"}:
            rank = lambda p: (p.get("market_date", ""), bool(p.get("technical_screen_complete")), p.get("published_at", ""))
        elif key == "latest_noon_overlay":
            rank = lambda p: (p.get("market_date", ""), bool(p.get("full_market_overlay_complete")), p.get("valid_quotes", 0), p.get("published_at", ""))
        else:
            rank = lambda p: (p.get("published_at", ""), p.get("market_date", ""))
        if rank(value) > rank(old):
            merged[key] = deepcopy(value)
    return merged


def merge_report_manifest(remote, incoming):
    from pipeline.manifest import update_report_readiness
    from pipeline.publisher import should_publish_fixed, should_publish_intraday
    merged = deepcopy(remote)
    def comparable(pointer):
        return {**pointer, "coverage": {"core": {"valid": pointer.get("core_effective_count", 0)}}}
    for kind, pointer in incoming.get("snapshots", {}).items():
        if not pointer:
            continue
        current = merged["snapshots"].get(kind)
        compare = should_publish_intraday if kind == "intraday" else should_publish_fixed
        if current is None or compare(comparable(pointer), comparable(current)):
            merged["snapshots"][kind] = deepcopy(pointer)
    if incoming.get("calendar", {}).get("date", "") > merged.get("calendar", {}).get("date", ""):
        merged["calendar"] = deepcopy(incoming["calendar"])
    merged["generated_at"] = max(merged.get("generated_at", ""), incoming.get("generated_at", ""))
    for key in ("last_grade_a_at", "last_grade_b_at"):
        merged.setdefault("health", {})[key] = max(remote.get("health", {}).get(key) or "", incoming.get("health", {}).get(key) or "") or None
    update_report_readiness(merged)
    return merged


def resolve_conflicts(root, paths):
    root = Path(root)
    def stage(number, path):
        return subprocess.check_output(["git", "show", f":{number}:{path}"], cwd=root)
    # JSON is authoritative; render matching Markdown after resolving it.
    for path in sorted(paths, key=lambda p: p.endswith(".md")):
        target = root / path
        if path == "output/boll/latest/manifest.json":
            merged = merge_boll_manifest(json.loads(stage(2, path)), json.loads(stage(3, path)))
        elif path == "output/latest/manifest.json":
            merged = merge_report_manifest(json.loads(stage(2, path)), json.loads(stage(3, path)))
        elif path == "output/boll/latest/noon_update.json":
            versions = [json.loads(stage(i, path)) for i in (2, 3)]
            merged = max(versions, key=lambda p: (p.get("report_date", ""), bool(p.get("accepted")), p.get("checked_at", "")))
        elif path.startswith("output/latest/") and path.endswith(".json") and "report_data" in path:
            versions = [json.loads(stage(i, path)) for i in (2, 3)]
            if versions[0].get("snapshot_type") == versions[1].get("snapshot_type"):
                from pipeline.publisher import should_publish_fixed, should_publish_intraday
                compare = should_publish_intraday if versions[0]["snapshot_type"] == "intraday" else should_publish_fixed
                merged = versions[1] if compare(versions[1], versions[0]) else versions[0]
            else:
                merged = max(versions, key=lambda p: p.get("published_at", ""))
        elif path.startswith("output/health/latest_run") and path.endswith(".json"):
            merged = max((json.loads(stage(i, path)) for i in (2, 3)), key=lambda p: p.get("finished_at", ""))
        elif path.endswith(".md") and path.startswith(("output/latest/", "output/health/latest_run")):
            data = json.loads(target.with_suffix(".json").read_text())
            from pipeline.render import render_health, render_manifest, render_snapshot
            render = render_manifest if path == "output/latest/manifest.md" else render_health if path.startswith("output/health/") else render_snapshot
            target.write_text(render(data), encoding="utf-8")
            subprocess.run(["git", "add", "--sparse", "--", path], cwd=root, check=True)
            continue
        else:
            raise ValueError("refuse_to_overwrite_immutable_or_unknown_conflict:" + path)
        target.write_text(json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        subprocess.run(["git", "add", "--sparse", "--", path], cwd=root, check=True)


def publish_outputs(root, label):
    """Operate only in an ephemeral Actions checkout; preserve concurrent work."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("publication_requires_ephemeral_GitHub_Actions_checkout")
    root = Path(root)
    changed = subprocess.check_output(["git", "diff", "--name-only", "-z", "HEAD", "--", "output"], cwd=root).decode().split("\0")
    changed += subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard", "-z", "--", "output"], cwd=root).decode().split("\0")
    allowed = ("output/boll/archive/", "output/boll/latest/", "output/boll/noon_checks/", "output/latest/", "output/archive/", "output/health/")
    changed = sorted({p for p in changed if p.startswith(allowed)})
    if not changed:
        return {"published": False, "reason": "no_changed_publication_files"}
    if any(not (root / p).is_file() for p in changed):
        raise ValueError("publication_must_not_delete_archives_or_pointers")
    for path in changed:
        if path.startswith(("output/boll/archive/", "output/boll/noon_checks/", "output/archive/", "output/health/runs/")):
            existing = subprocess.run(["git", "show", "HEAD:" + path], cwd=root, capture_output=True)
            if existing.returncode == 0 and existing.stdout != (root / path).read_bytes():
                raise ValueError("refuse_to_modify_immutable_evidence:" + path)
    subprocess.run(["git", "add", "--sparse", "--", *changed], cwd=root, check=True)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=root)
    if staged.returncode == 0:
        return {"published": False, "reason": "no_staged_changes"}
    subprocess.run(["git", "commit", "-m", "boll: " + label + " independent public evidence"], cwd=root, check=True)
    # These are disposable local collector caches; their source evidence is
    # already immutable. They must not block rebasing the data publication.
    tracked = subprocess.check_output(["git", "diff", "--name-only", "-z", "HEAD", "--", "output/boll/state", "output/cache"], cwd=root).decode().split("\0")
    tracked = [p for p in tracked if p]
    if tracked:
        subprocess.run(["git", "restore", "--worktree", "--", *tracked], cwd=root, check=True)
    for _ in range(3):
        result = subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=root)
        for _ in range(3):
            if result.returncode == 0:
                break
            conflicts = subprocess.check_output(["git", "diff", "--name-only", "--diff-filter=U"], cwd=root).decode().splitlines()
            if not conflicts:
                raise RuntimeError("publication_rebase_failed_without_resolvable_conflict")
            resolve_conflicts(root, conflicts)
            result = subprocess.run(["git", "rebase", "--continue"], cwd=root, env={**os.environ, "GIT_EDITOR": "true"})
        if result.returncode:
            raise RuntimeError("publication_rebase_retry_exhausted")
        if subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=root).returncode == 0:
            return {"published": True, "changed_files": len(changed)}
    raise RuntimeError("publication_push_retry_exhausted")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("hydrate", "publish"))
    parser.add_argument("--phase", default="noon")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(hydrate_inputs(root, args.phase) if args.mode == "hydrate" else publish_outputs(root, args.phase)), flush=True)


if __name__ == "__main__":
    main()

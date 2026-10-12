# 2026-10-12 pipeline repair

## Observed failures

- Scheduled 08:17 collection started at 13:51:13 China time (334.23 minutes late). GitHub run 38209744728 reported success despite `published=false`, grade F and `skipped_expired`.
- Manifest availability stayed on September 23 because failed/skipped attempts never refreshed it.
- Intraday freshness used collection **start** as its reference: a genuine quote arriving during collection had negative age and failed the quality gate.
- Push-triggered validation skipped collection entirely. MA5 processing preceded publication and could block the report pipeline.
- AKShare's all-market quote routine fetched ~70 pages serially, without request deadlines.

## Changes

- Refresh Manifest calendar/readiness on every attempt; keep archive bytes/dates unchanged. Persist last-attempt status and run history, and return nonzero after failed collection.
- Resolve delayed cron delivery to a new, explicitly named `delayed-current-phase` collection with actual China date/time. It does not recreate a missed report or relabel current prices as historical noon prices. Normal in-window schedules retain their fixed phase.
- Use publication time for quote age, retaining future-quote rejection.
- Check pointer hashes, dates/cycles/types, canonical paths and schema. A corrupt old target no longer blocks a new valid publication.
- Use bounded Sina batch stock/index queries with a bounded Tencent fallback. Source dates are mandatory. Sina volume is labelled shares; ambiguous fallback volume is omitted. Tencent amount is converted from 10,000 CNY to CNY.
- Fetch completed daily bars concurrently for full runs and for the locked symbol even on light runs. Exclude unfinished daily bars; expose date, adjustment and parameters. No claim of matching proprietary vendor initialization.
- Full runs attempt all SH/SZ A-share pages concurrently. Market totals are accepted only if all pages and the universe count reconcile. Missing totals/sectors remain explicit. B-grade intraday/close quote snapshots allow those gaps, while A-grade requirements remain unchanged.
- Publish report data before independent MA5 work. Push-triggered repairs now collect and publish. Preserve failure diagnostics before marking the workflow failed.
- Refresh an out-of-range calendar; an unverified weekday fallback cannot pass calendar validation.

## Verification

107 automated tests passed before publication, including stale readiness, corrupt pointer recovery, calendar expiry, delayed/cross-midnight scheduling, quote freshness, timestamp and unit parsing.

Live local collection published `20261012-1439-intraday-light-local20261012143953` at 14:40:05 China time. All 11 Core and 14 Watch quotes and three indices were available. Eastwell (688700) completed-daily BOLL/KDJ/MACD were available as of October 9. It was correctly B-grade because full-market/sector data was absent in the light run.

## Remaining operational boundaries

GitHub cron delivery itself is not a precise scheduler. Retargeting makes delayed jobs useful but cannot guarantee pre-report arrival. No missed reports are backfilled. A full-market or sector source outage must remain a declared gap, never be replaced with configured-pool totals. Raw historical snapshots keep their original dates.

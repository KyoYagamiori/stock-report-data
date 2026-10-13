# 2026-10-13 noon snapshot repair

## Root cause

At the investigation's start, the last Actions collection was at 05:23 China time; no current-day morning/noon collection run had arrived. Its original cron was the previous evening's 20:41 node, delivered over eight hours late. The noon pointer still selected 2026-09-23.

Late schedules were deliberately retargeted to the actual phase, which protected against using afternoon prices as noon but left noon unavailable indefinitely. `pipeline.catchup` existed without a workflow invocation, trusted an unverified pointer, and returned success even when recovery failed. The historical adapter also carried afternoon high/low and close-verification fields into recovered records and calculated daily indicators with an unfinished half-day bar.

## Changes

- Add the trading-day 12:23 light retry and run the verified noon catch-up after collection, before the publication commit. Verify the exchange calendar, canonical immutable pointer, raw hash, date/cycle/type and current quality gate. Skip an existing valid A/B snapshot; recover a stale, missing or corrupt target. Recovery failures preserve diagnostics and fail the workflow.
- Fetch bounded, unadjusted one-minute/daily Sina history directly, without AKShare's unnecessary qfq daily request. Use six workers and a killable 180-second recovery boundary. Incomplete or failed Sina minute series use the Eastmoney minute-history fallback; verify the security code and convert its volume from lots to shares once, leaving amounts in CNY.
- Require the exact 11:30 bar and every 09:31–11:30 minute before reconstructing cumulative amounts/volumes or high/low. Reject duplicates, missing/invalid numbers and incomplete histories. No estimated volume or synthetic missing minute is inserted. The 09:30 auction is included when supplied.
- Replace every recovered OHLC/volume/amount field with target-session values and remove later close-verification evidence. Noon technical indicators use only completed, unadjusted daily bars, with explicit dates and parameters. Noon quote gates accept 11:30 timestamps, refusing 11:25 or 11:35 refreshes as noon data.
- Keep all-market turnover, breadth and sector rankings blank during historical reconstruction; configured-pool totals and index component turnover never replace full-market statistics.
- Add the public report rule for one current full-market focus stock, candidate comparison, conditions, expiry and subsequent validation. Report schedules are unchanged.

## Verification and recovered snapshot

125 automated tests passed, including a corrupt pointer, holiday/unverified calendar, nonzero recovery failure, missing 11:30 data, incomplete/duplicate minute histories, missing numeric amounts, fallback units and rejection of another security's response. Workflow YAML and all nine cron mappings were checked.

The first live recovery correctly failed the existing quality gate and was not published. After the bounded fallback was added, the actual same-day recovery published:

- Snapshot ID: `20261013-1135-noon-full-local20261013144048-1c76f6b9`
- Cycle/profile: `2026-10-13-noon` / `trading_noon`
- State: `ready_b`; `historical_point_in_time_recovery`; `point_in_time_recovered=true`
- Coverage: Core 11/11, Watch 14/14, indices 2/3.
- Market timestamp: 2026-10-13 11:30 China time. Publication occurred after the report cutoff; it is explicitly an after-the-fact restoration.
- SHA-256 of immutable JSON bytes: `4938083fdbc720b087c00340feaaf3a628a9192c656d0ac5e8b800d9c41043c2`.
- Eastwell 688700: 53.28; high 53.33; low 49.66; 7,835,822 shares; CNY 399,989,158.0626. Completed daily indicators are dated 2026-10-12.

The missing index is 399006. Full-market turnover, breadth and sector rankings also remain unavailable in this reconstructed snapshot. These omissions are retained rather than promoted to grade A. Existing reports and old immutable archives are not rewritten. A subsequent successfully verified collection may improve the current pointer.

GitHub cron delivery can still be delayed or dropped; the additional retry and restoration do not guarantee availability before 12:40. See [GitHub's schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

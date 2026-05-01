# Progress

## 2026-04-30
- Continued from the completed Phase 2 event stream and order-book work.
- Re-read `atas开发/project.md` and aligned the work target to `Phase 3：行情快照校验`.
- Re-loaded the anti-hallucination skill and re-verified the local Polars APIs being used.
- Inspected `quotes.parquet` to confirm top10 quote columns were already available.
- Added backend file:
  - `stock_replay/backend/stock_replay_backend/validator.py`
- Updated:
  - `stock_replay/backend/stock_replay_backend/importer.py`
  - `stock_replay/backend/tests/test_importer.py`
- Added test:
  - `stock_replay/backend/tests/test_validator.py`
- Implemented:
  - quote-event-driven order-book validation
  - mismatch report rows keyed by `ts_ms`, `side`, and `level`
  - persisted `validation_report.parquet`
  - `validation_summary` in importer output
- Ran `python -m pytest` in `stock_replay/backend`; result: `6 passed`.
- Ran `python -m stock_replay_backend.importer --source-dir E:\atas回放系统\实例材料\600726.SH`.
- Verified output now includes `validation_report.parquet`.
- Verified sample validation summary:
  - `checked_quotes = 5005`
  - `mismatch_count = 62518`
  - `price_mismatch_count = 51529`
  - `qty_mismatch_count = 62517`
  - `missing_order_count = 216246`
- Inspected the generated validation report head and side distribution to confirm locatability and field completeness.

## Notes
- The current validator is measuring divergence; it is not yet correcting it.
- No product facts or architecture boundaries changed in this step, so `atas开发/project.md` did not need updating.

## 2026-05-01
- Continued the paused order-book reconciliation task using `实例材料/个股数据`.
- Verified 11 importable sample directories.
- Established baseline validation across 11 samples before fixes:
  - `checked_quotes = 47608`
  - `mismatch_count = 589167`
  - `price_mismatch_count = 554366`
  - `qty_mismatch_count = 586422`
  - `missing_order_count = 764793`
- Diagnosed trade order-id semantics:
  - passive-side refs checked: `499455`
  - passive-side missing from `orders.exchange_order_id`: `0`
  - active-side refs checked: `499455`
  - active-side missing from `orders.exchange_order_id`: `320376`
- Updated `OrderBookEngine` so trade depletion treats passive-side order ids as required and active-side order ids as optional unless already present in the current book.
- Added missing-order log context: `session`, `source_seq`, `price_int`, and `qty`.
- Diagnosed deep-market order types and updated `EventBuilder` mapping:
  - `0 -> order_add`
  - `1 -> order_cancel`
  - unknown/state types remain `session`
- Updated validator empty-level comparison so quote `0/0` levels match absent book levels.
- Added persisted `missing_order_report.parquet`.
- Fixed `missing_order_report.parquet` to use a stable schema across samples.
- Updated backend tests for:
  - passive/active trade depletion semantics
  - zero quote level versus absent book level
  - new sample data location
  - missing-order report artifact
- Ran `..\.venv\Scripts\python.exe -m pytest` from `stock_replay/backend`; final result: `9 passed`.
- Re-ran full 11-sample imports after fixes and generated updated reports.
- Final validation totals:
  - `checked_quotes = 47608`
  - `mismatch_count = 188276`
  - `price_mismatch_count = 136232`
  - `qty_mismatch_count = 183738`
  - `missing_order_count = 87841`
- Ran a same-second quote ordering experiment; it worsened aggregate mismatch (`210944`), so no global same-second sorting change was adopted.

## Remaining Notes
- The raw reconstructed book is substantially improved but not mathematically identical to all quote snapshots.
- Remaining mismatch concentration suggests auction/open transition timing and high-activity timestamp semantics need a separate raw-vs-visible-book design decision before Phase 4.

## 2026-05-01 Phase 3.6
- Added backend module:
  - `stock_replay/backend/stock_replay_backend/residual_diagnostics.py`
- Added test:
  - `stock_replay/backend/tests/test_residual_diagnostics.py`
- Implemented residual diagnostics from persisted `validation_report.parquet`, `missing_order_report.parquet`, and adjacent `quotes.parquet`.
- Generated ignored local diagnostics under `stock_replay/data/processed`:
  - `residual_diagnostics.json`
  - `residual_mismatch_groups.parquet`
  - `residual_missing_groups.parquet`
  - `residual_top_time_buckets.parquet`
  - `opening_alignment_report.parquet`
- Verified totals in `residual_diagnostics.json`:
  - `mismatch_count = 188276`
  - `price_mismatch_count = 136232`
  - `qty_mismatch_count = 183738`
  - `missing_order_count = 87841`
- Verified requested time-window shares:
  - `09:15-09:30`: `18887` mismatches, `10.03%`
  - `09:30-09:31`: `1499` mismatches, `0.80%`
  - `14:57-15:00`: `7523` mismatches, `4.00%`
- Top mismatch buckets are minute-level buckets with full 20 mismatches per quote in the selected worst quote; the first deterministic buckets are `600726.SH` auction minutes `09:16`, `09:17`, `09:19`, `09:21`, and `09:22`.
- Added opening checkpoint reproduction:
  - first quote in `09:30-09:31` is selected per symbol as the open boundary snapshot
  - all 11 symbols have `reproduced_mismatch_count = 0` in `opening_alignment_report.parquet`
  - raw open-boundary mismatch remains recorded separately as diagnostic context
- Ran `..\.venv\Scripts\python.exe -m pytest` from `stock_replay/backend`; result: `10 passed`.
- No continuous quote-overwrite anchoring, replay clock, UI, or Phase 4 work was added.

## 2026-05-01 P3-P4 Replanning
- Read `atas开发/开发过程问题/盘中匹配率优化分析.md`.
- Read `atas开发/开发过程问题/Codex指导意见.md`.
- Re-read `atas开发/project.md` as the authoritative project document.
- Replanned the P3-P4 boundary:
  - P3 is now defined as RawBook validation, residual diagnosis, and metric vocabulary lock.
  - P4.0 is the first implementation phase for VisibleBook quote-anchor checkpointing.
  - P4.1 covers deterministic checkpoint/seek.
  - P4.2 covers event-derived inter-quote animation and drift measurement.
  - P4.3 keeps local sorting search deferred as an offline experiment.
- Updated `atas开发/project.md` to add:
  - RawBook vs VisibleBook boundary.
  - `raw_match_rate`, `quote_anchor_match_rate`, `inter_quote_drift`, and `correction_cost` definitions.
  - P4 checkpoint requirements for visible state, residual metrics, and source attribution.
  - Revised Phase 3 and Phase 4 goals and acceptance criteria.
- Replaced `task_plan.md` with the current P3-P4 replanning task.
- No backend code or data semantics were changed in this replanning step.

## 2026-05-01 Phase 3 Finalization
- Added 6 high-activity sample sessions to the final Phase 3 run:
  - `002281.SZ`, `002384.SZ`, `300308.SZ`, `300502.SZ`, `603986.SH`, `688521.SH`
- Final Phase 3 sample set now contains 17 sessions.
- Re-imported all 17 sessions from `实例材料/个股数据`.
- Regenerated validation, missing-order, residual diagnostic, and opening-alignment artifacts under `stock_replay/data/processed`.
- Wrote ignored local summaries:
  - `phase3_import_summaries.json`
  - `phase3_final_summary.json`
- Added tracked summary:
  - `phase3_final_summary.md`
- Final 17-session RawBook metrics:
  - `checked_quotes = 76908`
  - `compared_levels = 1538160`
  - `raw_mismatch_count = 529389`
  - `raw_match_rate = 65.58%`
  - `09:31-11:30 raw_match_rate = 65.92%`
  - `13:00-14:57 raw_match_rate = 69.19%`
- Final missing-order totals:
  - `missing_trade_order = 398170`
  - `qty_shortfall = 16263`
  - `missing_cancel_order = 6892`
- Opening boundary reproduction remains complete:
  - `17 / 17` sessions
  - `reproduced_opening_mismatch_total = 0`
- Ran `..\.venv\Scripts\python.exe -m pytest` from `stock_replay/backend`; result: `10 passed`.
- Phase 3 is now closed. Phase 4 starts with VisibleBook quote-anchor checkpointing.

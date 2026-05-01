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

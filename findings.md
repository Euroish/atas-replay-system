# Findings

## Current Task
- The active development step is now `Phase 3：行情快照校验`.
- The existing Phase 2 interfaces were sufficient; no product or architecture changes were required.

## Quote Validation Inputs
- `quotes.parquet` already contains all required fields for snapshot validation:
  - `ask_price_1_int` to `ask_price_10_int`
  - `ask_qty_1` to `ask_qty_10`
  - `bid_price_1_int` to `bid_price_10_int`
  - `bid_qty_1` to `bid_qty_10`
- `events.parquet` already carries `event_type = quote` and `source_seq`, which is enough to map each quote event back to its source quote row.

## Implemented Phase 3 Components
- Added `stock_replay/backend/stock_replay_backend/validator.py`.
- Extended the importer to generate `validation_report.parquet`.
- Extended the importer summary to include `validation_summary`.

## Validation Rules Implemented
- Replay all events through `OrderBookEngine`.
- At each `quote` event:
  - locate the source quote row by `source_seq`
  - compare actual order-book top10 against expected quote top10
  - emit one report row per mismatched `side/level`
- Report fields include:
  - `quote_seq`
  - `ts_ms`
  - `side`
  - `level`
  - `expected_price_int`
  - `actual_price_int`
  - `expected_qty`
  - `actual_qty`
  - `price_match`
  - `qty_match`

## Verified Output
- Generated file: `stock_replay/data/processed/symbol=600726.SH/date=20260424/validation_report.parquet`
- Real sample import summary:
  - `checked_quotes = 5005`
  - `mismatch_count = 62518`
  - `price_mismatch_count = 51529`
  - `qty_mismatch_count = 62517`
  - `missing_order_count = 216246`
- Report side distribution:
  - `ask = 49114`
  - `bid = 13404`

## Interpretation
- The current order-book reconstruction does not yet align tightly with the quote snapshots, which is expected at this stage because the engine is still a minimal Phase 2 implementation.
- The important result for Phase 3 is not low mismatch counts, but that mismatches are now measurable, persisted, and locatable by timestamp, side, and level.

## Remaining Gaps After Phase 3
- No checkpointing or replay clock yet.
- No reconciliation strategy yet for reducing `missing_order_count` and quote mismatches.
- No UI or CLI presentation layer yet beyond import summary JSON and the Parquet report itself.

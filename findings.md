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

## Phase 3.5 Multi-Symbol Order-Book Findings
- Uploaded sample root used for this task: `实例材料/个股数据`.
- The sample set contains 11 importable symbol directories:
  - `000711.SZ`, `002820.SZ`, `002857.SZ`, `300408.SZ`, `301305.SZ`
  - `600726.SH`, `601609.SH`, `605389.SH`, `688008.SH`, `688758.SH`, `688819.SH`
- Multi-symbol diagnostics verified that passive-side trade references were fully present in the order table:
  - passive refs checked: `499455`
  - passive refs missing from `orders.exchange_order_id`: `0`
  - active refs checked: `499455`
  - active refs missing from `orders.exchange_order_id`: `320376`
- Implemented trade depletion rule:
  - `aggressor_side = B`: ask-side order is required/passive and is depleted; bid-side order is depleted only if currently present.
  - `aggressor_side = S`: bid-side order is required/passive and is depleted; ask-side order is depleted only if currently present.
  - Missing active-side ids are not counted as order-book missing orders.
- Deep samples use `order_type` values `0`, `1`, and `U`, not `A`, `D`, and `S`.
  - Verified mapping used by the event builder: `0 -> order_add`, `1 -> order_cancel`, `U -> session`.
  - The raw `order_type` value remains unchanged in normalized `orders.parquet`.
- Validator now treats a quote level of `price=0, qty=0` and an absent reconstructed level as the same empty level.
- Import now writes `missing_order_report.parquet` next to `validation_report.parquet` for objective follow-up diagnostics.

## Phase 3.5 Verified Metrics
- Baseline before Phase 3.5 fixes across 11 samples:
  - `checked_quotes = 47608`
  - `mismatch_count = 589167`
  - `price_mismatch_count = 554366`
  - `qty_mismatch_count = 586422`
  - `missing_order_count = 764793`
- Final after Phase 3.5 fixes across 11 samples:
  - `checked_quotes = 47608`
  - `mismatch_count = 188276`
  - `price_mismatch_count = 136232`
  - `qty_mismatch_count = 183738`
  - `missing_order_count = 87841`
- The fixes materially improved reconstruction and validation, but raw reconstructed top10 is not yet perfectly equal to every quote snapshot.
- A sorting experiment that moved quotes to the end of each same-second bucket improved some symbols, but worsened the total result (`mismatch_count = 210944`), so it was not adopted as a global rule.

## Remaining Objective Uncertainty
- Some residual mismatches appear around auction/open transitions and within high-activity seconds where quote timestamps and tick event timestamps may not represent a strict millisecond-before/after relationship.
- The current task did not implement quote-overwrite anchoring. Raw order-book validation remains an error-measurement path; a future visible-book layer can use quote snapshots as aggregate display anchors without fabricating order ids.

## Phase 3.6 Residual Diagnostics
- Added a reproducible residual diagnostic command:
  - `python -m stock_replay_backend.residual_diagnostics --processed-root E:\atas回放系统\stock_replay\data\processed`
- The command reads existing per-session `validation_report.parquet`, `missing_order_report.parquet`, and `quotes.parquet`; it does not change event ordering, order-book depletion, or validation semantics.
- Generated local diagnostic artifacts:
  - `stock_replay/data/processed/residual_diagnostics.json`
  - `stock_replay/data/processed/residual_mismatch_groups.parquet`
  - `stock_replay/data/processed/residual_missing_groups.parquet`
  - `stock_replay/data/processed/residual_top_time_buckets.parquet`
  - `stock_replay/data/processed/opening_alignment_report.parquet`
- `residual_mismatch_groups.parquet` groups residual mismatches by:
  - `symbol`, `exchange_code`, `session`, `minute_bucket`, `minute`, `side`, `level`
- `residual_missing_groups.parquet` groups missing-order events by:
  - `reason`, `session`, `symbol`
- `residual_diagnostics.json` includes:
  - aggregate totals
  - requested `09:15-09:30`, `09:30-09:31`, and `14:57-15:00` mismatch shares
  - opening checkpoint reproduction details for the first open quote per symbol
  - top 20 mismatch minute buckets
  - quote snapshot and reconstructed raw-book snapshot for the worst quote in each top bucket
- Verified Phase 3.6 totals remain:
  - `mismatch_count = 188276`
  - `price_mismatch_count = 136232`
  - `qty_mismatch_count = 183738`
  - `missing_order_count = 87841`
- Verified requested time-window mismatch shares:
  - `09:15-09:30`: `18887 / 188276`, about `10.03%`
  - `09:30-09:31`: `1499 / 188276`, about `0.80%`
  - `14:57-15:00`: `7523 / 188276`, about `4.00%`
- Top residual minute buckets currently include:
  - `600726.SH` auction `09:16`, `400` mismatches
  - `600726.SH` auction `09:17`, `400` mismatches
  - `600726.SH` auction `09:19`, `400` mismatches
  - `600726.SH` auction `09:21`, `400` mismatches
  - `600726.SH` auction `09:22`, `400` mismatches
- Top missing-order groups currently start with:
  - `missing_trade_order`, `continuous_am`, `300408.SZ`: `16744`
  - `missing_trade_order`, `continuous_am`, `000711.SZ`: `14013`
  - `missing_trade_order`, `continuous_pm`, `300408.SZ`: `9773`
- Opening checkpoint reproduction:
  - The first quote in `09:30-09:31` is treated as the open boundary snapshot for replay/display alignment.
  - Verified across all 11 symbols: `reproduced_mismatch_count = 0`.
  - The raw pre-checkpoint mismatch remains visible in `opening_alignment_report.parquet`; examples include `600726.SH = 20`, `300408.SZ = 20`, `000711.SZ = 20`, while `601609.SH` and `688819.SH` already have raw mismatch `0` at their first open quote.
- Phase 3.6 supports the same conclusion as Phase 3.5: the residual gap is measurable and concentrated enough for follow-up design work, but it is not evidence that general continuous quote snapshots should overwrite the raw reconstructed book in Phase 3.

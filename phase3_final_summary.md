# Phase 3 Final Summary

## Status

Phase 3 is complete.

Phase 3 owns RawBook validation, residual diagnostics, opening-boundary evidence, and metric vocabulary. It does not own VisibleBook implementation, replay clock, checkpoint seek, Heatmap, DOM, or UI.

## Sample Set

Final Phase 3 sample set:

- `000711.SZ`
- `002281.SZ`
- `002384.SZ`
- `002820.SZ`
- `002857.SZ`
- `300308.SZ`
- `300408.SZ`
- `300502.SZ`
- `301305.SZ`
- `600726.SH`
- `601609.SH`
- `603986.SH`
- `605389.SH`
- `688008.SH`
- `688521.SH`
- `688758.SH`
- `688819.SH`

Total: 17 symbol/date sessions.

## Final RawBook Metrics

Generated from `stock_replay/data/processed/phase3_final_summary.json`.

| Metric | Value |
| --- | ---: |
| checked_quotes | 76908 |
| compared_levels | 1538160 |
| raw_mismatch_count | 529389 |
| raw_price_mismatch_count | 439840 |
| raw_qty_mismatch_count | 495769 |
| raw_match_rate | 65.58% |
| raw_price_match_rate | 71.40% |
| raw_qty_match_rate | 67.77% |

## Window Metrics

| Window | Quotes | Raw Match Rate | Mismatches |
| --- | ---: | ---: | ---: |
| 09:15-09:30 | 1619 | 2.26% | 31647 |
| 09:30-09:31 | 339 | 49.51% | 3423 |
| 09:31-11:30 | 37779 | 65.92% | 257533 |
| 13:00-14:57 | 36535 | 69.19% | 225138 |
| 14:57-15:00 | 594 | 3.01% | 11523 |

## Missing Order Metrics

| Reason | Count |
| --- | ---: |
| missing_trade_order | 398170 |
| qty_shortfall | 16263 |
| missing_cancel_order | 6892 |

## Opening Boundary

The first quote in `09:30-09:31` is reproducible as an opening display checkpoint for all 17 sessions:

| Metric | Value |
| --- | ---: |
| opening sessions | 17 |
| raw opening mismatch total | 232 |
| reproduced opening mismatch total | 0 |

## Final Interpretation

The expanded high-activity sample set confirms that RawBook top10 matching is a data-quality and residual-diagnostics metric, not the correct target for a 95%+盘中 visible replay acceptance gate.

Phase 4 should start with VisibleBook quote-anchor checkpointing:

- RawBook remains pure order/trade/cancel reconstruction.
- Quote anchors must not overwrite RawBook or fabricate order IDs.
- VisibleBook/checkpoint metrics own the 95%+盘中 visible match target.
- `inter_quote_drift` and `correction_cost` must be recorded so quote-point alignment does not hide replay drift.

## Generated Local Artifacts

These are under ignored local data:

- `stock_replay/data/processed/phase3_import_summaries.json`
- `stock_replay/data/processed/phase3_final_summary.json`
- `stock_replay/data/processed/residual_diagnostics.json`
- `stock_replay/data/processed/residual_mismatch_groups.parquet`
- `stock_replay/data/processed/residual_missing_groups.parquet`
- `stock_replay/data/processed/residual_top_time_buckets.parquet`
- `stock_replay/data/processed/opening_alignment_report.parquet`

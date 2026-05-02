# Task Plan

## Goal
Make intraday continuous-auction order-book replay extremely accurate for A-share SH/SZ samples.

## Current Priority
- Focus on core intraday windows only:
  - `09:31-11:30`
  - `13:00-14:57`
- Treat `09:15-09:30` opening auction and `14:57-15:00` close auction as display-only boundaries, not RawBook accuracy targets.
- Opening/close auction only need enough data for normal display:
  - high-open / low-open / flat-open status.
  - opening or close auction total traded quantity.
  - first valid trade or first valid order marker.

## Scope
- Keep `RawBook` as the event-driven reconstruction path from `逐笔委托.csv` and `逐笔成交.csv`.
- Keep `VisibleBook` as a separate quote-anchored display/replay layer.
- Use residual groups and missing-order reasons only inside the core intraday windows to decide reconstruction fixes.
- Defer FastAPI/WebSocket, frontend polish, and multi-window work unless they directly unblock accurate intraday replay.

## Current Evidence
- Current active baseline is PDF-grounded RawBook with PDF-described 3-second quote merge/alignment for quote validation.
- Full 17-session validation after 3-second quote merge and auction quote skip:
  - full-day `mismatch_count = 80718`
  - full-day `price_mismatch_count = 62690`
  - full-day `qty_mismatch_count = 76670`
  - full-day `missing_order_count = 0`
- Core intraday residual:
  - `mismatch_count = 67470`
  - `price_mismatch_count = 49946`
  - `qty_mismatch_count = 63485`
- Core intraday residual by window:
  - `09:31-11:30`: `38839`
  - `13:00-14:57`: `28631`
- Strict reported-timestamp PDF-first replay is retained as a control/reference:
  - full-day `414593 / 344026 / 385801`
  - core intraday `399635 / 329622 / 371033`
- Missing-order residual is eliminated in the current 17-session sample set.
- Wind field definitions verified from `实例材料/wind-level2字段说明书.pdf`:
  - prices/amounts use `10000` precision.
  - quote, order, and trade quantities are already in shares, not lots.
  - SZ order types `1` and `U` are non-resting market/best-side flow.
  - SZ trade code `C` is a cancel execution report.
- The pure Wind-rule replay attempt is archived in `findings.md`/`progress.md`; it proved reported-timestamp-only replay does not fully reproduce Wind 3-second ten-level quote snapshots.
- Current quote validation uses the PDF-described 3-second snapshot generation behavior:
  - infer a stable per-session quote bucket end offset from quote trade deltas.
  - align quote validation after the corresponding cumulative trade anchor when available.
  - keep the reconstructed book state event-driven from tick orders/trades rather than overwriting RawBook with quote top10.
- Haitong LOB report rules are now reflected in code:
  - order/trade tick events use `message_seq` for same-time ordering where available.
  - RawBook can expose full-depth per-price order composition via `snapshot_order_queues()`.
  - This completes the queue-composition part of LOB reproduction without changing the quote-anchored VisibleBook separation.

## Immediate Next Steps
1. Keep all headline metrics scoped to core intraday windows unless explicitly discussing auction display.
2. Treat remaining `RawBook` top10 mismatch as evidence that Wind quote snapshot timing/display semantics and exchange/vendor sequencing still differ from the available tick stream.
3. Use quote-anchor `VisibleBook` checkpoints as the exact order-book surface for research/export at quote timestamps.
4. Keep quote phase rules grounded in the PDF-described 3-second generation behavior and measured trade-count/volume deltas.
5. Preserve RawBook and VisibleBook separation:
   - RawBook is diagnostics and event-derived state.
   - VisibleBook is the user-facing replay/display state anchored by quote snapshots.

## Out Of Scope For Current Phase
- Perfect RawBook reproduction during opening auction.
- Perfect RawBook reproduction during close auction.
- UI/transport work not tied to intraday order-book accuracy.
- Cosmetic replay smoothing that hides residuals without explaining them.

## Success Criteria
- Core intraday replay can be reported separately from full-day/auction metrics.
- Remaining fixes target verified SZ/SH continuous-auction error classes.
- Opening and close auction display shows correct open status, total volume, and first trade/order marker without treating auction RawBook mismatch as failure.
- No document should imply that quote-anchor VisibleBook success proves RawBook is complete.

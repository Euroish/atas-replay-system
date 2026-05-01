# Task Plan

## Goal
Advance Phase 4 by delivering the first backend VisibleBook quote-anchor checkpoint loop while preserving RawBook semantics.

## Scope
- Read `atas开发/project.md` and follow its P4 boundaries.
- Add a VisibleBook layer that anchors visible top10 state from quote events.
- Persist checkpoint rows with source attribution and raw residual metrics.
- Report `quote_anchor_match_rate`, `inter_quote_drift_abs_qty`, and `correction_cost`.
- Verify the 17-session sample set reaches at least 95% visible quote-anchor match rate for:
  - `09:31-11:30`
  - `13:00-14:57`

## Completed
- Added `stock_replay/backend/stock_replay_backend/visible_book.py`.
- Updated importer output with `visible_orderbook_checkpoints.parquet`.
- Added `visible_book_summary` to import reports.
- Added and updated backend tests.
- Re-imported all 17 sample sessions.
- Updated `atas开发/project.md`, `findings.md`, and `progress.md`.

## Verified Results
- Backend tests: `11 passed`.
- 17-session checkpoint rows: `1538160`.
- Aggregate `quote_anchor_match_rate`: `100%`.
- `09:31-11:30 quote_anchor_match_rate`: `100%`.
- `13:00-14:57 quote_anchor_match_rate`: `100%`.
- Aggregate `correction_cost`: `12866109226`.

## Out Of Scope For This Step
- Replay virtual clock.
- Seek from persisted checkpoint.
- WebSocket frame push.
- Quote-between event-derived VisibleBook animation.
- UI, Heatmap, DOM, or Footprint rendering changes.

## Next Phase 4 Step
Implement checkpoint seek/readback so repeated seek to the same timestamp returns deterministic VisibleBook state without replaying from open.

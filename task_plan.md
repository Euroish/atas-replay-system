# Task Plan

## Goal
Advance P4.1 by implementing deterministic VisibleBook checkpoint seek/readback without replaying from open.

## Scope
- Add a backend checkpoint store that reads persisted `visible_orderbook_checkpoints.parquet`.
- Given `symbol`, `trade_date`, and `ts_ms`, return the latest checkpoint at or before `ts_ms`.
- Return deterministic ask/bid top10 plus source, raw residual, and correction metadata.
- Do not implement replay virtual clock, WebSocket frame push, quote-between animation, or UI.

## Completed
- Added `stock_replay/backend/stock_replay_backend/checkpoint_store.py`.
- Added `VisibleCheckpointStore.load_checkpoint(symbol, trade_date, ts_ms, depth=10)`.
- Added tests for latest-at-or-before lookup, deterministic repeat seek, depth limiting, and pre-first-checkpoint rejection.
- Verified a real `600726.SH` checkpoint seek at `34260000`.
- Updated `atas开发/project.md`, `findings.md`, `progress.md`, and this task plan.

## Verified Results
- Backend tests: `14 passed`.
- Real sample seek:
  - symbol/date: `600726.SH` / `20260424`
  - target `ts_ms = 34260000`
  - returned checkpoint `ts_ms = 34260000`
  - returned `quote_seq = 224`
  - ask levels: `10`
  - bid levels: `10`
  - repeated seek result: deterministic
- Latest state: P4.1 minimum backend checkpoint readback is complete; replay engine work remains.

## Out Of Scope For This Step
- Replay virtual clock.
- Seek from persisted checkpoint.
- WebSocket frame push.
- Quote-between event-derived VisibleBook animation.
- UI, Heatmap, DOM, or Footprint rendering changes.

## Next Phase 4 Step
Build the replay-facing frame/load layer on top of `VisibleCheckpointStore`, then add virtual clock and WebSocket streaming.

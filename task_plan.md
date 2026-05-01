# Task Plan

## Goal
Advance P4.2 by implementing a window-scoped replay core on top of `VisibleCheckpointStore`.

## Scope
- Cache `visible_orderbook_checkpoints.parquet` in memory per session.
- Provide per-window `load`, `play`, `pause`, `seek`, `set_speed`, `tick`, and `snapshot`.
- Return deterministic frame payloads with ask/bid top10 and checkpoint metadata.
- Do not add FastAPI/WebSocket transport or UI integration in this step.

## Completed
- Added `stock_replay/backend/stock_replay_backend/replay_engine.py`.
- Extended `stock_replay/backend/stock_replay_backend/checkpoint_store.py` with `VisibleCheckpointSession` and `load_session(...)`.
- Added tests for replay load/play/pause/seek/tick and window isolation.
- Updated `atas开发/project.md`, `findings.md`, `progress.md`, and this task plan.

## Verified Results
- Backend tests: `16 passed`.
- Real sample replay:
  - symbol/date: `600726.SH` / `20260424`
  - target `ts_ms = 34260000`
  - returned checkpoint `ts_ms = 34260000`
  - returned `quote_seq = 224`
  - ask levels: `10`
  - bid levels: `10`
  - after `play` + `tick(1000)` at speed `1.0`, virtual clock advanced to `34261000` while the snapped checkpoint stayed deterministic

## Out Of Scope For This Step
- FastAPI request/response routes.
- WebSocket streaming loop.
- Browser UI integration.
- Quote-between animation and DOM/Heatmap rendering.

## Next Phase 4 Step
Wire the replay core into an API/streaming layer so per-window load/play/pause/seek/speed can be driven over HTTP/WebSocket.

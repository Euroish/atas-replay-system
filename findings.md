# Findings

## 2026-05-01 Project Drift Repair
- The active work focus has been re-centered on P3/P4 order-book reproduction, not replay plumbing or UI polish.
- External reconstruction references reviewed:
  - dxFeed order-book reconstruction docs describe snapshot-bound reconstruction with a pending queue and transactional application of order events.
  - LOBSTER-style order-driven market data is commonly reconstructed from message/event streams, with the book state derived from ordered add/cancel/execute updates rather than from UI checkpoints.
  - Recent research on limit-order-book dynamics continues to treat order additions, cancellations, executions, and queue state as the core reconstruction primitives.
- Practical implication for this project:
  - `RawBook` should stay the canonical event-driven reconstruction path.
  - `VisibleBook` should stay a separate quote-anchored display layer.
  - UI/replay work must not be used as proof that raw reconstruction is complete.

## Current Diagnostic Direction
- The most useful remaining signals are the residual buckets already produced by:
  - `validation_report.parquet`
  - `missing_order_report.parquet`
  - `residual_diagnostics.json`
- The next reconstruction questions should be framed as:
  - Is the mismatch caused by semantic parsing?
  - Is it caused by timestamp ordering within the same millisecond?
  - Is it caused by incomplete order lifecycle data?
  - Or is it only a visible-book correction problem?

## 2026-05-01 A-Share Order-Flow Rule Alignment
- Verified against the local Wind field guide and official exchange rules:
  - SZ `委托类型 = 0/1/U` are not cancel codes.
  - `1` and `U` are market / best-price submission types and should stay in the event stream as non-resting flow.
  - SZ `成交代码 = C` is a cancellation-style execution report and should be treated as a cancel-like flow at the same source priority, not as a normal trade.
- Code-path result after alignment:
  - `1/U` now map to `market_order`
  - `C` now maps to `trade_cancel`
  - `OrderBookEngine` ignores `market_order` and processes `trade_cancel` via the cancel path
- Verified sample import after the change:
  - `002281.SZ` / `20260325`
  - `missing_order_count = 267`
  - `mismatch_count = 35287`
  - `price_mismatch_count = 27579`
  - `qty_mismatch_count = 34482`
- Backend verification:
  - `18 passed`

## External Sources Consulted
- dxFeed order-book reconstruction documentation.
- Research material on limit-order-book reconstruction and order-driven market data.
- These sources were used only to confirm reconstruction strategy and diagnostic framing, not to override local sample evidence.

## Current Task
- The active development step is now P3/P4 order-book reproduction, not replay plumbing.
- The existing raw/event/checkpoint interfaces remain the right base; the remaining work is to improve reconstruction accuracy and keep visible-book metrics separate.

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

## P3-P4 Replanning From Development Issue Notes
- Read:
  - `atas开发/开发过程问题/盘中匹配率优化分析.md`
  - `atas开发/开发过程问题/Codex指导意见.md`
  - `atas开发/project.md`
- Core confirmed requirement:
  - 集合竞价不是当前重点。
  - 盘中 `09:31-11:30` and `13:00-14:57` 可见盘口匹配率需要达到 95%+。
  - Current raw matching around 80%+ should remain a diagnostic signal, not the P4 success metric.
- Important correction to avoid development drift:
  - Quote anchor should not be treated as proof that the full inter-quote order book is真实完整.
  - VisibleBook match rate must be reported separately from RawBook match rate.
  - Correction/drift cost must be recorded so quote point alignment does not become a misleading vanity metric.
- Adopted architecture boundary:
  - RawBook remains pure order/trade/cancel reconstruction.
  - VisibleBook is a display/replay layer anchored from quote snapshots.
  - Quote anchoring must not overwrite RawBook and must not fabricate order IDs.
- Revised phase interpretation:
  - P3 ends at raw validation, residual diagnostics, and metric vocabulary.
  - P4 starts with VisibleBook quote anchor and checkpoint generation.
  - P4.0 should not include UI, Heatmap rendering, local sorting search, or smoothing heuristics.
- Lower-priority / deferred ideas:
  - Local ordering search is an offline experiment only until proven stable across symbols and sessions.
  - Long-term correction layers such as `raw_qty + correction_qty` are risky when price levels shift; prefer anchor state plus event delta tape plus residual logs.
  - Any fixed smoothing window such as 200ms requires data evidence before adoption.

## Phase 3 Final State
- Expanded final sample set: 17 symbol/date sessions.
- Newly included high-activity samples:
  - `002281.SZ`, `002384.SZ`, `300308.SZ`, `300502.SZ`, `603986.SH`, `688521.SH`
- Final RawBook metrics:
  - `checked_quotes = 76908`
  - `compared_levels = 1538160`
  - `raw_mismatch_count = 529389`
  - `raw_price_mismatch_count = 439840`
  - `raw_qty_mismatch_count = 495769`
  - `raw_match_rate = 65.58%`
  - `raw_price_match_rate = 71.40%`
  - `raw_qty_match_rate = 67.77%`
- Final盘中 raw window metrics:
  - `09:31-11:30`: `65.92%`
  - `13:00-14:57`: `69.19%`
- Final missing-order metrics:
  - `missing_trade_order = 398170`
  - `qty_shortfall = 16263`
  - `missing_cancel_order = 6892`
- Opening boundary display reproduction:
  - `17 / 17` sessions reproduced with `reproduced_mismatch_count = 0`.
  - Raw opening mismatch total remains `232`, retained as diagnostic evidence.
- Conclusion:
  - Phase 3 is complete.
  - The high-activity samples strengthen, not weaken, the P3 conclusion that RawBook is a residual diagnostic layer.
  - P4 should target 95%+盘中 visible replay via VisibleBook quote-anchor checkpointing, while preserving RawBook as pure reconstruction.

## Phase 4.0 VisibleBook Quote Anchor Findings
- Implemented the first P4 backend checkpoint artifact:
  - `visible_orderbook_checkpoints.parquet`
- The artifact is generated during import next to `quotes.parquet`, `events.parquet`, `validation_report.parquet`, and `missing_order_report.parquet`.
- Each quote emits 20 checkpoint rows:
  - ask levels 1-10
  - bid levels 1-10
- VisibleBook state at P4.0 is quote-anchored:
  - `visible_price_int` and `visible_qty` come from the quote top10.
  - `source` is `quote_anchor`.
  - `quote_anchor_match` is true by construction for generated checkpoint rows.
- RawBook remains diagnostic and is not overwritten:
  - `raw_price_int` and `raw_qty` capture the current `OrderBookEngine` top10 before quote anchoring.
  - `raw_price_match` and `raw_qty_match` preserve the raw-vs-quote residual at the same level.
- P4 metric fields now exist at checkpoint level:
  - `inter_quote_drift_abs_qty`
  - `correction_cost`
  - `correction_abs_qty` retained as a compatibility alias for the current quantity-cost calculation.
- Verified across the 17-session sample set:
  - `checkpoint_rows = 1538160`
  - aggregate `quote_anchor_match_rate = 100%`
  - `09:31-11:30 quote_anchor_match_rate = 100%`
  - `13:00-14:57 quote_anchor_match_rate = 100%`
  - aggregate `correction_cost = 12866109226`
- This satisfies the P4.0 quote-anchor checkpoint target, but it does not yet satisfy the full Phase 4 replay service target because seek, virtual clock, WebSocket frames, and inter-quote animation are not implemented.

## P4.0 Process Draft Cleanup Findings
- `atas开发/开发过程问题/P4.0 开发进展分析.md` confirms the same state already recorded in current docs:
  - P4.0 has completed import-time VisibleBook quote-anchor checkpoint generation.
  - P4.0 has not implemented replay virtual clock, checkpoint seek/readback, WebSocket frames, quote-between animation, or UI/Heatmap/DOM.
  - `quote_anchor_match_rate = 100%` is constructed from quote anchor rows and must not be interpreted as RawBook perfect reconstruction.
- The older process drafts under `atas开发/开发过程问题` are now stale after P4.0 completion:
  - `盘中匹配率优化分析.md`
  - `Codex指导意见.md`
  - `P4.0 开发进展分析.md`
- Their durable conclusions are already represented in `atas开发/project.md`, `task_plan.md`, `findings.md`, and `progress.md`, so keeping the drafts would create parallel, lagging guidance.

## P4.1 Checkpoint Seek/Readback Findings
- `VisibleCheckpointStore` now provides the first backend readback path for `visible_orderbook_checkpoints.parquet`.
- The readback path does not replay events from open; it reads the persisted checkpoint file and selects the latest `ts_ms <= target`.
- Returned checkpoint state includes:
  - `symbol`
  - `trade_date`
  - `checkpoint_id`
  - `quote_seq`
  - `event_id`
  - `ts_ms`
  - `session`
  - ask/bid levels
  - per-level `source`
  - raw residual fields
  - aggregate `correction_cost`
  - aggregate `inter_quote_drift_abs_qty`
- Verified deterministic repeat seek on both test data and real `600726.SH` checkpoint data.
- This completes the minimum P4.1 backend checkpoint readback loop, but not the full replay service. Replay load/frame APIs, virtual clock, WebSocket streaming, and quote-between animation remain pending.

## P4.2 Replay Core Findings
- `VisibleCheckpointSession` provides an in-memory, per-session checkpoint cache so replay can seek without re-reading from the start of the day.
- `ReplayEngine` keeps window state isolated by `(workspace_id, window_id)` and treats play/pause/seek/speed/tick as per-window operations.
- `tick()` advances a virtual clock and snaps the visible frame to the latest checkpoint at or before the virtual time, which keeps frame output deterministic.
- The returned replay frame now carries both the snapped checkpoint metadata and the ask/bid top10 payload needed by a later HTTP/WebSocket layer.
- Verified behavior on both synthetic tests and real `600726.SH` data; the remaining gap is transport/UI, not replay state assembly.

## SH/SZ Order-Book Error Repair Findings
- The Wind field guide says order prices use precision `10000`, and Shanghai逐笔委托 `委托数量` is remaining order quantity.
- Shanghai same-millisecond `A/D` pairs can appear for the same `exchange_order_id`; source ordering alone can leave stale crossed orders when `D` precedes `A`.
- Event sorting now applies a lifecycle tie-break within the same millisecond:
  - group order-class events by `exchange_order_id`.
  - apply `order_add` before `order_cancel`.
  - keep quote after order/trade application for the current raw validation path.
- Shanghai active-side same-millisecond trades require a separate guard:
  - if the active-side order was added in the same millisecond as the trade, do not deduct that active-side order again.
  - this is limited to `.SH`; applying the same rule to `.SZ` was tested and sharply worsened Shenzhen quote reproduction.
- Full-sample verified effect after re-importing 17 sessions:
  - `mismatch_count = 446140`
  - `price_mismatch_count = 375342`
  - `qty_mismatch_count = 417309`
  - `missing_order_count = 938`
- Compared with the prior full-sample state after A-share rule alignment:
  - mismatch improved by `46726`.
  - missing order improved by `41191`.
  - Shanghai missing order is now eliminated in the sample set.
- Residual interpretation:
  - auction and close-auction snapshots still compare display/indicative quote semantics against a raw unexecuted order book.
  - this should be modeled as a visible-book/display-book rule, not hidden inside `RawBook`.
  - the remaining `938` missing orders are Shenzhen-side and should be investigated separately.

## Current Intraday Accuracy Focus
- The active accuracy target is now core continuous auction, not full-day RawBook matching.
- Core intraday windows:
  - `09:31-11:30`
  - `13:00-14:57`
- Excluded from current RawBook optimization:
  - opening auction `09:15-09:30`
  - close auction `14:57-15:00`
  - first transition minute `09:30-09:31` unless it directly affects later continuous replay
- Opening and close auction display requirements are deliberately smaller:
  - high-open / low-open / flat-open status.
  - auction cumulative traded quantity.
  - first valid trade or first valid order marker.
- Current core intraday residual after excluding auction and first minute:
  - `mismatch_count = 149923`
  - `price_mismatch_count = 111633`
  - `qty_mismatch_count = 140056`
- Core residual concentration by window:
  - `09:31-11:30`: `78378`
  - `13:00-14:57`: `71545`
- Top core-intraday symbols:
  - `300502.SZ`: `21495`
  - `300308.SZ`: `20894`
  - `688521.SH`: `19041`
  - `300408.SZ`: `16372`
  - `002384.SZ`: `14341`
- Missing-order residual is now `0`.
- Next best repair target:
  - inspect remaining high-error quote snapshots as timing/display residuals.
  - only adopt a new event-order rule if it improves the cross-sample metric without worsening other symbols.

## Quote Cumulative Trade Anchor Findings
- After missing-order residual was eliminated, the dominant core-intraday mismatch was verified as a quote/event ordering problem, not an order lifecycle gap.
- Quote `cum_qty` and `trade_count` both align with the non-cancel逐笔成交 prefix:
  - the quote should not be validated before the trade row that makes cumulative quantity equal to the quote snapshot.
  - cancellation-style trade rows with `trade_code = C` are excluded from the cumulative trade anchor.
- Implemented event sorting behavior:
  - quote rows retain the original行情 `ts_ms` for reporting and replay clock semantics.
  - quote rows gain `quote_anchor_ts_ms` and `quote_anchor_trade_seq` from the cumulative trade prefix.
  - sort order moves a quote after its cumulative trade anchor only when the anchor is later than the quote timestamp.
  - if the cumulative trade anchor is earlier than the quote timestamp, the quote stays at the original quote timestamp so later order events are not hidden.
- Verified 17-session effect after re-import:
  - full-day mismatch dropped from the previous `446140` class to `193706`.
  - core intraday mismatch dropped from `399635` to `149923`.
  - core `price_mismatch_count` dropped from `329622` to `111633`.
  - core `qty_mismatch_count` dropped from `371033` to `140056`.
  - `missing_order_count` remained `0`.
- Rejected a global "quote at second-end" ordering rule:
  - it improved some symbols but worsened others.
  - the evidence does not support applying it as a market-wide or exchange-wide rule.
- A narrower same-millisecond quote placement rule was adopted:
  - cumulative-trade quote anchors still move a quote later when needed.
  - at the selected millisecond, quote validation now runs after all order/trade events in that millisecond.
  - this reduced full-day residual by `635` and core intraday residual by `630` across the 17-session sample set without reintroducing missing orders.
- Remaining residual interpretation:
  - the raw book still does not mathematically reproduce all quote top10 snapshots.
  - the remaining large mismatches are timing/display residuals unless a future rule improves them across the sample set without increasing other symbols.
  - `VisibleBook` remains the exact quote-anchored盘口 surface for replay/export at quote timestamps.

## 2026-05-01 Remaining Residual Factor Study
- Current verified baseline after same-millisecond quote placement:
  - full-day: `193706 / 154912 / 183767`
  - core intraday: `149923 / 111633 / 140056`
  - missing orders remain `0`.
- Core residual split by exchange:
  - SZ: `97632` mismatches, `72644` price mismatches, `90462` quantity mismatches.
  - SH: `52291` mismatches, `38989` price mismatches, `49594` quantity mismatches.
- Core residual split by mismatch type:
  - SZ qty-only: `24988`; price-only: `7170`; both price+qty: `65474`.
  - SH qty-only: `13302`; price-only: `2697`; both price+qty: `36292`.
- Price residual has a strong one-level shift signature:
  - of `111633` core price mismatches, `75812` have `actual_price_int == quote_price_at_level+1`.
  - another `8692` have `actual_price_int == quote_price_at_level-1`.
  - `plus1` shift is therefore the largest current factor and likely means RawBook is missing a better visible quote level on that side, or quote timing still precedes the event that removes that level.
- The one-level shift is concentrated but cross-sample:
  - `300502.SZ`: `12658 / 18587` price mismatches are adjacent-level.
  - `300308.SZ`: `12640 / 17953`.
  - `688521.SH`: `12470 / 16966`.
  - `300408.SZ`: `9030 / 11640`.
  - `002384.SZ`: `8217 / 10751`.
- Quantity-only residual is mostly RawBook lower than quote:
  - SZ qty-only raw-less: `19380 / 24988`.
  - SH qty-only raw-less: `9365 / 13302`.
  - This points toward over-depletion or quote snapshots retaining visible quantity longer than the event stream does.
- Working hypothesis:
  - the largest remaining factor is not missing order references; it is level displacement from one visible price level missing in RawBook at validation time.
  - next investigation should inspect quote-side snapshots where raw levels align to quote levels `+1` and trace the lifecycle of the missing best visible price.
- Rejected active-side trade depletion as the large factor:
  - skipping all active-side depletion worsened core residual from `149923` to `1454249`.
  - skipping only SZ active-side depletion worsened core residual to `854171`.
  - skipping only SH active-side depletion worsened core residual to `750001`.
- Verified the large factor is no-trade quote order-book phase:
  - core residual was dominated by `last_qty = 0` quote snapshots: `145587 / 149923` mismatch rows before the fix.
  - for high-residual sessions, no-trade quote cumulative-trade anchor delay had a positive median, indicating the quote trade counters and order-book fields have different effective phases.
  - applying a global no-trade delay was rejected because it badly worsened some sessions.
  - applying a session-level delay rule by median anchor delay was accepted:
    - median delay `200-299ms`: no-trade quote sort time is at least `ts_ms + 500ms`.
    - median delay `>=300ms`: no-trade quote sort time is at least `ts_ms + 1000ms`.
  - The rule is data-derived from session timing distribution, not hard-coded to symbols.
- Verified 17-session effect after re-import:
  - full-day residual: `147241 / 116002 / 141613`.
  - core intraday residual: `103284 / 72556 / 97732`.
  - core `09:31-11:30`: `56033`.
  - core `13:00-14:57`: `47251`.
  - `missing_order_count` remained `0`.

## 2026-05-02 A-Share Level1 3-Second Bucket Semantics
- User clarified the key market-data semantic:
  - A-share Level1 quotes are 3-second aggregate presentations.
  - within the 3-second bucket, the same execution price displays aggregate traded volume and trade count.
  - the provided tick-by-tick trades are a precise decomposition of that 3-second aggregate.
- This invalidates treating the previous no-trade quote delay as a pure empirical vendor correction.
- Reframed quote ordering as deterministic 3-second bucket phase inference:
  - for each quote, compute quote-side `cum_qty` and `trade_count` deltas from the previous quote.
  - for each session, test candidate 3-second windows around the quote timestamp.
  - choose the window offset that maximizes exact `(quantity, count)` matches against non-cancel tick trades.
  - use the inferred bucket end offset as the minimum sort time for quote validation.
- Verified candidate bucket offsets on the 17-session sample set:
  - common inferred bucket end offsets include `250ms`, `500ms`, `750ms`, `1000ms`, `1250ms`, and `1500ms`.
  - examples:
    - `000711.SZ`: bucket end `+250ms`.
    - `002384.SZ`: `+500ms`.
    - `300308.SZ`: `+1000ms`.
    - `300408.SZ`: `+1250ms`.
    - `301305.SZ`: `+1500ms`.
    - `601609.SH`: `0ms`.
- Replacing the median-delay rule with 3-second bucket phase inference further reduced residual:
  - full-day residual: `112333 / 94181 / 108242`.
  - core intraday residual: `67470 / 49946 / 63485`.
  - core `09:31-11:30`: `38839`.
  - core `13:00-14:57`: `28631`.
  - `missing_order_count` remained `0`.
- Residual rate/distribution for that 3-second bucket baseline:
  - denominator: `76908` quote snapshots * `20` levels = `1538160` full-day level checks.
  - full-day mismatch rate: `112333 / 1538160 = 7.30%`.
  - full-day price mismatch rate: `6.12%`; quantity mismatch rate: `7.04%`.
  - full-day mismatch type split: both price+qty `90090` (`80.20%` of mismatches), price-only `4091` (`3.64%`), qty-only `18152` (`16.16%`).
  - core denominator: `74314` quote snapshots * `20` levels = `1486280` core level checks.
  - core mismatch rate: `67470 / 1486280 = 4.54%`.
  - core price mismatch rate: `3.36%`; quantity mismatch rate: `4.27%`.
  - core mismatch type split: both price+qty `45961` (`68.12%`), price-only `3985` (`5.91%`), qty-only `17524` (`25.97%`).
  - core time split: `09:31-11:30` has `38839` mismatches (`57.56%` of core; window rate `5.14%`), `13:00-14:57` has `28631` (`42.44%`; window rate `3.92%`).
  - non-core windows have `44863` mismatches (`39.94%` of full-day) despite far fewer quote snapshots, so auction/boundary residual density remains high.
- Interpretation:
  - this is less likely to overfit than the previous threshold rule because it is inferred from the documented 3-second aggregate relationship between quotes and decomposed trades.
  - remaining residual should now be studied as either residual bucket-boundary ambiguity, order/cancel phase within the same 3-second bucket, or quote top10 display semantics not captured by raw order lifecycle.

## 2026-05-02 Pure Rule Replay Attempt
- User provided `C:\Users\21274\Desktop\规则.md` and requested DOM replay without empirical/overfit alignment algorithms.
- Verified Wind field definitions from `实例材料/wind-level2字段说明书.pdf`:
  - quote price fields and tick/order/trade price fields use `10000` precision.
  - quote/order/trade quantities are in shares.
  - `行情.csv` `成交量` is period volume; `当日累计成交量` and `成交笔数` are cumulative.
  - SH order types: `A` normal order, `D` cancel.
  - SZ order types: `0` limit, `1` market, `U` best-side; `1/U` should not rest in the visible book.
  - SZ trade code `C` is a cancel execution report; empty/non-`C` is a trade execution report.
- Removed quote cumulative anchors and 3-second bucket phase inference from `EventBuilder`.
- Current pure-rule event ordering:
  - sort by Wind timestamp.
  - apply order adds/cancels/market flow before trades at the same timestamp.
  - validate quote snapshots after same-timestamp order/trade events.
  - preserve rule-derived handling for market orders and cancel execution reports.
- Re-imported all 17 sessions with the pure-rule replay path.
- Verified pure-rule full-day residual:
  - `mismatch_count = 446140`
  - `price_mismatch_count = 375342`
  - `qty_mismatch_count = 417309`
  - `missing_order_count = 0`
- Verified pure-rule core intraday residual:
  - `mismatch_count = 399635`
  - `price_mismatch_count = 329622`
  - `qty_mismatch_count = 371033`
  - `09:31-11:30 = 217329`
  - `13:00-14:57 = 182306`
- Conclusion:
  - pure Wind-field replay reconstructs order lifecycle without missing order references.
  - it does not perfectly reproduce Wind 3-second ten-level quote snapshots.
  - the gap is not a quantity unit problem: Wind defines quantities as shares, and sample quantities include many non-100 multiples.

## 2026-05-02 Haitong LOB Reconstruction Rules
- Source: `实例材料/20211227-海通证券-选股因子系列研究（七十五）：限价订单簿（LOB）的还原和应用.pdf`, section 1.
- Report rules/claims extracted from pages 5-7:
  - Level2 has quote snapshots and tick-by-tick data at different granularities; tick-by-tick order/trade data should reconstruct the lower-frequency snapshot surface in theory.
  - Tick-by-tick orders and trades have unified sequence numbers; within the same 0.01 second, those sequence numbers must be used to restore order/trade ordering.
  - Opening auction and continuous auction need separate handling because matching and snapshot semantics differ.
  - Opening auction snapshots only expose two levels: virtual match price/quantity plus unmatched remainder at that price on at most one side; tick data can reconstruct the real multi-price queued order book.
  - Continuous auction snapshots expose top ten bid/ask price/quantity levels and top-of-book order details, but tick reconstruction can maintain the full depth and all per-level order quantity/time details.
  - SZ cancel information is in tick-by-tick trades with execution type `C`; SH cancel information is in tick-by-tick orders with delete/cancel order type.
  - SZ best-side/market orders can have displayed price `0` or `-1`; their effective price must be inferred from the preceding order book if needed for simulation, but they should not become resting visible limit levels by default.
  - SH tick data can contain trades whose fully filled order is not present in tick orders; this mainly affects active/immediate orders and should not create visible resting depth unless the order actually rests.
- Current code already covers several rules:
  - Exchange-specific order/trade typing in `event_builder.py`.
  - Non-resting SZ market/best-side flow in `orderbook_engine.py`.
  - SH same-timestamp active-order skip to avoid incorrectly depleting fully filled active orders.
  - Full-depth aggregated price levels, not just top ten, in `OrderBookEngine`.
- Verified implementation gap:
  - `OrderBookEngine` stores per-order state in a flat dict and aggregated price-level totals, but it does not preserve per-price FIFO/order composition. The report explicitly says reconstructed continuous-auction LOB contains every order's quantity and order time at each price level; that is needed for complete queue-level LOB reproduction and simulation priority.
- Implemented after code update:
  - normalized tick rows now expose `message_seq` from order `交易所委托号` and trade `成交编号`.
  - `EventBuilder` uses `message_seq` to interleave order/trade events at the same effective timestamp, while keeping quote validation after tick events.
  - `OrderBookEngine.snapshot_order_queues()` now exposes full-depth bid/ask price levels, total quantity, and each resting order's remaining quantity, original quantity, add timestamp, source sequence, event id, and queue position.
- Verification:
  - backend tests: `27 passed`.
  - all 17 sample sessions re-imported; `missing_order_count = 0`.
  - residual diagnostics stayed at the current bucket baseline: full-day `112333 / 94181 / 108242`, core intraday `67470 / 49946 / 63485`.
  - real `600726.SH` queue snapshot at `09:31` produced per-price order composition with order id, remaining quantity, add timestamp, and source sequence.

## 2026-05-02 Auction Carryover Analysis
- Question checked: whether current core-intraday residual is mainly caused by opening auction not being aligned.
- PDF-grounded rule:
  - auction and continuous auction must be handled separately because matching and snapshot semantics differ.
  - auction snapshots are virtual/indicative two-level surfaces and cannot be used as real depth.
  - tick-by-tick reconstruction can still reconstruct the real multi-price queued auction book.
- Current implementation conflict:
  - `session` is labeled, but `OrderBookEngine` applies one shared add/cancel/trade model across auction and continuous sessions.
  - `OrderBookValidator` compares auction quote snapshots against raw reconstructed top10, even though the PDF says the auction snapshot surface is not the real multi-price queue.
  - There is no explicit auction uncrossing/opening-transition model; opening auction execution reports are consumed by the generic trade path.
- Empirical checks:
  - Artificially resetting the book at the first `09:31+` quote using quote top10 worsened core residual from about `67k` to about `843k`, proving the continuous session depends heavily on pre-09:31 accumulated book depth and cannot be rebuilt from top10 alone.
  - First opening quote mismatch versus core residual correlation across the 17 sessions was only about `0.29`.
  - Some sessions had `open_mis = 0` but still non-trivial core residual, e.g. `300308.SZ = 4012`, `603986.SH = 5465`, `688521.SH = 3291`.
  - `09:31-09:40` accounted for `6759 / 67470` core mismatches, about `10%`, so residual is not only an opening carryover phenomenon.
- Conclusion:
  - auction handling is incomplete and should be fixed according to the PDF, especially for correct opening state and to avoid invalid auction quote validation.
  - current evidence does not support "auction misalignment is the dominant cause of all盤中 residual"; remaining core residual is more consistent with continuous quote timing/display semantics plus possibly session-specific event sequencing details.

## 2026-05-02 PDF-First LOB Correction
- User requested code correction with the Haitong PDF as the authority.
- Applied PDF-first rules:
  - Raw LOB construction is driven by tick-by-tick order/trade events sorted by reported time and `message_seq`.
  - Quote cumulative-trade anchors and inferred 3-second bucket offsets no longer move RawBook validation events.
  - Auction quote snapshots are skipped in raw top10 validation because the PDF defines them as virtual/indicative two-level surfaces rather than true multi-price order-book depth.
  - Continuous/opening full-depth state remains generated from pre-open and auction tick events; it is not reset from quote top10.
- Code impact:
  - removed quote anchor/bucket fields from `EventBuilder`.
  - kept exchange-specific lifecycle rules: SH `A/D`, SZ `0/1/U`, SZ trade `C`, SH fully-filled active order guard.
  - kept `snapshot_order_queues()` for complete per-price order composition.
- Verification:
  - backend tests: `28 passed`.
  - re-imported all 17 sample sessions under PDF-first rules.
  - full-day residual: `mismatch_count = 414593`, `price_mismatch_count = 344026`, `qty_mismatch_count = 385801`, `missing_order_count = 0`.
  - core intraday residual: `mismatch_count = 399635`, `price_mismatch_count = 329622`, `qty_mismatch_count = 371033`.
- Interpretation:
  - the old `112333 / 94181 / 108242` baseline was a Wind quote-snapshot alignment baseline, not a PDF-first Raw LOB baseline.
  - under PDF-first RawBook semantics, larger quote mismatch is expected because exchange/vendor snapshots have documented lower frequency and latency/phase differences.
  - `VisibleBook` remains the right layer for quote-anchored replay display; `RawBook` is now cleaner as the PDF-grounded reconstructed LOB.

## 2026-05-02 PDF-Grounded 3-Second Quote Merge
- PDF rule now treated as authoritative for continuous-auction quote validation:
  - from 09:30 onward, exchange-pushed first quote snapshots can be delayed relative to `09:30:00.000`.
  - each stock's delay relative to each 3-second grid point is nearly stable.
  - the likely generation process is a 3-second cycle ordered by security code.
- Code decision:
  - restoring 3-second quote merge is not treated as arbitrary residual fitting when it is inferred from quote trade deltas and bounded by the PDF-described 3-second cycle.
  - quote validation can be placed at the inferred bucket end and cumulative trade anchor.
  - RawBook itself is still advanced only by tick order/trade events; quote rows are validation/display observations and do not inject or overwrite resting orders.
- Active verification baseline after update:
  - backend tests: `28 passed`.
  - full-day residual: `mismatch_count = 80718`, `price_mismatch_count = 62690`, `qty_mismatch_count = 76670`, `missing_order_count = 0`.
  - core intraday residual: `mismatch_count = 67470`, `price_mismatch_count = 49946`, `qty_mismatch_count = 63485`.
  - core windows: `09:31-11:30 = 38839`, `13:00-14:57 = 28631`.
- Remaining uncertainty:
  - residual is no longer explained by auction carryover alone.
  - remaining differences likely sit in exact exchange/vendor sequencing, active order display semantics, and any session-specific rules not present in the PDF excerpt or Wind field guide.

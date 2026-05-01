# Task Plan

## Goal
End Phase 3 with the expanded high-activity sample set, unify project state, and keep Phase 4 planned around VisibleBook quote-anchor checkpointing without corrupting RawBook semantics.

## Scope
- Include all 17 sample directories under `实例材料/个股数据`.
- Regenerate imports, validation reports, missing-order reports, residual diagnostics, and opening alignment diagnostics.
- Update long-term phase boundaries in `atas开发/project.md` where needed.
- Write final P3 summary.
- Do not implement Phase 4 code in this planning task.
- Do not change RawBook matching logic, event ordering, UI, Heatmap, DOM, or replay service code in this task.

## Revised Phase Boundaries

### Phase 3：Raw 校验与指标口径锁定
- Status: complete.
- Purpose:
  - Keep RawBook as pure order/trade/cancel reconstruction.
  - Produce `validation_report.parquet` and `missing_order_report.parquet`.
  - Report raw residuals by session/window/symbol/reason.
  - Lock metric vocabulary:
    - `raw_match_rate`
    - `quote_anchor_match_rate`
    - `inter_quote_drift`
    - `correction_cost`
  - Establish that盘中 95%+ should not be assigned to RawBook.
- Out of scope:
  - VisibleBook implementation.
  - Replay clock.
  - Checkpoint generation.
  - UI/Heatmap/DOM rendering.

### Phase 4.0：VisibleBook Quote Anchor 内核
- Status: planned.
- Purpose:
  - Add a VisibleBook layer for display/replay state.
  - At quote events, anchor VisibleBook to quote ask/bid top10.
  - Preserve RawBook unchanged and record RawBook-vs-quote residual.
  - Output visible validation/checkpoint artifacts.
- Acceptance:
  - RawBook is not overwritten by quote.
  - No fake order IDs are generated.
  - Quote-anchor visible match rate for `09:31-11:30` and `13:00-14:57` is at least 95%.
  - `inter_quote_drift` and `correction_cost` are recorded.
  - Existing backend tests still pass.

### Phase 4.1：Checkpoint 与 Seek 闭环
- Status: planned.
- Purpose:
  - Persist VisibleBook checkpoint state.
  - Make repeated seek to the same timestamp deterministic.
  - Keep checkpoint files rebuildable from normalized Parquet.
- Acceptance:
  - Seek does not replay from open.
  - Same timestamp produces the same VisibleBook, residual metrics, and trade aggregates.
  - Checkpoint source fields distinguish `quote_anchor`, `event_delta`, `correction`, and raw diagnostics.

### Phase 4.2：Quote 间事件推进
- Status: planned.
- Purpose:
  - Use order/cancel/trade events between quote anchors to animate visible liquidity.
  - Re-anchor at the next quote and record drift/correction cost.
- Acceptance:
  - Inter-quote animation is explicitly labeled as event-derived projection.
  - Drift is measurable before re-anchor.
  - No smoothing window such as 200ms is adopted without evidence.

### Phase 4.3：Raw 排序实验，仅作增强
- Status: deferred.
- Purpose:
  - Evaluate local ordering experiments offline.
  - Only promote a rule if it improves most symbols/windows without raising missing orders or harming trade statistics.
- Out of scope for P4.0:
  - Local sorting search as production replay logic.
  - Fitting event order solely to match quote.

## Success Criteria For This Planning Task
- All 17 samples import successfully.
- Final Phase 3 metrics are generated and recorded.
- `phase3_final_summary.md` exists.
- `atas开发/project.md` reflects the RawBook/VisibleBook boundary.
- P3 no longer promises raw 95% matching.
- P4 defines VisibleBook quote anchor/checkpoint as the path to盘中 95%+.
- Planning files record why P3 is complete and what P4 starts with.
- No code semantics are changed beyond existing diagnostics support.

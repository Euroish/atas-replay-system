# Task Plan

## Goal
Complete `Phase 3.5：订单簿对账收口` for the uploaded multi-symbol sample set. Fix the order-book reconstruction rule that produces inflated missing-order counts, keep the implementation faithful to observed data semantics, and verify the result against quote snapshots without starting Phase 4 replay/checkpoint work.

## Scope
- Work only on backend import/event/order-book/validation logic.
- Use `实例材料/个股数据/*` as the sample input set.
- Do not build UI, replay clock, checkpointing, or quote-overwrite anchoring in this task.
- Keep the external analysis markdown as evidence to verify, not as an authority.

## Phases
1. Re-check current repo state and locate uploaded multi-symbol data - complete
2. Run multi-symbol diagnostics for trade order-id matching and active/passive-side semantics - complete
3. Implement the minimal order-book fix and diagnostic detail needed to explain missing orders - complete
4. Update tests to cover passive-side trade depletion and the new sample location - complete
5. Run backend tests and multi-symbol import validation - complete
6. Record objective findings and remaining uncertainty - complete
7. Add Phase 3.6 residual diagnostics from persisted validation/missing-order reports - complete
8. Add first-open-quote checkpoint reproduction for precise opening alignment - complete

## Success Criteria
- Trade depletion removes only order-book-relevant passive-side liquidity when the active-side order id is not represented as a resting order.
- Missing-order counts drop materially on the uploaded sample set without introducing negative levels or quote overwrites.
- Validation reports are still generated and remain locatable by `ts_ms`, `side`, and `level`.
- Tests cover the corrected trade depletion semantics.
- `findings.md` and `progress.md` record verified metrics objectively.
- Residual diagnostics can be regenerated without modifying order-book reconstruction semantics.
- Opening boundary alignment is explicitly reproducible for every sample symbol.

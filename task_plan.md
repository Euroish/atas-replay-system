# Task Plan

## Goal
Implement `Phase 3：行情快照校验` so the sample session can compare reconstructed top10 bid/ask levels against `行情.csv` snapshots and produce a persisted validation report with inspectable summary metrics.

## Scope
- Work only on backend validation against quote snapshots.
- Reuse the existing `events.parquet` and `OrderBookEngine`.
- Do not start checkpointing, replay service, or frontend display work yet.

## Phases
1. Read `project.md` Phase 3 constraints and inspect the current backend interfaces - complete
2. Confirm the quote schema and available top10 fields for validation - complete
3. Implement `validator.py` and generate `validation_report.parquet` - complete
4. Wire validation summary into the import output - complete
5. Add tests and run real sample verification - complete

## Success Criteria
- `validation_report.parquet` is generated for the sample session.
- The report can locate mismatches by `ts_ms`, `side`, and `level`.
- Import output includes a usable validation summary.
- Tests cover report generation and summary counts.

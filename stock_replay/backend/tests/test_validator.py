from __future__ import annotations

from pathlib import Path

import polars as pl

from stock_replay_backend.validator import OrderBookValidator


def test_validator_generates_mismatch_report_and_summary() -> None:
    base = Path(r"E:\atas回放系统\stock_replay\data\processed\symbol=600726.SH\date=20260424")
    quotes = pl.read_parquet(base / "quotes.parquet")
    events = pl.read_parquet(base / "events.parquet")

    result = OrderBookValidator().validate(events, quotes)

    assert {"quote_seq", "ts_ms", "side", "level", "expected_price_int", "actual_price_int"}.issubset(
        result.report.columns
    )
    assert result.summary.checked_quotes == quotes.height
    assert result.summary.mismatch_count == result.report.height
    assert result.summary.price_mismatch_count >= 0
    assert result.summary.qty_mismatch_count >= 0
    assert result.summary.missing_order_count >= 0


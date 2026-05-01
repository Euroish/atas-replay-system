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


def test_validator_treats_zero_quote_level_and_missing_book_level_as_empty() -> None:
    quote_row = {
        "symbol": "sample",
        "exchange_code": "sample",
        "trade_date": 20260101,
        "time_raw": 93000000,
        "ts_ms": 34200000,
        "session": "continuous_am",
        "seq": 1,
        "last_price_int": 0,
        "last_qty": 0,
        "last_amount": 0,
        "trade_count": 0,
        "cum_qty": 0,
        "cum_amount": 0,
        "high_int": 0,
        "low_int": 0,
        "open_int": 0,
        "prev_close_int": 0,
        "price_scale": 1000,
    }
    for side in ("ask", "bid"):
        for level in range(1, 11):
            quote_row[f"{side}_price_{level}_int"] = 0
            quote_row[f"{side}_qty_{level}"] = 0

    quotes = pl.DataFrame([quote_row])
    events = pl.DataFrame(
        [
            {
                "event_id": 1,
                "symbol": "sample",
                "exchange_code": "sample",
                "trade_date": 20260101,
                "session": "continuous_am",
                "ts_ms": 34200000,
                "event_type": "quote",
                "priority": 3,
                "source_seq": 1,
                "payload_ref": "quotes:1",
            }
        ]
    )

    result = OrderBookValidator().validate(events, quotes)

    assert result.report.is_empty()
    assert result.summary.mismatch_count == 0

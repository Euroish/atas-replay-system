from __future__ import annotations

import polars as pl

from stock_replay_backend.visible_book import VisibleBookBuilder


def test_visible_book_anchors_quote_without_overwriting_raw_residual() -> None:
    quote_row = {
        "symbol": "sample",
        "exchange_code": "sample",
        "trade_date": 20260101,
        "time_raw": 93100000,
        "ts_ms": 34260000,
        "session": "continuous_am",
        "seq": 1,
        "last_price_int": 1000,
        "last_qty": 0,
        "last_amount": 0,
        "trade_count": 0,
        "cum_qty": 0,
        "cum_amount": 0,
        "high_int": 1000,
        "low_int": 1000,
        "open_int": 1000,
        "prev_close_int": 1000,
        "price_scale": 10_000,
    }
    for side in ("ask", "bid"):
        for level in range(1, 11):
            quote_row[f"{side}_price_{level}_int"] = 0
            quote_row[f"{side}_qty_{level}"] = 0
    quote_row["ask_price_1_int"] = 1010
    quote_row["ask_qty_1"] = 20

    events = pl.DataFrame(
        [
            {
                "event_id": 1,
                "symbol": "sample",
                "exchange_code": "sample",
                "trade_date": 20260101,
                "session": "continuous_am",
                "ts_ms": 34259900,
                "event_type": "order_add",
                "priority": 1,
                "source_seq": 1,
                "payload_ref": "orders:1",
                "exchange_order_id": "ask-1",
                "side": "S",
                "price_int": 1010,
                "qty": 15,
            },
            {
                "event_id": 2,
                "symbol": "sample",
                "exchange_code": "sample",
                "trade_date": 20260101,
                "session": "continuous_am",
                "ts_ms": 34260000,
                "event_type": "quote",
                "priority": 3,
                "source_seq": 1,
                "payload_ref": "quotes:1",
            },
        ]
    )

    result = VisibleBookBuilder().build(events, pl.DataFrame([quote_row]))
    ask_1 = result.checkpoints.filter((pl.col("side") == "ask") & (pl.col("level") == 1)).to_dicts()[0]

    assert result.summary.checked_quotes == 1
    assert result.summary.checkpoint_rows == 20
    assert result.summary.quote_anchor_match_rate == 1.0
    assert ask_1["source"] == "quote_anchor"
    assert ask_1["visible_price_int"] == 1010
    assert ask_1["visible_qty"] == 20
    assert ask_1["raw_price_int"] == 1010
    assert ask_1["raw_qty"] == 15
    assert ask_1["raw_qty_match"] is False
    assert ask_1["correction_abs_qty"] == 5

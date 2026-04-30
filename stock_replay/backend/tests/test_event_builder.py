from __future__ import annotations

from pathlib import Path

import polars as pl

from stock_replay_backend.event_builder import EventBuilder


def test_event_builder_creates_stable_sorted_events() -> None:
    base = Path(r"E:\atas回放系统\stock_replay\data\processed\symbol=600726.SH\date=20260424")
    quotes = pl.read_parquet(base / "quotes.parquet")
    orders = pl.read_parquet(base / "orders.parquet")
    trades = pl.read_parquet(base / "trades.parquet")

    result = EventBuilder().build(quotes, orders, trades)
    events = result.events

    assert events.height == quotes.height + orders.height + trades.height
    assert {"event_id", "event_type", "ts_ms", "priority", "source_seq", "payload_ref"}.issubset(events.columns)
    assert events["event_id"][0] == 1

    preview = events.head(50).select(["ts_ms", "priority", "source_seq"]).rows()
    assert preview == sorted(preview)
    assert "converted 4 order rows into session events" in result.warnings


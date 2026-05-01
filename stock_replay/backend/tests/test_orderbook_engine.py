from __future__ import annotations

from pathlib import Path

import polars as pl

from stock_replay_backend.orderbook_engine import OrderBookEngine


def test_orderbook_engine_handles_add_cancel_trade_and_missing_orders() -> None:
    engine = OrderBookEngine()
    engine.apply_events(
        [
            {"event_id": 1, "event_type": "order_add", "exchange_order_id": "bid-1", "side": "B", "price_int": 100, "qty": 10, "ts_ms": 1},
            {"event_id": 2, "event_type": "order_add", "exchange_order_id": "ask-1", "side": "S", "price_int": 101, "qty": 8, "ts_ms": 2},
            {"event_id": 3, "event_type": "trade", "aggressor_side": "B", "ask_order_id": "ask-1", "bid_order_id": "bid-1", "qty": 3, "ts_ms": 3},
            {"event_id": 4, "event_type": "order_cancel", "exchange_order_id": "bid-1", "qty": 7, "ts_ms": 4},
            {"event_id": 5, "event_type": "trade", "aggressor_side": "B", "ask_order_id": "missing", "bid_order_id": "", "qty": 1, "ts_ms": 5},
        ]
    )

    snapshot = engine.snapshot_top_levels()
    assert snapshot["bids"] == []
    assert snapshot["asks"][0].price_int == 101
    assert snapshot["asks"][0].qty == 5
    assert engine.missing_order_log
    assert all(level.qty >= 0 for side in snapshot.values() for level in side)


def test_orderbook_engine_does_not_count_missing_active_trade_order() -> None:
    engine = OrderBookEngine()
    engine.apply_events(
        [
            {"event_id": 1, "event_type": "order_add", "exchange_order_id": "ask-1", "side": "S", "price_int": 101, "qty": 10, "ts_ms": 1},
            {"event_id": 2, "event_type": "trade", "aggressor_side": "B", "ask_order_id": "ask-1", "bid_order_id": "missing-active", "qty": 4, "ts_ms": 2},
        ]
    )

    snapshot = engine.snapshot_top_levels()
    assert snapshot["asks"][0].qty == 6
    assert engine.missing_order_log == []


def test_orderbook_engine_removes_active_trade_order_when_it_is_resting() -> None:
    engine = OrderBookEngine()
    engine.apply_events(
        [
            {"event_id": 1, "event_type": "order_add", "exchange_order_id": "bid-1", "side": "B", "price_int": 100, "qty": 6, "ts_ms": 1},
            {"event_id": 2, "event_type": "order_add", "exchange_order_id": "ask-1", "side": "S", "price_int": 101, "qty": 10, "ts_ms": 1},
            {"event_id": 3, "event_type": "trade", "aggressor_side": "B", "ask_order_id": "ask-1", "bid_order_id": "bid-1", "qty": 4, "ts_ms": 2},
        ]
    )

    snapshot = engine.snapshot_top_levels()
    assert snapshot["bids"][0].qty == 2
    assert snapshot["asks"][0].qty == 6
    assert engine.missing_order_log == []


def test_orderbook_engine_can_build_top10_from_sample_events() -> None:
    base = Path(r"E:\atas回放系统\stock_replay\data\processed\symbol=600726.SH\date=20260424")
    events = pl.read_parquet(base / "events.parquet")
    selected = events.filter(pl.col("ts_ms") <= 33905000).iter_rows(named=True)

    engine = OrderBookEngine()
    engine.apply_events(selected)
    snapshot = engine.snapshot_top_levels(depth=10)

    assert len(snapshot["bids"]) <= 10
    assert len(snapshot["asks"]) <= 10
    assert all(level.qty >= 0 for side in snapshot.values() for level in side)

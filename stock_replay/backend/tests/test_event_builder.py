from __future__ import annotations

from pathlib import Path

import polars as pl

from stock_replay_backend.event_builder import EventBuilder
from stock_replay_backend.orderbook_engine import OrderBookEngine


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

    quote_events = events.filter(pl.col("event_type") == "quote")
    assert "quote_bucket_end_offset_ms" in quote_events.columns
    assert quote_events.select(pl.col("quote_bucket_end_offset_ms").n_unique()).item() == 1
    assert "quote_anchor_ts_ms" in quote_events.columns
    assert "converted 4 order rows into session events" in result.warnings


def test_event_builder_closes_same_timestamp_add_cancel_pairs() -> None:
    quotes = _quote_frame(ts_ms=1000)
    orders = pl.DataFrame(
        [
            _order_row(ts_ms=900, seq=1, order_id="sh-1", order_type="D", side="B", price_int=10000, qty=100),
            _order_row(ts_ms=900, seq=2, order_id="sh-1", order_type="A", side="B", price_int=10000, qty=100),
        ]
    )
    trades = _empty_trades()

    events = EventBuilder().build(quotes, orders, trades).events
    order_refs = events.filter(pl.col("payload_ref").str.starts_with("orders:")).get_column("payload_ref").to_list()
    assert order_refs == ["orders:2", "orders:1"]

    engine = OrderBookEngine()
    engine.apply_events(events.iter_rows(named=True))
    snapshot = engine.snapshot_top_levels()
    assert snapshot["bids"] == []
    assert snapshot["asks"] == []


def test_event_builder_treats_shenzhen_market_orders_as_non_resting_flow() -> None:
    quotes = _quote_frame(symbol="000001.SZ", exchange_code="000001", ts_ms=1000)
    orders = pl.DataFrame(
        [
            _order_row(
                symbol="000001.SZ",
                exchange_code="000001",
                ts_ms=900,
                seq=1,
                order_id="101",
                order_type="1",
                side="B",
                price_int=0,
                qty=100,
            ),
            _order_row(
                symbol="000001.SZ",
                exchange_code="000001",
                ts_ms=910,
                seq=2,
                order_id="102",
                order_type="U",
                side="S",
                price_int=0,
                qty=200,
            ),
        ]
    )
    trades = _empty_trades()

    events = EventBuilder().build(quotes, orders, trades).events

    assert events.filter(pl.col("payload_ref") == "orders:1").item(0, "event_type") == "market_order"
    assert events.filter(pl.col("payload_ref") == "orders:2").item(0, "event_type") == "market_order"

    engine = OrderBookEngine()
    engine.apply_events(events.iter_rows(named=True))
    snapshot = engine.snapshot_top_levels()
    assert snapshot["bids"] == []
    assert snapshot["asks"] == []


def test_event_builder_treats_shenzhen_trade_code_c_as_trade_cancel() -> None:
    quotes = _quote_frame(symbol="000001.SZ", exchange_code="000001", ts_ms=1000)
    orders = pl.DataFrame(
        [
            _order_row(
                symbol="000001.SZ",
                exchange_code="000001",
                ts_ms=900,
                seq=1,
                order_id="201",
                order_type="0",
                side="B",
                price_int=10000,
                qty=100,
            )
        ]
    )
    trades = pl.DataFrame(
        [
            _trade_row(
                symbol="000001.SZ",
                exchange_code="000001",
                ts_ms=950,
                seq=1,
                trade_id="301",
                trade_code="C",
                aggressor_side="",
                price_int=0,
                qty=100,
                ask_order_id="0",
                bid_order_id="201",
            )
        ]
    )

    events = EventBuilder().build(quotes, orders, trades).events
    trade_cancel = events.filter(pl.col("payload_ref") == "trades:1")
    assert trade_cancel.item(0, "event_type") == "trade_cancel"
    assert trade_cancel.item(0, "exchange_order_id") == "201"

    engine = OrderBookEngine()
    engine.apply_events(events.iter_rows(named=True))
    snapshot = engine.snapshot_top_levels()
    assert snapshot["bids"] == []
    assert snapshot["asks"] == []


def test_event_builder_checks_quote_after_same_timestamp_order_and_trade_events() -> None:
    quotes = _quote_frame(symbol="000001.SZ", exchange_code="000001", ts_ms=1000)
    orders = pl.DataFrame(
        [
            _order_row(
                symbol="000001.SZ",
                exchange_code="000001",
                ts_ms=1000,
                seq=1,
                order_id="203",
                order_type="0",
                side="B",
                price_int=9900,
                qty=100,
            )
        ]
    )
    trades = pl.DataFrame(
        [
            _trade_row(
                symbol="000001.SZ",
                exchange_code="000001",
                ts_ms=1000,
                seq=1,
                trade_id="301",
                trade_code="0",
                aggressor_side="B",
                price_int=10000,
                qty=100,
                ask_order_id="201",
                bid_order_id="202",
            )
        ]
    )

    events = EventBuilder().build(quotes, orders, trades).events
    assert events.get_column("payload_ref").to_list() == ["orders:1", "trades:1", "quotes:1"]


def test_event_builder_uses_unified_message_sequence_for_tick_ordering() -> None:
    quotes = _quote_frame(symbol="000001.SZ", exchange_code="000001", ts_ms=1000)
    orders = pl.DataFrame(
        [
            _order_row(
                symbol="000001.SZ",
                exchange_code="000001",
                ts_ms=1000,
                seq=1,
                order_id="101",
                order_type="0",
                side="B",
                price_int=9900,
                qty=100,
            )
        ]
    )
    trades = pl.DataFrame(
        [
            _trade_row(
                symbol="000001.SZ",
                exchange_code="000001",
                ts_ms=1000,
                seq=1,
                trade_id="100",
                trade_code="0",
                aggressor_side="B",
                price_int=10000,
                qty=100,
                ask_order_id="99",
                bid_order_id="98",
            )
        ]
    )

    events = EventBuilder().build(quotes, orders, trades).events

    assert events.get_column("payload_ref").to_list() == ["trades:1", "orders:1", "quotes:1"]
    assert events.filter(pl.col("payload_ref") == "orders:1").item(0, "message_seq") == 101
    assert events.filter(pl.col("payload_ref") == "trades:1").item(0, "message_seq") == 100


def test_event_builder_applies_three_second_quote_merge_phase() -> None:
    quote_rows = []
    trade_rows = []
    for seq in range(1, 4):
        ts_ms = 34_260_000 + (seq * 3000)
        quote_rows.append(
            {
                "symbol": "000001.SZ",
                "exchange_code": "000001",
                "trade_date": 20260101,
                "session": "continuous_am",
                "ts_ms": ts_ms,
                "seq": seq,
                "last_price_int": 10000,
                "last_qty": 0,
                "cum_qty": seq * 100,
                "trade_count": seq,
            }
        )
        trade_rows.append(
            _trade_row(
                symbol="000001.SZ",
                exchange_code="000001",
                ts_ms=ts_ms - 1900,
                seq=seq,
                trade_id=str(seq),
                trade_code="0",
                aggressor_side="B",
                price_int=10000,
                qty=100,
                ask_order_id=str(seq),
                bid_order_id=str(seq + 10),
            )
        )
    quotes = pl.DataFrame(quote_rows)
    orders = pl.DataFrame(
        [
            _order_row(
                symbol="000001.SZ",
                exchange_code="000001",
                ts_ms=34_263_700,
                seq=1,
                order_id="later-order",
                order_type="0",
                side="B",
                price_int=9900,
                qty=100,
            )
        ]
    )
    trades = pl.DataFrame(trade_rows)

    events = EventBuilder().build(quotes, orders, trades).events
    refs = events.get_column("payload_ref").to_list()
    quote = events.filter(pl.col("payload_ref") == "quotes:1")

    assert refs.index("orders:1") < refs.index("quotes:1")
    assert quote.item(0, "ts_ms") == 34_263_000
    assert quote.item(0, "quote_anchor_ts_ms") == 34_261_100
    assert quote.item(0, "quote_bucket_end_offset_ms") == 1000


def _quote_frame(
    *,
    symbol: str = "600000.SH",
    exchange_code: str = "600000",
    ts_ms: int,
) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "symbol": symbol,
                "exchange_code": exchange_code,
                "trade_date": 20260101,
                "session": "continuous_am",
                "ts_ms": ts_ms,
                "seq": 1,
                "last_price_int": 10000,
                "last_qty": 0,
            }
        ]
    )


def _order_row(
    *,
    symbol: str = "600000.SH",
    exchange_code: str = "600000",
    ts_ms: int,
    seq: int,
    order_id: str,
    order_type: str,
    side: str,
    price_int: int,
    qty: int,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "exchange_code": exchange_code,
        "trade_date": 20260101,
        "session": "continuous_am",
        "ts_ms": ts_ms,
        "seq": seq,
        "exchange_order_id": order_id,
        "order_no": "0",
        "order_type": order_type,
        "side": side,
        "price_int": price_int,
        "qty": qty,
    }


def _trade_row(
    *,
    symbol: str,
    exchange_code: str,
    ts_ms: int,
    seq: int,
    trade_id: str,
    trade_code: str,
    aggressor_side: str,
    price_int: int,
    qty: int,
    ask_order_id: str,
    bid_order_id: str,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "exchange_code": exchange_code,
        "trade_date": 20260101,
        "session": "continuous_am",
        "ts_ms": ts_ms,
        "seq": seq,
        "trade_id": trade_id,
        "trade_code": trade_code,
        "aggressor_side": aggressor_side,
        "price_int": price_int,
        "qty": qty,
        "ask_order_id": ask_order_id,
        "bid_order_id": bid_order_id,
    }


def _empty_trades() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "symbol": pl.String,
            "exchange_code": pl.String,
            "trade_date": pl.Int64,
            "session": pl.String,
            "ts_ms": pl.Int64,
            "seq": pl.Int64,
            "trade_id": pl.String,
            "trade_code": pl.String,
            "aggressor_side": pl.String,
            "price_int": pl.Int64,
            "qty": pl.Int64,
            "ask_order_id": pl.String,
            "bid_order_id": pl.String,
        }
    )

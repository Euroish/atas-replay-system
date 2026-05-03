from __future__ import annotations

import polars as pl

from stock_replay_backend.quote_aligned_validator import (
    L1L2BookAlignmentEvaluator,
    QuoteAlignedValidator,
    SurfaceQuoteAlignmentEvaluator,
    ThreeSecondBucketEvaluator,
)


def test_quote_aligned_validator_scores_bounded_future_candidate_without_changing_current() -> None:
    events = pl.DataFrame(
        [
            _event(1, "quote", 1000, "quotes:1", source_seq=1),
            _event(
                2,
                "order_add",
                1001,
                "orders:1",
                source_seq=1,
                exchange_order_id="1",
                side="B",
                price_int=10000,
                qty=100,
            ),
        ]
    )
    quotes = pl.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "exchange_code": "000001",
                "trade_date": 20260101,
                "session": "continuous_am",
                "ts_ms": 1000,
                "seq": 1,
                "bid_price_1_int": 10000,
                "bid_qty_1": 100,
                **_empty_levels("bid", start=2),
                **_empty_levels("ask", start=1),
            }
        ]
    )

    result = QuoteAlignedValidator(max_past_ticks=0, max_future_ticks=1, max_future_ms=10, core_intraday_only=False).validate(
        events,
        quotes,
    )

    assert result.summary.checked_quotes == 1
    assert result.summary.current_mismatch_count == 1
    assert result.summary.aligned_mismatch_count == 0
    assert result.report.item(0, "selected_label") == "future"
    assert result.report.item(0, "selected_event_delta") == 1


def test_surface_quote_alignment_evaluator_uses_persisted_current_surface(tmp_path) -> None:
    session_dir = tmp_path / "symbol=000001.SZ" / "date=20260101"
    session_dir.mkdir(parents=True)
    events = pl.DataFrame(
        [
            _event(1, "quote", 34_260_000, "quotes:1", source_seq=1),
            _event(
                2,
                "order_add",
                34_260_001,
                "orders:1",
                source_seq=1,
                exchange_order_id="1",
                side="B",
                price_int=10000,
                qty=100,
            ),
        ]
    )
    quotes = pl.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "exchange_code": "000001",
                "trade_date": 20260101,
                "session": "continuous_am",
                "ts_ms": 34_260_000,
                "seq": 1,
                "bid_price_1_int": 10000,
                "bid_qty_1": 100,
                **_empty_levels("bid", start=2),
                **_empty_levels("ask", start=1),
            }
        ]
    )
    validation_report = pl.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "trade_date": 20260101,
                "quote_seq": 1,
                "event_id": 1,
                "ts_ms": 34_260_000,
                "side": "bid",
                "level": 1,
                "expected_price_int": 10000,
                "actual_price_int": None,
                "expected_qty": 100,
                "actual_qty": None,
                "price_match": False,
                "qty_match": False,
            }
        ],
        schema={
            "symbol": pl.String,
            "trade_date": pl.Int64,
            "quote_seq": pl.Int64,
            "event_id": pl.Int64,
            "ts_ms": pl.Int64,
            "side": pl.String,
            "level": pl.Int64,
            "expected_price_int": pl.Int64,
            "actual_price_int": pl.Int64,
            "expected_qty": pl.Int64,
            "actual_qty": pl.Int64,
            "price_match": pl.Boolean,
            "qty_match": pl.Boolean,
        },
    )
    events.write_parquet(session_dir / "events.parquet")
    quotes.write_parquet(session_dir / "quotes.parquet")
    validation_report.write_parquet(session_dir / "validation_report.parquet")

    result = SurfaceQuoteAlignmentEvaluator(max_future_ticks=1, max_future_ms=10).evaluate_session(session_dir)

    assert result.summary.current_mismatch_count == 1
    assert result.summary.aligned_mismatch_count == 0
    assert result.report.item(0, "selected_label") == "future_surface"


def test_three_second_bucket_evaluator_scores_tick_and_book_alignment(tmp_path) -> None:
    session_dir = tmp_path / "symbol=000001.SZ" / "date=20260101"
    session_dir.mkdir(parents=True)
    quotes = pl.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "exchange_code": "000001",
                "trade_date": 20260101,
                "session": "continuous_am",
                "ts_ms": 34_260_000,
                "seq": 1,
                "cum_qty": 0,
                "trade_count": 0,
                "quote_bucket_end_offset_ms": 0,
            },
            {
                "symbol": "000001.SZ",
                "exchange_code": "000001",
                "trade_date": 20260101,
                "session": "continuous_am",
                "ts_ms": 34_263_000,
                "seq": 2,
                "cum_qty": 100,
                "trade_count": 1,
                "quote_bucket_end_offset_ms": 0,
            },
        ]
    )
    trades = pl.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "exchange_code": "000001",
                "trade_date": 20260101,
                "session": "continuous_am",
                "ts_ms": 34_260_250,
                "seq": 1,
                "trade_code": "0",
                "qty": 100,
            }
        ]
    )
    events = pl.DataFrame(
        [
            {
                "event_id": 1,
                "event_type": "quote",
                "source_seq": 1,
                "quote_bucket_end_offset_ms": 0,
                "quote_anchor_ts_ms": None,
                "quote_anchor_trade_seq": None,
            },
            {
                "event_id": 2,
                "event_type": "quote",
                "source_seq": 2,
                "quote_bucket_end_offset_ms": 0,
                "quote_anchor_ts_ms": None,
                "quote_anchor_trade_seq": None,
            },
        ],
        schema={
            "event_id": pl.Int64,
            "event_type": pl.String,
            "source_seq": pl.Int64,
            "quote_bucket_end_offset_ms": pl.Int64,
            "quote_anchor_ts_ms": pl.Int64,
            "quote_anchor_trade_seq": pl.Int64,
        },
    )
    validation_report = pl.DataFrame(
        [
            {
                "quote_seq": 2,
                "ts_ms": 34_263_000,
            }
        ]
    )
    quotes.write_parquet(session_dir / "quotes.parquet")
    events.write_parquet(session_dir / "events.parquet")
    trades.write_parquet(session_dir / "trades.parquet")
    validation_report.write_parquet(session_dir / "validation_report.parquet")

    report = ThreeSecondBucketEvaluator().evaluate_session(session_dir)

    assert report.height == 1
    assert report.item(0, "expected_bucket_qty") == 100
    assert report.item(0, "current_bucket_qty") == 100
    assert report.item(0, "book_mismatch_count") == 1


def test_l1_l2_book_alignment_evaluator_compares_bucket_endpoint_books(tmp_path) -> None:
    session_dir = tmp_path / "symbol=000001.SZ" / "date=20260101"
    session_dir.mkdir(parents=True)
    quotes = pl.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "exchange_code": "000001",
                "trade_date": 20260101,
                "session": "continuous_am",
                "ts_ms": 34_260_000,
                "seq": 1,
                "cum_qty": 0,
                "trade_count": 0,
                "bid_price_1_int": 0,
                "bid_qty_1": 0,
                **_empty_levels("bid", start=2),
                **_empty_levels("ask", start=1),
            },
            {
                "symbol": "000001.SZ",
                "exchange_code": "000001",
                "trade_date": 20260101,
                "session": "continuous_am",
                "ts_ms": 34_263_000,
                "seq": 2,
                "cum_qty": 0,
                "trade_count": 0,
                "bid_price_1_int": 10000,
                "bid_qty_1": 100,
                **_empty_levels("bid", start=2),
                **_empty_levels("ask", start=1),
            },
        ]
    )
    events = pl.DataFrame(
        [
            _event(1, "quote", 34_260_000, "quotes:1", source_seq=1),
            _event(
                2,
                "order_add",
                34_262_800,
                "orders:1",
                source_seq=1,
                exchange_order_id="1",
                side="B",
                price_int=10000,
                qty=100,
            ),
            _event(3, "quote", 34_263_000, "quotes:2", source_seq=2),
        ]
    )
    trades = pl.DataFrame(
        schema={
            "symbol": pl.String,
            "exchange_code": pl.String,
            "trade_date": pl.Int64,
            "session": pl.String,
            "ts_ms": pl.Int64,
            "seq": pl.Int64,
            "trade_code": pl.String,
            "qty": pl.Int64,
        }
    )
    quotes.write_parquet(session_dir / "quotes.parquet")
    events.write_parquet(session_dir / "events.parquet")
    trades.write_parquet(session_dir / "trades.parquet")
    pl.DataFrame(schema={"quote_seq": pl.Int64}).write_parquet(session_dir / "validation_report.parquet")

    result = L1L2BookAlignmentEvaluator(offsets_ms=(0, -250)).evaluate_session(session_dir)

    row = result.report.filter(pl.col("quote_seq") == 2)
    assert row.item(0, "current_mismatch_count") == 0
    assert row.item(0, "aligned_mismatch_count") == 0


def test_l1_l2_book_current_uses_quote_event_boundary(tmp_path) -> None:
    session_dir = tmp_path / "symbol=000001.SZ" / "date=20260101"
    session_dir.mkdir(parents=True)
    quotes = pl.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "exchange_code": "000001",
                "trade_date": 20260101,
                "session": "continuous_am",
                "ts_ms": 34_260_000,
                "seq": 1,
                "cum_qty": 0,
                "trade_count": 0,
                "bid_price_1_int": 0,
                "bid_qty_1": 0,
                **_empty_levels("bid", start=2),
                **_empty_levels("ask", start=1),
            },
            {
                "symbol": "000001.SZ",
                "exchange_code": "000001",
                "trade_date": 20260101,
                "session": "continuous_am",
                "ts_ms": 34_263_000,
                "seq": 2,
                "cum_qty": 0,
                "trade_count": 0,
                "bid_price_1_int": 0,
                "bid_qty_1": 0,
                **_empty_levels("bid", start=2),
                **_empty_levels("ask", start=1),
            },
        ]
    )
    events = pl.DataFrame(
        [
            _event(1, "quote", 34_260_000, "quotes:1", source_seq=1),
            {
                **_event(2, "quote", 34_263_000, "quotes:2", source_seq=2),
                "quote_bucket_end_offset_ms": 750,
            },
            _event(
                3,
                "order_add",
                34_263_400,
                "orders:1",
                source_seq=1,
                exchange_order_id="1",
                side="B",
                price_int=10000,
                qty=100,
            ),
        ]
    )
    trades = pl.DataFrame(
        schema={
            "symbol": pl.String,
            "exchange_code": pl.String,
            "trade_date": pl.Int64,
            "session": pl.String,
            "ts_ms": pl.Int64,
            "seq": pl.Int64,
            "trade_code": pl.String,
            "qty": pl.Int64,
        }
    )
    quotes.write_parquet(session_dir / "quotes.parquet")
    events.write_parquet(session_dir / "events.parquet")
    trades.write_parquet(session_dir / "trades.parquet")
    pl.DataFrame(schema={"quote_seq": pl.Int64}).write_parquet(session_dir / "validation_report.parquet")

    result = L1L2BookAlignmentEvaluator(offsets_ms=(0,)).evaluate_session(session_dir)

    row = result.report.filter(pl.col("quote_seq") == 2)
    assert row.item(0, "current_mismatch_count") == 0


def test_l1_l2_book_guard_rejects_worse_tick_bucket(tmp_path) -> None:
    session_dir = tmp_path / "symbol=000001.SZ" / "date=20260101"
    session_dir.mkdir(parents=True)
    quotes = pl.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "exchange_code": "000001",
                "trade_date": 20260101,
                "session": "continuous_am",
                "ts_ms": 34_260_000,
                "seq": 1,
                "cum_qty": 0,
                "trade_count": 0,
                "bid_price_1_int": 0,
                "bid_qty_1": 0,
                **_empty_levels("bid", start=2),
                **_empty_levels("ask", start=1),
            },
            {
                "symbol": "000001.SZ",
                "exchange_code": "000001",
                "trade_date": 20260101,
                "session": "continuous_am",
                "ts_ms": 34_263_000,
                "seq": 2,
                "cum_qty": 100,
                "trade_count": 1,
                "bid_price_1_int": 10100,
                "bid_qty_1": 100,
                **_empty_levels("bid", start=2),
                **_empty_levels("ask", start=1),
            },
        ]
    )
    events = pl.DataFrame(
        [
            _event(1, "quote", 34_260_000, "quotes:1", source_seq=1),
            _event(
                2,
                "order_add",
                34_262_900,
                "orders:1",
                source_seq=1,
                exchange_order_id="1",
                side="B",
                price_int=10000,
                qty=100,
            ),
            {
                **_event(3, "quote", 34_263_000, "quotes:2", source_seq=2),
                "quote_bucket_end_offset_ms": 0,
            },
            _event(
                4,
                "order_add",
                34_263_100,
                "orders:2",
                source_seq=2,
                exchange_order_id="2",
                side="B",
                price_int=10100,
                qty=100,
            ),
        ]
    )
    trades = pl.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "exchange_code": "000001",
                "trade_date": 20260101,
                "session": "continuous_am",
                "ts_ms": 34_262_800,
                "seq": 1,
                "trade_code": "0",
                "qty": 100,
            },
            {
                "symbol": "000001.SZ",
                "exchange_code": "000001",
                "trade_date": 20260101,
                "session": "continuous_am",
                "ts_ms": 34_263_100,
                "seq": 2,
                "trade_code": "0",
                "qty": 999,
            },
        ]
    )
    quotes.write_parquet(session_dir / "quotes.parquet")
    events.write_parquet(session_dir / "events.parquet")
    trades.write_parquet(session_dir / "trades.parquet")
    pl.DataFrame(schema={"quote_seq": pl.Int64}).write_parquet(session_dir / "validation_report.parquet")

    result = L1L2BookAlignmentEvaluator(
        offsets_ms=(0, 250),
        selection="book_with_tick_guard",
    ).evaluate_session(session_dir)

    row = result.report.filter(pl.col("quote_seq") == 2)
    assert row.item(0, "selected_event_delta") == 0
    assert row.item(0, "aligned_mismatch_count") == row.item(0, "current_mismatch_count")


def test_l1_l2_book_uses_market_specific_offsets(tmp_path) -> None:
    session_dir = tmp_path / "symbol=000001.SZ" / "date=20260101"
    session_dir.mkdir(parents=True)
    quotes = pl.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "exchange_code": "000001",
                "trade_date": 20260101,
                "session": "continuous_am",
                "ts_ms": 34_260_000,
                "seq": 1,
                "cum_qty": 0,
                "trade_count": 0,
                "bid_price_1_int": 0,
                "bid_qty_1": 0,
                **_empty_levels("bid", start=2),
                **_empty_levels("ask", start=1),
            },
            {
                "symbol": "000001.SZ",
                "exchange_code": "000001",
                "trade_date": 20260101,
                "session": "continuous_am",
                "ts_ms": 34_263_000,
                "seq": 2,
                "cum_qty": 0,
                "trade_count": 0,
                "bid_price_1_int": 10000,
                "bid_qty_1": 100,
                **_empty_levels("bid", start=2),
                **_empty_levels("ask", start=1),
            },
        ]
    )
    events = pl.DataFrame(
        [
            _event(1, "quote", 34_260_000, "quotes:1", source_seq=1),
            _event(2, "quote", 34_263_000, "quotes:2", source_seq=2),
            _event(
                3,
                "order_add",
                34_263_100,
                "orders:1",
                source_seq=1,
                exchange_order_id="1",
                side="B",
                price_int=10000,
                qty=100,
            ),
        ]
    )
    trades = pl.DataFrame(
        schema={
            "symbol": pl.String,
            "exchange_code": pl.String,
            "trade_date": pl.Int64,
            "session": pl.String,
            "ts_ms": pl.Int64,
            "seq": pl.Int64,
            "trade_code": pl.String,
            "qty": pl.Int64,
        }
    )
    quotes.write_parquet(session_dir / "quotes.parquet")
    events.write_parquet(session_dir / "events.parquet")
    trades.write_parquet(session_dir / "trades.parquet")
    pl.DataFrame(schema={"quote_seq": pl.Int64}).write_parquet(session_dir / "validation_report.parquet")

    result = L1L2BookAlignmentEvaluator(
        offsets_ms=(0,),
        market_offsets_ms={"SZ": (0, 250)},
    ).evaluate_session(session_dir)

    row = result.report.filter(pl.col("quote_seq") == 2)
    assert row.item(0, "selected_event_delta") == 250
    assert row.item(0, "aligned_mismatch_count") == 0


def test_l1_l2_book_uses_default_sz_market_offsets(tmp_path) -> None:
    session_dir = tmp_path / "symbol=000001.SZ" / "date=20260101"
    session_dir.mkdir(parents=True)
    quotes = pl.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "exchange_code": "000001",
                "trade_date": 20260101,
                "session": "continuous_am",
                "ts_ms": 34_260_000,
                "seq": 1,
                "cum_qty": 0,
                "trade_count": 0,
                "bid_price_1_int": 0,
                "bid_qty_1": 0,
                **_empty_levels("bid", start=2),
                **_empty_levels("ask", start=1),
            },
            {
                "symbol": "000001.SZ",
                "exchange_code": "000001",
                "trade_date": 20260101,
                "session": "continuous_am",
                "ts_ms": 34_263_000,
                "seq": 2,
                "cum_qty": 0,
                "trade_count": 0,
                "bid_price_1_int": 10000,
                "bid_qty_1": 100,
                **_empty_levels("bid", start=2),
                **_empty_levels("ask", start=1),
            },
        ]
    )
    events = pl.DataFrame(
        [
            _event(1, "quote", 34_260_000, "quotes:1", source_seq=1),
            _event(2, "quote", 34_263_000, "quotes:2", source_seq=2),
            _event(
                3,
                "order_add",
                34_263_240,
                "orders:1",
                source_seq=1,
                exchange_order_id="1",
                side="B",
                price_int=10000,
                qty=100,
            ),
        ]
    )
    trades = pl.DataFrame(
        schema={
            "symbol": pl.String,
            "exchange_code": pl.String,
            "trade_date": pl.Int64,
            "session": pl.String,
            "ts_ms": pl.Int64,
            "seq": pl.Int64,
            "trade_code": pl.String,
            "qty": pl.Int64,
        }
    )
    quotes.write_parquet(session_dir / "quotes.parquet")
    events.write_parquet(session_dir / "events.parquet")
    trades.write_parquet(session_dir / "trades.parquet")
    pl.DataFrame(schema={"quote_seq": pl.Int64}).write_parquet(session_dir / "validation_report.parquet")

    result = L1L2BookAlignmentEvaluator().evaluate_session(session_dir)

    row = result.report.filter(pl.col("quote_seq") == 2)
    assert row.item(0, "selected_event_delta") == 250
    assert row.item(0, "aligned_mismatch_count") == 0


def test_l1_l2_book_uses_default_sh_market_offsets(tmp_path) -> None:
    session_dir = tmp_path / "symbol=600000.SH" / "date=20260101"
    session_dir.mkdir(parents=True)
    quotes = pl.DataFrame(
        [
            {
                "symbol": "600000.SH",
                "exchange_code": "600000",
                "trade_date": 20260101,
                "session": "continuous_am",
                "ts_ms": 34_260_000,
                "seq": 1,
                "cum_qty": 0,
                "trade_count": 0,
                "bid_price_1_int": 0,
                "bid_qty_1": 0,
                **_empty_levels("bid", start=2),
                **_empty_levels("ask", start=1),
            },
            {
                "symbol": "600000.SH",
                "exchange_code": "600000",
                "trade_date": 20260101,
                "session": "continuous_am",
                "ts_ms": 34_263_000,
                "seq": 2,
                "cum_qty": 0,
                "trade_count": 0,
                "bid_price_1_int": 10000,
                "bid_qty_1": 100,
                **_empty_levels("bid", start=2),
                **_empty_levels("ask", start=1),
            },
        ]
    )
    events = pl.DataFrame(
        [
            _event(1, "quote", 34_260_000, "quotes:1", source_seq=1, symbol="600000.SH", exchange_code="600000"),
            _event(2, "quote", 34_263_000, "quotes:2", source_seq=2, symbol="600000.SH", exchange_code="600000"),
            _event(
                3,
                "order_add",
                34_263_240,
                "orders:1",
                source_seq=1,
                symbol="600000.SH",
                exchange_code="600000",
                exchange_order_id="1",
                side="B",
                price_int=10000,
                qty=100,
            ),
        ]
    )
    trades = pl.DataFrame(
        schema={
            "symbol": pl.String,
            "exchange_code": pl.String,
            "trade_date": pl.Int64,
            "session": pl.String,
            "ts_ms": pl.Int64,
            "seq": pl.Int64,
            "trade_code": pl.String,
            "qty": pl.Int64,
        }
    )
    quotes.write_parquet(session_dir / "quotes.parquet")
    events.write_parquet(session_dir / "events.parquet")
    trades.write_parquet(session_dir / "trades.parquet")
    pl.DataFrame(schema={"quote_seq": pl.Int64}).write_parquet(session_dir / "validation_report.parquet")

    result = L1L2BookAlignmentEvaluator().evaluate_session(session_dir)

    row = result.report.filter(pl.col("quote_seq") == 2)
    assert row.item(0, "selected_event_delta") == 250
    assert row.item(0, "aligned_mismatch_count") == 0


def _event(
    event_id: int,
    event_type: str,
    ts_ms: int,
    payload_ref: str,
    *,
    source_seq: int,
    symbol: str = "000001.SZ",
    exchange_code: str = "000001",
    exchange_order_id: str | None = None,
    side: str | None = None,
    price_int: int | None = None,
    qty: int | None = None,
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "symbol": symbol,
        "exchange_code": exchange_code,
        "trade_date": 20260101,
        "session": "continuous_am",
        "ts_ms": ts_ms,
        "event_type": event_type,
        "priority": 1,
        "source_seq": source_seq,
        "payload_ref": payload_ref,
        "exchange_order_id": exchange_order_id,
        "message_seq": source_seq,
        "side": side,
        "price_int": price_int,
        "qty": qty,
        "quote_bucket_end_offset_ms": 0,
    }


def _empty_levels(side: str, *, start: int) -> dict[str, int]:
    values = {}
    for level in range(start, 11):
        values[f"{side}_price_{level}_int"] = 0
        values[f"{side}_qty_{level}"] = 0
    return values

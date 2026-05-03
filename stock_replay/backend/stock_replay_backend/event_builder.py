from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass

import polars as pl


EVENT_PRIORITY = {
    "session": 0,
    "order_add": 1,
    "order_cancel": 1,
    "market_order": 1,
    "trade": 2,
    "trade_cancel": 2,
    "quote": 3,
}

ORDER_EVENT_TYPE = {
    "A": "order_add",
    "0": "order_add",
    "D": "order_cancel",
    "1": "market_order",
    "U": "market_order",
}

CORE_INTRADAY_WINDOWS = (
    (34_260_000, 41_400_000),
    (46_800_000, 53_820_000),
)
QUOTE_BUCKET_START_OFFSETS_MS = tuple(range(-3000, 1001, 250))


@dataclass(frozen=True)
class EventBuildResult:
    events: pl.DataFrame
    warnings: list[str]


class EventBuilder:
    def build(
        self,
        quotes: pl.DataFrame,
        orders: pl.DataFrame,
        trades: pl.DataFrame,
    ) -> EventBuildResult:
        orders = _with_message_seq(orders, "exchange_order_id")
        trades = _with_message_seq(trades, "trade_id")
        quote_anchors = _build_quote_trade_anchors(quotes, trades)
        quote_bucket_end_offset_ms = _infer_quote_bucket_end_offset_ms(quotes, trades)
        quote_events = quotes.join(quote_anchors, on="seq", how="left").select(
            [
                "symbol",
                "exchange_code",
                "trade_date",
                "session",
                "ts_ms",
                pl.lit("quote").alias("event_type"),
                pl.lit(EVENT_PRIORITY["quote"]).alias("priority"),
                pl.col("seq").alias("source_seq"),
                pl.format("quotes:{}", pl.col("seq")).alias("payload_ref"),
                pl.col("last_price_int").alias("last_price_int"),
                pl.col("last_qty").alias("last_qty"),
                pl.col("quote_anchor_ts_ms"),
                pl.col("quote_anchor_trade_seq"),
                pl.lit(quote_bucket_end_offset_ms).alias("quote_bucket_end_offset_ms"),
            ]
        )

        order_events = orders.with_columns(
            pl.col("order_type").replace_strict(ORDER_EVENT_TYPE, default="session").alias("event_type")
        ).with_columns(pl.col("event_type").replace_strict(EVENT_PRIORITY).alias("priority"))

        session_warning_count = order_events.filter(pl.col("event_type") == "session").height
        warnings: list[str] = []
        if session_warning_count:
            warnings.append(f"converted {session_warning_count} order rows into session events")

        order_events = order_events.select(
            [
                "symbol",
                "exchange_code",
                "trade_date",
                "session",
                "ts_ms",
                "event_type",
                "priority",
                pl.col("seq").alias("source_seq"),
                pl.format("orders:{}", pl.col("seq")).alias("payload_ref"),
                "exchange_order_id",
                "message_seq",
                _optional_column(order_events, "biz_index", pl.Int64),
                "order_no",
                "order_type",
                "side",
                "price_int",
                "qty",
            ]
        )

        trade_events = trades.with_columns(
            _trade_event_type_expr().alias("event_type"),
            _trade_cancel_order_id_expr().alias("exchange_order_id"),
        ).with_columns(pl.col("event_type").replace_strict(EVENT_PRIORITY).alias("priority"))
        trade_events = trade_events.select(
            [
                "symbol",
                "exchange_code",
                "trade_date",
                "session",
                "ts_ms",
                "event_type",
                "priority",
                pl.col("seq").alias("source_seq"),
                pl.format("trades:{}", pl.col("seq")).alias("payload_ref"),
                "trade_id",
                "message_seq",
                _optional_column(trade_events, "biz_index", pl.Int64),
                "trade_code",
                "aggressor_side",
                "price_int",
                "qty",
                "ask_order_id",
                "bid_order_id",
                "exchange_order_id",
            ]
        )

        events = (
            pl.concat([quote_events, order_events, trade_events], how="diagonal_relaxed")
            .with_columns(
                [
                    pl.when(pl.col("event_type") == "quote")
                    .then(
                        pl.max_horizontal(
                            [
                                pl.col("ts_ms") + pl.col("quote_bucket_end_offset_ms").fill_null(0),
                                pl.col("quote_anchor_ts_ms").fill_null(pl.col("ts_ms")),
                            ]
                        )
                    )
                    .otherwise(pl.col("ts_ms"))
                    .alias("_sort_ts_ms"),
                    pl.when(pl.col("event_type").is_in(["session"]))
                    .then(pl.lit(0))
                    .when(pl.col("event_type").is_in(["order_add", "order_cancel", "market_order", "trade", "trade_cancel"]))
                    .then(pl.lit(1))
                    .otherwise(pl.lit(3))
                    .alias("_sort_group"),
                    pl.when(pl.col("event_type").is_in(["order_add", "order_cancel", "market_order", "trade", "trade_cancel"]))
                    .then(
                        pl.when(_is_shanghai_expr() & pl.col("biz_index").is_not_null())
                        .then(pl.col("biz_index").fill_null(0))
                        .when(_is_shenzhen_expr())
                        .then(pl.col("message_seq").fill_null(0))
                        .otherwise(pl.lit(0))
                    )
                    .otherwise(pl.lit(0))
                    .alias("_message_sort"),
                    pl.when(pl.col("priority") == EVENT_PRIORITY["order_add"])
                    .then(pl.col("exchange_order_id").fill_null(""))
                    .otherwise(pl.lit(""))
                    .alias("_order_id_sort"),
                    pl.when((pl.col("priority") == EVENT_PRIORITY["order_add"]) & (pl.col("event_type") == "order_add"))
                    .then(pl.lit(0))
                    .when(
                        (pl.col("priority") == EVENT_PRIORITY["order_cancel"])
                        & (pl.col("event_type") == "order_cancel")
                    )
                    .then(pl.lit(1))
                    .otherwise(pl.lit(2))
                    .alias("_order_lifecycle_sort"),
                ]
            )
            .sort(
                [
                    "_sort_ts_ms",
                    "_sort_group",
                    "_message_sort",
                    "priority",
                    "_order_id_sort",
                    "_order_lifecycle_sort",
                    "source_seq",
                ]
            )
            .drop(
                [
                    "_sort_ts_ms",
                    "_sort_group",
                    "_message_sort",
                    "_order_id_sort",
                    "_order_lifecycle_sort",
                ]
            )
        )
        events = events.with_row_index(name="event_id", offset=1)
        return EventBuildResult(events=events, warnings=warnings)


def _with_message_seq(frame: pl.DataFrame, source_column: str) -> pl.DataFrame:
    if "message_seq" in frame.columns:
        return frame
    if source_column not in frame.columns:
        return frame.with_columns(pl.lit(None, dtype=pl.Int64).alias("message_seq"))
    return frame.with_columns(pl.col(source_column).cast(pl.Int64, strict=False).alias("message_seq"))


def _optional_column(frame: pl.DataFrame, column: str, dtype: pl.DataType) -> pl.Expr:
    if column in frame.columns:
        return pl.col(column)
    return pl.lit(None, dtype=dtype).alias(column)


def _is_shanghai_expr() -> pl.Expr:
    symbol = pl.col("symbol").fill_null("").str.to_uppercase()
    exchange_code = pl.col("exchange_code").fill_null("")
    return symbol.str.ends_with(".SH") | exchange_code.str.starts_with("6") | exchange_code.str.starts_with("9")


def _is_shenzhen_expr() -> pl.Expr:
    symbol = pl.col("symbol").fill_null("").str.to_uppercase()
    exchange_code = pl.col("exchange_code").fill_null("")
    return symbol.str.ends_with(".SZ") | exchange_code.str.starts_with("0") | exchange_code.str.starts_with("3")


def _trade_event_type_expr() -> pl.Expr:
    trade_code = pl.col("trade_code").fill_null("").str.to_uppercase()
    return pl.when(trade_code == "C").then(pl.lit("trade_cancel")).otherwise(pl.lit("trade"))


def _trade_cancel_order_id_expr() -> pl.Expr:
    ask_order_id = pl.col("ask_order_id").fill_null("")
    bid_order_id = pl.col("bid_order_id").fill_null("")
    return pl.when(~ask_order_id.is_in(["", "0"])).then(ask_order_id).otherwise(bid_order_id)


def _build_quote_trade_anchors(quotes: pl.DataFrame, trades: pl.DataFrame) -> pl.DataFrame:
    schema = {
        "seq": pl.Int64,
        "quote_anchor_ts_ms": pl.Int64,
        "quote_anchor_trade_seq": pl.Int64,
    }
    if quotes.is_empty() or trades.is_empty() or "cum_qty" not in quotes.columns:
        return pl.DataFrame(schema=schema)

    trade_anchors = (
        trades.filter(pl.col("trade_code").fill_null("").str.to_uppercase() != "C")
        .sort(["ts_ms", "seq"])
        .with_columns(pl.col("qty").cum_sum().alias("_cum_qty"))
        .select(
            [
                pl.col("_cum_qty").alias("cum_qty"),
                pl.col("ts_ms").alias("quote_anchor_ts_ms"),
                pl.col("seq").alias("quote_anchor_trade_seq"),
            ]
        )
    )
    if trade_anchors.is_empty():
        return pl.DataFrame(schema=schema)

    return (
        quotes.select(["seq", "cum_qty"])
        .filter(pl.col("cum_qty") > 0)
        .join(trade_anchors, on="cum_qty", how="inner")
        .select(["seq", "quote_anchor_ts_ms", "quote_anchor_trade_seq"])
    )


def _infer_quote_bucket_end_offset_ms(quotes: pl.DataFrame, trades: pl.DataFrame) -> int:
    required_quote_columns = {"ts_ms", "cum_qty", "trade_count"}
    required_trade_columns = {"ts_ms", "qty", "trade_code"}
    if (
        quotes.is_empty()
        or trades.is_empty()
        or not required_quote_columns.issubset(quotes.columns)
        or not required_trade_columns.issubset(trades.columns)
    ):
        return 0

    quote_rows = (
        quotes.sort("seq")
        .select(["ts_ms", "cum_qty", "trade_count"])
        .with_columns(
            [
                (pl.col("cum_qty") - pl.col("cum_qty").shift(1)).alias("_cum_delta"),
                (pl.col("trade_count") - pl.col("trade_count").shift(1)).alias("_count_delta"),
            ]
        )
        .filter(_core_intraday_expr())
        .drop_nulls(["_cum_delta", "_count_delta"])
        .select(["ts_ms", "_cum_delta", "_count_delta"])
        .iter_rows()
    )

    trade_rows = (
        trades.filter(pl.col("trade_code").fill_null("").str.to_uppercase() != "C")
        .sort(["ts_ms", "seq"] if "seq" in trades.columns else ["ts_ms"])
        .select(["ts_ms", "qty"])
        .iter_rows()
    )
    trade_points = [(int(ts_ms), int(qty or 0)) for ts_ms, qty in trade_rows]
    quote_points = [
        (int(ts_ms), int(cum_delta or 0), int(count_delta or 0))
        for ts_ms, cum_delta, count_delta in quote_rows
    ]
    if not quote_points or not trade_points:
        return 0

    trade_ts = [point[0] for point in trade_points]
    prefix_qty = [0]
    for _, qty in trade_points:
        prefix_qty.append(prefix_qty[-1] + qty)

    best: tuple[int, int, int, int, int] | None = None
    for start_offset_ms in QUOTE_BUCKET_START_OFFSETS_MS:
        match_both = 0
        match_qty = 0
        abs_qty_diff = 0
        abs_count_diff = 0
        for quote_ts_ms, expected_qty, expected_count in quote_points:
            start = quote_ts_ms + start_offset_ms
            end = start + 3000
            left = bisect_left(trade_ts, start)
            right = bisect_left(trade_ts, end)
            actual_qty = prefix_qty[right] - prefix_qty[left]
            actual_count = right - left
            if actual_qty == expected_qty:
                match_qty += 1
            if actual_qty == expected_qty and actual_count == expected_count:
                match_both += 1
            abs_qty_diff += abs(actual_qty - expected_qty)
            abs_count_diff += abs(actual_count - expected_count)

        score = (match_both, match_qty, -abs_qty_diff, -abs_count_diff, start_offset_ms)
        if best is None or score > best:
            best = score

    if best is None:
        return 0
    return best[4] + 3000


def _core_intraday_expr() -> pl.Expr:
    predicate = pl.lit(False)
    for start_ms, end_ms in CORE_INTRADAY_WINDOWS:
        predicate = predicate | ((pl.col("ts_ms") >= start_ms) & (pl.col("ts_ms") < end_ms))
    return predicate

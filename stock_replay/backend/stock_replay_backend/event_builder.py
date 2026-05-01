from __future__ import annotations

from dataclasses import dataclass

import polars as pl


EVENT_PRIORITY = {
    "session": 0,
    "order_add": 1,
    "order_cancel": 1,
    "trade": 2,
    "quote": 3,
}

ORDER_EVENT_TYPE = {
    "A": "order_add",
    "0": "order_add",
    "D": "order_cancel",
    "1": "order_cancel",
}


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
        quote_events = quotes.select(
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
                "order_no",
                "order_type",
                "side",
                "price_int",
                "qty",
            ]
        )

        trade_events = trades.select(
            [
                "symbol",
                "exchange_code",
                "trade_date",
                "session",
                "ts_ms",
                pl.lit("trade").alias("event_type"),
                pl.lit(EVENT_PRIORITY["trade"]).alias("priority"),
                pl.col("seq").alias("source_seq"),
                pl.format("trades:{}", pl.col("seq")).alias("payload_ref"),
                "trade_id",
                "aggressor_side",
                "price_int",
                "qty",
                "ask_order_id",
                "bid_order_id",
            ]
        )

        events = pl.concat([quote_events, order_events, trade_events], how="diagonal_relaxed").sort(
            ["ts_ms", "priority", "source_seq"]
        )
        events = events.with_row_index(name="event_id", offset=1)
        return EventBuildResult(events=events, warnings=warnings)

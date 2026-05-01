from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from .orderbook_engine import BookLevel, OrderBookEngine


CONTINUOUS_WINDOWS = (
    ("09:31-11:30", 34_260_000, 41_400_000),
    ("13:00-14:57", 46_800_000, 53_820_000),
)


@dataclass(frozen=True)
class VisibleBookSummary:
    checked_quotes: int
    checkpoint_rows: int
    quote_anchor_match_count: int
    quote_anchor_match_rate: float
    inter_quote_drift_abs_qty: int
    correction_cost: int
    correction_abs_qty: int
    correction_price_change_count: int
    continuous_am_match_rate: float
    continuous_pm_match_rate: float


@dataclass(frozen=True)
class VisibleBookResult:
    checkpoints: pl.DataFrame
    summary: VisibleBookSummary


class VisibleBookBuilder:
    def build(self, events: pl.DataFrame, quotes: pl.DataFrame) -> VisibleBookResult:
        quote_lookup = {row["seq"]: row for row in quotes.iter_rows(named=True)}
        engine = OrderBookEngine()
        rows: list[dict[str, object]] = []
        checked_quotes = 0

        for event in events.iter_rows(named=True):
            if event["event_type"] != "quote":
                engine.apply_event(event)
                continue

            checked_quotes += 1
            quote_seq = int(event["source_seq"])
            quote_row = quote_lookup[quote_seq]
            raw_snapshot = engine.snapshot_top_levels(depth=10)
            rows.extend(self._checkpoint_rows(quote_row, event, raw_snapshot))

        checkpoints = (
            pl.from_dicts(rows, schema=self._checkpoint_schema(), strict=False)
            if rows
            else self._empty_checkpoints()
        )
        return VisibleBookResult(
            checkpoints=checkpoints,
            summary=self._build_summary(checked_quotes, checkpoints),
        )

    def _checkpoint_rows(
        self,
        quote_row: dict[str, object],
        event: dict[str, object],
        raw_snapshot: dict[str, list[BookLevel]],
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        checkpoint_id = f"{quote_row['symbol']}-{quote_row['trade_date']}-{quote_row['seq']}"

        for side_name in ("ask", "bid"):
            raw_levels = raw_snapshot[f"{side_name}s"]
            for level in range(1, 11):
                visible_price = quote_row[f"{side_name}_price_{level}_int"]
                visible_qty = quote_row[f"{side_name}_qty_{level}"]
                raw_level = raw_levels[level - 1] if level - 1 < len(raw_levels) else None
                raw_price = raw_level.price_int if raw_level else None
                raw_qty = raw_level.qty if raw_level else None
                raw_price_match = visible_price == raw_price
                raw_qty_match = visible_qty == raw_qty
                correction_abs_qty = self._correction_abs_qty(visible_price, visible_qty, raw_price, raw_qty)

                rows.append(
                    {
                        "symbol": quote_row["symbol"],
                        "trade_date": quote_row["trade_date"],
                        "checkpoint_id": checkpoint_id,
                        "quote_seq": quote_row["seq"],
                        "event_id": event["event_id"],
                        "ts_ms": quote_row["ts_ms"],
                        "session": quote_row["session"],
                        "source": "quote_anchor",
                        "side": side_name,
                        "level": level,
                        "visible_price_int": visible_price,
                        "visible_qty": visible_qty,
                        "raw_price_int": raw_price,
                        "raw_qty": raw_qty,
                        "raw_price_match": raw_price_match,
                        "raw_qty_match": raw_qty_match,
                        "quote_anchor_match": True,
                        "correction_price_changed": not raw_price_match,
                        "inter_quote_drift_abs_qty": correction_abs_qty,
                        "correction_cost": correction_abs_qty,
                        "correction_abs_qty": correction_abs_qty,
                    }
                )

        return rows

    @staticmethod
    def _correction_abs_qty(
        visible_price: object,
        visible_qty: object,
        raw_price: object,
        raw_qty: object,
    ) -> int:
        visible_qty_int = int(visible_qty or 0)
        raw_qty_int = int(raw_qty or 0)
        if visible_price == raw_price:
            return abs(visible_qty_int - raw_qty_int)
        return visible_qty_int + raw_qty_int

    @staticmethod
    def _build_summary(checked_quotes: int, checkpoints: pl.DataFrame) -> VisibleBookSummary:
        if checkpoints.is_empty():
            return VisibleBookSummary(
                checked_quotes=checked_quotes,
                checkpoint_rows=0,
                quote_anchor_match_count=0,
                quote_anchor_match_rate=0.0,
                inter_quote_drift_abs_qty=0,
                correction_cost=0,
                correction_abs_qty=0,
                correction_price_change_count=0,
                continuous_am_match_rate=0.0,
                continuous_pm_match_rate=0.0,
            )

        match_count = _count_true(checkpoints, "quote_anchor_match")
        correction_cost = int(checkpoints.select(pl.col("correction_cost").sum()).item() or 0)
        return VisibleBookSummary(
            checked_quotes=checked_quotes,
            checkpoint_rows=checkpoints.height,
            quote_anchor_match_count=match_count,
            quote_anchor_match_rate=match_count / checkpoints.height,
            inter_quote_drift_abs_qty=int(
                checkpoints.select(pl.col("inter_quote_drift_abs_qty").sum()).item() or 0
            ),
            correction_cost=correction_cost,
            correction_abs_qty=correction_cost,
            correction_price_change_count=_count_true(checkpoints, "correction_price_changed"),
            continuous_am_match_rate=_window_match_rate(checkpoints, CONTINUOUS_WINDOWS[0][1], CONTINUOUS_WINDOWS[0][2]),
            continuous_pm_match_rate=_window_match_rate(checkpoints, CONTINUOUS_WINDOWS[1][1], CONTINUOUS_WINDOWS[1][2]),
        )

    @staticmethod
    def _empty_checkpoints() -> pl.DataFrame:
        return pl.DataFrame(schema=VisibleBookBuilder._checkpoint_schema())

    @staticmethod
    def _checkpoint_schema() -> dict[str, pl.DataType]:
        return {
            "symbol": pl.String,
            "trade_date": pl.Int64,
            "checkpoint_id": pl.String,
            "quote_seq": pl.Int64,
            "event_id": pl.Int64,
            "ts_ms": pl.Int64,
            "session": pl.String,
            "source": pl.String,
            "side": pl.String,
            "level": pl.Int64,
            "visible_price_int": pl.Int64,
            "visible_qty": pl.Int64,
            "raw_price_int": pl.Int64,
            "raw_qty": pl.Int64,
            "raw_price_match": pl.Boolean,
            "raw_qty_match": pl.Boolean,
            "quote_anchor_match": pl.Boolean,
            "correction_price_changed": pl.Boolean,
            "inter_quote_drift_abs_qty": pl.Int64,
            "correction_cost": pl.Int64,
            "correction_abs_qty": pl.Int64,
        }


def _count_true(frame: pl.DataFrame, column: str) -> int:
    return int(frame.select(pl.col(column).cast(pl.Int64).sum()).item() or 0)


def _window_match_rate(frame: pl.DataFrame, start_ms: int, end_ms: int) -> float:
    window = frame.filter((pl.col("ts_ms") >= start_ms) & (pl.col("ts_ms") < end_ms))
    if window.is_empty():
        return 0.0
    return _count_true(window, "quote_anchor_match") / window.height

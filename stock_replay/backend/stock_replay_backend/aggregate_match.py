from __future__ import annotations

from dataclasses import dataclass
from bisect import bisect_left

import polars as pl


CORE_INTRADAY_WINDOWS = (
    (34_260_000, 41_400_000),
    (46_800_000, 53_820_000),
)


@dataclass(frozen=True)
class AggregateMatchSummary:
    checked_buckets: int
    exact_match_count: int
    exact_match_rate: float
    qty_abs_error: int
    count_abs_error: int
    total_abs_error: int
    expected_qty: int
    actual_qty: int
    expected_count: int
    actual_count: int


@dataclass(frozen=True)
class AggregateMatchResult:
    report: pl.DataFrame
    summary: AggregateMatchSummary


class ThreeSecondAggregateMatcher:
    """Compare quote cumulative deltas with L2 non-cancel trade flow per quote bucket."""

    def match(self, quotes: pl.DataFrame, trades: pl.DataFrame) -> AggregateMatchResult:
        if quotes.is_empty() or trades.is_empty() or not {"cum_qty", "trade_count"}.issubset(quotes.columns):
            report = self._empty_report()
            return AggregateMatchResult(report=report, summary=self._build_summary(report))

        quote_rows = (
            quotes.sort("seq")
            .with_columns(
                [
                    (pl.col("cum_qty") - pl.col("cum_qty").shift(1)).alias("expected_qty"),
                    (pl.col("trade_count") - pl.col("trade_count").shift(1)).alias("expected_count"),
                ]
            )
            .filter(_core_expr())
            .drop_nulls(["expected_qty", "expected_count"])
            .to_dicts()
        )
        trade_index = _trade_index(trades)
        if not quote_rows or not trade_index[0]:
            report = self._empty_report()
            return AggregateMatchResult(report=report, summary=self._build_summary(report))

        rows: list[dict[str, object]] = []
        previous_end_ms: int | None = None
        for quote in quote_rows:
            bucket_end_ms = int(quote["ts_ms"])
            bucket_start_ms = previous_end_ms if previous_end_ms is not None else bucket_end_ms - 3000
            actual_qty, actual_count = _trade_delta(trade_index, bucket_start_ms, bucket_end_ms)
            expected_qty = int(quote["expected_qty"] or 0)
            expected_count = int(quote["expected_count"] or 0)
            qty_abs_error = abs(actual_qty - expected_qty)
            count_abs_error = abs(actual_count - expected_count)
            rows.append(
                {
                    "symbol": quote["symbol"],
                    "trade_date": quote["trade_date"],
                    "exchange_code": quote["exchange_code"],
                    "quote_seq": quote["seq"],
                    "ts_ms": quote["ts_ms"],
                    "bucket_start_ms": bucket_start_ms,
                    "bucket_end_ms": bucket_end_ms,
                    "expected_qty": expected_qty,
                    "actual_qty": actual_qty,
                    "expected_count": expected_count,
                    "actual_count": actual_count,
                    "qty_abs_error": qty_abs_error,
                    "count_abs_error": count_abs_error,
                    "total_abs_error": qty_abs_error + count_abs_error,
                    "exact_match": qty_abs_error == 0 and count_abs_error == 0,
                }
            )
            previous_end_ms = bucket_end_ms

        report = pl.from_dicts(rows, schema=self._report_schema(), strict=False) if rows else self._empty_report()
        return AggregateMatchResult(report=report, summary=self._build_summary(report))

    @staticmethod
    def _build_summary(report: pl.DataFrame) -> AggregateMatchSummary:
        if report.is_empty():
            return AggregateMatchSummary(
                checked_buckets=0,
                exact_match_count=0,
                exact_match_rate=0.0,
                qty_abs_error=0,
                count_abs_error=0,
                total_abs_error=0,
                expected_qty=0,
                actual_qty=0,
                expected_count=0,
                actual_count=0,
            )

        exact_match_count = int(report.select(pl.col("exact_match").cast(pl.Int64).sum()).item() or 0)
        qty_abs_error = int(report.select(pl.col("qty_abs_error").sum()).item() or 0)
        count_abs_error = int(report.select(pl.col("count_abs_error").sum()).item() or 0)
        return AggregateMatchSummary(
            checked_buckets=report.height,
            exact_match_count=exact_match_count,
            exact_match_rate=exact_match_count / report.height,
            qty_abs_error=qty_abs_error,
            count_abs_error=count_abs_error,
            total_abs_error=qty_abs_error + count_abs_error,
            expected_qty=int(report.select(pl.col("expected_qty").sum()).item() or 0),
            actual_qty=int(report.select(pl.col("actual_qty").sum()).item() or 0),
            expected_count=int(report.select(pl.col("expected_count").sum()).item() or 0),
            actual_count=int(report.select(pl.col("actual_count").sum()).item() or 0),
        )

    @staticmethod
    def _empty_report() -> pl.DataFrame:
        return pl.DataFrame(schema=ThreeSecondAggregateMatcher._report_schema())

    @staticmethod
    def _report_schema() -> dict[str, pl.DataType]:
        return {
            "symbol": pl.String,
            "trade_date": pl.Int64,
            "exchange_code": pl.String,
            "quote_seq": pl.Int64,
            "ts_ms": pl.Int64,
            "bucket_start_ms": pl.Int64,
            "bucket_end_ms": pl.Int64,
            "expected_qty": pl.Int64,
            "actual_qty": pl.Int64,
            "expected_count": pl.Int64,
            "actual_count": pl.Int64,
            "qty_abs_error": pl.Int64,
            "count_abs_error": pl.Int64,
            "total_abs_error": pl.Int64,
            "exact_match": pl.Boolean,
        }


def _trade_index(trades: pl.DataFrame) -> tuple[list[int], list[int]]:
    ts_values: list[int] = []
    prefix_qty = [0]
    for row in (
        trades.filter(pl.col("trade_code").fill_null("").str.to_uppercase() != "C")
        .sort(["ts_ms", "seq"])
        .select(["ts_ms", "qty"])
        .iter_rows(named=True)
    ):
        ts_values.append(int(row["ts_ms"]))
        prefix_qty.append(prefix_qty[-1] + int(row["qty"] or 0))
    return ts_values, prefix_qty


def _trade_delta(trade_index: tuple[list[int], list[int]], start_ms: int, end_ms: int) -> tuple[int, int]:
    ts_values, prefix_qty = trade_index
    left = bisect_left(ts_values, start_ms)
    right = bisect_left(ts_values, end_ms)
    return prefix_qty[right] - prefix_qty[left], right - left


def _core_expr() -> pl.Expr:
    predicate = pl.lit(False)
    for start_ms, end_ms in CORE_INTRADAY_WINDOWS:
        predicate = predicate | ((pl.col("ts_ms") >= start_ms) & (pl.col("ts_ms") < end_ms))
    return predicate

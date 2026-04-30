from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from .orderbook_engine import BookLevel, OrderBookEngine


@dataclass(frozen=True)
class ValidationSummary:
    checked_quotes: int
    mismatch_count: int
    price_mismatch_count: int
    qty_mismatch_count: int
    missing_order_count: int


@dataclass(frozen=True)
class ValidationResult:
    report: pl.DataFrame
    summary: ValidationSummary


class OrderBookValidator:
    def validate(self, events: pl.DataFrame, quotes: pl.DataFrame) -> ValidationResult:
        quote_lookup = {
            row["seq"]: row
            for row in quotes.iter_rows(named=True)
        }
        engine = OrderBookEngine()
        mismatch_rows: list[dict[str, object]] = []
        checked_quotes = 0

        for event in events.iter_rows(named=True):
            if event["event_type"] != "quote":
                engine.apply_event(event)
                continue

            checked_quotes += 1
            quote_seq = int(event["source_seq"])
            quote_row = quote_lookup[quote_seq]
            snapshot = engine.snapshot_top_levels(depth=10)
            mismatch_rows.extend(self._compare_quote_to_book(quote_row, event, snapshot))

        report = pl.from_dicts(mismatch_rows) if mismatch_rows else self._empty_report()
        summary = ValidationSummary(
            checked_quotes=checked_quotes,
            mismatch_count=report.height,
            price_mismatch_count=report.filter(pl.col("price_match") == False).height,
            qty_mismatch_count=report.filter(pl.col("qty_match") == False).height,
            missing_order_count=len(engine.missing_order_log),
        )
        return ValidationResult(report=report, summary=summary)

    def _compare_quote_to_book(
        self,
        quote_row: dict[str, object],
        event: dict[str, object],
        snapshot: dict[str, list[BookLevel]],
    ) -> list[dict[str, object]]:
        mismatch_rows: list[dict[str, object]] = []

        for side_name, side_prefix in (("ask", "ask"), ("bid", "bid")):
            actual_levels = snapshot[f"{side_name}s"]
            for level in range(1, 11):
                expected_price = quote_row[f"{side_prefix}_price_{level}_int"]
                expected_qty = quote_row[f"{side_prefix}_qty_{level}"]
                actual_level = actual_levels[level - 1] if level - 1 < len(actual_levels) else None
                actual_price = actual_level.price_int if actual_level else None
                actual_qty = actual_level.qty if actual_level else None
                price_match = expected_price == actual_price
                qty_match = expected_qty == actual_qty

                if price_match and qty_match:
                    continue

                mismatch_rows.append(
                    {
                        "symbol": quote_row["symbol"],
                        "trade_date": quote_row["trade_date"],
                        "quote_seq": quote_row["seq"],
                        "event_id": event["event_id"],
                        "ts_ms": quote_row["ts_ms"],
                        "side": side_name,
                        "level": level,
                        "expected_price_int": expected_price,
                        "actual_price_int": actual_price,
                        "expected_qty": expected_qty,
                        "actual_qty": actual_qty,
                        "price_match": price_match,
                        "qty_match": qty_match,
                    }
                )

        return mismatch_rows

    @staticmethod
    def _empty_report() -> pl.DataFrame:
        return pl.DataFrame(
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
            }
        )


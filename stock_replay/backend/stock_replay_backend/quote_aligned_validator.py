from __future__ import annotations

import argparse
from bisect import bisect_left
import json
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import polars as pl

from .orderbook_engine import BookLevel, OrderBookEngine


CORE_INTRADAY_WINDOWS = (
    (34_260_000, 41_400_000),
    (46_800_000, 53_820_000),
)
TICK_EVENT_TYPES = {"order_add", "order_cancel", "market_order", "trade", "trade_cancel"}
BUCKET_ALIGNMENT_OFFSETS_MS = (-1000, -750, -500, -250, 0, 250, 500, 750, 1000)
DEFAULT_SZ_MARKET_OFFSETS_MS = (0, -500, -250, 250)
DEFAULT_SH_MARKET_OFFSETS_MS = (0, -500, -250, 250)


@dataclass(frozen=True)
class QuoteAlignmentSummary:
    checked_quotes: int
    level_slots: int
    current_mismatch_count: int
    current_price_mismatch_count: int
    current_qty_mismatch_count: int
    aligned_mismatch_count: int
    aligned_price_mismatch_count: int
    aligned_qty_mismatch_count: int
    improved_quote_count: int
    selected_current_count: int
    current_alignment_rate: float
    aligned_alignment_rate: float


@dataclass(frozen=True)
class QuoteAlignmentResult:
    report: pl.DataFrame
    summary: QuoteAlignmentSummary


@dataclass(frozen=True)
class CandidateScore:
    label: str
    event_delta: int
    ts_delta_ms: int
    mismatch_count: int
    price_mismatch_count: int
    qty_mismatch_count: int


def _market_from_quote_row(quote_row: dict[str, object]) -> str:
    symbol = str(quote_row.get("symbol") or "").upper()
    exchange_code = str(quote_row.get("exchange_code") or "")
    if symbol.endswith(".SZ") or exchange_code.startswith(("0", "3")):
        return "SZ"
    if symbol.endswith(".SH") or exchange_code.startswith(("6", "9")):
        return "SH"
    return ""


class QuoteAlignedValidator:
    """Research evaluator for bounded quote-surface alignment candidates.

    This intentionally does not mutate RawBook semantics. It compares quote rows
    against nearby event-derived states to measure how much residual can be
    explained by quote generation phase differences.
    """

    def __init__(
        self,
        *,
        max_past_ticks: int = 3,
        max_future_ticks: int = 3,
        max_future_ms: int = 250,
        core_intraday_only: bool = True,
        quote_limit: int | None = None,
    ) -> None:
        self.max_past_ticks = max(0, max_past_ticks)
        self.max_future_ticks = max(0, max_future_ticks)
        self.max_future_ms = max(0, max_future_ms)
        self.core_intraday_only = core_intraday_only
        self.quote_limit = quote_limit

    def validate(self, events: pl.DataFrame, quotes: pl.DataFrame) -> QuoteAlignmentResult:
        quote_lookup = {row["seq"]: row for row in quotes.iter_rows(named=True)}
        event_rows = list(events.iter_rows(named=True))
        engine = OrderBookEngine()
        past_snapshots: deque[tuple[int, int, dict[str, list[BookLevel]]]] = deque(maxlen=self.max_past_ticks)
        report_rows: list[dict[str, object]] = []

        for index, event in enumerate(event_rows):
            if event["event_type"] != "quote":
                engine.apply_event(event)
                if event["event_type"] in TICK_EVENT_TYPES and self.max_past_ticks:
                    past_snapshots.append(
                        (
                            int(event["event_id"]),
                            int(event["ts_ms"]),
                            engine.snapshot_top_levels(depth=10),
                        )
                    )
                continue

            quote_row = quote_lookup[int(event["source_seq"])]
            if self._skip_quote(quote_row):
                continue
            if self.quote_limit is not None and len(report_rows) >= self.quote_limit:
                break

            current_snapshot = engine.snapshot_top_levels(depth=10)
            scores = [
                self._score_candidate("current", 0, 0, current_snapshot, quote_row),
                *self._past_scores(past_snapshots, event, quote_row),
                *self._future_scores(engine, event_rows, index, event, quote_row),
            ]
            best = min(scores, key=self._score_key)
            current = scores[0]
            report_rows.append(
                {
                    "symbol": quote_row["symbol"],
                    "trade_date": quote_row["trade_date"],
                    "exchange_code": quote_row["exchange_code"],
                    "quote_seq": quote_row["seq"],
                    "event_id": event["event_id"],
                    "ts_ms": quote_row["ts_ms"],
                    "current_mismatch_count": current.mismatch_count,
                    "current_price_mismatch_count": current.price_mismatch_count,
                    "current_qty_mismatch_count": current.qty_mismatch_count,
                    "aligned_mismatch_count": best.mismatch_count,
                    "aligned_price_mismatch_count": best.price_mismatch_count,
                    "aligned_qty_mismatch_count": best.qty_mismatch_count,
                    "improvement": current.mismatch_count - best.mismatch_count,
                    "selected_label": best.label,
                    "selected_event_delta": best.event_delta,
                    "selected_ts_delta_ms": best.ts_delta_ms,
                }
            )

        report = pl.from_dicts(report_rows) if report_rows else self._empty_report()
        return QuoteAlignmentResult(report=report, summary=self._build_summary(report))

    def _past_scores(
        self,
        past_snapshots: deque[tuple[int, int, dict[str, list[BookLevel]]]],
        quote_event: dict[str, object],
        quote_row: dict[str, object],
    ) -> list[CandidateScore]:
        scores: list[CandidateScore] = []
        quote_event_id = int(quote_event["event_id"])
        quote_ts_ms = int(quote_event["ts_ms"])
        for event_id, ts_ms, snapshot in past_snapshots:
            scores.append(
                self._score_candidate(
                    "past",
                    event_id - quote_event_id,
                    ts_ms - quote_ts_ms,
                    snapshot,
                    quote_row,
                )
            )
        return scores

    def _future_scores(
        self,
        engine: OrderBookEngine,
        event_rows: list[dict[str, object]],
        quote_index: int,
        quote_event: dict[str, object],
        quote_row: dict[str, object],
    ) -> list[CandidateScore]:
        if not self.max_future_ticks:
            return []

        scores: list[CandidateScore] = []
        restore_point = self._capture_restore_point(engine)
        quote_effective_ts_ms = self._quote_effective_ts_ms(quote_event)
        quote_event_id = int(quote_event["event_id"])
        tick_count = 0

        try:
            for future_event in event_rows[quote_index + 1 :]:
                if future_event["event_type"] == "quote":
                    continue
                if future_event["event_type"] not in TICK_EVENT_TYPES:
                    continue
                future_ts_ms = int(future_event["ts_ms"])
                if future_ts_ms - quote_effective_ts_ms > self.max_future_ms:
                    break

                engine.apply_event(future_event)
                tick_count += 1
                scores.append(
                    self._score_candidate(
                        "future",
                        int(future_event["event_id"]) - quote_event_id,
                        future_ts_ms - int(quote_event["ts_ms"]),
                        engine.snapshot_top_levels(depth=10),
                        quote_row,
                    )
                )
                if tick_count >= self.max_future_ticks:
                    break
        finally:
            self._restore_engine(engine, restore_point)

        return scores

    def _score_candidate(
        self,
        label: str,
        event_delta: int,
        ts_delta_ms: int,
        snapshot: dict[str, list[BookLevel]],
        quote_row: dict[str, object],
    ) -> CandidateScore:
        mismatch_count = 0
        price_mismatch_count = 0
        qty_mismatch_count = 0

        for side_name, side_prefix in (("ask", "ask"), ("bid", "bid")):
            actual_levels = snapshot[f"{side_name}s"]
            for level in range(1, 11):
                expected_price = quote_row[f"{side_prefix}_price_{level}_int"]
                expected_qty = quote_row[f"{side_prefix}_qty_{level}"]
                actual_level = actual_levels[level - 1] if level - 1 < len(actual_levels) else None
                actual_price = actual_level.price_int if actual_level else None
                actual_qty = actual_level.qty if actual_level else None
                if self._is_empty_level(expected_price, expected_qty) and actual_level is None:
                    continue

                price_match = expected_price == actual_price
                qty_match = expected_qty == actual_qty
                if price_match and qty_match:
                    continue

                mismatch_count += 1
                price_mismatch_count += int(not price_match)
                qty_mismatch_count += int(not qty_match)

        return CandidateScore(
            label=label,
            event_delta=event_delta,
            ts_delta_ms=ts_delta_ms,
            mismatch_count=mismatch_count,
            price_mismatch_count=price_mismatch_count,
            qty_mismatch_count=qty_mismatch_count,
        )

    def _skip_quote(self, quote_row: dict[str, object]) -> bool:
        if quote_row["session"] == "auction":
            return True
        if not self.core_intraday_only:
            return False
        ts_ms = int(quote_row["ts_ms"])
        return not any(start_ms <= ts_ms < end_ms for start_ms, end_ms in CORE_INTRADAY_WINDOWS)

    @staticmethod
    def _score_key(score: CandidateScore) -> tuple[int, int, int, int, int]:
        label_penalty = 0 if score.label == "current" else 1
        return (
            score.mismatch_count,
            score.price_mismatch_count,
            score.qty_mismatch_count,
            abs(score.event_delta),
            label_penalty,
        )

    @staticmethod
    def _quote_effective_ts_ms(quote_event: dict[str, object]) -> int:
        ts_ms = int(quote_event["ts_ms"])
        offset = quote_event.get("quote_bucket_end_offset_ms") or 0
        anchor = quote_event.get("quote_anchor_ts_ms")
        anchor_ts_ms = ts_ms if anchor is None else int(anchor)
        return max(ts_ms + int(offset), anchor_ts_ms)

    @staticmethod
    def _capture_restore_point(engine: OrderBookEngine) -> tuple[dict[str, Any], dict[int, int], dict[int, int], int]:
        return (
            dict(engine.orders),
            dict(engine.bid_levels),
            dict(engine.ask_levels),
            len(engine.missing_order_log),
        )

    @staticmethod
    def _restore_engine(
        engine: OrderBookEngine,
        restore_point: tuple[dict[str, Any], dict[int, int], dict[int, int], int],
    ) -> None:
        orders, bid_levels, ask_levels, missing_count = restore_point
        engine.orders.clear()
        engine.orders.update(orders)
        engine.bid_levels.clear()
        engine.bid_levels.update(bid_levels)
        engine.ask_levels.clear()
        engine.ask_levels.update(ask_levels)
        del engine.missing_order_log[missing_count:]

    @staticmethod
    def _build_summary(report: pl.DataFrame) -> QuoteAlignmentSummary:
        checked_quotes = report.height
        level_slots = checked_quotes * 20
        if report.is_empty():
            return QuoteAlignmentSummary(
                checked_quotes=0,
                level_slots=0,
                current_mismatch_count=0,
                current_price_mismatch_count=0,
                current_qty_mismatch_count=0,
                aligned_mismatch_count=0,
                aligned_price_mismatch_count=0,
                aligned_qty_mismatch_count=0,
                improved_quote_count=0,
                selected_current_count=0,
                current_alignment_rate=0.0,
                aligned_alignment_rate=0.0,
            )

        current_mismatch_count = int(report.select(pl.col("current_mismatch_count").sum()).item())
        aligned_mismatch_count = int(report.select(pl.col("aligned_mismatch_count").sum()).item())
        return QuoteAlignmentSummary(
            checked_quotes=checked_quotes,
            level_slots=level_slots,
            current_mismatch_count=current_mismatch_count,
            current_price_mismatch_count=int(report.select(pl.col("current_price_mismatch_count").sum()).item()),
            current_qty_mismatch_count=int(report.select(pl.col("current_qty_mismatch_count").sum()).item()),
            aligned_mismatch_count=aligned_mismatch_count,
            aligned_price_mismatch_count=int(report.select(pl.col("aligned_price_mismatch_count").sum()).item()),
            aligned_qty_mismatch_count=int(report.select(pl.col("aligned_qty_mismatch_count").sum()).item()),
            improved_quote_count=report.filter(pl.col("improvement") > 0).height,
            selected_current_count=report.filter(pl.col("selected_event_delta") == 0).height,
            current_alignment_rate=(level_slots - current_mismatch_count) / level_slots if level_slots else 0.0,
            aligned_alignment_rate=(level_slots - aligned_mismatch_count) / level_slots if level_slots else 0.0,
        )

    @staticmethod
    def _empty_report() -> pl.DataFrame:
        return pl.DataFrame(
            schema={
                "symbol": pl.String,
                "trade_date": pl.Int64,
                "exchange_code": pl.String,
                "quote_seq": pl.Int64,
                "event_id": pl.Int64,
                "ts_ms": pl.Int64,
                "current_mismatch_count": pl.Int64,
                "current_price_mismatch_count": pl.Int64,
                "current_qty_mismatch_count": pl.Int64,
                "aligned_mismatch_count": pl.Int64,
                "aligned_price_mismatch_count": pl.Int64,
                "aligned_qty_mismatch_count": pl.Int64,
                "improvement": pl.Int64,
                "selected_label": pl.String,
                "selected_event_delta": pl.Int64,
                "selected_ts_delta_ms": pl.Int64,
            }
        )

    @staticmethod
    def _is_empty_level(price_int: object, qty: object) -> bool:
        return price_int in {None, 0} and qty in {None, 0}


class SurfaceQuoteAlignmentEvaluator:
    """Fast research pass using persisted validation rows as the current surface."""

    def __init__(self, *, max_future_ticks: int = 3, max_future_ms: int = 250) -> None:
        self.max_future_ticks = max(0, max_future_ticks)
        self.max_future_ms = max(0, max_future_ms)

    def evaluate_session(self, session_dir: Path) -> QuoteAlignmentResult:
        quotes = pl.read_parquet(session_dir / "quotes.parquet")
        report = pl.read_parquet(session_dir / "validation_report.parquet")
        events = pl.read_parquet(session_dir / "events.parquet")
        if report.is_empty():
            return QuoteAlignmentResult(report=QuoteAlignedValidator._empty_report(), summary=QuoteAlignedValidator._build_summary(QuoteAlignedValidator._empty_report()))

        quote_lookup = {row["seq"]: row for row in quotes.iter_rows(named=True)}
        event_lookup = {row["event_id"]: row for row in events.iter_rows(named=True)}
        mismatches_by_quote = {
            quote_seq: rows
            for quote_seq, rows in report.group_by("quote_seq", maintain_order=True)
        }
        event_rows = list(events.iter_rows(named=True))
        event_index_by_id = {int(row["event_id"]): index for index, row in enumerate(event_rows)}

        rows: list[dict[str, object]] = []
        for quote_seq, mismatch_rows in mismatches_by_quote.items():
            quote_row = quote_lookup[int(quote_seq[0] if isinstance(quote_seq, tuple) else quote_seq)]
            if quote_row["session"] == "auction":
                continue
            ts_ms = int(quote_row["ts_ms"])
            if not any(start_ms <= ts_ms < end_ms for start_ms, end_ms in CORE_INTRADAY_WINDOWS):
                continue

            current_surface = self._current_surface_from_report(quote_row, mismatch_rows)
            quote_event_id = int(mismatch_rows.item(0, "event_id"))
            current = self._score_surface(current_surface, quote_row)
            candidates = [CandidateScore("current", 0, 0, *current)]
            candidates.extend(
                self._future_surface_scores(
                    current_surface,
                    event_rows,
                    event_index_by_id[quote_event_id],
                    event_lookup[quote_event_id],
                    quote_row,
                )
            )
            best = min(candidates, key=QuoteAlignedValidator._score_key)
            rows.append(
                {
                    "symbol": quote_row["symbol"],
                    "trade_date": quote_row["trade_date"],
                    "exchange_code": quote_row["exchange_code"],
                    "quote_seq": quote_row["seq"],
                    "event_id": quote_event_id,
                    "ts_ms": ts_ms,
                    "current_mismatch_count": candidates[0].mismatch_count,
                    "current_price_mismatch_count": candidates[0].price_mismatch_count,
                    "current_qty_mismatch_count": candidates[0].qty_mismatch_count,
                    "aligned_mismatch_count": best.mismatch_count,
                    "aligned_price_mismatch_count": best.price_mismatch_count,
                    "aligned_qty_mismatch_count": best.qty_mismatch_count,
                    "improvement": candidates[0].mismatch_count - best.mismatch_count,
                    "selected_label": best.label,
                    "selected_event_delta": best.event_delta,
                    "selected_ts_delta_ms": best.ts_delta_ms,
                }
            )

        result_report = pl.from_dicts(rows) if rows else QuoteAlignedValidator._empty_report()
        return QuoteAlignmentResult(report=result_report, summary=QuoteAlignedValidator._build_summary(result_report))

    @staticmethod
    def build_level_shift_diagnostics(session_dir: Path) -> pl.DataFrame:
        report = pl.read_parquet(session_dir / "validation_report.parquet")
        if report.is_empty():
            return pl.DataFrame(
                schema={
                    "symbol": pl.String,
                    "trade_date": pl.Int64,
                    "side": pl.String,
                    "delta": pl.Int64,
                    "matched_mismatch_rows": pl.Int64,
                    "total_side_mismatch": pl.Int64,
                }
            )
        quotes = pl.read_parquet(session_dir / "quotes.parquet")
        joined = report.filter(SurfaceQuoteAlignmentEvaluator._core_expr()).join(
            quotes.select(
                [
                    "seq",
                    *[
                        f"{side}_price_{level}_int"
                        for side in ("ask", "bid")
                        for level in range(1, 11)
                    ],
                ]
            ),
            left_on="quote_seq",
            right_on="seq",
            how="left",
        )
        rows: list[dict[str, object]] = []
        symbol = session_dir.parent.name.removeprefix("symbol=")
        trade_date = int(session_dir.name.removeprefix("date="))
        for side in ("ask", "bid"):
            side_frame = joined.filter(pl.col("side") == side)
            for delta in (-3, -2, -1, 1, 2, 3):
                predicate = pl.lit(False)
                for level in range(1, 11):
                    other_level = level + delta
                    if 1 <= other_level <= 10:
                        predicate = predicate | (
                            (pl.col("level") == level)
                            & (pl.col("actual_price_int") == pl.col(f"{side}_price_{other_level}_int"))
                        )
                matched = int(side_frame.select(predicate.cast(pl.Int64).sum()).item()) if not side_frame.is_empty() else 0
                rows.append(
                    {
                        "symbol": symbol,
                        "trade_date": trade_date,
                        "side": side,
                        "delta": delta,
                        "matched_mismatch_rows": matched,
                        "total_side_mismatch": side_frame.height,
                    }
                )
        return pl.from_dicts(rows)

    def _future_surface_scores(
        self,
        surface: dict[str, dict[int, int]],
        event_rows: list[dict[str, object]],
        quote_index: int,
        quote_event: dict[str, object],
        quote_row: dict[str, object],
    ) -> list[CandidateScore]:
        scores: list[CandidateScore] = []
        candidate_surface = {side: dict(levels) for side, levels in surface.items()}
        quote_effective_ts_ms = QuoteAlignedValidator._quote_effective_ts_ms(quote_event)
        quote_event_id = int(quote_event["event_id"])
        tick_count = 0
        for event in event_rows[quote_index + 1 :]:
            if event["event_type"] == "quote":
                continue
            if event["event_type"] not in TICK_EVENT_TYPES:
                continue
            event_ts_ms = int(event["ts_ms"])
            if event_ts_ms - quote_effective_ts_ms > self.max_future_ms:
                break
            self._apply_surface_event(candidate_surface, event)
            tick_count += 1
            mismatch_count, price_mismatch_count, qty_mismatch_count = self._score_surface(candidate_surface, quote_row)
            scores.append(
                CandidateScore(
                    "future_surface",
                    int(event["event_id"]) - quote_event_id,
                    event_ts_ms - int(quote_event["ts_ms"]),
                    mismatch_count,
                    price_mismatch_count,
                    qty_mismatch_count,
                )
            )
            if tick_count >= self.max_future_ticks:
                break
        return scores

    @staticmethod
    def _current_surface_from_report(
        quote_row: dict[str, object],
        mismatch_rows: pl.DataFrame,
    ) -> dict[str, dict[int, int]]:
        surface = {
            side: {
                quote_row[f"{side}_price_{level}_int"]: quote_row[f"{side}_qty_{level}"]
                for level in range(1, 11)
                if quote_row[f"{side}_price_{level}_int"] not in {None, 0}
            }
            for side in ("ask", "bid")
        }
        for mismatch in mismatch_rows.iter_rows(named=True):
            side = mismatch["side"]
            expected_price = mismatch["expected_price_int"]
            actual_price = mismatch["actual_price_int"]
            if expected_price not in {None, 0}:
                surface[side].pop(expected_price, None)
            if actual_price not in {None, 0}:
                surface[side][actual_price] = mismatch["actual_qty"] or 0
        return surface

    @staticmethod
    def _apply_surface_event(surface: dict[str, dict[int, int]], event: dict[str, object]) -> None:
        side_code = event.get("side")
        if side_code == "B":
            side = "bid"
        elif side_code == "S":
            side = "ask"
        else:
            return
        price = event.get("price_int")
        qty = event.get("qty")
        if price in {None, 0} or qty in {None, 0}:
            return
        price_int = int(price)
        qty_int = int(qty)
        if event["event_type"] == "order_add":
            surface[side][price_int] = surface[side].get(price_int, 0) + qty_int
        elif event["event_type"] in {"order_cancel", "trade_cancel"}:
            updated = surface[side].get(price_int, 0) - qty_int
            if updated > 0:
                surface[side][price_int] = updated
            else:
                surface[side].pop(price_int, None)

    @staticmethod
    def _score_surface(surface: dict[str, dict[int, int]], quote_row: dict[str, object]) -> tuple[int, int, int]:
        mismatch_count = 0
        price_mismatch_count = 0
        qty_mismatch_count = 0
        for side, reverse in (("ask", False), ("bid", True)):
            actual_levels = sorted(surface[side].items(), reverse=reverse)[:10]
            for level in range(1, 11):
                expected_price = quote_row[f"{side}_price_{level}_int"]
                expected_qty = quote_row[f"{side}_qty_{level}"]
                actual_price, actual_qty = actual_levels[level - 1] if level - 1 < len(actual_levels) else (None, None)
                if expected_price in {None, 0} and expected_qty in {None, 0} and actual_price is None:
                    continue
                price_match = expected_price == actual_price
                qty_match = expected_qty == actual_qty
                if price_match and qty_match:
                    continue
                mismatch_count += 1
                price_mismatch_count += int(not price_match)
                qty_mismatch_count += int(not qty_match)
        return mismatch_count, price_mismatch_count, qty_mismatch_count

    @staticmethod
    def _core_expr() -> pl.Expr:
        predicate = pl.lit(False)
        for start_ms, end_ms in CORE_INTRADAY_WINDOWS:
            predicate = predicate | ((pl.col("ts_ms") >= start_ms) & (pl.col("ts_ms") < end_ms))
        return predicate


class ThreeSecondBucketEvaluator:
    """Diagnose L2 tick refinement against each quote's 3-second L1 aggregate."""

    def __init__(self, *, offsets_ms: tuple[int, ...] = BUCKET_ALIGNMENT_OFFSETS_MS) -> None:
        self.offsets_ms = offsets_ms

    def evaluate_session(self, session_dir: Path) -> pl.DataFrame:
        quotes = pl.read_parquet(session_dir / "quotes.parquet")
        events = pl.read_parquet(session_dir / "events.parquet")
        trades = pl.read_parquet(session_dir / "trades.parquet")
        validation_report = pl.read_parquet(session_dir / "validation_report.parquet")
        if quotes.is_empty() or trades.is_empty():
            return self._empty_report()

        quote_rows = self._quote_rows(quotes, events)
        trade_index = self._trade_index(trades)
        if not quote_rows or not trade_index[0]:
            return self._empty_report()

        quote_mismatch_counts = self._quote_mismatch_counts(validation_report)
        rows: list[dict[str, object]] = []
        for quote in quote_rows:
            bucket_end_ms = int(quote["ts_ms"]) + int(quote.get("quote_bucket_end_offset_ms") or 0)
            base_start_ms = bucket_end_ms - 3000
            expected_qty = int(quote["_cum_delta"] or 0)
            expected_count = int(quote["_count_delta"] or 0)
            candidate_rows = []
            for offset_ms in self.offsets_ms:
                start_ms = base_start_ms + offset_ms
                end_ms = bucket_end_ms + offset_ms
                actual_qty, actual_count = self._trade_delta(trade_index, start_ms, end_ms)
                candidate_rows.append(
                    {
                        "offset_ms": offset_ms,
                        "start_ms": start_ms,
                        "end_ms": end_ms,
                        "actual_qty": actual_qty,
                        "actual_count": actual_count,
                        "qty_abs_error": abs(actual_qty - expected_qty),
                        "count_abs_error": abs(actual_count - expected_count),
                    }
                )
            best = min(candidate_rows, key=lambda row: (row["qty_abs_error"] + row["count_abs_error"], row["qty_abs_error"], abs(row["offset_ms"])))
            current = next(row for row in candidate_rows if row["offset_ms"] == 0)
            rows.append(
                {
                    "symbol": quote["symbol"],
                    "trade_date": quote["trade_date"],
                    "exchange_code": quote["exchange_code"],
                    "quote_seq": quote["seq"],
                    "ts_ms": quote["ts_ms"],
                    "expected_bucket_qty": expected_qty,
                    "expected_bucket_count": expected_count,
                    "current_bucket_qty": current["actual_qty"],
                    "current_bucket_count": current["actual_count"],
                    "current_qty_abs_error": current["qty_abs_error"],
                    "current_count_abs_error": current["count_abs_error"],
                    "best_offset_ms": best["offset_ms"],
                    "best_bucket_qty": best["actual_qty"],
                    "best_bucket_count": best["actual_count"],
                    "best_qty_abs_error": best["qty_abs_error"],
                    "best_count_abs_error": best["count_abs_error"],
                    "tick_error_improvement": (current["qty_abs_error"] + current["count_abs_error"])
                    - (best["qty_abs_error"] + best["count_abs_error"]),
                    "book_mismatch_count": quote_mismatch_counts.get(int(quote["seq"]), 0),
                }
            )
        return pl.from_dicts(rows) if rows else self._empty_report()

    @staticmethod
    def _quote_rows(quotes: pl.DataFrame, events: pl.DataFrame) -> list[dict[str, object]]:
        required = {"cum_qty", "trade_count"}
        if not required.issubset(quotes.columns):
            return []
        quote_event_columns = [
            pl.col("source_seq").alias("seq"),
            ThreeSecondBucketEvaluator._optional_event_column(events, "event_id", pl.Int64),
            ThreeSecondBucketEvaluator._optional_event_column(events, "quote_bucket_end_offset_ms", pl.Int64),
            ThreeSecondBucketEvaluator._optional_event_column(events, "quote_anchor_ts_ms", pl.Int64),
            ThreeSecondBucketEvaluator._optional_event_column(events, "quote_anchor_trade_seq", pl.Int64),
        ]
        quote_events = events.filter(pl.col("event_type") == "quote").select(quote_event_columns)

        return (
            quotes.sort("seq")
            .join(quote_events, on="seq", how="left")
            .with_columns(
                [
                    (pl.col("cum_qty") - pl.col("cum_qty").shift(1)).alias("_cum_delta"),
                    (pl.col("trade_count") - pl.col("trade_count").shift(1)).alias("_count_delta"),
                ]
            )
            .filter(SurfaceQuoteAlignmentEvaluator._core_expr())
            .drop_nulls(["_cum_delta", "_count_delta"])
            .to_dicts()
        )

    @staticmethod
    def _optional_event_column(events: pl.DataFrame, column: str, dtype: pl.DataType) -> pl.Expr:
        if column in events.columns:
            return pl.col(column)
        return pl.lit(None, dtype=dtype).alias(column)

    @staticmethod
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

    @staticmethod
    def _trade_delta(trade_index: tuple[list[int], list[int]], start_ms: int, end_ms: int) -> tuple[int, int]:
        ts_values, prefix_qty = trade_index
        left = bisect_left(ts_values, start_ms)
        right = bisect_left(ts_values, end_ms)
        return prefix_qty[right] - prefix_qty[left], right - left

    @staticmethod
    def _quote_mismatch_counts(validation_report: pl.DataFrame) -> dict[int, int]:
        if validation_report.is_empty():
            return {}
        return {
            int(row["quote_seq"]): int(row["book_mismatch_count"])
            for row in validation_report.group_by("quote_seq")
            .agg(pl.len().alias("book_mismatch_count"))
            .iter_rows(named=True)
        }

    @staticmethod
    def _empty_report() -> pl.DataFrame:
        return pl.DataFrame(
            schema={
                "symbol": pl.String,
                "trade_date": pl.Int64,
                "exchange_code": pl.String,
                "quote_seq": pl.Int64,
                "ts_ms": pl.Int64,
                "expected_bucket_qty": pl.Int64,
                "expected_bucket_count": pl.Int64,
                "current_bucket_qty": pl.Int64,
                "current_bucket_count": pl.Int64,
                "current_qty_abs_error": pl.Int64,
                "current_count_abs_error": pl.Int64,
                "best_offset_ms": pl.Int64,
                "best_bucket_qty": pl.Int64,
                "best_bucket_count": pl.Int64,
                "best_qty_abs_error": pl.Int64,
                "best_count_abs_error": pl.Int64,
                "tick_error_improvement": pl.Int64,
                "book_mismatch_count": pl.Int64,
            }
        )


class L1L2BookAlignmentEvaluator:
    """Compare each L1 quote with L2 RawBook states at candidate 3-second bucket ends."""

    def __init__(
        self,
        *,
        offsets_ms: tuple[int, ...] = (0, -250),
        market_offsets_ms: dict[str, tuple[int, ...]] | None = None,
        selection: str = "book_with_tick_guard",
        max_tick_error_worsening: int = 0,
    ) -> None:
        self.offsets_ms = offsets_ms
        self.market_offsets_ms = dict(market_offsets_ms or {})
        # SZ order/trade rows share a same-channel message sequence, so keep
        # sequencing rule-grounded and only use a fixed market-level quote phase family.
        self.market_offsets_ms.setdefault("SZ", DEFAULT_SZ_MARKET_OFFSETS_MS)
        # Wind's SH three-table feed does not expose the official shared BizIndex,
        # so use a fixed market-level fallback instead of symbol-specific tuning.
        self.market_offsets_ms.setdefault("SH", DEFAULT_SH_MARKET_OFFSETS_MS)
        self.selection = selection
        self.max_tick_error_worsening = max_tick_error_worsening

    def evaluate_session(self, session_dir: Path) -> QuoteAlignmentResult:
        events = pl.read_parquet(session_dir / "events.parquet")
        quotes = pl.read_parquet(session_dir / "quotes.parquet")
        trades = pl.read_parquet(session_dir / "trades.parquet")
        quote_rows = ThreeSecondBucketEvaluator._quote_rows(quotes, events)
        if not quote_rows:
            empty = QuoteAlignedValidator._empty_report()
            return QuoteAlignmentResult(report=empty, summary=QuoteAlignedValidator._build_summary(empty))

        trade_index = ThreeSecondBucketEvaluator._trade_index(trades)
        offsets_ms = self._offsets_for_session(quote_rows[0])
        quote_tasks = self._build_quote_tasks(quote_rows, offsets_ms)
        target_times = sorted({target for task in quote_tasks for target in task["targets"].values()})
        snapshots = self._snapshots_at_targets(events, target_times)
        quote_event_snapshots = self._snapshots_at_quote_events(events)
        selected_offsets = self._select_coherent_offsets(quote_tasks, snapshots, quote_event_snapshots, trade_index)

        rows: list[dict[str, object]] = []
        previous_selected_end_ms: int | None = None
        previous_current_end_ms: int | None = None
        for task, selected_offset in zip(quote_tasks, selected_offsets):
            quote_row = task["quote"]
            expected_qty = int(quote_row["_cum_delta"] or 0)
            expected_count = int(quote_row["_count_delta"] or 0)
            scores: list[CandidateScore] = []
            tick_scores: dict[int, tuple[int, int, int, int]] = {}
            for offset_ms, target_ms in task["targets"].items():
                bucket_end_ms = int(task["bucket_end_ms"]) + offset_ms
                if offset_ms == 0:
                    bucket_start_ms = previous_current_end_ms if previous_current_end_ms is not None else int(task["bucket_start_ms"])
                elif offset_ms == selected_offset:
                    bucket_start_ms = previous_selected_end_ms if previous_selected_end_ms is not None else int(task["bucket_start_ms"]) + offset_ms
                else:
                    bucket_start_ms = int(task["bucket_start_ms"]) + offset_ms
                actual_qty, actual_count = ThreeSecondBucketEvaluator._trade_delta(
                    trade_index,
                    bucket_start_ms,
                    bucket_end_ms,
                )
                tick_scores[offset_ms] = (
                    actual_qty,
                    actual_count,
                    abs(actual_qty - expected_qty),
                    abs(actual_count - expected_count),
                )
                snapshot = self._snapshot_for_offset(task, offset_ms, snapshots, quote_event_snapshots)
                scores.append(self._score_snapshot(f"offset_{offset_ms}", offset_ms, target_ms - int(quote_row["ts_ms"]), snapshot, quote_row))

            current = next(score for score in scores if score.event_delta == 0)
            best = next(score for score in scores if score.event_delta == selected_offset)
            best_tick = tick_scores[best.event_delta]
            current_tick = tick_scores[0]
            previous_selected_end_ms = int(task["bucket_end_ms"]) + selected_offset
            previous_current_end_ms = int(task["bucket_end_ms"])
            rows.append(
                {
                    "symbol": quote_row["symbol"],
                    "trade_date": quote_row["trade_date"],
                    "exchange_code": quote_row["exchange_code"],
                    "quote_seq": quote_row["seq"],
                    "event_id": task["quote_event_id"],
                    "ts_ms": quote_row["ts_ms"],
                    "current_mismatch_count": current.mismatch_count,
                    "current_price_mismatch_count": current.price_mismatch_count,
                    "current_qty_mismatch_count": current.qty_mismatch_count,
                    "aligned_mismatch_count": best.mismatch_count,
                    "aligned_price_mismatch_count": best.price_mismatch_count,
                    "aligned_qty_mismatch_count": best.qty_mismatch_count,
                    "improvement": current.mismatch_count - best.mismatch_count,
                    "selected_label": best.label,
                    "selected_event_delta": best.event_delta,
                    "selected_ts_delta_ms": best.ts_delta_ms,
                    "expected_bucket_qty": expected_qty,
                    "expected_bucket_count": expected_count,
                    "current_bucket_qty": current_tick[0],
                    "current_bucket_count": current_tick[1],
                    "current_tick_abs_error": current_tick[2] + current_tick[3],
                    "aligned_bucket_qty": best_tick[0],
                    "aligned_bucket_count": best_tick[1],
                    "aligned_tick_abs_error": best_tick[2] + best_tick[3],
                }
            )

        report = pl.from_dicts(rows) if rows else QuoteAlignedValidator._empty_report()
        return QuoteAlignmentResult(report=report, summary=QuoteAlignedValidator._build_summary(report))

    def _select_coherent_offsets(
        self,
        quote_tasks: list[dict[str, object]],
        snapshots: dict[int, dict[str, list[BookLevel]]],
        quote_event_snapshots: dict[int, dict[str, list[BookLevel]]],
        trade_index: tuple[list[int], list[int]],
    ) -> list[int]:
        if not quote_tasks:
            return []

        states: dict[int, tuple[tuple[int, int, int, int], list[int]]] = {
            offset_ms: ((0, 0, 0, 0), [])
            for offset_ms in self._offsets_for_session(quote_tasks[0]["quote"])
        }
        for task_index, task in enumerate(quote_tasks):
            quote_row = task["quote"]
            expected_qty = int(quote_row["_cum_delta"] or 0)
            expected_count = int(quote_row["_count_delta"] or 0)
            current_start_ms = (
                int(quote_tasks[task_index - 1]["bucket_end_ms"])
                if task_index
                else int(task["bucket_start_ms"])
            )
            current_qty, current_count = ThreeSecondBucketEvaluator._trade_delta(
                trade_index,
                current_start_ms,
                int(task["bucket_end_ms"]),
            )
            current_tick_error = abs(current_qty - expected_qty) + abs(current_count - expected_count)
            next_states: dict[int, tuple[tuple[int, int, int, int], list[int]]] = {}
            for current_offset in self._offsets_for_session(quote_row):
                current_end_ms = int(task["bucket_end_ms"]) + current_offset
                snapshot = self._snapshot_for_offset(task, current_offset, snapshots, quote_event_snapshots)
                book_score = self._score_snapshot(
                    f"offset_{current_offset}",
                    current_offset,
                    current_end_ms - int(quote_row["ts_ms"]),
                    snapshot,
                    quote_row,
                )
                best_state: tuple[tuple[int, int, int, int], list[int]] | None = None
                for previous_offset, (previous_cost, path) in states.items():
                    if path:
                        previous_task = quote_tasks[len(path) - 1]
                        previous_end_ms = int(previous_task["bucket_end_ms"]) + previous_offset
                    else:
                        previous_end_ms = int(task["bucket_start_ms"]) + current_offset
                    actual_qty, actual_count = ThreeSecondBucketEvaluator._trade_delta(
                        trade_index,
                        previous_end_ms,
                        current_end_ms,
                    )
                    tick_error = abs(actual_qty - expected_qty) + abs(actual_count - expected_count)
                    if (
                        self.selection == "book_with_tick_guard"
                        and tick_error > current_tick_error + self.max_tick_error_worsening
                    ):
                        continue
                    cost = self._append_cost(previous_cost, book_score, tick_error)
                    candidate = (cost, [*path, current_offset])
                    if best_state is None or candidate[0] < best_state[0]:
                        best_state = candidate
                if best_state is not None:
                    next_states[current_offset] = best_state
            states = next_states

        return min(states.values(), key=lambda state: state[0])[1]

    def _append_cost(
        self,
        previous_cost: tuple[int, int, int, int],
        book_score: CandidateScore,
        tick_error: int,
    ) -> tuple[int, int, int, int]:
        if self.selection == "tick_first":
            return (
                previous_cost[0] + tick_error,
                previous_cost[1] + book_score.mismatch_count,
                previous_cost[2] + book_score.price_mismatch_count,
                previous_cost[3] + abs(book_score.event_delta),
            )
        if self.selection == "book_with_tick_guard":
            return (
                previous_cost[0] + book_score.mismatch_count,
                previous_cost[1] + tick_error,
                previous_cost[2] + book_score.price_mismatch_count,
                previous_cost[3] + abs(book_score.event_delta),
            )
        return (
            previous_cost[0] + book_score.mismatch_count,
            previous_cost[1] + book_score.price_mismatch_count,
            previous_cost[2] + book_score.qty_mismatch_count,
            previous_cost[3] + tick_error,
        )

    def _build_quote_tasks(
        self,
        quote_rows: list[dict[str, object]],
        offsets_ms: tuple[int, ...],
    ) -> list[dict[str, object]]:
        tasks: list[dict[str, object]] = []
        for quote in quote_rows:
            bucket_end_ms = int(quote["ts_ms"]) + int(quote.get("quote_bucket_end_offset_ms") or 0)
            bucket_start_ms = bucket_end_ms - 3000
            targets = {offset_ms: bucket_end_ms + offset_ms for offset_ms in offsets_ms}
            tasks.append(
                {
                    "quote": quote,
                    "quote_event_id": int(quote.get("event_id") or 0),
                    "bucket_start_ms": bucket_start_ms,
                    "bucket_end_ms": bucket_end_ms,
                    "targets": targets,
                }
            )
        return tasks

    def _offsets_for_session(self, quote_row: dict[str, object]) -> tuple[int, ...]:
        market = _market_from_quote_row(quote_row)
        return self.market_offsets_ms.get(market, self.offsets_ms)

    @staticmethod
    def _snapshots_at_targets(events: pl.DataFrame, target_times: list[int]) -> dict[int, dict[str, list[BookLevel]]]:
        engine = OrderBookEngine()
        snapshots: dict[int, dict[str, list[BookLevel]]] = {}
        target_index = 0
        event_rows = events.filter(pl.col("event_type") != "quote").sort(["ts_ms", "event_id"]).iter_rows(named=True)
        for event in event_rows:
            event_ts_ms = int(event["ts_ms"])
            while target_index < len(target_times) and target_times[target_index] < event_ts_ms:
                snapshots[target_times[target_index]] = engine.snapshot_top_levels(depth=10)
                target_index += 1
            engine.apply_event(event)
        while target_index < len(target_times):
            snapshots[target_times[target_index]] = engine.snapshot_top_levels(depth=10)
            target_index += 1
        return snapshots

    @staticmethod
    def _snapshots_at_quote_events(events: pl.DataFrame) -> dict[int, dict[str, list[BookLevel]]]:
        engine = OrderBookEngine()
        snapshots: dict[int, dict[str, list[BookLevel]]] = {}
        for event in events.iter_rows(named=True):
            if event["event_type"] == "quote":
                snapshots[int(event["event_id"])] = engine.snapshot_top_levels(depth=10)
            else:
                engine.apply_event(event)
        return snapshots

    @staticmethod
    def _snapshot_for_offset(
        task: dict[str, object],
        offset_ms: int,
        snapshots: dict[int, dict[str, list[BookLevel]]],
        quote_event_snapshots: dict[int, dict[str, list[BookLevel]]],
    ) -> dict[str, list[BookLevel]]:
        if offset_ms == 0:
            quote_event_id = int(task["quote_event_id"])
            if quote_event_id in quote_event_snapshots:
                return quote_event_snapshots[quote_event_id]
        return snapshots[int(task["targets"][offset_ms])]

    @staticmethod
    def _score_snapshot(
        label: str,
        offset_ms: int,
        ts_delta_ms: int,
        snapshot: dict[str, list[BookLevel]],
        quote_row: dict[str, object],
    ) -> CandidateScore:
        return QuoteAlignedValidator()._score_candidate(label, offset_ms, ts_delta_ms, snapshot, quote_row)

    @staticmethod
    def _combined_score_key(tick_scores: dict[int, tuple[int, int, int, int]], selection: str):
        def key(score: CandidateScore) -> tuple[int, int, int, int, int, int]:
            tick_error = tick_scores[score.event_delta][2] + tick_scores[score.event_delta][3]
            if selection == "tick_first":
                return (
                    tick_error,
                    score.mismatch_count,
                    score.price_mismatch_count,
                    score.qty_mismatch_count,
                    abs(score.event_delta),
                    0 if score.event_delta == 0 else 1,
                )
            return (
                score.mismatch_count,
                score.price_mismatch_count,
                score.qty_mismatch_count,
                tick_error,
                abs(score.event_delta),
                0 if score.event_delta == 0 else 1,
            )

        return key

    def _select_candidate(
        self,
        scores: list[CandidateScore],
        tick_scores: dict[int, tuple[int, int, int, int]],
    ) -> CandidateScore:
        if self.selection == "book_with_tick_guard":
            current_tick_error = tick_scores[0][2] + tick_scores[0][3]
            guarded_scores = [
                score
                for score in scores
                if (tick_scores[score.event_delta][2] + tick_scores[score.event_delta][3])
                <= current_tick_error + self.max_tick_error_worsening
            ]
            return min(guarded_scores, key=self._combined_score_key(tick_scores, "book_first"))
        return min(scores, key=self._combined_score_key(tick_scores, self.selection))


def validate_session(session_dir: Path, validator: QuoteAlignedValidator) -> QuoteAlignmentResult:
    return validator.validate(
        pl.read_parquet(session_dir / "events.parquet"),
        pl.read_parquet(session_dir / "quotes.parquet"),
    )


def _parse_offsets(value: str) -> tuple[int, ...]:
    offsets = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    if 0 not in offsets:
        return (0, *offsets)
    return offsets


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate bounded quote-aligned order-book candidates.")
    backend_dir = Path(__file__).resolve().parent.parent
    default_root = backend_dir.parent / "data" / "processed"
    parser.add_argument("--processed-root", type=Path, default=default_root)
    parser.add_argument("--symbol", action="append", default=None)
    parser.add_argument("--max-past-ticks", type=int, default=3)
    parser.add_argument("--max-future-ticks", type=int, default=3)
    parser.add_argument("--max-future-ms", type=int, default=250)
    parser.add_argument("--quote-limit", type=int, default=None)
    parser.add_argument("--surface", action="store_true", help="Use fast persisted-validation surface evaluator.")
    parser.add_argument("--bucket", action="store_true", help="Evaluate 3-second L2 tick aggregate against L1 quote deltas.")
    parser.add_argument("--l1-l2-book", action="store_true", help="Evaluate L1 quote top10 against L2 RawBook at bucket candidate endpoints.")
    parser.add_argument(
        "--l1-l2-selection",
        choices=("book_first", "tick_first", "book_with_tick_guard"),
        default="book_with_tick_guard",
        help="Candidate selection priority for --l1-l2-book.",
    )
    parser.add_argument(
        "--max-tick-error-worsening",
        type=int,
        default=0,
        help="Allowed aggregate tick error worsening for --l1-l2-selection book_with_tick_guard.",
    )
    parser.add_argument(
        "--bucket-offsets-ms",
        default=None,
        help="Comma-separated candidate offsets for --bucket, for example 0,-250.",
    )
    parser.add_argument(
        "--sz-bucket-offsets-ms",
        default=None,
        help="Comma-separated SZ candidate offsets for --l1-l2-book, overriding --bucket-offsets-ms.",
    )
    parser.add_argument(
        "--sh-bucket-offsets-ms",
        default=None,
        help="Comma-separated SH candidate offsets for --l1-l2-book, overriding --bucket-offsets-ms.",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    validator = QuoteAlignedValidator(
        max_past_ticks=args.max_past_ticks,
        max_future_ticks=args.max_future_ticks,
        max_future_ms=args.max_future_ms,
        quote_limit=args.quote_limit,
    )
    surface_evaluator = SurfaceQuoteAlignmentEvaluator(
        max_future_ticks=args.max_future_ticks,
        max_future_ms=args.max_future_ms,
    )
    bucket_offsets = (
        _parse_offsets(args.bucket_offsets_ms)
        if args.bucket_offsets_ms
        else BUCKET_ALIGNMENT_OFFSETS_MS
    )
    market_offsets = {}
    if args.sz_bucket_offsets_ms:
        market_offsets["SZ"] = _parse_offsets(args.sz_bucket_offsets_ms)
    if args.sh_bucket_offsets_ms:
        market_offsets["SH"] = _parse_offsets(args.sh_bucket_offsets_ms)
    bucket_evaluator = ThreeSecondBucketEvaluator(offsets_ms=bucket_offsets)
    l1_l2_book_evaluator = L1L2BookAlignmentEvaluator(
        offsets_ms=bucket_offsets,
        market_offsets_ms=market_offsets,
        selection=args.l1_l2_selection,
        max_tick_error_worsening=args.max_tick_error_worsening,
    )
    output_dir = args.output_dir or args.processed_root
    output_dir.mkdir(parents=True, exist_ok=True)

    reports: list[pl.DataFrame] = []
    shift_reports: list[pl.DataFrame] = []
    summaries: list[dict[str, Any]] = []
    symbols = set(args.symbol or [])
    for session_dir in sorted(args.processed_root.glob("symbol=*/date=*")):
        symbol = session_dir.parent.name.removeprefix("symbol=")
        if symbols and symbol not in symbols:
            continue
        if args.bucket:
            bucket_report = bucket_evaluator.evaluate_session(session_dir)
            bucket_path = output_dir / f"quote_bucket_alignment_{symbol}.parquet"
            bucket_report.write_parquet(bucket_path, compression="zstd")
            summaries.append(
                {
                    "symbol": symbol,
                    "session_dir": str(session_dir),
                    "bucket_report": str(bucket_path),
                    "checked_quotes": bucket_report.height,
                    "current_tick_abs_error": int(
                        bucket_report.select((pl.col("current_qty_abs_error") + pl.col("current_count_abs_error")).sum()).item()
                    )
                    if not bucket_report.is_empty()
                    else 0,
                    "best_tick_abs_error": int(
                        bucket_report.select((pl.col("best_qty_abs_error") + pl.col("best_count_abs_error")).sum()).item()
                    )
                    if not bucket_report.is_empty()
                    else 0,
                    "book_mismatch_count": int(bucket_report.select(pl.col("book_mismatch_count").sum()).item())
                    if not bucket_report.is_empty()
                    else 0,
                }
            )
            continue
        if args.l1_l2_book:
            result = l1_l2_book_evaluator.evaluate_session(session_dir)
            reports.append(result.report)
            summaries.append({"symbol": symbol, "session_dir": str(session_dir), **asdict(result.summary)})
            continue
        result = surface_evaluator.evaluate_session(session_dir) if args.surface else validate_session(session_dir, validator)
        reports.append(result.report)
        if args.surface:
            shift_reports.append(SurfaceQuoteAlignmentEvaluator.build_level_shift_diagnostics(session_dir))
        summaries.append({"symbol": symbol, "session_dir": str(session_dir), **asdict(result.summary)})

    report = pl.concat(reports, how="vertical") if reports else QuoteAlignedValidator._empty_report()
    report_path = output_dir / "quote_alignment_report.parquet"
    summary_path = output_dir / "quote_alignment_summary.json"
    report.write_parquet(report_path, compression="zstd")
    shift_path = output_dir / "quote_alignment_shift_diagnostics.parquet"
    if shift_reports:
        pl.concat(shift_reports, how="vertical").write_parquet(shift_path, compression="zstd")
    summary_path.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "report": str(report_path),
                "shift_diagnostics": str(shift_path) if shift_reports else None,
                "summary": str(summary_path),
                "sessions": summaries,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

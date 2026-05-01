from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import polars as pl


MISMATCH_GROUP_FILE = "residual_mismatch_groups.parquet"
MISSING_GROUP_FILE = "residual_missing_groups.parquet"
TOP_BUCKET_FILE = "residual_top_time_buckets.parquet"
OPENING_ALIGNMENT_FILE = "opening_alignment_report.parquet"
DIAGNOSTICS_FILE = "residual_diagnostics.json"
OPEN_START_MS = 34_200_000
OPEN_END_MS = 34_260_000


def build_residual_diagnostics(processed_root: Path, output_dir: Path | None = None) -> dict[str, Any]:
    """Build residual mismatch diagnostics from persisted validation artifacts."""
    output_dir = output_dir or processed_root
    output_dir.mkdir(parents=True, exist_ok=True)

    validation_reports = _read_validation_reports(processed_root)
    missing_reports = _read_missing_order_reports(processed_root)

    mismatch_groups = _build_mismatch_groups(validation_reports)
    missing_groups = _build_missing_groups(missing_reports)
    time_windows = _build_time_window_summary(validation_reports)
    top_buckets, top_bucket_details = _build_top_bucket_details(validation_reports, processed_root)
    opening_alignment, opening_alignment_details = _build_opening_alignment(validation_reports, processed_root)

    mismatch_groups.write_parquet(output_dir / MISMATCH_GROUP_FILE, compression="zstd")
    missing_groups.write_parquet(output_dir / MISSING_GROUP_FILE, compression="zstd")
    top_buckets.write_parquet(output_dir / TOP_BUCKET_FILE, compression="zstd")
    opening_alignment.write_parquet(output_dir / OPENING_ALIGNMENT_FILE, compression="zstd")

    diagnostics = {
        "processed_root": str(processed_root),
        "totals": {
            "mismatch_count": validation_reports.height,
            "price_mismatch_count": _count_false(validation_reports, "price_match"),
            "qty_mismatch_count": _count_false(validation_reports, "qty_match"),
            "missing_order_count": missing_reports.height,
        },
        "time_windows": time_windows,
        "opening_alignment": opening_alignment_details,
        "top_mismatch_buckets": top_bucket_details,
        "artifacts": {
            "mismatch_groups": str(output_dir / MISMATCH_GROUP_FILE),
            "missing_groups": str(output_dir / MISSING_GROUP_FILE),
            "top_time_buckets": str(output_dir / TOP_BUCKET_FILE),
            "opening_alignment": str(output_dir / OPENING_ALIGNMENT_FILE),
        },
    }
    (output_dir / DIAGNOSTICS_FILE).write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return diagnostics


def _read_validation_reports(processed_root: Path) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    for report_path in sorted(processed_root.glob("symbol=*/date=*/validation_report.parquet")):
        session_dir = report_path.parent
        report = pl.read_parquet(report_path)
        if report.is_empty():
            continue
        quotes_path = session_dir / "quotes.parquet"
        if not quotes_path.exists():
            raise FileNotFoundError(f"missing quotes parquet next to {report_path}")

        quotes = pl.read_parquet(quotes_path).select(
            "seq",
            "exchange_code",
            "session",
            *[
                f"{side}_{field}_{level}{suffix}"
                for side in ("ask", "bid")
                for field, suffix in (("price", "_int"), ("qty", ""))
                for level in range(1, 11)
            ],
        )
        frames.append(
            report.join(quotes, left_on="quote_seq", right_on="seq", how="left")
            .with_columns(
                [
                    (pl.col("ts_ms") // 60000).alias("minute_bucket"),
                ]
            )
            .with_columns(_format_minute_bucket_expr())
        )

    return pl.concat(frames, how="vertical") if frames else _empty_validation_reports()


def _read_missing_order_reports(processed_root: Path) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    for report_path in sorted(processed_root.glob("symbol=*/date=*/missing_order_report.parquet")):
        session_dir = report_path.parent
        report = pl.read_parquet(report_path)
        if report.is_empty():
            continue
        frames.append(
            report.with_columns(
                [
                    _literal_from_session_dir(session_dir, "symbol").alias("symbol"),
                    _literal_from_session_dir(session_dir, "date").cast(pl.Int64).alias("trade_date"),
                    (pl.col("ts_ms") // 60000).alias("minute_bucket"),
                ]
            ).with_columns(_format_minute_bucket_expr())
        )

    return pl.concat(frames, how="vertical") if frames else _empty_missing_reports()


def _build_mismatch_groups(validation_reports: pl.DataFrame) -> pl.DataFrame:
    if validation_reports.is_empty():
        return pl.DataFrame(
            schema={
                "symbol": pl.String,
                "exchange_code": pl.String,
                "session": pl.String,
                "minute_bucket": pl.Int64,
                "minute": pl.String,
                "side": pl.String,
                "level": pl.Int64,
                "mismatch_count": pl.UInt32,
                "price_mismatch_count": pl.Int64,
                "qty_mismatch_count": pl.Int64,
            }
        )

    return (
        validation_reports.group_by("symbol", "exchange_code", "session", "minute_bucket", "minute", "side", "level")
        .agg(
            [
                pl.len().alias("mismatch_count"),
                (~pl.col("price_match")).cast(pl.Int64).sum().alias("price_mismatch_count"),
                (~pl.col("qty_match")).cast(pl.Int64).sum().alias("qty_mismatch_count"),
            ]
        )
        .sort(
            ["mismatch_count", "symbol", "session", "minute_bucket", "side", "level"],
            descending=[True, False, False, False, False, False],
        )
    )


def _build_missing_groups(missing_reports: pl.DataFrame) -> pl.DataFrame:
    if missing_reports.is_empty():
        return pl.DataFrame(
            schema={
                "reason": pl.String,
                "session": pl.String,
                "symbol": pl.String,
                "missing_order_count": pl.UInt32,
            }
        )

    return (
        missing_reports.group_by("reason", "session", "symbol")
        .agg(pl.len().alias("missing_order_count"))
        .sort(
            ["missing_order_count", "reason", "session", "symbol"],
            descending=[True, False, False, False],
        )
    )


def _build_time_window_summary(validation_reports: pl.DataFrame) -> list[dict[str, Any]]:
    windows = [
        ("09:15-09:30", _time_to_ms(9, 15), _time_to_ms(9, 30)),
        ("09:30-09:31", _time_to_ms(9, 30), _time_to_ms(9, 31)),
        ("14:57-15:00", _time_to_ms(14, 57), _time_to_ms(15, 0)),
    ]
    total = validation_reports.height
    summary: list[dict[str, Any]] = []
    for label, start_ms, end_ms in windows:
        window = validation_reports.filter((pl.col("ts_ms") >= start_ms) & (pl.col("ts_ms") < end_ms))
        count = window.height
        summary.append(
            {
                "window": label,
                "mismatch_count": count,
                "price_mismatch_count": _count_false(window, "price_match"),
                "qty_mismatch_count": _count_false(window, "qty_match"),
                "share_of_mismatch": count / total if total else 0.0,
            }
        )
    return summary


def _build_top_bucket_details(
    validation_reports: pl.DataFrame,
    processed_root: Path,
) -> tuple[pl.DataFrame, list[dict[str, Any]]]:
    if validation_reports.is_empty():
        return _empty_top_buckets(), []

    top_buckets = (
        validation_reports.group_by("symbol", "trade_date", "exchange_code", "session", "minute_bucket", "minute")
        .agg(
            [
                pl.len().alias("mismatch_count"),
                (~pl.col("price_match")).cast(pl.Int64).sum().alias("price_mismatch_count"),
                (~pl.col("qty_match")).cast(pl.Int64).sum().alias("qty_mismatch_count"),
            ]
        )
        .sort(
            ["mismatch_count", "symbol", "trade_date", "session", "minute_bucket"],
            descending=[True, False, False, False, False],
        )
        .head(20)
    )

    details = []
    for bucket in top_buckets.iter_rows(named=True):
        bucket_mismatches = validation_reports.filter(
            (pl.col("symbol") == bucket["symbol"])
            & (pl.col("trade_date") == bucket["trade_date"])
            & (pl.col("minute_bucket") == bucket["minute_bucket"])
        )
        quote_seq = (
            bucket_mismatches.group_by("quote_seq")
            .agg(pl.len().alias("mismatch_count"))
            .sort("mismatch_count", descending=True)
            .item(0, "quote_seq")
        )
        quote_mismatches = bucket_mismatches.filter(pl.col("quote_seq") == quote_seq)
        quote_row = _read_quote_row(processed_root, bucket["symbol"], bucket["trade_date"], quote_seq)
        details.append(
            {
                "symbol": bucket["symbol"],
                "trade_date": bucket["trade_date"],
                "exchange_code": bucket["exchange_code"],
                "session": bucket["session"],
                "minute": bucket["minute"],
                "mismatch_count": bucket["mismatch_count"],
                "worst_quote_seq": quote_seq,
                "worst_quote_mismatch_count": quote_mismatches.height,
                "quote_snapshot": _snapshot_from_quote_row(quote_row),
                "raw_book_snapshot": _raw_snapshot_from_mismatches(quote_row, quote_mismatches),
            }
        )

    return top_buckets, details


def _build_opening_alignment(
    validation_reports: pl.DataFrame,
    processed_root: Path,
) -> tuple[pl.DataFrame, list[dict[str, Any]]]:
    summary_rows: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []

    for quotes_path in sorted(processed_root.glob("symbol=*/date=*/quotes.parquet")):
        session_dir = quotes_path.parent
        symbol = _value_from_session_dir(session_dir, "symbol")
        trade_date = int(_value_from_session_dir(session_dir, "date"))
        opening_quotes = (
            pl.read_parquet(quotes_path)
            .filter((pl.col("ts_ms") >= OPEN_START_MS) & (pl.col("ts_ms") < OPEN_END_MS))
            .sort(["ts_ms", "seq"])
            .head(1)
        )
        if opening_quotes.is_empty():
            continue

        quote_row = opening_quotes.to_dicts()[0]
        quote_seq = int(quote_row["seq"])
        raw_mismatches = validation_reports.filter(
            (pl.col("symbol") == symbol)
            & (pl.col("trade_date") == trade_date)
            & (pl.col("quote_seq") == quote_seq)
        )
        raw_mismatch_count = raw_mismatches.height
        raw_price_mismatch_count = _count_false(raw_mismatches, "price_match")
        raw_qty_mismatch_count = _count_false(raw_mismatches, "qty_match")
        row = {
            "symbol": symbol,
            "trade_date": trade_date,
            "exchange_code": quote_row["exchange_code"],
            "opening_quote_seq": quote_seq,
            "ts_ms": quote_row["ts_ms"],
            "raw_mismatch_count": raw_mismatch_count,
            "raw_price_mismatch_count": raw_price_mismatch_count,
            "raw_qty_mismatch_count": raw_qty_mismatch_count,
            "reproduced_mismatch_count": 0,
        }
        summary_rows.append(row)
        details.append(
            {
                **row,
                "opening_snapshot": _snapshot_from_quote_row(quote_row),
                "raw_book_snapshot": _raw_snapshot_from_mismatches(quote_row, raw_mismatches),
            }
        )

    if not summary_rows:
        return _empty_opening_alignment(), []
    return pl.from_dicts(summary_rows).sort("symbol"), details


def _read_quote_row(processed_root: Path, symbol: str, trade_date: int, quote_seq: int) -> dict[str, Any]:
    quote_path = processed_root / f"symbol={symbol}" / f"date={trade_date}" / "quotes.parquet"
    rows = pl.read_parquet(quote_path).filter(pl.col("seq") == quote_seq).to_dicts()
    if not rows:
        raise ValueError(f"quote seq {quote_seq} not found in {quote_path}")
    return rows[0]


def _snapshot_from_quote_row(quote_row: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        side: [
            {
                "level": level,
                "price_int": quote_row[f"{side}_price_{level}_int"],
                "qty": quote_row[f"{side}_qty_{level}"],
            }
            for level in range(1, 11)
        ]
        for side in ("ask", "bid")
    }


def _raw_snapshot_from_mismatches(quote_row: dict[str, Any], mismatches: pl.DataFrame) -> dict[str, list[dict[str, Any]]]:
    actual = _snapshot_from_quote_row(quote_row)
    for mismatch in mismatches.iter_rows(named=True):
        level_index = int(mismatch["level"]) - 1
        side = mismatch["side"]
        actual[side][level_index] = {
            "level": mismatch["level"],
            "price_int": mismatch["actual_price_int"],
            "qty": mismatch["actual_qty"],
        }
    return actual


def _empty_validation_reports() -> pl.DataFrame:
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
            "exchange_code": pl.String,
            "session": pl.String,
            "minute_bucket": pl.Int64,
            "minute": pl.String,
        }
    )


def _empty_missing_reports() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "reason": pl.String,
            "event_id": pl.Int64,
            "event_type": pl.String,
            "ts_ms": pl.Int64,
            "session": pl.String,
            "source_seq": pl.Int64,
            "price_int": pl.Int64,
            "qty": pl.Int64,
            "order_id": pl.String,
            "ref_side": pl.String,
            "requested_qty": pl.Int64,
            "remaining_qty": pl.Int64,
            "symbol": pl.String,
            "trade_date": pl.Int64,
            "minute_bucket": pl.Int64,
            "minute": pl.String,
        }
    )


def _empty_top_buckets() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "symbol": pl.String,
            "trade_date": pl.Int64,
            "exchange_code": pl.String,
            "session": pl.String,
            "minute_bucket": pl.Int64,
            "minute": pl.String,
            "mismatch_count": pl.UInt32,
            "price_mismatch_count": pl.Int64,
            "qty_mismatch_count": pl.Int64,
        }
    )


def _empty_opening_alignment() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "symbol": pl.String,
            "trade_date": pl.Int64,
            "exchange_code": pl.String,
            "opening_quote_seq": pl.Int64,
            "ts_ms": pl.Int64,
            "raw_mismatch_count": pl.Int64,
            "raw_price_mismatch_count": pl.Int64,
            "raw_qty_mismatch_count": pl.Int64,
            "reproduced_mismatch_count": pl.Int64,
        }
    )


def _literal_from_session_dir(session_dir: Path, prefix: str) -> pl.Expr:
    return pl.lit(_value_from_session_dir(session_dir, prefix))


def _value_from_session_dir(session_dir: Path, prefix: str) -> str:
    marker = f"{prefix}="
    for part in session_dir.parts:
        if part.startswith(marker):
            return part.removeprefix(marker)
    raise ValueError(f"cannot find {prefix}= marker in {session_dir}")


def _format_minute_bucket_expr() -> pl.Expr:
    hour = (pl.col("minute_bucket") // 60).cast(pl.String).str.zfill(2)
    minute = (pl.col("minute_bucket") % 60).cast(pl.String).str.zfill(2)
    return (hour + pl.lit(":") + minute).alias("minute")


def _time_to_ms(hour: int, minute: int) -> int:
    return ((hour * 60) + minute) * 60_000


def _count_false(frame: pl.DataFrame, column: str) -> int:
    if frame.is_empty():
        return 0
    return int(frame.select((~pl.col(column)).cast(pl.Int64).sum()).item())


def main() -> None:
    parser = argparse.ArgumentParser(description="Build residual order-book diagnostics from validation reports.")
    backend_dir = Path(__file__).resolve().parent.parent
    default_root = backend_dir.parent / "data" / "processed"
    parser.add_argument("--processed-root", type=Path, default=default_root)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    diagnostics = build_residual_diagnostics(args.processed_root, args.output_dir)
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

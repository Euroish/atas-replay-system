from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from .aggregate_match import AggregateMatchSummary, ThreeSecondAggregateMatcher
from .config import AppPaths
from .event_builder import EventBuilder
from .normalizer import load_csv_table, normalize_orders, normalize_quotes, normalize_trades
from .validator import ValidationSummary, OrderBookValidator
from .visible_book import VisibleBookBuilder, VisibleBookSummary


CSV_FILE_NAMES = {
    "quotes": "行情.csv",
    "orders": "逐笔委托.csv",
    "trades": "逐笔成交.csv",
}


@dataclass(frozen=True)
class ImportArtifact:
    name: str
    source_file: str
    parquet_file: str
    encoding: str
    source_rows: int
    null_bytes_removed: int


@dataclass(frozen=True)
class ImportSummary:
    session_id: str
    symbol: str
    trade_date: int
    raw_dir: str
    processed_dir: str
    artifacts: list[ImportArtifact]
    warnings: list[str]
    validation_summary: ValidationSummary | None = None
    visible_book_summary: VisibleBookSummary | None = None
    aggregate_match_summary: AggregateMatchSummary | None = None


class SessionImporter:
    def __init__(self, backend_dir: Path) -> None:
        self.paths = AppPaths.from_backend_dir(backend_dir)

    def import_session(self, source_dir: Path) -> ImportSummary:
        self._validate_source_dir(source_dir)
        tables = {name: load_csv_table(source_dir / file_name) for name, file_name in CSV_FILE_NAMES.items()}
        symbol, trade_date = self._infer_identity(tables)
        raw_dir = self.paths.session_raw_dir(symbol, trade_date)
        processed_dir = self.paths.session_processed_dir(symbol, trade_date)
        raw_dir.mkdir(parents=True, exist_ok=True)
        processed_dir.mkdir(parents=True, exist_ok=True)

        artifacts = []
        warnings: list[str] = []
        normalized_frames = {
            "quotes": normalize_quotes(tables["quotes"]),
            "orders": normalize_orders(tables["orders"]),
            "trades": normalize_trades(tables["trades"]),
        }
        event_result = EventBuilder().build(
            normalized_frames["quotes"],
            normalized_frames["orders"],
            normalized_frames["trades"],
        )
        validation_result = OrderBookValidator().validate(
            event_result.events,
            normalized_frames["quotes"],
        )
        aggregate_match_result = ThreeSecondAggregateMatcher().match(
            normalized_frames["quotes"],
            normalized_frames["trades"],
        )
        visible_book_result = VisibleBookBuilder().build(
            event_result.events,
            normalized_frames["quotes"],
        )

        for name, file_name in CSV_FILE_NAMES.items():
            source_path = source_dir / file_name
            copied_path = raw_dir / file_name
            shutil.copy2(source_path, copied_path)
            parquet_path = processed_dir / f"{name}.parquet"
            normalized_frames[name].write_parquet(parquet_path, compression="zstd")

            table = tables[name]
            artifacts.append(
                ImportArtifact(
                    name=name,
                    source_file=str(copied_path),
                    parquet_file=str(parquet_path),
                    encoding=table.encoding,
                    source_rows=table.row_count,
                    null_bytes_removed=table.null_bytes_removed,
                )
            )

            if table.null_bytes_removed:
                warnings.append(f"{file_name}: removed {table.null_bytes_removed} null bytes")

        events_path = processed_dir / "events.parquet"
        event_result.events.write_parquet(events_path, compression="zstd")
        artifacts.append(
            ImportArtifact(
                name="events",
                source_file="generated",
                parquet_file=str(events_path),
                encoding="derived",
                source_rows=event_result.events.height,
                null_bytes_removed=0,
            )
        )
        warnings.extend(event_result.warnings)

        validation_path = processed_dir / "validation_report.parquet"
        validation_result.report.write_parquet(validation_path, compression="zstd")
        artifacts.append(
            ImportArtifact(
                name="validation_report",
                source_file="generated",
                parquet_file=str(validation_path),
                encoding="derived",
                source_rows=validation_result.report.height,
                null_bytes_removed=0,
            )
        )
        missing_order_path = processed_dir / "missing_order_report.parquet"
        validation_result.missing_order_report.write_parquet(missing_order_path, compression="zstd")
        artifacts.append(
            ImportArtifact(
                name="missing_order_report",
                source_file="generated",
                parquet_file=str(missing_order_path),
                encoding="derived",
                source_rows=validation_result.missing_order_report.height,
                null_bytes_removed=0,
            )
        )
        aggregate_match_path = processed_dir / "aggregate_match_report.parquet"
        aggregate_match_result.report.write_parquet(aggregate_match_path, compression="zstd")
        artifacts.append(
            ImportArtifact(
                name="aggregate_match_report",
                source_file="generated",
                parquet_file=str(aggregate_match_path),
                encoding="derived",
                source_rows=aggregate_match_result.report.height,
                null_bytes_removed=0,
            )
        )
        visible_checkpoint_path = processed_dir / "visible_orderbook_checkpoints.parquet"
        visible_book_result.checkpoints.write_parquet(visible_checkpoint_path, compression="zstd")
        artifacts.append(
            ImportArtifact(
                name="visible_orderbook_checkpoints",
                source_file="generated",
                parquet_file=str(visible_checkpoint_path),
                encoding="derived",
                source_rows=visible_book_result.checkpoints.height,
                null_bytes_removed=0,
            )
        )

        summary = ImportSummary(
            session_id=f"{symbol}-{trade_date}",
            symbol=symbol,
            trade_date=trade_date,
            raw_dir=str(raw_dir),
            processed_dir=str(processed_dir),
            artifacts=artifacts,
            warnings=warnings,
            validation_summary=validation_result.summary,
            visible_book_summary=visible_book_result.summary,
            aggregate_match_summary=aggregate_match_result.summary,
        )
        report_path = processed_dir / "import_report.json"
        report_path.write_text(
            json.dumps(asdict(summary), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return summary

    @staticmethod
    def _infer_identity(tables: dict[str, object]) -> tuple[str, int]:
        symbols = set()
        trade_dates = set()
        for table in tables.values():
            first_row = table.rows[0]
            symbols.add(first_row["万得代码"].strip())
            trade_dates.add(int(first_row["自然日"].strip()))
        if len(symbols) != 1 or len(trade_dates) != 1:
            raise ValueError("input files do not belong to a single symbol/trade_date session")
        return symbols.pop(), trade_dates.pop()

    @staticmethod
    def _validate_source_dir(source_dir: Path) -> None:
        missing_files = [file_name for file_name in CSV_FILE_NAMES.values() if not (source_dir / file_name).exists()]
        if missing_files:
            missing = ", ".join(missing_files)
            raise FileNotFoundError(f"missing required csv files in {source_dir}: {missing}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import one replay session into standardized Parquet files.")
    backend_dir = Path(__file__).resolve().parent.parent
    default_source = backend_dir.parent.parent / "实例材料" / "个股数据" / "600726.SH"
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=default_source,
        help=f"Directory containing {', '.join(CSV_FILE_NAMES.values())}. Default: {default_source}",
    )
    args = parser.parse_args()

    importer = SessionImporter(backend_dir)
    summary = importer.import_session(args.source_dir)
    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

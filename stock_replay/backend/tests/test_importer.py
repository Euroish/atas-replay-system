from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from stock_replay_backend.importer import SessionImporter


def test_import_sample_session() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    repo_dir = backend_dir.parents[1]
    source_dir = repo_dir / "实例材料" / "个股数据" / "600726.SH"

    importer = SessionImporter(backend_dir)
    summary = importer.import_session(source_dir)

    assert summary.symbol == "600726.SH"
    assert summary.trade_date == 20260424
    assert summary.session_id == "600726.SH-20260424"
    assert len(summary.artifacts) == 6

    processed_dir = Path(summary.processed_dir)
    quotes = pl.read_parquet(processed_dir / "quotes.parquet")
    orders = pl.read_parquet(processed_dir / "orders.parquet")
    trades = pl.read_parquet(processed_dir / "trades.parquet")
    events = pl.read_parquet(processed_dir / "events.parquet")
    validation_report = pl.read_parquet(processed_dir / "validation_report.parquet")
    missing_order_report = pl.read_parquet(processed_dir / "missing_order_report.parquet")

    assert quotes.height == 5005
    assert orders.height == 291702
    assert trades.height == 222530
    assert events.height == 519237
    assert validation_report.height >= 0
    assert missing_order_report.height >= 0

    assert {"symbol", "trade_date", "time_raw", "ts_ms", "price_scale"}.issubset(quotes.columns)
    assert {"symbol", "trade_date", "time_raw", "ts_ms", "exchange_order_id"}.issubset(orders.columns)
    assert {"symbol", "trade_date", "time_raw", "ts_ms", "aggressor_side"}.issubset(trades.columns)
    assert {"event_id", "event_type", "priority", "source_seq", "payload_ref"}.issubset(events.columns)
    assert {"quote_seq", "side", "level", "expected_price_int", "actual_price_int"}.issubset(validation_report.columns)
    assert {"reason", "event_id", "event_type", "ts_ms", "session", "source_seq"}.issubset(
        missing_order_report.columns
    )
    assert summary.validation_summary is not None

    report = json.loads((processed_dir / "import_report.json").read_text(encoding="utf-8"))
    assert report["warnings"]
    assert report["validation_summary"]["checked_quotes"] == 5005

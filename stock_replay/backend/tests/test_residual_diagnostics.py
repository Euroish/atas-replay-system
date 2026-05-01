from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from stock_replay_backend.residual_diagnostics import (
    DIAGNOSTICS_FILE,
    MISSING_GROUP_FILE,
    MISMATCH_GROUP_FILE,
    OPENING_ALIGNMENT_FILE,
    TOP_BUCKET_FILE,
    build_residual_diagnostics,
)


def test_build_residual_diagnostics_outputs_grouped_artifacts(tmp_path: Path) -> None:
    session_dir = tmp_path / "symbol=TEST.SH" / "date=20260101"
    session_dir.mkdir(parents=True)

    quote_row = {
        "seq": 10,
        "exchange_code": "TEST",
        "session": "continuous_am",
        "ts_ms": 34_200_000,
    }
    for side in ("ask", "bid"):
        for level in range(1, 11):
            quote_row[f"{side}_price_{level}_int"] = 1000 + level
            quote_row[f"{side}_qty_{level}"] = 100 * level
    pl.DataFrame([quote_row]).write_parquet(session_dir / "quotes.parquet")

    pl.DataFrame(
        [
            {
                "symbol": "TEST.SH",
                "trade_date": 20260101,
                "quote_seq": 10,
                "event_id": 1,
                "ts_ms": 34_200_000,
                "side": "ask",
                "level": 1,
                "expected_price_int": 1001,
                "actual_price_int": 999,
                "expected_qty": 100,
                "actual_qty": 90,
                "price_match": False,
                "qty_match": False,
            },
            {
                "symbol": "TEST.SH",
                "trade_date": 20260101,
                "quote_seq": 10,
                "event_id": 1,
                "ts_ms": 34_200_000,
                "side": "bid",
                "level": 1,
                "expected_price_int": 1001,
                "actual_price_int": 1001,
                "expected_qty": 100,
                "actual_qty": 80,
                "price_match": True,
                "qty_match": False,
            },
        ]
    ).write_parquet(session_dir / "validation_report.parquet")

    pl.DataFrame(
        [
            {
                "reason": "missing_cancel_order",
                "event_id": 2,
                "event_type": "order_cancel",
                "ts_ms": 34_200_001,
                "session": "continuous_am",
                "source_seq": 20,
                "price_int": 1001,
                "qty": 100,
                "order_id": "abc",
                "ref_side": None,
                "requested_qty": None,
                "remaining_qty": None,
            }
        ]
    ).write_parquet(session_dir / "missing_order_report.parquet")

    diagnostics = build_residual_diagnostics(tmp_path)

    assert diagnostics["totals"] == {
        "mismatch_count": 2,
        "price_mismatch_count": 1,
        "qty_mismatch_count": 2,
        "missing_order_count": 1,
    }
    assert diagnostics["time_windows"][1]["window"] == "09:30-09:31"
    assert diagnostics["time_windows"][1]["mismatch_count"] == 2
    assert diagnostics["top_mismatch_buckets"][0]["raw_book_snapshot"]["ask"][0] == {
        "level": 1,
        "price_int": 999,
        "qty": 90,
    }
    assert diagnostics["opening_alignment"][0]["opening_quote_seq"] == 10
    assert diagnostics["opening_alignment"][0]["raw_mismatch_count"] == 2
    assert diagnostics["opening_alignment"][0]["reproduced_mismatch_count"] == 0

    for artifact in (
        DIAGNOSTICS_FILE,
        MISMATCH_GROUP_FILE,
        MISSING_GROUP_FILE,
        TOP_BUCKET_FILE,
        OPENING_ALIGNMENT_FILE,
    ):
        assert (tmp_path / artifact).exists()

    saved = json.loads((tmp_path / DIAGNOSTICS_FILE).read_text(encoding="utf-8"))
    assert saved["totals"]["mismatch_count"] == 2

    mismatch_groups = pl.read_parquet(tmp_path / MISMATCH_GROUP_FILE)
    missing_groups = pl.read_parquet(tmp_path / MISSING_GROUP_FILE)

    assert {"exchange_code", "session", "minute", "side", "level", "mismatch_count"}.issubset(
        mismatch_groups.columns
    )
    assert missing_groups.item(0, "reason") == "missing_cancel_order"

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import polars as pl
import pytest

from stock_replay_backend.checkpoint_store import VISIBLE_CHECKPOINT_FILE, VisibleCheckpointStore


def test_load_checkpoint_returns_latest_checkpoint_at_or_before_target(tmp_path: Path) -> None:
    processed_root = tmp_path / "processed"
    session_dir = processed_root / "symbol=sample" / "date=20260101"
    session_dir.mkdir(parents=True)
    _checkpoint_frame(
        [
            *_checkpoint_rows(ts_ms=1000, quote_seq=1, ask_qty=10, bid_qty=20),
            *_checkpoint_rows(ts_ms=2000, quote_seq=2, ask_qty=15, bid_qty=25),
        ]
    ).write_parquet(session_dir / VISIBLE_CHECKPOINT_FILE)

    store = VisibleCheckpointStore(processed_root)
    checkpoint = store.load_checkpoint("sample", 20260101, 2500)
    repeated = store.load_checkpoint("sample", 20260101, 2500)

    assert checkpoint.ts_ms == 2000
    assert checkpoint.quote_seq == 2
    assert len(checkpoint.asks) == 10
    assert len(checkpoint.bids) == 10
    assert checkpoint.asks[0].price_int == 101
    assert checkpoint.asks[0].qty == 15
    assert checkpoint.bids[0].price_int == 99
    assert checkpoint.bids[0].qty == 25
    assert checkpoint.correction_cost == 20
    assert asdict(checkpoint) == asdict(repeated)


def test_load_checkpoint_can_limit_depth(tmp_path: Path) -> None:
    processed_root = tmp_path / "processed"
    session_dir = processed_root / "symbol=sample" / "date=20260101"
    session_dir.mkdir(parents=True)
    _checkpoint_frame(_checkpoint_rows(ts_ms=1000, quote_seq=1, ask_qty=10, bid_qty=20)).write_parquet(
        session_dir / VISIBLE_CHECKPOINT_FILE
    )

    checkpoint = VisibleCheckpointStore(processed_root).load_checkpoint("sample", 20260101, 1000, depth=3)

    assert [level.level for level in checkpoint.asks] == [1, 2, 3]
    assert [level.level for level in checkpoint.bids] == [1, 2, 3]


def test_load_checkpoint_rejects_time_before_first_checkpoint(tmp_path: Path) -> None:
    processed_root = tmp_path / "processed"
    session_dir = processed_root / "symbol=sample" / "date=20260101"
    session_dir.mkdir(parents=True)
    _checkpoint_frame(_checkpoint_rows(ts_ms=1000, quote_seq=1, ask_qty=10, bid_qty=20)).write_parquet(
        session_dir / VISIBLE_CHECKPOINT_FILE
    )

    with pytest.raises(ValueError, match="no visible checkpoint"):
        VisibleCheckpointStore(processed_root).load_checkpoint("sample", 20260101, 999)


def _checkpoint_rows(ts_ms: int, quote_seq: int, ask_qty: int, bid_qty: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for side in ("ask", "bid"):
        for level in range(1, 11):
            visible_price = 100 + level if side == "ask" else 100 - level
            visible_qty = ask_qty if side == "ask" else bid_qty
            rows.append(
                {
                    "symbol": "sample",
                    "trade_date": 20260101,
                    "checkpoint_id": f"sample-20260101-{quote_seq}",
                    "quote_seq": quote_seq,
                    "event_id": quote_seq * 10,
                    "ts_ms": ts_ms,
                    "session": "continuous_am",
                    "source": "quote_anchor",
                    "side": side,
                    "level": level,
                    "visible_price_int": visible_price,
                    "visible_qty": visible_qty,
                    "raw_price_int": visible_price,
                    "raw_qty": visible_qty - 1,
                    "raw_price_match": True,
                    "raw_qty_match": False,
                    "quote_anchor_match": True,
                    "correction_price_changed": False,
                    "inter_quote_drift_abs_qty": 1,
                    "correction_cost": 1,
                    "correction_abs_qty": 1,
                }
            )
    return rows


def _checkpoint_frame(rows: list[dict[str, object]]) -> pl.DataFrame:
    return pl.DataFrame(rows)

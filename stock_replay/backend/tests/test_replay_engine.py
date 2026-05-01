from __future__ import annotations

from pathlib import Path

import polars as pl

from stock_replay_backend.checkpoint_store import VISIBLE_CHECKPOINT_FILE
from stock_replay_backend.replay_engine import ReplayEngine


def test_load_window_returns_checkpoint_frame(tmp_path: Path) -> None:
    processed_root = tmp_path / "processed"
    session_dir = processed_root / "symbol=sample" / "date=20260101"
    session_dir.mkdir(parents=True)
    _checkpoint_frame(
        [
            *_checkpoint_rows(ts_ms=1000, quote_seq=1, ask_qty=10, bid_qty=20),
            *_checkpoint_rows(ts_ms=2000, quote_seq=2, ask_qty=15, bid_qty=25),
            *_checkpoint_rows(ts_ms=4000, quote_seq=3, ask_qty=18, bid_qty=28),
        ]
    ).write_parquet(session_dir / VISIBLE_CHECKPOINT_FILE)

    engine = ReplayEngine(processed_root)
    frame = engine.load_window(
        workspace_id="workspace-a",
        window_id="window-a",
        symbol="sample",
        trade_date=20260101,
        ts_ms=2500,
    )

    assert frame.status == "paused"
    assert frame.current_ts_ms == 2000
    assert frame.checkpoint_ts_ms == 2000
    assert frame.virtual_ts_ms == 2500
    assert frame.checkpoint["quote_seq"] == 2
    assert frame.orderbook_top["asks"][0]["price_int"] == 101
    assert frame.orderbook_top["asks"][0]["qty"] == 15
    assert frame.orderbook_top["bids"][0]["price_int"] == 99
    assert frame.orderbook_top["bids"][0]["qty"] == 25


def test_window_controls_stay_isolated(tmp_path: Path) -> None:
    processed_root = tmp_path / "processed"
    session_dir = processed_root / "symbol=sample" / "date=20260101"
    session_dir.mkdir(parents=True)
    _checkpoint_frame(
        [
            *_checkpoint_rows(ts_ms=1000, quote_seq=1, ask_qty=10, bid_qty=20),
            *_checkpoint_rows(ts_ms=2000, quote_seq=2, ask_qty=15, bid_qty=25),
            *_checkpoint_rows(ts_ms=4000, quote_seq=3, ask_qty=18, bid_qty=28),
        ]
    ).write_parquet(session_dir / VISIBLE_CHECKPOINT_FILE)

    engine = ReplayEngine(processed_root)
    engine.load_window("workspace-a", "window-a", "sample", 20260101, ts_ms=1000)
    engine.load_window("workspace-a", "window-b", "sample", 20260101, ts_ms=4000)

    engine.play("workspace-a", "window-a")
    engine.set_speed("workspace-a", "window-a", 2.0)
    moved = engine.tick("workspace-a", "window-a", 500)

    window_a = engine.describe_window("workspace-a", "window-a")
    window_b = engine.describe_window("workspace-a", "window-b")

    assert moved.status == "playing"
    assert moved.current_ts_ms == 2000
    assert window_a["status"] == "playing"
    assert window_a["speed"] == 2.0
    assert window_a["current_ts_ms"] == 2000
    assert window_a["virtual_clock_ms"] == 2000.0
    assert window_b["status"] == "paused"
    assert window_b["speed"] == 1.0
    assert window_b["current_ts_ms"] == 4000
    assert window_b["virtual_clock_ms"] == 4000.0

    engine.pause("workspace-a", "window-a")
    paused = engine.snapshot("workspace-a", "window-a")
    assert paused.status == "paused"


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

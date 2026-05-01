from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import polars as pl

from .config import AppPaths


VISIBLE_CHECKPOINT_FILE = "visible_orderbook_checkpoints.parquet"


@dataclass(frozen=True)
class VisibleCheckpointLevel:
    level: int
    price_int: int
    qty: int
    source: str
    raw_price_int: int | None
    raw_qty: int | None
    raw_price_match: bool
    raw_qty_match: bool
    correction_cost: int
    inter_quote_drift_abs_qty: int


@dataclass(frozen=True)
class VisibleCheckpoint:
    symbol: str
    trade_date: int
    checkpoint_id: str
    quote_seq: int
    event_id: int
    ts_ms: int
    session: str
    asks: list[VisibleCheckpointLevel]
    bids: list[VisibleCheckpointLevel]
    correction_cost: int
    inter_quote_drift_abs_qty: int


class VisibleCheckpointStore:
    def __init__(self, processed_root: Path) -> None:
        self.processed_root = processed_root

    @classmethod
    def from_backend_dir(cls, backend_dir: Path) -> "VisibleCheckpointStore":
        return cls(AppPaths.from_backend_dir(backend_dir).processed_dir)

    def load_checkpoint(self, symbol: str, trade_date: int, ts_ms: int, depth: int = 10) -> VisibleCheckpoint:
        checkpoint_path = self._checkpoint_path(symbol, trade_date)
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"missing visible checkpoint file: {checkpoint_path}")

        checkpoints = pl.read_parquet(checkpoint_path)
        eligible = checkpoints.filter(pl.col("ts_ms") <= ts_ms)
        if eligible.is_empty():
            raise ValueError(f"no visible checkpoint at or before ts_ms={ts_ms} for {symbol}-{trade_date}")

        checkpoint_ts = int(eligible.select(pl.col("ts_ms").max()).item())
        checkpoint_rows = (
            eligible.filter(pl.col("ts_ms") == checkpoint_ts)
            .filter(pl.col("level") <= depth)
            .sort(["side", "level"])
        )
        if checkpoint_rows.is_empty():
            raise ValueError(f"visible checkpoint at ts_ms={checkpoint_ts} has no rows for {symbol}-{trade_date}")

        rows = checkpoint_rows.to_dicts()
        first = rows[0]
        asks = self._levels_from_rows(rows, "ask")
        bids = self._levels_from_rows(rows, "bid")
        return VisibleCheckpoint(
            symbol=str(first["symbol"]),
            trade_date=int(first["trade_date"]),
            checkpoint_id=str(first["checkpoint_id"]),
            quote_seq=int(first["quote_seq"]),
            event_id=int(first["event_id"]),
            ts_ms=int(first["ts_ms"]),
            session=str(first["session"]),
            asks=asks,
            bids=bids,
            correction_cost=sum(level.correction_cost for level in asks + bids),
            inter_quote_drift_abs_qty=sum(level.inter_quote_drift_abs_qty for level in asks + bids),
        )

    def _checkpoint_path(self, symbol: str, trade_date: int) -> Path:
        return self.processed_root / f"symbol={symbol}" / f"date={trade_date}" / VISIBLE_CHECKPOINT_FILE

    @staticmethod
    def _levels_from_rows(rows: list[dict[str, object]], side: str) -> list[VisibleCheckpointLevel]:
        return [
            VisibleCheckpointLevel(
                level=int(row["level"]),
                price_int=int(row["visible_price_int"] or 0),
                qty=int(row["visible_qty"] or 0),
                source=str(row["source"]),
                raw_price_int=_optional_int(row["raw_price_int"]),
                raw_qty=_optional_int(row["raw_qty"]),
                raw_price_match=bool(row["raw_price_match"]),
                raw_qty_match=bool(row["raw_qty_match"]),
                correction_cost=int(row["correction_cost"] or 0),
                inter_quote_drift_abs_qty=int(row["inter_quote_drift_abs_qty"] or 0),
            )
            for row in rows
            if row["side"] == side
        ]


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)

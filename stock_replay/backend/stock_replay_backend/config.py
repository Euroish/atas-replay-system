from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    root_dir: Path
    data_dir: Path
    raw_dir: Path
    processed_dir: Path

    @classmethod
    def from_backend_dir(cls, backend_dir: Path) -> "AppPaths":
        root_dir = backend_dir.parent
        data_dir = root_dir / "data"
        return cls(
            root_dir=root_dir,
            data_dir=data_dir,
            raw_dir=data_dir / "raw",
            processed_dir=data_dir / "processed",
        )

    def session_raw_dir(self, symbol: str, trade_date: int) -> Path:
        return self.raw_dir / f"symbol={symbol}" / f"date={trade_date}"

    def session_processed_dir(self, symbol: str, trade_date: int) -> Path:
        return self.processed_dir / f"symbol={symbol}" / f"date={trade_date}"


from __future__ import annotations

from stock_replay_backend.normalizer import parse_ts_ms


def test_parse_ts_ms() -> None:
    assert parse_ts_ms("91400130") == 33240130
    assert parse_ts_ms("92500400") == 33900400

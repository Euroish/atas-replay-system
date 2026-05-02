from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import polars as pl

from .encoding import read_clean_text


PRICE_SCALE = 10_000


@dataclass(frozen=True)
class CsvTable:
    path: Path
    encoding: str
    null_bytes_removed: int
    rows: list[dict[str, str]]
    row_count: int


def load_csv_table(path: Path) -> CsvTable:
    cleaned = read_clean_text(path)
    reader = csv.DictReader(io.StringIO(cleaned.text))
    fieldnames = [field for field in (reader.fieldnames or []) if field]
    rows: list[dict[str, str]] = []

    for raw_row in reader:
        row = {field: _clean_cell(raw_row.get(field, "")) for field in fieldnames}
        rows.append(row)

    return CsvTable(
        path=path,
        encoding=cleaned.encoding,
        null_bytes_removed=cleaned.null_bytes_removed,
        rows=rows,
        row_count=len(rows),
    )


def normalize_quotes(table: CsvTable) -> pl.DataFrame:
    records = []
    for seq, row in enumerate(table.rows, start=1):
        record = _base_record(row, seq)
        record.update(
            {
                "last_price_int": _to_int(row["成交价"]),
                "last_qty": _to_int(row["成交量"]),
                "last_amount": _to_int(row["成交额"]),
                "trade_count": _to_int(row["成交笔数"]),
                "cum_qty": _to_int(row["当日累计成交量"]),
                "cum_amount": _to_int(row["当日成交额"]),
                "high_int": _to_int(row["最高价"]),
                "low_int": _to_int(row["最低价"]),
                "open_int": _to_int(row["开盘价"]),
                "prev_close_int": _to_int(row["前收盘"]),
                "price_scale": PRICE_SCALE,
            }
        )
        record.update(_book_levels(row, "ask", "申卖价", "申卖量"))
        record.update(_book_levels(row, "bid", "申买价", "申买量"))
        records.append(record)

    return pl.from_dicts(records)


def normalize_orders(table: CsvTable) -> pl.DataFrame:
    records = []
    for seq, row in enumerate(table.rows, start=1):
        order_type = _clean_cell(row["委托类型"]) or "unknown"
        side = _clean_cell(row["委托代码"]) or "unknown"
        records.append(
            {
                **_base_record(row, seq),
                "order_no": _clean_cell(row["委托编号"]),
                "exchange_order_id": _clean_cell(row["交易所委托号"]),
                "message_seq": _to_int(row["交易所委托号"]),
                "order_type": order_type,
                "side": side,
                "price_int": _to_int(row["委托价格"]),
                "qty": _to_int(row["委托数量"]),
            }
        )

    return pl.from_dicts(records)


def normalize_trades(table: CsvTable) -> pl.DataFrame:
    records = []
    for seq, row in enumerate(table.rows, start=1):
        records.append(
            {
                **_base_record(row, seq),
                "trade_id": _clean_cell(row["成交编号"]),
                "message_seq": _to_int(row["成交编号"]),
                "trade_code": _clean_cell(row["成交代码"]),
                "order_code": _clean_cell(row["委托代码"]),
                "aggressor_side": _normalize_side(row["BS标志"]),
                "price_int": _to_int(row["成交价格"]),
                "qty": _to_int(row["成交数量"]),
                "ask_order_id": _clean_cell(row["叫卖序号"]),
                "bid_order_id": _clean_cell(row["叫买序号"]),
            }
        )

    return pl.from_dicts(records)


def parse_ts_ms(value: str) -> int:
    digits = _clean_cell(value)
    if not digits:
        raise ValueError("time value is empty")
    digits = digits.zfill(9)
    hour = int(digits[0:2])
    minute = int(digits[2:4])
    second = int(digits[4:6])
    millisecond = int(digits[6:9])
    return ((hour * 60 + minute) * 60 + second) * 1000 + millisecond


def _base_record(row: dict[str, str], seq: int) -> dict[str, object]:
    return {
        "symbol": _clean_cell(row["万得代码"]),
        "exchange_code": _clean_cell(row["交易所代码"]),
        "trade_date": _to_int(row["自然日"]),
        "time_raw": _to_int(row["时间"]),
        "ts_ms": parse_ts_ms(row["时间"]),
        "session": _classify_session(row["时间"]),
        "seq": seq,
    }


def _book_levels(
    row: dict[str, str],
    side_prefix: str,
    price_prefix: str,
    qty_prefix: str,
) -> dict[str, int | None]:
    values: dict[str, int | None] = {}
    for level in range(1, 11):
        values[f"{side_prefix}_price_{level}_int"] = _to_int(row[f"{price_prefix}{level}"])
        values[f"{side_prefix}_qty_{level}"] = _to_int(row[f"{qty_prefix}{level}"])
    return values


def _classify_session(time_raw: str) -> str:
    ts_ms = parse_ts_ms(time_raw)
    if ts_ms < parse_ts_ms("091500000"):
        return "preopen"
    if ts_ms < parse_ts_ms("092500000"):
        return "auction"
    if ts_ms < parse_ts_ms("113000000"):
        return "continuous_am"
    if ts_ms < parse_ts_ms("130000000"):
        return "lunch"
    if ts_ms < parse_ts_ms("150000000"):
        return "continuous_pm"
    return "close"


def _normalize_side(value: str) -> str:
    cleaned = _clean_cell(value).upper()
    if cleaned in {"B", "S"}:
        return cleaned
    return "unknown"


def _clean_cell(value: str | None) -> str:
    return (value or "").replace("\x00", "").strip()


def _to_int(value: str | None) -> int | None:
    cleaned = _clean_cell(value)
    if not cleaned:
        return None
    return int(cleaned)

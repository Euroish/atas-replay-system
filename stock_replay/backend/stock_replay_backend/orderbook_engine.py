from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable


@dataclass
class OrderState:
    order_id: str
    side: str
    price_int: int
    qty: int


@dataclass(frozen=True)
class BookLevel:
    price_int: int
    qty: int


class OrderBookEngine:
    def __init__(self) -> None:
        self.orders: dict[str, OrderState] = {}
        self.bid_levels: defaultdict[int, int] = defaultdict(int)
        self.ask_levels: defaultdict[int, int] = defaultdict(int)
        self.missing_order_log: list[dict[str, object]] = []

    def apply_events(self, events: Iterable[dict[str, object]]) -> None:
        for event in events:
            self.apply_event(event)

    def apply_event(self, event: dict[str, object]) -> None:
        event_type = event.get("event_type")
        if event_type == "order_add":
            self._apply_order_add(event)
        elif event_type == "order_cancel":
            self._apply_order_cancel(event)
        elif event_type == "trade":
            self._apply_trade(event)

    def snapshot_top_levels(self, depth: int = 10) -> dict[str, list[BookLevel]]:
        bids = [
            BookLevel(price_int=price_int, qty=qty)
            for price_int, qty in sorted(self.bid_levels.items(), reverse=True)
            if qty > 0
        ][:depth]
        asks = [
            BookLevel(price_int=price_int, qty=qty)
            for price_int, qty in sorted(self.ask_levels.items())
            if qty > 0
        ][:depth]
        return {"bids": bids, "asks": asks}

    def _apply_order_add(self, event: dict[str, object]) -> None:
        order_id = self._as_string(event.get("exchange_order_id"))
        side = self._normalize_side(event.get("side"))
        price_int = self._as_int(event.get("price_int"))
        qty = self._as_int(event.get("qty"))

        if not order_id or side not in {"B", "S"} or price_int is None or qty is None or qty <= 0:
            self._log_missing("invalid_order_add", event, order_id=order_id, side=side)
            return

        if order_id in self.orders:
            self._remove_order(order_id, self.orders[order_id].qty)

        self.orders[order_id] = OrderState(order_id=order_id, side=side, price_int=price_int, qty=qty)
        self._adjust_level(side, price_int, qty)

    def _apply_order_cancel(self, event: dict[str, object]) -> None:
        order_id = self._as_string(event.get("exchange_order_id"))
        cancel_qty = self._as_int(event.get("qty"))
        if not order_id or cancel_qty is None or cancel_qty <= 0:
            self._log_missing("invalid_order_cancel", event, order_id=order_id)
            return
        self._remove_order(order_id, cancel_qty, reason="missing_cancel_order", event=event)

    def _apply_trade(self, event: dict[str, object]) -> None:
        trade_qty = self._as_int(event.get("qty"))
        if trade_qty is None or trade_qty <= 0:
            self._log_missing("invalid_trade_qty", event)
            return

        ask_order_id = self._as_string(event.get("ask_order_id"))
        bid_order_id = self._as_string(event.get("bid_order_id"))

        if ask_order_id:
            self._remove_order(ask_order_id, trade_qty, reason="missing_trade_order", event=event, ref_side="ask")
        if bid_order_id:
            self._remove_order(bid_order_id, trade_qty, reason="missing_trade_order", event=event, ref_side="bid")

    def _remove_order(
        self,
        order_id: str,
        remove_qty: int,
        *,
        reason: str | None = None,
        event: dict[str, object] | None = None,
        ref_side: str | None = None,
    ) -> None:
        order = self.orders.get(order_id)
        if order is None:
            if reason and event is not None:
                self._log_missing(reason, event, order_id=order_id, ref_side=ref_side)
            return

        actual_remove_qty = min(remove_qty, order.qty)
        self._adjust_level(order.side, order.price_int, -actual_remove_qty)
        order.qty -= actual_remove_qty

        if remove_qty > actual_remove_qty and reason and event is not None:
            self._log_missing(
                "qty_shortfall",
                event,
                order_id=order_id,
                requested_qty=remove_qty,
                remaining_qty=actual_remove_qty,
                ref_side=ref_side,
            )

        if order.qty == 0:
            del self.orders[order_id]

    def _adjust_level(self, side: str, price_int: int, delta_qty: int) -> None:
        levels = self.bid_levels if side == "B" else self.ask_levels
        updated_qty = levels[price_int] + delta_qty
        levels[price_int] = max(updated_qty, 0)
        if levels[price_int] == 0:
            levels.pop(price_int, None)

    def _log_missing(self, reason: str, event: dict[str, object], **extra: object) -> None:
        payload = {
            "reason": reason,
            "event_id": event.get("event_id"),
            "event_type": event.get("event_type"),
            "ts_ms": event.get("ts_ms"),
        }
        payload.update(extra)
        self.missing_order_log.append(payload)

    @staticmethod
    def _normalize_side(value: object) -> str:
        text = OrderBookEngine._as_string(value).upper()
        return text if text in {"B", "S"} else "unknown"

    @staticmethod
    def _as_string(value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _as_int(value: object) -> int | None:
        if value is None or value == "":
            return None
        return int(value)


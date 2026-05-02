from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import AppPaths
from .checkpoint_store import VisibleCheckpoint, VisibleCheckpointSession, VisibleCheckpointStore


@dataclass
class ReplayWindowState:
    workspace_id: str
    window_id: str
    replay_id: str
    session_id: str
    symbol: str
    trade_date: int
    mode: str
    interval: str
    status: str
    speed: float
    virtual_clock_ms: float
    current_ts_ms: int
    checkpoint_ts_ms: int
    session: VisibleCheckpointSession


@dataclass(frozen=True)
class ReplayFrame:
    type: str
    workspace_id: str
    window_id: str
    replay_id: str
    session_id: str
    symbol: str
    trade_date: int
    mode: str
    interval: str
    status: str
    speed: float
    virtual_ts_ms: int
    current_ts_ms: int
    checkpoint_ts_ms: int
    checkpoint: dict[str, Any]
    orderbook_top: dict[str, list[dict[str, Any]]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReplayEngine:
    def __init__(self, processed_root: Path) -> None:
        self.store = VisibleCheckpointStore(processed_root)
        self._session_cache: dict[tuple[str, int], VisibleCheckpointSession] = {}
        self._window_state: dict[tuple[str, str], ReplayWindowState] = {}

    @classmethod
    def from_backend_dir(cls, backend_dir: Path) -> "ReplayEngine":
        return cls(AppPaths.from_backend_dir(backend_dir).processed_dir)

    def load_window(
        self,
        workspace_id: str,
        window_id: str,
        symbol: str,
        trade_date: int,
        *,
        mode: str = "heatmap",
        interval: str = "1s",
        ts_ms: int | None = None,
        speed: float = 1.0,
    ) -> ReplayFrame:
        self._validate_speed(speed)
        session = self._load_session(symbol, trade_date)
        resolved_ts = session.first_ts_ms if ts_ms is None else ts_ms
        checkpoint = session.load_checkpoint(resolved_ts)
        state = ReplayWindowState(
            workspace_id=workspace_id,
            window_id=window_id,
            replay_id=self._build_replay_id(workspace_id, window_id, symbol, trade_date, mode, interval),
            session_id=f"{symbol}-{trade_date}",
            symbol=symbol,
            trade_date=trade_date,
            mode=mode,
            interval=interval,
            status="paused",
            speed=speed,
            virtual_clock_ms=float(resolved_ts),
            current_ts_ms=resolved_ts,
            checkpoint_ts_ms=checkpoint.ts_ms,
            session=session,
        )
        self._window_state[self._state_key(workspace_id, window_id)] = state
        return self._build_frame(state, checkpoint)

    def play(self, workspace_id: str, window_id: str) -> ReplayFrame:
        state = self._require_state(workspace_id, window_id)
        state.status = "playing"
        return self._build_frame_from_state(state)

    def pause(self, workspace_id: str, window_id: str) -> ReplayFrame:
        state = self._require_state(workspace_id, window_id)
        state.status = "paused"
        return self._build_frame_from_state(state)

    def set_speed(self, workspace_id: str, window_id: str, speed: float) -> ReplayFrame:
        self._validate_speed(speed)
        state = self._require_state(workspace_id, window_id)
        state.speed = speed
        return self._build_frame_from_state(state)

    def seek(self, workspace_id: str, window_id: str, ts_ms: int) -> ReplayFrame:
        state = self._require_state(workspace_id, window_id)
        checkpoint = state.session.load_checkpoint(ts_ms)
        state.virtual_clock_ms = float(ts_ms)
        state.current_ts_ms = ts_ms
        state.checkpoint_ts_ms = checkpoint.ts_ms
        return self._build_frame(state, checkpoint)

    def tick(self, workspace_id: str, window_id: str, elapsed_ms: int) -> ReplayFrame:
        if elapsed_ms < 0:
            raise ValueError("elapsed_ms must be non-negative")
        state = self._require_state(workspace_id, window_id)
        if state.status != "playing":
            return self._build_frame_from_state(state)

        state.virtual_clock_ms += elapsed_ms * state.speed
        state.current_ts_ms = int(state.virtual_clock_ms)
        checkpoint = state.session.load_checkpoint(state.current_ts_ms)
        state.checkpoint_ts_ms = checkpoint.ts_ms
        return self._build_frame(state, checkpoint)

    def snapshot(self, workspace_id: str, window_id: str) -> ReplayFrame:
        state = self._require_state(workspace_id, window_id)
        return self._build_frame_from_state(state)

    def describe_window(self, workspace_id: str, window_id: str) -> dict[str, Any]:
        state = self._require_state(workspace_id, window_id)
        return {
            "workspace_id": state.workspace_id,
            "window_id": state.window_id,
            "replay_id": state.replay_id,
            "session_id": state.session_id,
            "symbol": state.symbol,
            "trade_date": state.trade_date,
            "mode": state.mode,
            "interval": state.interval,
            "status": state.status,
            "speed": state.speed,
            "current_ts_ms": state.current_ts_ms,
            "virtual_clock_ms": state.virtual_clock_ms,
            "checkpoint_ts_ms": state.checkpoint_ts_ms,
        }

    def _build_frame_from_state(self, state: ReplayWindowState) -> ReplayFrame:
        checkpoint = state.session.load_checkpoint(state.current_ts_ms)
        return self._build_frame(state, checkpoint)

    def _build_frame(self, state: ReplayWindowState, checkpoint: VisibleCheckpoint) -> ReplayFrame:
        orderbook_top = {
            "asks": [asdict(level) for level in checkpoint.asks],
            "bids": [asdict(level) for level in checkpoint.bids],
        }
        checkpoint_meta = {
            "checkpoint_id": checkpoint.checkpoint_id,
            "quote_seq": checkpoint.quote_seq,
            "event_id": checkpoint.event_id,
            "ts_ms": checkpoint.ts_ms,
            "session": checkpoint.session,
            "correction_cost": checkpoint.correction_cost,
            "inter_quote_drift_abs_qty": checkpoint.inter_quote_drift_abs_qty,
        }
        return ReplayFrame(
            type="frame",
            workspace_id=state.workspace_id,
            window_id=state.window_id,
            replay_id=state.replay_id,
            session_id=state.session_id,
            symbol=state.symbol,
            trade_date=state.trade_date,
            mode=state.mode,
            interval=state.interval,
            status=state.status,
            speed=state.speed,
            virtual_ts_ms=int(state.virtual_clock_ms),
            current_ts_ms=state.current_ts_ms,
            checkpoint_ts_ms=checkpoint.ts_ms,
            checkpoint=checkpoint_meta,
            orderbook_top=orderbook_top,
        )

    def _load_session(self, symbol: str, trade_date: int) -> VisibleCheckpointSession:
        cache_key = (symbol, trade_date)
        session = self._session_cache.get(cache_key)
        if session is None:
            session = self.store.load_session(symbol, trade_date)
            self._session_cache[cache_key] = session
        return session

    def _require_state(self, workspace_id: str, window_id: str) -> ReplayWindowState:
        state = self._window_state.get(self._state_key(workspace_id, window_id))
        if state is None:
            raise KeyError(f"window {workspace_id}/{window_id} is not loaded")
        return state

    @staticmethod
    def _state_key(workspace_id: str, window_id: str) -> tuple[str, str]:
        return workspace_id, window_id

    @staticmethod
    def _build_replay_id(
        workspace_id: str,
        window_id: str,
        symbol: str,
        trade_date: int,
        mode: str,
        interval: str,
    ) -> str:
        return f"{workspace_id}:{window_id}:{symbol}-{trade_date}:{mode}:{interval}"

    @staticmethod
    def _validate_speed(speed: float) -> None:
        if speed <= 0:
            raise ValueError("speed must be greater than 0")

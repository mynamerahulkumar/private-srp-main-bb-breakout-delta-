from __future__ import annotations

import os
import resource
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import load_dotenv

from utils.timezone_helper import now_ist

ROOT_DIR = Path(__file__).resolve().parents[1]


class BotShutdown(Exception):
    """Raised when the bot should stop gracefully."""


class CriticalBotError(BotShutdown):
    """Raised for critical failures where continuing would waste cost or risk money."""


def load_config(path: str | Path = "config/config.yaml") -> dict[str, Any]:
    load_dotenv()
    config_path = Path(path)
    if not config_path.is_absolute():
        config_path = ROOT_DIR / config_path
    with config_path.open("r", encoding="utf-8") as handle:
        raw_config = yaml.safe_load(handle) or {}
    return _expand_env(raw_config)


def _expand_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return os.getenv(value[2:-1], "")
    return value


def ensure_directories() -> None:
    for directory in ("logs", "config", "strategy", "broker", "ui", "utils"):
        (ROOT_DIR / directory).mkdir(exist_ok=True)


def timeframe_to_seconds(timeframe: str) -> int:
    normalized = timeframe.strip().lower()
    unit = normalized[-1]
    amount = int(normalized[:-1])
    if unit == "m":
        return amount * 60
    if unit == "h":
        return amount * 60 * 60
    if unit == "d":
        return amount * 24 * 60 * 60
    raise ValueError(f"Unsupported timeframe: {timeframe}")


def unix_seconds() -> int:
    return int(time.time())


def normalize_candle_timestamp(timestamp: int, timeframe: str) -> int:
    if timestamp > 10_000_000_000_000:
        timestamp = timestamp // 1_000_000
    elif timestamp > 10_000_000_000:
        timestamp = timestamp // 1_000
    candle_seconds = timeframe_to_seconds(timeframe)
    return timestamp - (timestamp % candle_seconds)


def system_usage() -> dict[str, float]:
    max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    memory_mb = max_rss / (1024 * 1024) if sys.platform == "darwin" else max_rss / 1024
    load_avg = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0
    return {"memory_mb": round(memory_mb, 2), "cpu_load_1m": round(load_avg, 2)}


@dataclass(slots=True)
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def direction(self) -> str:
        if self.close > self.open:
            return "bullish"
        if self.close < self.open:
            return "bearish"
        return "neutral"


@dataclass(slots=True)
class IndicatorSnapshot:
    upper_band: float = 0.0
    middle_band: float = 0.0
    lower_band: float = 0.0
    current_rsi: float = 0.0
    previous_rsi: float = 0.0
    rsi_trend: str = "flat"
    distance_upper: float = 0.0
    distance_middle: float = 0.0
    distance_lower: float = 0.0


@dataclass(slots=True)
class SignalDecision:
    action: Literal["buy", "sell", "hold"] = "hold"
    status: str = "WAITING"
    rejected_reason: str = ""
    upper_band_touched: bool = False
    lower_band_touched: bool = False
    bearish_candle: bool = False
    bullish_candle: bool = False
    previous_low_broken: bool = False
    previous_high_broken: bool = False
    rsi_valid: bool = False
    confirmation_active: bool = False
    # Band proximity diagnostics (filled by BollingerReversalStrategy when BB enabled)
    band_touch_min_low: float = 0.0
    band_touch_max_high: float = 0.0
    band_touch_lower_line: float = 0.0
    band_touch_upper_line: float = 0.0
    band_touch_lower_threshold: float = 0.0
    band_touch_upper_threshold: float = 0.0
    band_touch_includes_forming: bool = False

    @property
    def should_trade(self) -> bool:
        return self.action in {"buy", "sell"} and not self.rejected_reason


@dataclass(slots=True)
class PositionState:
    active: bool = False
    side: str = ""
    entry_price: float = 0.0
    quantity: float = 0.0
    # (mark - entry) * quantity * contract_value ≈ USD PnL for vanilla linear perps on Delta
    contract_value: float = 1.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    """True when SL/TP were sent to Delta (bracket); validate_exit syncs flat from exchange."""
    exchange_brackets: bool = False
    trailing_stop_active: bool = False
    trailing_stop_percent: float = 0.0
    trailing_reference_price: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0

    @property
    def current_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl


@dataclass(slots=True)
class ExchangePositionOverview:
    """Open legs from Delta GET /v2/positions/margined; not the same as bot-managed PositionState."""

    source: Literal["off", "paper", "ok", "error"] = "off"
    error: str = ""
    open_count: int = 0
    position_lines: tuple[str, ...] = ()
    sum_realized_pnl: float = 0.0
    sum_est_unrealized: float = 0.0


@dataclass(slots=True)
class MonitoringSnapshot:
    symbol: str
    timeframe: str
    current_price: float
    current_candle: Candle | None
    previous_candle: Candle | None
    indicators: IndicatorSnapshot
    signal: SignalDecision
    position: PositionState
    trades_today: int
    closed_trades_today: int
    max_trades_per_day: int
    daily_pnl: float
    daily_loss_limit: float
    api_status: str
    websocket_status: str
    last_signal_check: str
    next_signal_check_seconds: int
    running_seconds: int
    memory_mb: float
    cpu_load_1m: float
    # Live bar for current bucket (if any); band proximity can include it when enabled in config.
    forming_candle: Candle | None = None
    exchange_positions: ExchangePositionOverview = field(default_factory=ExchangePositionOverview)
    created_at: str = field(default_factory=lambda: now_ist().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

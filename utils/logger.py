from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from utils.helpers import MonitoringSnapshot, ROOT_DIR
from utils.timezone_helper import format_ist, now_ist


class ISTFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        return format_ist(now_ist())


def setup_logging(config: dict[str, Any]) -> dict[str, logging.Logger]:
    log_dir = ROOT_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    max_bytes = int(config["system"].get("max_log_file_size_mb", 10) * 1024 * 1024)
    use_rotation = bool(config["system"].get("log_rotation_enabled", True))

    formatter = ISTFormatter("[%(asctime)s IST] [%(levelname)s] %(message)s")
    loggers = {
        "trading": _build_logger("trading", log_dir / "trading.log", formatter, max_bytes, use_rotation),
        "error": _build_logger("error", log_dir / "error.log", formatter, max_bytes, use_rotation),
        "system": _build_logger("system", log_dir / "system.log", formatter, max_bytes, use_rotation),
    }
    return loggers


def _build_logger(
    name: str,
    path: Path,
    formatter: logging.Formatter,
    max_bytes: int,
    use_rotation: bool,
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    handler: logging.Handler
    if use_rotation:
        handler = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=3, encoding="utf-8")
    else:
        handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


def log_snapshot(logger: logging.Logger, snapshot: MonitoringSnapshot) -> None:
    current = snapshot.current_candle
    previous = snapshot.previous_candle
    indicators = snapshot.indicators
    signal = snapshot.signal
    position = snapshot.position

    logger.info(
        "%s | PRICE=%.2f | RSI=%.2f | PREV_RSI=%.2f | RSI_TREND=%s | "
        "BB_UPPER=%.2f | BB_MIDDLE=%.2f | BB_LOWER=%.2f | "
        "DIST_UPPER=%.2f | DIST_MIDDLE=%.2f | DIST_LOWER=%.2f",
        snapshot.symbol,
        snapshot.current_price,
        indicators.current_rsi,
        indicators.previous_rsi,
        indicators.rsi_trend,
        indicators.upper_band,
        indicators.middle_band,
        indicators.lower_band,
        indicators.distance_upper,
        indicators.distance_middle,
        indicators.distance_lower,
    )
    if current:
        logger.info(
            "CURRENT_CANDLE | O=%.2f | H=%.2f | L=%.2f | C=%.2f | DIRECTION=%s",
            current.open,
            current.high,
            current.low,
            current.close,
            current.direction,
        )
    if previous:
        logger.info(
            "PREVIOUS_CANDLE | O=%.2f | H=%.2f | L=%.2f | C=%.2f",
            previous.open,
            previous.high,
            previous.low,
            previous.close,
        )
    logger.info(
        "SIGNAL | STATUS=%s | ACTION=%s | REJECTED_REASON=%s | UPPER_TOUCH=%s | "
        "LOWER_TOUCH=%s | BEARISH=%s | BULLISH=%s | PREV_LOW_BREAK=%s | "
        "PREV_HIGH_BREAK=%s | RSI_VALID=%s | CONFIRMATION_ACTIVE=%s",
        signal.status,
        signal.action,
        signal.rejected_reason or "none",
        signal.upper_band_touched,
        signal.lower_band_touched,
        signal.bearish_candle,
        signal.bullish_candle,
        signal.previous_low_broken,
        signal.previous_high_broken,
        signal.rsi_valid,
        signal.confirmation_active,
    )
    logger.info(
        "POSITION | ACTIVE=%s | SIDE=%s | ENTRY=%.2f | QTY=%.4f | PNL=%.2f | "
        "REALIZED=%.2f | UNREALIZED=%.2f | SL=%.2f | TP=%.2f | TRAILING=%s | TRAIL_PERCENT=%.2f",
        position.active,
        position.side or "none",
        position.entry_price,
        position.quantity,
        position.current_pnl,
        position.realized_pnl,
        position.unrealized_pnl,
        position.stop_loss,
        position.take_profit,
        position.trailing_stop_active,
        position.trailing_stop_percent,
    )
    logger.info(
        "DAILY | TRADES=%s/%s | REMAINING=%s | DAILY_PNL=%.2f | LOSS_LIMIT=%.2f | "
        "API=%s | WEBSOCKET=%s | NEXT_CHECK=%ss | MEMORY_MB=%.2f | CPU_LOAD_1M=%.2f",
        snapshot.trades_today,
        snapshot.max_trades_per_day,
        max(snapshot.max_trades_per_day - snapshot.trades_today, 0),
        snapshot.daily_pnl,
        snapshot.daily_loss_limit,
        snapshot.api_status,
        snapshot.websocket_status,
        snapshot.next_signal_check_seconds,
        snapshot.memory_mb,
        snapshot.cpu_load_1m,
    )

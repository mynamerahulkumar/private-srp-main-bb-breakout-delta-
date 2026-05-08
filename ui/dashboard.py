from __future__ import annotations

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from utils.helpers import MonitoringSnapshot


class Dashboard:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.console = Console()

    def start(self) -> None:
        if self.enabled:
            self.console.print("[bold blue]Dashboard started. Printing one snapshot per signal check.[/bold blue]")

    def stop(self) -> None:
        return

    def alert(self, message: str, style: str = "bold red") -> None:
        self.console.print(Panel(message, style=style))

    def update(self, snapshot: MonitoringSnapshot) -> None:
        if not self.enabled:
            return
        renderable = Group(
            _header(snapshot),
            _decision_table(snapshot),
            _position_risk_table(snapshot),
        )
        self.console.rule(f"Signal Check | {snapshot.created_at}")
        self.console.print(renderable)


def _header(snapshot: MonitoringSnapshot) -> Panel:
    text = Text()
    text.append(f"TIME (IST): {snapshot.created_at}\n", style="bold blue")
    text.append(
        f"SYMBOL: {snapshot.symbol} | TIMEFRAME: {snapshot.timeframe} | "
        f"PRICE: {snapshot.current_price:.2f}\n"
    )
    text.append(f"SIGNAL: {snapshot.signal.status} | ACTION: {snapshot.signal.action.upper()}")
    return Panel(text, title="Delta BB + RSI Bot")


def _decision_table(snapshot: MonitoringSnapshot) -> Table:
    signal = snapshot.signal
    indicators = snapshot.indicators
    table = Table(title="Trade Decision", expand=True)
    table.add_column("Decision Item", style="magenta")
    table.add_column("Value")
    table.add_column("Status")
    table.add_row("Buy Entry Trigger", _buy_trigger(snapshot), _yes(signal.previous_high_broken))
    table.add_row("Sell Entry Trigger", _sell_trigger(snapshot), _yes(signal.previous_low_broken))
    table.add_row("Current Candle", _current_candle_summary(snapshot), signal.status)
    table.add_row("Band Touch", _band_touch_summary(snapshot), _band_touch_status(snapshot))
    table.add_row("RSI", f"{_num(indicators.current_rsi)} ({indicators.rsi_trend})", _yes(signal.rsi_valid))
    table.add_row("Missing Condition", signal.rejected_reason or "none", "READY" if signal.should_trade else "WAIT")
    return table


def _position_risk_table(snapshot: MonitoringSnapshot) -> Table:
    position = snapshot.position
    table = Table(title="Position And Risk", expand=True)
    table.add_column("Metric", style="green")
    table.add_column("Value")
    if position.active:
        table.add_row("Position", f"ACTIVE {position.side.upper()}")
        table.add_row("Entry Price", _num(position.entry_price))
        table.add_row("Current PnL", _num(position.current_pnl))
        table.add_row("Stop Loss", _num(position.stop_loss))
        table.add_row("Take Profit", _num(position.take_profit))
        table.add_row("Trailing Stop", "ACTIVE" if position.trailing_stop_active else "OFF")
    else:
        table.add_row("Position", "NO ACTIVE POSITION")
    table.add_row("Trades Today", f"{snapshot.trades_today} / {snapshot.max_trades_per_day}")
    table.add_row("Remaining Trades", str(max(snapshot.max_trades_per_day - snapshot.trades_today, 0)))
    table.add_row("Daily PnL", _num(snapshot.daily_pnl))
    table.add_row("Daily Loss Limit", _num(snapshot.daily_loss_limit))
    return table


def _buy_trigger(snapshot: MonitoringSnapshot) -> str:
    previous = snapshot.previous_candle
    if not previous:
        return "n/a"
    return f"BUY above previous high > {_num(previous.high)}"


def _sell_trigger(snapshot: MonitoringSnapshot) -> str:
    previous = snapshot.previous_candle
    if not previous:
        return "n/a"
    return f"SELL below previous low < {_num(previous.low)}"


def _current_candle_summary(snapshot: MonitoringSnapshot) -> str:
    current = snapshot.current_candle
    if not current:
        return "n/a"
    return f"{current.direction.upper()} | Close {_num(current.close)}"


def _band_touch_summary(snapshot: MonitoringSnapshot) -> str:
    indicators = snapshot.indicators
    return f"Upper {_num(indicators.upper_band)} | Lower {_num(indicators.lower_band)}"


def _band_touch_status(snapshot: MonitoringSnapshot) -> str:
    signal = snapshot.signal
    if signal.upper_band_touched:
        return "UPPER TOUCHED"
    if signal.lower_band_touched:
        return "LOWER TOUCHED"
    return "NO TOUCH"


def _num(value: float) -> str:
    return f"{value:.2f}"


def _yes(value: bool) -> str:
    return "[green]YES[/green]" if value else "[red]NO[/red]"

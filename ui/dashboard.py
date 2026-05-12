from __future__ import annotations

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from utils.helpers import ExchangePositionOverview, MonitoringSnapshot


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
    ex = snapshot.exchange_positions
    table = Table(title="Position And Risk", expand=True)
    table.add_column("Metric", style="green")
    table.add_column("Value")
    table.add_row("Bot-tracked position", _bot_position_summary(position))
    if position.active:
        table.add_row("Entry (bot)", _num(position.entry_price))
        table.add_row("Current PnL (bot, USD)", _usd(position.current_pnl))
        table.add_row("Stop Loss", _num(position.stop_loss))
        table.add_row("Take Profit", _num(position.take_profit))
        table.add_row("Trailing Stop", "ACTIVE" if position.trailing_stop_active else "OFF")
        table.add_row("TP/SL on exchange", "yes (Delta bracket)" if position.exchange_brackets else "no (bot price only)")
    table.add_row("Opens today (bot CSV)", _opens_today_cell(snapshot, ex))
    table.add_row("Closes today (bot CSV)", str(snapshot.closed_trades_today))
    table.add_row(
        "CSV scope",
        "Only fills from this bot's OrderManager; manual Delta orders are not logged",
    )
    table.add_row("Remaining (bot limit)", str(max(snapshot.max_trades_per_day - snapshot.trades_today, 0)))
    table.add_row("Daily PnL (bot log, USD)", _usd(snapshot.daily_pnl))
    table.add_row("Daily loss limit", _num(snapshot.daily_loss_limit))
    _add_exchange_rows(table, ex)
    return table


def _opens_today_cell(snapshot: MonitoringSnapshot, ex: ExchangePositionOverview) -> str:
    cell = f"{snapshot.trades_today} / {snapshot.max_trades_per_day} (OPEN rows in logs/trades.csv)"
    if ex.source == "ok":
        cell += f" — exchange {ex.open_count} open"
    return cell


def _bot_position_summary(position) -> str:
    if position.active:
        return f"ACTIVE {position.side.upper()}"
    return "none (bot has not opened a position this run)"


def _add_exchange_rows(table: Table, ex: ExchangePositionOverview) -> None:
    if ex.source == "off":
        table.add_row("Exchange positions", "fetch disabled (dashboard_exchange_positions)")
        return
    if ex.source == "paper":
        table.add_row("Exchange positions", "paper trading — not fetched")
        return
    if ex.source == "error":
        table.add_row("Exchange positions", f"error: {ex.error}")
        return
    table.add_row("Open on exchange (API)", str(ex.open_count))
    if ex.open_count == 0:
        table.add_row("Exchange PnL (open legs)", "n/a (no open positions)")
        return
    table.add_row("Sum realized PnL (exchange, USD)", _usd(ex.sum_realized_pnl))
    table.add_row("Est. unrealized USD (mark−entry)×contracts×cv)", _usd(ex.sum_est_unrealized))
    for line in ex.position_lines:
        table.add_row("— leg", line)


def _buy_trigger(snapshot: MonitoringSnapshot) -> str:
    previous = snapshot.previous_candle
    if not previous:
        return "n/a"
    return f"BUY at/above previous high >= {_num(previous.high)}"


def _sell_trigger(snapshot: MonitoringSnapshot) -> str:
    previous = snapshot.previous_candle
    if not previous:
        return "n/a"
    return f"SELL at/below previous low <= {_num(previous.low)}"


def _current_candle_summary(snapshot: MonitoringSnapshot) -> str:
    current = snapshot.current_candle
    if not current:
        return "n/a"
    return f"{current.direction.upper()} | Close {_num(current.close)}"


def _band_touch_summary(snapshot: MonitoringSnapshot) -> str:
    indicators = snapshot.indicators
    signal = snapshot.signal
    line = f"BB Lower {_num(indicators.lower_band)} | Upper {_num(indicators.upper_band)}"
    if signal.band_touch_lower_threshold != 0.0 or signal.band_touch_upper_threshold != 0.0:
        suffix = " +form" if signal.band_touch_includes_forming else ""
        line += (
            f" | eff L {_num(signal.band_touch_lower_line)} U {_num(signal.band_touch_upper_line)}"
            f" | long if minL≤{_num(signal.band_touch_lower_threshold)}"
            f" | short if maxH≥{_num(signal.band_touch_upper_threshold)}"
            f" | ext L/H {_num(signal.band_touch_min_low)}/{_num(signal.band_touch_max_high)}{suffix}"
        )
    return line


def _band_touch_status(snapshot: MonitoringSnapshot) -> str:
    signal = snapshot.signal
    if signal.upper_band_touched:
        return "NEAR UPPER"
    if signal.lower_band_touched:
        return "NEAR LOWER"
    return "OUTSIDE ZONE"


def _num(value: float) -> str:
    return f"{value:.2f}"


def _usd(value: float) -> str:
    """USD PnL: more decimals when the magnitude is small (typical perp PnL)."""
    magnitude = abs(value)
    if magnitude >= 1000:
        return f"{value:,.2f} USD"
    if magnitude >= 1:
        return f"{value:.2f} USD"
    return f"{value:.4f} USD"


def _yes(value: bool) -> str:
    return "[green]YES[/green]" if value else "[red]NO[/red]"

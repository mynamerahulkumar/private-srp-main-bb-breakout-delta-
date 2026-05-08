from __future__ import annotations

import logging

from broker.delta_client import DeltaClient
from utils.helpers import CriticalBotError, PositionState
from utils.timezone_helper import format_ist, today_ist
from utils.trade_tracker import TradeRecord, TradeTracker


class OrderManager:
    def __init__(
        self,
        config: dict,
        client: DeltaClient,
        tracker: TradeTracker,
        logger: logging.Logger,
    ) -> None:
        self.config = config
        self.client = client
        self.tracker = tracker
        self.logger = logger
        self.position = PositionState()

    @property
    def paper_trading(self) -> bool:
        return bool(self.config["trading"].get("paper_trading", True))

    async def open_position(self, symbol: str, side: str, price: float) -> PositionState:
        if self.position.active:
            raise CriticalBotError("Order attempted while another position is active")

        trading = self.config["trading"]
        risk = self.config["risk_management"]
        product_id = int(trading["product_ids"][symbol])
        quantity = float(trading["quantity"])
        order_type = str(trading["order_type"])
        await self._place_entry_order(product_id, quantity, side, order_type, price)

        stop_loss_ratio = _percent_to_ratio(float(risk["stop_loss_percent"]))
        take_profit_ratio = _percent_to_ratio(float(risk["take_profit_percent"]))
        trailing_stop = risk.get("trailing_stop", {})
        trailing_ratio = _percent_to_ratio(float(trailing_stop.get("trail_percent", 0.0)))
        trailing_enabled = bool(trailing_stop.get("enabled", False)) and trailing_ratio > 0
        if side == "buy":
            stop_loss = price * (1 - stop_loss_ratio)
            take_profit = price * (1 + take_profit_ratio)
        else:
            stop_loss = price * (1 + stop_loss_ratio)
            take_profit = price * (1 - take_profit_ratio)

        self.position = PositionState(
            active=True,
            side=side,
            entry_price=price,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_stop_active=trailing_enabled,
            trailing_stop_percent=float(trailing_stop.get("trail_percent", 0.0)),
            trailing_reference_price=price,
        )
        self.tracker.append(
            TradeRecord(
                timestamp=format_ist(),
                trade_date=today_ist(),
                symbol=symbol,
                side=side,
                quantity=quantity,
                entry_price=price,
                exit_price=0.0,
                realized_pnl=0.0,
                status="OPEN",
                reason="signal",
                paper_trading=self.paper_trading,
            )
        )
        self.logger.info("%s POSITION OPENED | SYMBOL=%s | ENTRY=%.2f", side.upper(), symbol, price)
        return self.position

    async def validate_exit(self, symbol: str, current_price: float) -> PositionState:
        if not self.position.active:
            return self.position

        self.position.unrealized_pnl = self._calculate_pnl(current_price)
        self._update_trailing_stop(current_price)
        exit_reason = ""
        if self.position.side == "buy":
            if current_price <= self.position.stop_loss:
                exit_reason = "stop_loss"
            elif current_price >= self.position.take_profit:
                exit_reason = "take_profit"
        else:
            if current_price >= self.position.stop_loss:
                exit_reason = "stop_loss"
            elif current_price <= self.position.take_profit:
                exit_reason = "take_profit"

        if exit_reason:
            await self.close_position(symbol, current_price, exit_reason)
        return self.position

    async def close_position(self, symbol: str, price: float, reason: str) -> PositionState:
        if not self.position.active:
            return self.position
        exit_side = "sell" if self.position.side == "buy" else "buy"
        product_id = int(self.config["trading"]["product_ids"][symbol])
        await self._place_exit_order(product_id, self.position.quantity, exit_side, price)
        realized_pnl = self._calculate_pnl(price)
        self.tracker.append(
            TradeRecord(
                timestamp=format_ist(),
                trade_date=today_ist(),
                symbol=symbol,
                side=self.position.side,
                quantity=self.position.quantity,
                entry_price=self.position.entry_price,
                exit_price=price,
                realized_pnl=realized_pnl,
                status="CLOSED",
                reason=reason,
                paper_trading=self.paper_trading,
            )
        )
        self.logger.info("POSITION CLOSED | SYMBOL=%s | REASON=%s | PNL=%.2f", symbol, reason, realized_pnl)
        self.position = PositionState(realized_pnl=realized_pnl)
        return self.position

    def _calculate_pnl(self, current_price: float) -> float:
        if not self.position.active:
            return self.position.realized_pnl
        if self.position.side == "buy":
            return (current_price - self.position.entry_price) * self.position.quantity
        return (self.position.entry_price - current_price) * self.position.quantity

    def _update_trailing_stop(self, current_price: float) -> None:
        if not self.position.trailing_stop_active or self.position.trailing_stop_percent <= 0:
            return
        trail_ratio = _percent_to_ratio(self.position.trailing_stop_percent)
        if self.position.side == "buy":
            best_price = max(self.position.trailing_reference_price, current_price)
            trailed_stop = best_price * (1 - trail_ratio)
            if trailed_stop > self.position.stop_loss:
                self.position.stop_loss = trailed_stop
                self.position.trailing_reference_price = best_price
                self.logger.info("TRAILING STOP UPDATED | SIDE=BUY | SL=%.2f", self.position.stop_loss)
        else:
            best_price = min(self.position.trailing_reference_price, current_price)
            trailed_stop = best_price * (1 + trail_ratio)
            if trailed_stop < self.position.stop_loss:
                self.position.stop_loss = trailed_stop
                self.position.trailing_reference_price = best_price
                self.logger.info("TRAILING STOP UPDATED | SIDE=SELL | SL=%.2f", self.position.stop_loss)

    async def _place_entry_order(
        self,
        product_id: int,
        quantity: float,
        side: str,
        order_type: str,
        price: float,
    ) -> None:
        if self.paper_trading:
            self.logger.info("PAPER ORDER | PRODUCT=%s | SIDE=%s | QTY=%s | PRICE=%.2f", product_id, side, quantity, price)
            return
        await self.client.set_leverage(product_id, self.config["trading"]["leverage"])
        await self.client.place_order(product_id, quantity, side, order_type)

    async def _place_exit_order(self, product_id: int, quantity: float, side: str, price: float) -> None:
        if self.paper_trading:
            self.logger.info("PAPER EXIT | PRODUCT=%s | SIDE=%s | QTY=%s | PRICE=%.2f", product_id, side, quantity, price)
            return
        await self.client.place_order(product_id, quantity, side, "market_order", reduce_only=True)


def _percent_to_ratio(percent: float) -> float:
    if percent < 0:
        raise CriticalBotError("Risk percentage values must be zero or greater")
    return percent / 100

from __future__ import annotations

from utils.helpers import Candle, IndicatorSnapshot, SignalDecision


class BollingerReversalStrategy:
    def __init__(self, config: dict) -> None:
        self.config = config

    def evaluate(self, candles: list[Candle], indicators: IndicatorSnapshot) -> SignalDecision:
        if len(candles) < 2:
            return SignalDecision(status="WAITING_FOR_DATA", rejected_reason="not enough candles")

        current = candles[-1]
        previous = candles[-2]
        signal_control = self.config["signal_control"]
        rsi_config = self.config["rsi"]
        bb_config = self.config["bollinger_bands"]
        rsi_buy_level = float(rsi_config["rsi_buy_level"])
        rsi_sell_level = float(rsi_config["rsi_sell_level"])
        rsi_enabled = rsi_config.get("rsi_enabled", True)
        rsi_neutral = rsi_buy_level <= indicators.current_rsi <= rsi_sell_level

        if not bb_config.get("bb_enabled", True):
            return SignalDecision(status="WAITING", rejected_reason="bollinger bands disabled")

        sell = SignalDecision(
            action="sell",
            status="WAITING_FOR_SELL_CONFIRMATION",
            upper_band_touched=previous.high >= indicators.upper_band or current.high >= indicators.upper_band,
            bearish_candle=current.close < current.open,
            previous_low_broken=current.close < previous.low,
            rsi_valid=(not rsi_enabled) or rsi_neutral,
            confirmation_active=True,
        )
        buy = SignalDecision(
            action="buy",
            status="WAITING_FOR_BUY_CONFIRMATION",
            lower_band_touched=previous.low <= indicators.lower_band or current.low <= indicators.lower_band,
            bullish_candle=current.close > current.open,
            previous_high_broken=current.close > previous.high,
            rsi_valid=(not rsi_enabled) or rsi_neutral,
            confirmation_active=True,
        )

        sell_ready = sell.upper_band_touched and sell.bearish_candle and sell.previous_low_broken and sell.rsi_valid
        buy_ready = buy.lower_band_touched and buy.bullish_candle and buy.previous_high_broken and buy.rsi_valid

        if sell_ready and signal_control.get("enable_sell_signals", True):
            sell.status = "SELL_CONFIRMED"
            return sell
        if buy_ready and signal_control.get("enable_buy_signals", True):
            buy.status = "BUY_CONFIRMED"
            return buy
        if sell.upper_band_touched:
            return self._reject(sell)
        if buy.lower_band_touched:
            return self._reject(buy)
        return SignalDecision(status="WAITING", rejected_reason="no band touch")

    def _reject(self, decision: SignalDecision) -> SignalDecision:
        missing: list[str] = []
        if decision.action == "sell":
            if not decision.bearish_candle:
                missing.append("bearish candle not formed")
            if not decision.previous_low_broken:
                missing.append("previous candle low not broken")
        if decision.action == "buy":
            if not decision.bullish_candle:
                missing.append("bullish candle not formed")
            if not decision.previous_high_broken:
                missing.append("previous candle high not broken")
        if not decision.rsi_valid:
            missing.append("RSI condition failed")
        decision.action = "hold"
        decision.status = "SIGNAL_REJECTED"
        decision.rejected_reason = ", ".join(missing) or "signal not confirmed"
        return decision

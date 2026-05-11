import unittest

from strategy.bollinger_strategy import BollingerReversalStrategy
from utils.helpers import Candle, IndicatorSnapshot


def _config() -> dict:
    return {
        "signal_control": {
            "enable_buy_signals": True,
            "enable_sell_signals": True,
        },
        "rsi": {
            "rsi_enabled": True,
            "rsi_buy_level": 30,
            "rsi_sell_level": 70,
        },
        "bollinger_bands": {
            "bb_enabled": True,
        },
    }


class BollingerReversalStrategyTest(unittest.TestCase):
    def test_buy_confirms_when_rsi_is_in_neutral_zone(self) -> None:
        strategy = BollingerReversalStrategy(_config())
        candles = [
            Candle(timestamp=1, open=100, high=105, low=94, close=98),
            Candle(timestamp=2, open=99, high=108, low=98, close=107),
        ]
        indicators = IndicatorSnapshot(lower_band=95, current_rsi=50)

        decision = strategy.evaluate(candles, indicators)

        self.assertEqual(decision.status, "BUY_CONFIRMED")
        self.assertEqual(decision.action, "buy")
        self.assertTrue(decision.rsi_valid)

    def test_sell_confirms_when_rsi_is_in_neutral_zone(self) -> None:
        strategy = BollingerReversalStrategy(_config())
        candles = [
            Candle(timestamp=1, open=100, high=106, low=95, close=102),
            Candle(timestamp=2, open=101, high=102, low=90, close=94),
        ]
        indicators = IndicatorSnapshot(upper_band=105, current_rsi=50)

        decision = strategy.evaluate(candles, indicators)

        self.assertEqual(decision.status, "SELL_CONFIRMED")
        self.assertEqual(decision.action, "sell")
        self.assertTrue(decision.rsi_valid)

    def test_rejects_signal_when_rsi_is_outside_neutral_zone(self) -> None:
        strategy = BollingerReversalStrategy(_config())
        candles = [
            Candle(timestamp=1, open=100, high=105, low=94, close=98),
            Candle(timestamp=2, open=99, high=108, low=98, close=107),
        ]
        indicators = IndicatorSnapshot(lower_band=95, current_rsi=25)

        decision = strategy.evaluate(candles, indicators)

        self.assertEqual(decision.status, "SIGNAL_REJECTED")
        self.assertEqual(decision.action, "hold")
        self.assertFalse(decision.rsi_valid)
        self.assertIn("RSI condition failed", decision.rejected_reason)


if __name__ == "__main__":
    unittest.main()

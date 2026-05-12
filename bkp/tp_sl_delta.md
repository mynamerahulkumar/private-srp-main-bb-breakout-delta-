## Percentage-Based TP/SL Configuration

Your algo bot supports automatic **Take Profit (TP)** and **Stop Loss (SL)** calculation using percentage values from `config.yaml`.

Instead of manually entering TP/SL prices, the bot calculates them dynamically using the current market entry price.

### Example

If the current market entry price is:

* Entry Price = `100000`

And your config contains:

```yaml
take_profit_percent: 5
stop_loss_percent: 3
```

Then the bot will automatically calculate:

* Take Profit Price = `105000` (+5%)
* Stop Loss Price = `97000` (-3%)

---

# Configuration

Add the following fields in `config.yaml`:

```yaml
# TP/SL Percentage Configuration
enable_bracket_tp_sl: true

# Percentage values
take_profit_percent: 5
stop_loss_percent: 3

# Optional limit buffer for limit exits
tp_limit_buffer_percent: 0.1
sl_limit_buffer_percent: 0.1

# Trigger method
bracket_stop_trigger_method: "mark_price"
```

---

# How TP/SL Calculation Works

## For BUY Orders

TP and SL are calculated from the current market entry price.

Formula:

TP = EntryPrice \times \left(1 + \frac{TP%}{100}\right)

SL = EntryPrice \times \left(1 - \frac{SL%}{100}\right)

Example:

```text
Entry Price = 100000
TP % = 5
SL % = 3

TP = 105000
SL = 97000
```

---

## For SELL Orders

Formula:

TP = EntryPrice \times \left(1 - \frac{TP%}{100}\right)

SL = EntryPrice \times \left(1 + \frac{SL%}{100}\right)

Example:

```text
Entry Price = 100000
TP % = 5
SL % = 3

TP = 95000
SL = 103000
```

---

# Order Placement Flow

1. Bot fetches current market price.
2. Bot calculates TP and SL prices using configured percentages.
3. Bot sends a single Delta Exchange market order request with bracket TP/SL attached.
4. Delta Exchange automatically manages exits.

---

# Example Generated Payload (BUY)

```json
{
  "product_symbol": "BTCUSD",
  "order_type": "market_order",
  "size": 10,
  "side": "buy",
  "bracket_take_profit_price": "105000",
  "bracket_take_profit_limit_price": "104900",
  "bracket_stop_loss_price": "97000",
  "bracket_stop_loss_limit_price": "96900",
  "bracket_stop_trigger_method": "mark_price"
}
```

---

# Important Notes

* TP/SL prices are calculated dynamically from live market price.
* Percentage values must be positive numbers.
* The bot automatically handles BUY and SELL calculation logic separately.
* Bracket orders close the full position automatically.
* If TP/SL percentage values are invalid, the bot should stop execution and print a clear error in logs.
* Recommended TP/SL percentages:

  * Scalping: TP 1–2%, SL 0.5–1%
  * Intraday: TP 3–5%, SL 1–2%
  * Swing: TP 5–10%, SL 2–5%

---

# Validation Rules

The bot should validate:

* `take_profit_percent > 0`
* `stop_loss_percent > 0`
* Market price fetched successfully
* Calculated TP/SL prices are valid
* TP is above entry for BUY
* SL is below entry for BUY
* TP is below entry for SELL
* SL is above entry for SELL

If validation fails:

```text
[ERROR] Invalid TP/SL calculation detected.
[ERROR] Bot stopped to prevent incorrect order placement.
```

---

# Recommended Logging

```text
===============================
ENTRY PRICE : 100000
ORDER SIDE  : BUY

TP %        : 5%
SL %        : 3%

TP PRICE    : 105000
SL PRICE    : 97000
===============================
```

This helps during live trading, debugging, and YouTube demo sessions.


Place Market Order with Bracket TP/SL (Single Request)
You can attach TP and SL directly when placing the market order using the bracket order fields.

Endpoint: POST https://api.india.delta.exchange/v2/orders

Key Parameters:

Parameter	Type	Description
product_id or product_symbol	integer / string	Product identifier (use one)
order_type	string	Set to "market_order"
size	integer	Order size (in lots)
side	string	"buy" or "sell"
bracket_take_profit_price	string	TP trigger price
bracket_take_profit_limit_price	string	TP limit price (for limit TP exit)
bracket_stop_loss_price	string	SL trigger price
bracket_stop_loss_limit_price	string	SL limit price (for limit SL exit)
bracket_stop_trigger_method	string	Trigger method: mark_price (default), last_traded_price, or spot_price
Example Request Body (Buy Market Order with TP/SL):


{
  "product_symbol": "BTCUSD",
  "order_type": "market_order",
  "size": 10,
  "side": "buy",
  "bracket_take_profit_price": "105000",
  "bracket_take_profit_limit_price": "104900",
  "bracket_stop_loss_price": "95000",
  "bracket_stop_loss_limit_price": "94900",
  "bracket_stop_trigger_method": "mark_price"
}

Curl Example:


curl -X POST "https://api.india.delta.exchange/v2/orders" \
  -H "api-key: your_api_key" \
  -H "timestamp: your_timestamp" \
  -H "signature: your_signature" \
  -H "Content-Type: application/json" \
  -d '{
    "product_symbol": "BTCUSD",
    "order_type": "market_order",
    "size": 10,
    "side": "buy",
    "bracket_take_profit_price": "105000",
    "bracket_take_profit_limit_price": "104900",
    "bracket_stop_loss_price": "95000",
    "bracket_stop_loss_limit_price": "94900",
    "bracket_stop_trigger_method": "mark_price"
  }'

Approach 2: Add Bracket TP/SL to an Existing Position
If you already have an open position or order, you can attach a bracket order separately.

Endpoint: POST https://api.india.delta.exchange/v2/orders/bracket

Key Parameters:

Parameter	Type	Description
product_id or product_symbol	integer / string	Product identifier (use one)
stop_loss_order	object	SL order details (stop_price, order_type, limit_price)
take_profit_order	object	TP order details (stop_price, order_type, limit_price)
bracket_stop_trigger_method	string	Trigger method: mark_price (default), last_traded_price, spot_price
Example Request Body:


{
  "product_symbol": "BTCUSD",
  "bracket_stop_trigger_method": "mark_price",
  "stop_loss_order": {
    "order_type": "limit_order",
    "stop_price": "95000",
    "limit_price": "94900"
  },
  "take_profit_order": {
    "order_type": "limit_order",
    "stop_price": "105000",
    "limit_price": "104900"
  }
}

Curl Example:


curl -X POST "https://api.india.delta.exchange/v2/orders/bracket" \
  -H "api-key: your_api_key" \
  -H "timestamp: your_timestamp" \
  -H "signature: your_signature" \
  -H "Content-Type: application/json" \
  -d '{
    "product_symbol": "BTCUSD",
    "bracket_stop_trigger_method": "mark_price",
    "stop_loss_order": {
      "order_type": "limit_order",
      "stop_price": "95000",
      "limit_price": "94900"
    },
    "take_profit_order": {
      "order_type": "limit_order",
      "stop_price": "105000",
      "limit_price": "104900"
    }
  }'

Important Notes
Bracket orders close the entire position - you do not need to specify a size for bracket orders on positions.
For open orders, you can have multiple bracket orders, but for an open position, only a single bracket order is allowed per contract.
If you want a market exit on TP/SL trigger, set order_type to "market_order" inside the bracket objects and omit limit_price.
All requests require proper authentication headers (api-key, timestamp, signature). Refer to the authentication docs for signature generation details.
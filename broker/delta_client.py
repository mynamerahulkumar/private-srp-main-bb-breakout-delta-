from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import urlencode

import aiohttp

from utils.helpers import CriticalBotError


class DeltaAPIError(Exception):
    pass


class DeltaClient:
    def __init__(self, base_url: str, api_key: str = "", api_secret: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "DeltaClient":
        await self.open()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def open(self) -> None:
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=10, connect=3)
            self.session = aiohttp.ClientSession(timeout=timeout)

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()

    async def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        auth: bool = False,
    ) -> Any:
        await self.open()
        assert self.session is not None
        method = method.upper()
        body = _body_string(payload)
        query_string = f"?{urlencode(query)}" if query else ""
        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json", "User-Agent": "delta-bb-rsi-bot"}

        if auth:
            if not self.api_key or not self.api_secret:
                raise CriticalBotError("API key/secret missing for authenticated Delta request")
            timestamp = str(int(time.time()))
            signature_data = method + timestamp + path + query_string + body
            headers.update(
                {
                    "api-key": self.api_key,
                    "timestamp": timestamp,
                    "signature": _generate_signature(self.api_secret, signature_data),
                }
            )

        async with self.session.request(method, url, params=query, data=body or None, headers=headers) as response:
            text = await response.text()
            if response.status >= 400:
                self._raise_http_error(response.status, text)
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise DeltaAPIError(f"Invalid Delta response: {text[:200]}") from exc

        if data.get("success") is True:
            return data.get("result")
        error = data.get("error") or data
        message = str(error)
        self._raise_api_error(message)
        raise DeltaAPIError(message)

    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        return await self.request("GET", f"/v2/tickers/{symbol}")

    async def get_candles(self, symbol: str, resolution: str, start: int, end: int) -> list[dict[str, Any]]:
        return await self.request(
            "GET",
            "/v2/history/candles",
            query={"symbol": symbol, "resolution": resolution, "start": start, "end": end},
        )

    async def get_position(self, product_id: int) -> Any:
        return await self.request("GET", "/v2/positions", query={"product_id": product_id}, auth=True)

    async def set_leverage(self, product_id: int, leverage: int | float) -> Any:
        return await self.request(
            "POST",
            f"/v2/products/{product_id}/orders/leverage",
            payload={"leverage": leverage},
            auth=True,
        )

    async def place_order(
        self,
        product_id: int,
        size: float,
        side: str,
        order_type: str,
        limit_price: float | None = None,
        reduce_only: bool = False,
    ) -> Any:
        payload: dict[str, Any] = {
            "product_id": product_id,
            "size": int(size),
            "side": side,
            "order_type": order_type,
            "reduce_only": "true" if reduce_only else "false",
        }
        if order_type == "limit_order" and limit_price is not None:
            payload["limit_price"] = str(limit_price)
        return await self.request("POST", "/v2/orders", payload=payload, auth=True)

    def _raise_http_error(self, status: int, text: str) -> None:
        message = f"Delta HTTP {status}: {text[:300]}"
        if status in {401, 403}:
            raise CriticalBotError(f"Delta authentication/permission failure: {message}")
        raise DeltaAPIError(message)

    def _raise_api_error(self, message: str) -> None:
        lowered = message.lower()
        critical_terms = ("invalid api", "authentication", "permission", "insufficient balance")
        if any(term in lowered for term in critical_terms):
            raise CriticalBotError(f"Critical Delta API error: {message}")


def _generate_signature(secret: str, message: str) -> str:
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def _body_string(body: dict[str, Any] | None) -> str:
    if body is None:
        return ""
    return json.dumps(body, separators=(",", ":"))

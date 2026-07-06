from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd

from src.data.downloader.utils import INTERVAL_MS


BINANCE_SPOT_KLINES_URL = "https://api.binance.com/api/v3/klines"
DATA_CONTRACT_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume", "is_closed"]


class BinanceAPIError(RuntimeError):
    pass


class EmptyBinanceResponseError(BinanceAPIError):
    pass


def convert_klines_to_dataframe(raw_klines: list[list[Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for raw in raw_klines:
        if len(raw) < 6:
            raise BinanceAPIError(f"unexpected kline payload length: {len(raw)}")
        rows.append(
            {
                "timestamp": int(raw[0]),
                "open": float(raw[1]),
                "high": float(raw[2]),
                "low": float(raw[3]),
                "close": float(raw[4]),
                "volume": float(raw[5]),
                "is_closed": True,
            }
        )

    frame = pd.DataFrame(rows, columns=DATA_CONTRACT_COLUMNS)
    if frame.empty:
        return frame.astype(
            {
                "timestamp": "int64",
                "open": "float64",
                "high": "float64",
                "low": "float64",
                "close": "float64",
                "volume": "float64",
                "is_closed": "bool",
            }
        )

    return frame.astype(
        {
            "timestamp": "int64",
            "open": "float64",
            "high": "float64",
            "low": "float64",
            "close": "float64",
            "volume": "float64",
            "is_closed": "bool",
        }
    )


class BinanceSpotKlineClient:
    def __init__(
        self,
        *,
        base_url: str = BINANCE_SPOT_KLINES_URL,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = base_url
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.timeout_seconds = timeout_seconds

    def fetch_klines(self, symbol: str, timeframe: str, start_ms: int, end_ms: int) -> pd.DataFrame:
        interval_ms = INTERVAL_MS[timeframe]
        cursor_ms = start_ms
        raw_rows: list[list[Any]] = []

        while cursor_ms < end_ms:
            batch = self._request_klines(symbol, timeframe, cursor_ms, end_ms - 1)
            if not batch:
                raise EmptyBinanceResponseError(
                    f"empty Binance kline response for {symbol} {timeframe} at {cursor_ms}"
                )

            filtered_batch = [row for row in batch if start_ms <= int(row[0]) < end_ms]
            raw_rows.extend(filtered_batch)

            last_open_time = int(batch[-1][0])
            next_cursor_ms = last_open_time + interval_ms
            if next_cursor_ms <= cursor_ms:
                raise BinanceAPIError("Binance pagination did not advance")
            cursor_ms = next_cursor_ms

            if len(batch) < 1000:
                break

        if not raw_rows:
            raise EmptyBinanceResponseError(f"empty Binance kline response for {symbol} {timeframe}")

        return convert_klines_to_dataframe(raw_rows)

    def _request_klines(self, symbol: str, timeframe: str, start_ms: int, end_ms: int) -> list[list[Any]]:
        query = urlencode(
            {
                "symbol": symbol,
                "interval": timeframe,
                "startTime": start_ms,
                "endTime": end_ms,
                "limit": 1000,
            }
        )
        url = f"{self.base_url}?{query}"

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                with urlopen(url, timeout=self.timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if isinstance(payload, dict):
                    raise BinanceAPIError(str(payload))
                if not isinstance(payload, list):
                    raise BinanceAPIError(f"unexpected Binance response type: {type(payload).__name__}")
                return payload
            except (HTTPError, URLError, TimeoutError, BinanceAPIError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(self.backoff_seconds * attempt)

        raise BinanceAPIError(f"Binance kline request failed after {self.max_retries} retries: {last_error}")

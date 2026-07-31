"""
Отримання свічок (OHLCV) з будь-якої біржі, підтримуваної ccxt.
Публічні ринкові дані не потребують API ключів.
"""
import ccxt
import pandas as pd
import config


def get_exchange(exchange_id: str):
    """Створює підключення до біржі за її id в ccxt (наприклад 'binance', 'bybit', 'coinbase')."""
    exchange_class = getattr(ccxt, exchange_id)
    params = {"enableRateLimit": True}
    params.update(config.EXCHANGE_OPTIONS.get(exchange_id, {}))
    return exchange_class(params)


def fetch_ohlcv(exchange, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    """
    Тягне свічки для символу (наприклад 'BTC/USDT') і повертає DataFrame
    з колонками: timestamp, open, high, low, close, volume.
    """
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def fetch_ticker(exchange, symbol: str) -> dict:
    """Поточна ціна та статистика за 24г для символу."""
    return exchange.fetch_ticker(symbol)

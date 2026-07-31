"""
Індикатори та розрахунки "сили руху" й "запасу ходу" — усе за методологією книги.
ATR тут скрізь рахується через book_atr.calculate_book_atr (з виключенням
паранормальних барів), а не через стандартну бібліотеку.
"""
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
import config
import book_atr


def add_rsi(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["rsi"] = RSIIndicator(close=df["close"], window=config.RSI_PERIOD).rsi()
    return df


def avg_volume(df: pd.DataFrame, lookback: int = 20) -> float:
    return df["volume"].iloc[-(lookback + 1):-1].mean()


def volume_vs_average_pct(df: pd.DataFrame, lookback: int = 20) -> float:
    avg = avg_volume(df, lookback)
    if not avg or pd.isna(avg):
        return 0.0
    last = df["volume"].iloc[-1]
    return ((last - avg) / avg) * 100


def is_volume_confirmed(volume_change_pct: float) -> bool:
    return volume_change_pct >= config.VOLUME_CONFIRMATION_THRESHOLD_PCT


def price_change_24h_pct(ticker: dict) -> float:
    return ticker.get("percentage") or 0.0


def calculate_impulse(df_signal: pd.DataFrame, direction: str) -> dict:
    """Рух за останні IMPULSE_LOOKBACK_CANDLES свічок відносно ATR(5хв, book-методика)."""
    completed = df_signal.iloc[:-1] if len(df_signal) > 1 else df_signal
    atr = book_atr.calculate_book_atr(completed)

    lookback = min(config.IMPULSE_LOOKBACK_CANDLES, len(df_signal) - 1)
    start_price = df_signal["close"].iloc[-(lookback + 1)]
    end_price = df_signal["close"].iloc[-1]

    move = (end_price - start_price) if direction == "long" else (start_price - end_price)
    ratio = (move / atr) if atr else 0.0
    confirmed = ratio >= config.IMPULSE_ATR_MULTIPLIER

    return {"move": float(move), "atr": float(atr), "ratio": float(ratio), "confirmed": bool(confirmed)}


def detect_trend(df_higher_tf: pd.DataFrame) -> dict:
    df = df_higher_tf.copy()
    if len(df) < config.TREND_EMA_SLOW:
        return {"direction": "unknown", "label": "недостатньо даних"}

    ema_fast = EMAIndicator(close=df["close"], window=config.TREND_EMA_FAST).ema_indicator().iloc[-1]
    ema_slow = EMAIndicator(close=df["close"], window=config.TREND_EMA_SLOW).ema_indicator().iloc[-1]
    price = df["close"].iloc[-1]

    if price > ema_fast > ema_slow:
        return {"direction": "uptrend", "label": "висхідний"}
    if price < ema_fast < ema_slow:
        return {"direction": "downtrend", "label": "низхідний"}
    return {"direction": "range", "label": "боковий/змішаний"}


def is_signal_with_trend(direction: str, trend: dict) -> bool | None:
    if trend["direction"] == "uptrend":
        return direction == "long"
    if trend["direction"] == "downtrend":
        return direction == "short"
    return None


def calculate_daily_atr(df_daily: pd.DataFrame) -> float:
    """Денний ATR за методикою книги, рахований на завершених денних барах."""
    completed = df_daily.iloc[:-1] if len(df_daily) > 1 else df_daily
    return book_atr.calculate_book_atr(completed)


def daily_atr_consumed_pct(df_daily: pd.DataFrame, current_price: float, daily_atr: float) -> float:
    """
    % денного ATR, вже пройденого сьогодні: |поточна ціна - ціна відкриття сьогоднішнього
    дня| / денний ATR * 100. Використовує open останнього (поточного, ще не закритого)
    денного бару як точку відліку дня.
    """
    if not daily_atr or daily_atr == 0:
        return 0.0
    today_open = df_daily["open"].iloc[-1]
    moved = abs(current_price - today_open)
    return (moved / daily_atr) * 100


def is_local_extreme(df_daily: pd.DataFrame, direction: str, lookback: int = None) -> bool:
    """
    Перевіряє, чи поточна ціна на новому локальному екстремумі (максимум для LONG,
    мінімум для SHORT) за останні lookback барів — виняток з правила 75-80% ATR
    (немає технічних перешкод попереду).
    """
    lookback = lookback or config.LOCAL_EXTREME_LOOKBACK_BARS
    window = df_daily.tail(lookback)
    current_price = df_daily["close"].iloc[-1]

    if direction == "long":
        return current_price >= window["high"].max() - 1e-9
    else:
        return current_price <= window["low"].min() + 1e-9


def technical_atr_ok(nearest_other_level: dict | None, current_price: float, calculated_atr: float) -> bool:
    """
    Технічний ATR (відстань до найближчого стороннього рівня) має бути >= розрахункового
    ATR — інакше рівень "затиснутий" і входити ризиковано. Якщо поруч немає інших рівнів
    в межах розумної відстані — вважаємо умову виконаною (перешкод немає).
    """
    if nearest_other_level is None:
        return True
    technical_atr = abs(nearest_other_level["price"] - current_price)
    return technical_atr >= calculated_atr


def room_to_opposite_level_in_stops(opposite_level: dict | None, current_price: float, stop_size: float) -> float | None:
    """Скільки стопів вміщує відстань до протилежного рівня. None, якщо протилежного рівня не знайдено."""
    if opposite_level is None or not stop_size:
        return None
    distance = abs(opposite_level["price"] - current_price)
    return distance / stop_size


def overall_confidence(impulse_confirmed: bool, volume_confirmed: bool, with_trend: bool | None) -> str:
    score = 0
    if impulse_confirmed:
        score += 2
    if volume_confirmed:
        score += 1
    if with_trend:
        score += 1
    elif with_trend is False:
        score -= 1

    if score >= 3:
        return "висока"
    if score >= 1:
        return "середня"
    return "низька"

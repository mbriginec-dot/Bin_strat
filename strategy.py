"""
Реалізація трьох торгових моделей з книги відносно знайдених рівнів:
  1. Пробій (breakout)
  2. Відбій (rejection)
  3. Хибний пробій (false breakout)

А також логіка "радару" — завчасного наближення ціни до сильного рівня.

Все, що повертають функції тут, — це ПОТЕНЦІЙНІ сетапи для сповіщення в Telegram.
Бот нічого не торгує сам.

Примітка: рівні, що приходять сюди (з main.py), уже відфільтровані за силою
(multi_tf_levels.py застосовує config.MIN_LEVEL_STRENGTH окремо для кожного ТФ),
тому тут додатковий поріг сили не перевіряється — лише відстань/патерн.
"""
import config


def distance_pct(price: float, level_price: float) -> float:
    """Відстань у % між ціною і рівнем."""
    return abs(price - level_price) / level_price * 100


def find_radar_candidates(current_price: float, levels: list[dict]) -> list[dict]:
    """Знаходить рівні, до яких ціна наблизилась на RADAR_DISTANCE_PCT."""
    candidates = []
    for level in levels:
        dist = distance_pct(current_price, level["price"])
        if dist <= config.RADAR_DISTANCE_PCT:
            side = "resistance" if current_price < level["price"] else "support"
            candidates.append({"level": level, "distance_pct": dist, "side": side})
    return candidates


def _tolerance(level_price: float) -> float:
    return level_price * (config.LEVEL_CLUSTER_TOLERANCE_PCT / 100)


def check_breakout(df_signal, level: dict) -> dict | None:
    """Пробій: попереднє закриття по один бік рівня, останнє — впевнено за рівнем."""
    if len(df_signal) < 2:
        return None

    level_price = level["price"]
    tol = _tolerance(level_price)
    prev_close = df_signal["close"].iloc[-2]
    last_close = df_signal["close"].iloc[-1]

    if prev_close < level_price - tol and last_close > level_price + tol:
        return {"pattern": "breakout", "direction": "long", "entry": float(last_close)}
    if prev_close > level_price + tol and last_close < level_price - tol:
        return {"pattern": "breakout", "direction": "short", "entry": float(last_close)}
    return None


def check_rejection(df_signal, level: dict) -> dict | None:
    """Відбій: тінь протестувала рівень, закриття підтвердило неспроможність пробити."""
    if len(df_signal) < 1:
        return None

    level_price = level["price"]
    tol = _tolerance(level_price)
    last = df_signal.iloc[-1]

    touched_support = last["low"] <= level_price + tol
    closed_above = last["close"] > level_price + tol
    if touched_support and closed_above and last["close"] > last["open"]:
        return {"pattern": "rejection", "direction": "long", "entry": float(last["close"])}

    touched_resistance = last["high"] >= level_price - tol
    closed_below = last["close"] < level_price - tol
    if touched_resistance and closed_below and last["close"] < last["open"]:
        return {"pattern": "rejection", "direction": "short", "entry": float(last["close"])}

    return None


def check_false_breakout(df_signal, level: dict) -> dict | None:
    """Хибний пробій: тінь пробила рівень, закриття повернулось назад."""
    if len(df_signal) < 1:
        return None

    level_price = level["price"]
    tol = _tolerance(level_price)
    last = df_signal.iloc[-1]

    wick_through_up = last["high"] > level_price + tol
    closed_back_below = last["close"] < level_price - tol
    if wick_through_up and closed_back_below:
        return {"pattern": "false_breakout", "direction": "short", "entry": float(last["close"])}

    wick_through_down = last["low"] < level_price - tol
    closed_back_above = last["close"] > level_price + tol
    if wick_through_down and closed_back_above:
        return {"pattern": "false_breakout", "direction": "long", "entry": float(last["close"])}

    return None


def calculate_risk_levels(entry: float, level_price: float, direction: str, atr_5m: float) -> dict:
    """
    Стоп-лосс = рівень ± ATR(5хв, за методикою книги) — короткий стоп, "захований"
    за рівень на відстань середнього 5-хвилинного бару. Тейк = risk * MIN_RISK_REWARD_RATIO (3:1).
    """
    if direction == "long":
        stop_loss = level_price - atr_5m
        risk = entry - stop_loss
        take_profit = entry + risk * config.MIN_RISK_REWARD_RATIO
    else:
        stop_loss = level_price + atr_5m
        risk = stop_loss - entry
        take_profit = entry - risk * config.MIN_RISK_REWARD_RATIO

    return {
        "stop_loss": round(stop_loss, 8),
        "take_profit": round(take_profit, 8),
        "risk": round(risk, 8),
        "risk_reward_ratio": config.MIN_RISK_REWARD_RATIO,
    }


def check_all_patterns(df_signal, level: dict) -> dict | None:
    """Перевіряє всі 3 патерни для одного рівня, повертає перший знайдений (БЕЗ ризик-рівнів —
    їх рахує main.py окремо, коли відомий ATR(5хв))."""
    for check_fn in (check_breakout, check_rejection, check_false_breakout):
        result = check_fn(df_signal, level)
        if result:
            result["level"] = level
            return result
    return None

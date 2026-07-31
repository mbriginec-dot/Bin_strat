"""
Пошук цінових рівнів на графіку та оцінка їхньої сили — за методологією
з книги (типи рівнів, дотики, хибні пробої, кругні числа, старший таймфрейм).

Це осередок "знань з книги", формалізований у код. Спрощення для MVP:
- рівні шукаються як кластери локальних екстремумів (pivot high/low) на старшому ТФ
- сила рівня рахується за кількістю дотиків, наявністю хибних пробоїв і круглим числом
- типи рівнів (злам тренду / історичний / дзеркальний / лімітний / паранормальна свічка /
  проторговка / геп) наразі об'єднані в загальну оцінку сили, окремі типи можна
  деталізувати пізніше, коли назбирається статистика по реальних сигналах.
"""
import pandas as pd
import numpy as np
import config


def find_pivots(df: pd.DataFrame, window: int = 3) -> tuple[list[int], list[int]]:
    """
    Знаходить індекси локальних максимумів і мінімумів (pivot points) —
    ключові точки, від яких будуються рівні (аналог "точок зламу тренду" з книги).
    window — скільки свічок з кожного боку мають бути нижче/вище, щоб точка вважалась pivot.
    """
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)

    pivot_high_idx = []
    pivot_low_idx = []

    for i in range(window, n - window):
        if highs[i] == max(highs[i - window:i + window + 1]):
            pivot_high_idx.append(i)
        if lows[i] == min(lows[i - window:i + window + 1]):
            pivot_low_idx.append(i)

    return pivot_high_idx, pivot_low_idx


def is_round_number(price: float) -> bool:
    """
    Перевіряє, чи ціна близька до "круглого" числа (закінчується на .0, .5 і т.п.),
    з урахуванням порядку величини ціни (книга: круглі числа підсилюють рівень ~на 20%).
    """
    if price == 0:
        return False

    magnitude = 10 ** (len(str(int(price))) - 2) if price >= 1 else 0.01
    remainder = price % magnitude
    tolerance = magnitude * 0.02
    return remainder < tolerance or (magnitude - remainder) < tolerance


def cluster_pivots(df: pd.DataFrame, pivot_idx: list[int], price_col: str) -> list[dict]:
    """
    Групує близькі pivot-точки в єдині рівні (в межах LEVEL_CLUSTER_TOLERANCE_PCT),
    рахує кількість дотиків для кожного кластера.
    """
    if not pivot_idx:
        return []

    prices = [(idx, df[price_col].iloc[idx]) for idx in pivot_idx]
    prices.sort(key=lambda x: x[1])

    clusters = []
    current_cluster = [prices[0]]

    for idx, price in prices[1:]:
        cluster_avg = np.mean([p for _, p in current_cluster])
        tolerance = cluster_avg * (config.LEVEL_CLUSTER_TOLERANCE_PCT / 100)

        if abs(price - cluster_avg) <= tolerance:
            current_cluster.append((idx, price))
        else:
            clusters.append(current_cluster)
            current_cluster = [(idx, price)]

    clusters.append(current_cluster)

    levels = []
    for cluster in clusters:
        cluster_prices = [p for _, p in cluster]
        level_price = float(np.mean(cluster_prices))
        levels.append({
            "price": level_price,
            "touches": len(cluster),
            "indices": [idx for idx, _ in cluster],
        })

    return levels


def detect_false_breakouts(df: pd.DataFrame, level_price: float) -> int:
    """
    Рахує кількість хибних пробоїв рівня: свічка пробила рівень тінню,
    але закрилась назад по інший бік рівня.
    """
    tolerance = level_price * (config.LEVEL_CLUSTER_TOLERANCE_PCT / 100)
    count = 0

    for _, row in df.iterrows():
        wick_through_up = row["high"] > level_price + tolerance and row["close"] < level_price
        wick_through_down = row["low"] < level_price - tolerance and row["close"] > level_price
        if wick_through_up or wick_through_down:
            count += 1

    return count


def calculate_strength(touches: int, false_breakouts: int, is_round: bool) -> int:
    """Формула сили рівня за вагами з config.py (книга: більше дотиків/хибних пробоїв/кругле число = сильніший рівень)."""
    strength = touches * config.TOUCH_STRENGTH_WEIGHT
    strength += false_breakouts * config.FALSE_BREAKOUT_STRENGTH_BONUS
    if is_round:
        strength += config.ROUND_NUMBER_STRENGTH_BONUS
    return strength


def find_levels(df: pd.DataFrame, pivot_window: int = 3) -> list[dict]:
    """
    Головна функція: повертає список знайдених рівнів з повною інформацією
    (ціна, дотики, хибні пробої, кругле число, сила).
    """
    pivot_high_idx, pivot_low_idx = find_pivots(df, window=pivot_window)

    high_levels = cluster_pivots(df, pivot_high_idx, "high")
    low_levels = cluster_pivots(df, pivot_low_idx, "low")

    all_levels = high_levels + low_levels
    result = []

    for lvl in all_levels:
        if lvl["touches"] < config.MIN_TOUCHES_FOR_LEVEL:
            continue

        false_breakouts = detect_false_breakouts(df, lvl["price"])
        round_flag = is_round_number(lvl["price"])
        strength = calculate_strength(lvl["touches"], false_breakouts, round_flag)

        result.append({
            "price": lvl["price"],
            "touches": lvl["touches"],
            "false_breakouts": false_breakouts,
            "is_round": round_flag,
            "strength": strength,
        })

    result.sort(key=lambda x: x["strength"], reverse=True)
    return result


def filter_by_strength(levels: list[dict], min_strength: int) -> list[dict]:
    """Залишає тільки рівні із силою >= min_strength."""
    return [lvl for lvl in levels if lvl["strength"] >= min_strength]


def find_nearest_opposite_level(current_price: float, levels: list[dict], direction: str) -> dict | None:
    """
    Знаходить найближчий рівень по інший бік від напрямку угоди — тобто потенційну
    "стелю" руху (для LONG — найближчий рівень ВИЩЕ ціни; для SHORT — найближчий НИЖЧЕ).
    Потрібно для розрахунку "запасу ходу" за книгою.
    """
    if direction == "long":
        candidates = [lvl for lvl in levels if lvl["price"] > current_price]
        if not candidates:
            return None
        return min(candidates, key=lambda lvl: lvl["price"])
    else:
        candidates = [lvl for lvl in levels if lvl["price"] < current_price]
        if not candidates:
            return None
        return max(candidates, key=lambda lvl: lvl["price"])


def find_nearest_level_any_side(current_price: float, levels: list[dict], exclude_price: float = None) -> dict | None:
    """
    Знаходить найближчий рівень (з будь-якого боку) до поточної ціни — потрібно для
    "технічного ATR" (відстань до найближчої технічної перешкоди). exclude_price
    дозволяє виключити сам рівень угоди з пошуку.
    """
    candidates = levels
    if exclude_price is not None:
        candidates = [lvl for lvl in levels if abs(lvl["price"] - exclude_price) > 1e-9]
    if not candidates:
        return None
    return min(candidates, key=lambda lvl: abs(lvl["price"] - current_price))


def strength_label(strength: int) -> str:
    """Перетворює числову силу рівня в текстову мітку для повідомлень."""
    if strength >= 6:
        return "дуже висока"
    if strength >= 4:
        return "висока"
    if strength >= 2:
        return "середня"
    return "низька"

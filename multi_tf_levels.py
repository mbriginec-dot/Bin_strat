"""
Збір рівнів з кількох таймфреймів:
- Основний (1D) — усі рівні, що пройшли базовий поріг дотиків.
- Додаткові (4h/2h/1h) — тільки рівні, сила яких проходить ПІДВИЩЕНИЙ поріг
  (config.MIN_LEVEL_STRENGTH), бо на молодших ТФ природньо більше шумових дотиків.

Кожен рівень позначається джерельним таймфреймом ("timeframe" в словнику рівня).
"""
import data_fetcher
import levels as levels_module
import config


def gather_multi_tf_levels(exchange, exchange_id: str, symbol: str) -> list[dict]:
    """Повертає об'єднаний список рівнів з усіх сконфігурованих таймфреймів
    (додаткові таймфрейми беруться з урахуванням можливих обмежень API конкретної біржі)."""
    all_levels = []

    # Основний ТФ — без підвищеного порогу (тільки базовий MIN_TOUCHES_FOR_LEVEL з levels.py)
    df_primary = data_fetcher.fetch_ohlcv(
        exchange, symbol, config.PRIMARY_LEVEL_TIMEFRAME, config.LEVEL_CANDLES_LIMIT
    )
    primary_levels = levels_module.find_levels(df_primary)
    min_strength_primary = config.MIN_LEVEL_STRENGTH.get(config.PRIMARY_LEVEL_TIMEFRAME, 0)
    primary_levels = levels_module.filter_by_strength(primary_levels, min_strength_primary)
    for lvl in primary_levels:
        lvl["timeframe"] = config.PRIMARY_LEVEL_TIMEFRAME
    all_levels.extend(primary_levels)

    # Додаткові ТФ — тільки сильні рівні (список залежить від біржі)
    extra_timeframes = config.get_extra_timeframes(exchange_id)
    for tf in extra_timeframes:
        df_tf = data_fetcher.fetch_ohlcv(exchange, symbol, tf, config.LEVEL_CANDLES_LIMIT)
        tf_levels = levels_module.find_levels(df_tf)
        min_strength = config.MIN_LEVEL_STRENGTH.get(tf, 5)
        tf_levels = levels_module.filter_by_strength(tf_levels, min_strength)
        for lvl in tf_levels:
            lvl["timeframe"] = tf
        all_levels.extend(tf_levels)

    return all_levels


def has_cross_tf_confirmation(level: dict, all_levels: list[dict]) -> tuple[bool, list[str]]:
    """
    Перевіряє, чи цей рівень (за ціною, в межах толерантності) також присутній
    як сильний рівень на ІНШОМУ таймфреймі, ніж його власний. Повертає
    (чи є підтвердження, список ТФ, де воно знайдене).
    """
    tolerance = level["price"] * (config.CROSS_TF_LEVEL_TOLERANCE_PCT / 100)
    confirming_tfs = []

    for other in all_levels:
        if other["timeframe"] == level["timeframe"]:
            continue
        if abs(other["price"] - level["price"]) <= tolerance:
            if other["timeframe"] not in confirming_tfs:
                confirming_tfs.append(other["timeframe"])

    return (len(confirming_tfs) > 0, confirming_tfs)

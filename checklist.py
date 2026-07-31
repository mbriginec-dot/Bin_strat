"""
Збирає повний чекліст підтверджень з книги для конкретного сигналу (LONG/SHORT).
Поріг для надсилання поки НЕ застосовується (за домовленістю) — чекліст лише
інформує про якість сетапу, сигнал шлеться завжди, коли патерн підтверджений.
"""
import pandas as pd
import config
import indicators
import levels as levels_module
import multi_tf_levels


def build_checklist(
    level: dict,
    direction: str,
    current_price: float,
    all_levels: list[dict],
    df_daily: pd.DataFrame,
    df_signal: pd.DataFrame,
    impulse: dict,
    volume_confirmed: bool,
    trend: dict,
    with_trend,
    daily_atr: float,
    atr_5m: float,
) -> dict:
    """
    Повертає словник:
    {
        "items": [{"key": str, "label": str, "passed": bool, "detail": str}, ...],
        "passed_count": int,
        "total": int,
    }
    """
    items = []

    # 1. Сила рівня
    min_strength = config.MIN_LEVEL_STRENGTH.get(level["timeframe"], 0)
    level_strength_ok = level["strength"] >= min_strength
    items.append({
        "key": "level_strength",
        "label": f"Сила рівня ({level['timeframe']})",
        "passed": level_strength_ok,
        "detail": f"{level['strength']} (поріг {min_strength}), дотиків: {level['touches']}, "
                  f"хибних пробоїв: {level['false_breakouts']}",
    })

    # 2. Імпульс
    items.append({
        "key": "impulse",
        "label": "Імпульс",
        "passed": impulse["confirmed"],
        "detail": f"{impulse['ratio']:.1f}x ATR(5хв) (поріг {config.IMPULSE_ATR_MULTIPLIER:.1f}x)",
    })

    # 3. Обсяг
    items.append({
        "key": "volume",
        "label": "Обсяг",
        "passed": volume_confirmed,
        "detail": "підтверджує рух" if volume_confirmed else "не підтверджує",
    })

    # 4. Тренд 1D
    if with_trend is None:
        trend_passed = False
        trend_detail = f"{trend['label']} (нейтрально)"
    else:
        trend_passed = with_trend
        trend_detail = f"{trend['label']} ({'за трендом' if with_trend else 'проти тренду'})"
    items.append({"key": "trend", "label": "Тренд (1D)", "passed": trend_passed, "detail": trend_detail})

    # 5. Денний ATR не вичерпаний (або виняток - локальний екстремум)
    consumed_pct = indicators.daily_atr_consumed_pct(df_daily, current_price, daily_atr)
    at_extreme = indicators.is_local_extreme(df_daily, direction)
    atr_room_ok = consumed_pct < config.DAILY_ATR_CONSUMED_WARNING_PCT or at_extreme
    detail_5 = f"пройдено {consumed_pct:.0f}% денного ATR"
    if at_extreme:
        detail_5 += " (новий локальний екстремум — виняток застосовано)"
    items.append({"key": "daily_atr_room", "label": "Запас денного ATR", "passed": atr_room_ok, "detail": detail_5})

    # 6. Технічний ATR (рівень не затиснутий)
    nearest_other = levels_module.find_nearest_level_any_side(current_price, all_levels, exclude_price=level["price"])
    technical_ok = indicators.technical_atr_ok(nearest_other, current_price, daily_atr)
    if nearest_other:
        detail_6 = f"найближчий інший рівень на {abs(nearest_other['price'] - current_price):.4f}"
    else:
        detail_6 = "інших рівнів поруч не знайдено"
    items.append({"key": "technical_atr", "label": "Технічний ATR", "passed": technical_ok, "detail": detail_6})

    # 7. Запас ходу до протилежного рівня >= MIN_STOPS
    opposite_level = levels_module.find_nearest_opposite_level(current_price, all_levels, direction)
    stop_size = atr_5m
    stops_in_room = indicators.room_to_opposite_level_in_stops(opposite_level, current_price, stop_size)
    if stops_in_room is None:
        room_ok = True  # немає протилежного рівня - простір необмежений технічно
        detail_7 = "протилежного рівня не знайдено (простір не обмежений)"
    else:
        room_ok = stops_in_room >= config.MIN_STOPS_IN_ROOM_TO_OPPOSITE_LEVEL
        detail_7 = f"{stops_in_room:.1f} стопів до {opposite_level['price']:.4f} " \
                   f"(поріг {config.MIN_STOPS_IN_ROOM_TO_OPPOSITE_LEVEL})"
    items.append({"key": "room_to_opposite", "label": "Запас ходу до рівня", "passed": room_ok, "detail": detail_7})

    # 8. Підтвердження зі старшого/іншого ТФ
    confirmed_cross_tf, confirming_tfs = multi_tf_levels.has_cross_tf_confirmation(level, all_levels)
    detail_8 = f"підтверджено на: {', '.join(confirming_tfs)}" if confirmed_cross_tf else "не знайдено на інших ТФ"
    items.append({"key": "cross_tf", "label": "Підтвердження з іншого ТФ", "passed": confirmed_cross_tf, "detail": detail_8})

    passed_count = sum(1 for item in items if item["passed"])

    return {"items": items, "passed_count": passed_count, "total": len(items)}

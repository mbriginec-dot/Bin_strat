"""
Формування текстів повідомлень та надсилання в Telegram.

Два типи:
1. Радар — ЧИСТО ІНФОРМАЦІЙНИЙ (без точки входу/стопу/тейку). Мета: дати контекст
   заздалегідь, щоб встигнути підготуватись і слідкувати за графіком самостійно.
2. Підтверджений сигнал — єдине повідомлення, за яким приймається рішення про вхід.
   Містить точку входу/стоп/тейк і повний чекліст підтверджень з книги (X/8).
"""
import requests
import datetime
import config
import levels as levels_module

PATTERN_NAMES = {
    "breakout": "ПРОБІЙ",
    "rejection": "ВІДБІЙ",
    "false_breakout": "ХИБНИЙ ПРОБІЙ",
}

DIRECTION_NAMES = {
    "long": "LONG",
    "short": "SHORT",
}


def _now_str() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")


def format_radar_message(exchange_id: str, symbol: str, current_price: float, level: dict,
                          side: str, dist_pct: float, rsi: float, price_change_24h: float,
                          day_volume: float, daily_atr: float, atr_consumed_pct: float) -> str:
    """Інформаційне повідомлення при наближенні до рівня. Без точки входу/стопу/тейку."""
    side_label = "опору" if side == "resistance" else "підтримки"
    strength_lbl = levels_module.strength_label(level["strength"])
    round_flag = "так" if level["is_round"] else "ні"

    return (
        f"🔎 РАДАР: {symbol} ({exchange_id})\n"
        f"🕐 {_now_str()}\n\n"
        f"Поточна ціна: {current_price:.4f}\n"
        f"Рівень ({side_label}): {level['price']:.4f} [{level['timeframe']}]\n"
        f"Відстань до рівня: {dist_pct:.2f}%\n\n"
        f"Сила рівня: {strength_lbl} ({level['strength']})\n"
        f" • Дотиків: {level['touches']}\n"
        f" • Хибних пробоїв: {level['false_breakouts']}\n"
        f" • Кругле число: {round_flag}\n\n"
        f"📈 Денний контекст:\n"
        f" • Зміна ціни за день: {price_change_24h:+.2f}%\n"
        f" • Обсяг торгів за день: {day_volume:,.0f}\n"
        f" • Пройдено денного ATR: {atr_consumed_pct:.0f}%\n"
        f" • Середній денний ATR: {daily_atr:.4f}\n\n"
        f"RSI({config.RSI_PERIOD}, {config.SIGNAL_TIMEFRAME}): {rsi:.1f}\n\n"
        f"⏳ Це інформаційне повідомлення. Слідкуй за графіком — точку входу/стоп/тейк "
        f"надішлемо окремо, коли патерн підтвердиться."
    )


def format_signal_message(exchange_id: str, symbol: str, signal: dict, rsi: float,
                           checklist: dict) -> str:
    """Підтверджений сигнал - єдине повідомлення для прийняття рішення про вхід."""
    pattern_name = PATTERN_NAMES.get(signal["pattern"], signal["pattern"])
    direction_name = DIRECTION_NAMES.get(signal["direction"], signal["direction"])
    level = signal["level"]
    strength_lbl = levels_module.strength_label(level["strength"])

    entry = signal["entry"]
    stop = signal["stop_loss"]
    take = signal["take_profit"]
    risk_pct = abs(entry - stop) / entry * 100
    reward_pct = abs(take - entry) / entry * 100
    level_role = "підтримки" if signal["direction"] == "long" else "опору"

    reasoning = {
        "breakout": "закриття свічки підтвердило пробій рівня — вихід за межі зони консолідації.",
        "rejection": "ціна протестувала рівень і не змогла його пробити, закриття підтверджує відбій.",
        "false_breakout": "ціна пробила рівень тінню, але закрилась назад — ознака пастки для трейдерів у бік пробою.",
    }.get(signal["pattern"], "")

    checklist_lines = []
    for item in checklist["items"]:
        icon = "✅" if item["passed"] else "❌"
        checklist_lines.append(f"{icon} {item['label']}: {item['detail']}")
    checklist_block = "\n".join(checklist_lines)

    return (
        f"✅ СИГНАЛ ПІДТВЕРДЖЕНО: {symbol} ({exchange_id}) — {pattern_name} ({direction_name})\n"
        f"🕐 {_now_str()}\n\n"
        f"Стиль: {pattern_name.capitalize()} від {level_role} рівня, внутрішньоденна угода\n"
        f"Рівень: {level['price']:.4f} [{level['timeframe']}] (сила: {strength_lbl} — "
        f"{level['touches']} дотиків, {level['false_breakouts']} хибних пробоїв)\n\n"
        f"📍 Точка входу: {entry:.4f} ({direction_name})\n"
        f"🛑 Стоп-лосс: {stop:.4f} (−{risk_pct:.2f}%, = ATR 5хв)\n"
        f"🎯 Тейк-профіт: {take:.4f} (+{reward_pct:.2f}%, R:R = {signal['risk_reward_ratio']:.0f}:1)\n\n"
        f"ПІДТВЕРДЖЕННЯ ДЛЯ {direction_name} ({checklist['passed_count']}/{checklist['total']}):\n"
        f"{checklist_block}\n\n"
        f"RSI({config.RSI_PERIOD}): {rsi:.1f}\n\n"
        f"Обґрунтування: {reasoning}\n\n"
        f"⚠️ Це не фінансова порада — перевір графік самостійно перед входом."
    )


def send_telegram_message(text: str) -> bool:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        print("[telegram_notifier] Токен або chat_id не налаштовані в .env.")
        return False

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": config.TELEGRAM_CHAT_ID, "text": text}

    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"[telegram_notifier] Помилка надсилання: {e}")
        return False

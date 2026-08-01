"""
Головний скрипт бота. Для кожної біржі з config.EXCHANGES і кожної її пари з pairs.json:

1. Збирає рівні з кількох таймфреймів (1D основний + 4h/2h/1h якщо сильні) — multi_tf_levels.py.
2. Тягне денні свічки -> рахує денний ATR (book_atr), % пройденого, тренд.
3. Тягне 5-хвилинні свічки -> перевіряє радар (наближення 0.5% ТІЛЬКИ до сильних
   денних (1D) рівнів, чисто інформаційний) та 3 патерни (пробій/відбій/хибний
   пробій) - strategy.py.
4. Якщо патерн підтвердився — рахує ATR(5хв) для стопу, збирає повний чекліст
   з 8 підтверджень (checklist.py), рахує вхід/стоп/тейк. Сигнал відправляється
   в Telegram, тільки якщо пройдено >= config.MIN_CHECKLIST_CONFIRMATIONS пунктів.
5. Радар шлеться окремо і раніше (0.5%), як суто інформаційне повідомлення.

Запуск разово (для GitHub Actions): python main.py
Запуск циклом (для локального тесту): python main.py --loop
"""
import sys
import time
import traceback

import config
import data_fetcher
import indicators
import levels as levels_module
import multi_tf_levels
import strategy
import checklist as checklist_module
import book_atr
import state as state_module
import telegram_notifier


def process_pair(exchange, exchange_id: str, symbol: str, bot_state: dict):
    scope = f"{exchange_id}:{symbol}"
    print(f"\n--- {scope} ---")

    # --- Мультитаймфреймові рівні ---
    all_levels = multi_tf_levels.gather_multi_tf_levels(exchange, exchange_id, symbol)
    print(f"Знайдено рівнів (усі ТФ): {len(all_levels)}")
    if not all_levels:
        return

    # --- Денний контекст: ATR, тренд, % пройдено ---
    df_daily = data_fetcher.fetch_ohlcv(exchange, symbol, config.PRIMARY_LEVEL_TIMEFRAME, config.LEVEL_CANDLES_LIMIT)
    trend = indicators.detect_trend(df_daily)
    daily_atr = indicators.calculate_daily_atr(df_daily)

    # --- 5-хвилинний графік для точки входу ---
    df_signal = data_fetcher.fetch_ohlcv(exchange, symbol, config.SIGNAL_TIMEFRAME, config.SIGNAL_CANDLES_LIMIT)
    df_signal = indicators.add_rsi(df_signal)
    ticker = data_fetcher.fetch_ticker(exchange, symbol)

    current_price = df_signal["close"].iloc[-1]
    rsi = df_signal["rsi"].iloc[-1]
    price_change_24h = indicators.price_change_24h_pct(ticker)
    day_volume = ticker.get("quoteVolume") or 0.0
    atr_consumed_pct = indicators.daily_atr_consumed_pct(df_daily, current_price, daily_atr)

    completed_signal = df_signal.iloc[:-1] if len(df_signal) > 1 else df_signal
    atr_5m = book_atr.calculate_book_atr(completed_signal)

    for level in all_levels:
        state_module.update_state_for_level(bot_state, scope, level["price"], current_price)

    # --- 1. Радар (інформаційний, 0.5%) — тільки по сильних ДЕННИХ рівнях ---
    daily_levels = [lvl for lvl in all_levels if lvl["timeframe"] == config.PRIMARY_LEVEL_TIMEFRAME]
    radar_candidates = strategy.find_radar_candidates(current_price, daily_levels)
    for candidate in radar_candidates:
        level = candidate["level"]
        if state_module.should_send_radar_alert(bot_state, scope, level["price"]):
            print(f"РАДАР: наближення до рівня {level['price']} [{level['timeframe']}] "
                  f"({candidate['distance_pct']:.2f}%)")
            msg = telegram_notifier.format_radar_message(
                exchange_id, symbol, current_price, level, candidate["side"],
                candidate["distance_pct"], rsi, price_change_24h,
                day_volume, daily_atr, atr_consumed_pct
            )
            sent = telegram_notifier.send_telegram_message(msg)
            if sent:
                state_module.mark_radar_alert_sent(bot_state, scope, level["price"])

    # --- 2. Підтверджені сигнали (3 патерни) по кожному рівню + повний чекліст ---
    for level in all_levels:
        signal = strategy.check_all_patterns(df_signal, level)
        if not signal:
            continue

        risk_levels = strategy.calculate_risk_levels(
            signal["entry"], level["price"], signal["direction"], atr_5m
        )
        signal.update(risk_levels)

        impulse = indicators.calculate_impulse(df_signal, signal["direction"])
        volume_change_pct = indicators.volume_vs_average_pct(df_signal)
        volume_confirmed = indicators.is_volume_confirmed(volume_change_pct)
        with_trend = indicators.is_signal_with_trend(signal["direction"], trend)

        signal_checklist = checklist_module.build_checklist(
            level=level,
            direction=signal["direction"],
            current_price=current_price,
            all_levels=all_levels,
            df_daily=df_daily,
            df_signal=df_signal,
            impulse=impulse,
            volume_confirmed=volume_confirmed,
            trend=trend,
            with_trend=with_trend,
            daily_atr=daily_atr,
            atr_5m=atr_5m,
        )

        print(f"СИГНАЛ: {signal['pattern']} / {signal['direction']} на рівні {level['price']} "
              f"[{level['timeframe']}] — {signal_checklist['passed_count']}/{signal_checklist['total']}")

        if signal_checklist["passed_count"] < config.MIN_CHECKLIST_CONFIRMATIONS:
            print(f"  -> пропущено: менше {config.MIN_CHECKLIST_CONFIRMATIONS} підтверджень з чекліста")
            continue

        msg = telegram_notifier.format_signal_message(exchange_id, symbol, signal, rsi, signal_checklist)
        telegram_notifier.send_telegram_message(msg)


def run_scan():
    pairs_by_exchange = config.load_pairs()
    bot_state = state_module.load_state()

    for exchange_id in config.EXCHANGES:
        symbols = pairs_by_exchange.get(exchange_id, [])
        print(f"\n=== Біржа: {exchange_id} ({len(symbols)} пар) ===")
        exchange = data_fetcher.get_exchange(exchange_id)

        for symbol in symbols:
            try:
                process_pair(exchange, exchange_id, symbol, bot_state)
            except Exception as e:
                print(f"[{exchange_id}:{symbol}] Помилка: {e}")
                traceback.print_exc()

    state_module.save_state(bot_state)
    print("\nСканування завершено. Стан збережено.")


def main():
    if "--loop" in sys.argv:
        print("Запуск у циклі (Ctrl+C для зупинки)...")
        while True:
            run_scan()
            print(f"Очікування {config.CHECK_INTERVAL_SECONDS} сек...\n")
            time.sleep(config.CHECK_INTERVAL_SECONDS)
    else:
        run_scan()


if __name__ == "__main__":
    main()

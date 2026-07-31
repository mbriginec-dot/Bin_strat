"""
Оновлює pairs.json списком топ-N активів (за замовчуванням 20) за СУМАРНИМ обсягом
торгів по всіх валютах котирування з config.QUOTE_CURRENCIES (USDT+USDC+USD разом) —
це дає точнішу картину реальної ліквідності активу, ніж рахувати лише одну пару
котирування.

Запуск вручну, коли захочеш освіжити список:
    python update_pairs.py

Це НЕ запускається автоматично при кожному скані — pairs.json є "джерелом правди",
яке ти контролюєш сам.
"""
import json
import config
import data_fetcher


def get_top_assets_by_combined_volume(exchange_id: str, top_n: int = None) -> list[str]:
    """
    Для заданої біржі: рахує сумарний обсяг торгів по кожному базовому активу
    (додаючи обсяги з усіх пар цього активу з валютами із QUOTE_CURRENCIES),
    повертає топ-N пар у форматі 'BASE/QUOTE' — обирається найліквідніша
    з наявних валют котирування для кожного активу (пріоритет: порядок у QUOTE_CURRENCIES).
    """
    top_n = top_n or config.TOP_N_PAIRS
    exchange = data_fetcher.get_exchange(exchange_id)

    markets = exchange.load_markets()
    tickers = exchange.fetch_tickers()

    # base_asset -> {"total_volume": float, "best_pair": str, "best_pair_volume": float}
    asset_data = {}

    for symbol, market in markets.items():
        if not market.get("active", True) or market.get("type") != "spot":
            continue
        base = market.get("base")
        quote = market.get("quote")
        if quote not in config.QUOTE_CURRENCIES:
            continue

        ticker = tickers.get(symbol)
        if not ticker or ticker.get("quoteVolume") is None:
            continue

        volume = ticker["quoteVolume"]
        entry = asset_data.setdefault(base, {"total_volume": 0.0, "best_pair": None, "best_pair_volume": -1})
        entry["total_volume"] += volume

        # Як пару для сканування обираємо ту, де в цього активу найбільший обсяг
        if volume > entry["best_pair_volume"]:
            entry["best_pair_volume"] = volume
            entry["best_pair"] = symbol

    ranked = sorted(asset_data.items(), key=lambda x: x[1]["total_volume"], reverse=True)
    return [data["best_pair"] for _, data in ranked[:top_n] if data["best_pair"]]


def main():
    result = {
        "_comment": "Пари для сканування, окремо по кожній біржі. Формат: 'BASE/QUOTE', "
                    "наприклад 'BTC/USDT'. Можна вручну додавати/видаляти пари або цілі біржі "
                    "(назва біржі має бути в config.EXCHANGES). Щоб перегенерувати топ-20 за "
                    "сумарним обсягом (USDT+USDC+USD), запусти: python update_pairs.py",
    }

    for exchange_id in config.EXCHANGES:
        print(f"\nОбробка біржі: {exchange_id}...")
        top_pairs = get_top_assets_by_combined_volume(exchange_id)
        result[exchange_id] = top_pairs
        print(f"Знайдено {len(top_pairs)} пар:")
        for p in top_pairs:
            print(f"  - {p}")

    with open(config.PAIRS_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n{config.PAIRS_FILE} оновлено.")


if __name__ == "__main__":
    main()

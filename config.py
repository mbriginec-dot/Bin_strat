"""
Центральна конфігурація бота. Параметри стратегії та роботи міняй тут.
"""
import os
import json
from dotenv import load_dotenv

load_dotenv()

# --- API ключі (з .env) ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- Біржі ---
# Активна зараз Bybit (Binance блокує дата-центри GitHub Actions - HTTP 451,
# обмеження за геолокацією сервера). Щоб додати ще одну біржу — впиши її сюди
# і додай для неї список пар у pairs.json. Решта коду вже мультибіржова.
EXCHANGES = ["bybit"]

# Додаткові параметри ccxt для конкретних бірж (наприклад щоб гарантовано
# отримувати спотовий, а не ф'ючерсний/перпетуальний ринок).
EXCHANGE_OPTIONS = {
    "bybit": {"options": {"defaultType": "spot"}},
}

# --- Ринок ---
QUOTE_CURRENCIES = ["USDT", "USDC", "USD"]
PAIRS_FILE = "pairs.json"
TOP_N_PAIRS = 60

# --- Таймфрейми рівнів ---
# "1d" — основний, завжди враховується (мінімум дотиків, без підвищеного порогу сили).
# Інші — додаткові: враховуються ТІЛЬКИ якщо рівень на них "сильний" (поріг вище за денний,
# бо на молодших ТФ природньо більше шумових дотиків).
PRIMARY_LEVEL_TIMEFRAME = "1d"
EXTRA_LEVEL_TIMEFRAMES = ["4h", "2h", "1h"]
LEVEL_CANDLES_LIMIT = 200

# Поріг сили рівня для радару/сигналу — окремо для денного і для додаткових ТФ
MIN_LEVEL_STRENGTH = {
    "1d": 3,
    "4h": 5,
    "2h": 6,
    "1h": 7,
}

# --- Точка входу шукаємо на 5-хвилинному ТФ ---
SIGNAL_TIMEFRAME = "5m"
SIGNAL_CANDLES_LIMIT = 200

# --- Пошук рівнів (методологія книги) ---
MIN_TOUCHES_FOR_LEVEL = 2
LEVEL_CLUSTER_TOLERANCE_PCT = 0.3
PARABOLIC_CANDLE_MULTIPLIER = 2.0
ROUND_NUMBER_STRENGTH_BONUS = 1
TOUCH_STRENGTH_WEIGHT = 1
FALSE_BREAKOUT_STRENGTH_BONUS = 2

# Толерантність, у межах якої рівні з різних ТФ вважаються "тим самим рівнем"
# (для пункту чекліста "підтверджено зі старшого ТФ")
CROSS_TF_LEVEL_TOLERANCE_PCT = 0.3

# --- Радар (завчасне інформаційне попередження, БЕЗ точок входу/стопу/тейку) ---
RADAR_DISTANCE_PCT = 0.5
RETEST_MOVE_AWAY_PCT = 2.0

# --- Ризик-менеджмент (книга: мінімум 3:1) ---
MIN_RISK_REWARD_RATIO = 3.0

# --- ATR за методикою книги ---
# Береться середнє (high-low) за ATR_LOOKBACK_BARS барів, ВИКЛЮЧАючи "паранормальні"
# бари (>= PARANORMAL_MAX_MULTIPLIER x ATR або <= PARANORMAL_MIN_FRACTION x ATR) —
# такі бари замінюються сусідніми нормальними.
ATR_LOOKBACK_BARS = 5
PARANORMAL_MAX_MULTIPLIER = 2.0
PARANORMAL_MIN_FRACTION = 1.0 / 3.0
ATR_BASELINE_WINDOW = 20  # ширше вікно для попередньої оцінки "норми" при відборі паранормальних барів

# --- Імпульс (книга: підтверджуючий рух 2-3x ATR) ---
IMPULSE_LOOKBACK_CANDLES = 3
IMPULSE_ATR_MULTIPLIER = 2.0

# --- Обсяг як підтвердження ---
VOLUME_CONFIRMATION_THRESHOLD_PCT = 20

# --- Контекст тренду (старший ТФ) ---
TREND_EMA_FAST = 50
TREND_EMA_SLOW = 200

# --- Запас ходу (книга: розділ "Волатильність і запас ходу (ATR)") ---
DAILY_ATR_CONSUMED_WARNING_PCT = 75  # від цього % пройденого денного ATR - попередження/контр-тренд
MIN_STOPS_IN_ROOM_TO_OPPOSITE_LEVEL = 4  # мінімум стопів має вміщувати запас ходу до протилежного рівня
LOCAL_EXTREME_LOOKBACK_BARS = 20  # вікно для перевірки "новий локальний екстремум" (виняток з правила ATR)

# --- Індикатори для контексту ---
RSI_PERIOD = 14

# --- Стан бота ---
STATE_FILE = "state.json"

# --- Частота (для локального запуску циклом) ---
CHECK_INTERVAL_SECONDS = 300


def load_pairs() -> dict[str, list[str]]:
    """Читає список пар з pairs.json (окремо по кожній біржі)."""
    with open(PAIRS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}

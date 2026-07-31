"""
ATR за методикою з книги (розділ "Волатильність і запас ходу (ATR)"):
- Розмір бару = high - low (не open/close).
- Береться середнє за ATR_LOOKBACK_BARS (3-5) попередніх ЗАВЕРШЕНИХ барів
  (поточний, ще не закритий бар в розрахунок не йде).
- "Паранормальні" бари — ті, що >= 2x ATR або <= 1/3 ATR — виключаються і
  замінюються сусідніми нормальними барами.

Оскільки визначення "паранормальний" саме через ATR є циклічним (потрібен ATR, щоб
визначити паранормальність, і навпаки), тут для базової оцінки норми використовується
ширше вікно (ATR_BASELINE_WINDOW) як орієнтир, а потім з останніх барів відбираються
ATR_LOOKBACK_BARS нормальних (пропускаючи й замінюючи паранормальні сусідніми
старшими барами).
"""
import pandas as pd
import config


def _bar_ranges(df: pd.DataFrame) -> pd.Series:
    return df["high"] - df["low"]


def calculate_book_atr(df: pd.DataFrame, lookback_bars: int = None) -> float:
    """
    Рахує ATR за методикою книги на завершених барах df (останній рядок df
    вважається завершеним — виклик має сам подбати, щоб не передавати поточний
    незакритий бар, або прибрати його заздалегідь через df.iloc[:-1]).
    """
    lookback_bars = lookback_bars or config.ATR_LOOKBACK_BARS

    if len(df) < config.ATR_BASELINE_WINDOW:
        # Замало даних для повної методики — просте середнє за наявні бари
        ranges = _bar_ranges(df).tail(lookback_bars)
        return float(ranges.mean()) if len(ranges) else 0.0

    baseline_ranges = _bar_ranges(df).tail(config.ATR_BASELINE_WINDOW)
    baseline_atr = float(baseline_ranges.mean())

    if baseline_atr == 0:
        return 0.0

    max_normal = baseline_atr * config.PARANORMAL_MAX_MULTIPLIER
    min_normal = baseline_atr * config.PARANORMAL_MIN_FRACTION

    all_ranges = _bar_ranges(df)
    normal_ranges = all_ranges[(all_ranges < max_normal) & (all_ranges > min_normal)]

    selected = normal_ranges.tail(lookback_bars)

    if len(selected) < lookback_bars:
        # Якщо нормальних барів не вистачає (рідкісний випадок суцільної волатильності),
        # добираємо з усіх барів без фільтра, щоб не лишитись без значення.
        selected = all_ranges.tail(lookback_bars)

    return float(selected.mean()) if len(selected) else 0.0


def is_paranormal_bar(bar_range: float, baseline_atr: float) -> bool:
    if baseline_atr == 0:
        return False
    return bar_range >= baseline_atr * config.PARANORMAL_MAX_MULTIPLIER or \
        bar_range <= baseline_atr * config.PARANORMAL_MIN_FRACTION

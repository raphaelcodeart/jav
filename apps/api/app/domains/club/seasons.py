"""Stagioni ed età, come le conta il judo.

La stagione va dal 1° settembre al 31 agosto e si chiama con l'anno in cui
comincia (la stagione 2026 è settembre 2026 – agosto 2027). L'età che decide
il piano è quella **al 1° settembre**: un bambino non cambia piano a metà
anno perché compie gli anni a febbraio.
"""

from datetime import date

MONTH_NAMES = (
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
)


def season_of(day: date) -> int:
    return day.year if day.month >= 9 else day.year - 1


def season_start(season: int) -> date:
    return date(season, 9, 1)


def season_end(season: int) -> date:
    return date(season + 1, 8, 31)


def season_label(season: int) -> str:
    return f"{season}/{season + 1}"


def age_on(birth_date: date, day: date) -> int:
    return day.year - birth_date.year - ((day.month, day.day) < (birth_date.month, birth_date.day))


def season_age(birth_date: date, season: int) -> int:
    """L'età con cui l'atleta conta per tutta la stagione."""
    return age_on(birth_date, season_start(season))


def parse_period(period: str) -> tuple[int, int]:
    """`YYYY-MM` -> (anno, mese). Solleva ValueError se non è un mese."""
    year_s, month_s = period.split("-")
    year, month = int(year_s), int(month_s)
    if not (1 <= month <= 12) or not (2000 <= year <= 2100):
        raise ValueError(period)
    return year, month


def period_of(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def month_label(year: int, month: int) -> str:
    return f"{MONTH_NAMES[month - 1]} {year}"

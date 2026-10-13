"""The Italian codice fiscale, checked against the person it belongs to.

Session 89: the pratica's data form asks date and place of birth next to
the fiscal code, so that the code can be checked against name, surname,
birth date and birthplace instead of trusted as typed. The rules (letters
of surname and name, year/month/day with +40 for women, Belfiore code of
the comune or foreign state, control character, omocodia) come from
`python-codicefiscale`, which also carries the list of comuni -- the
suppressed ones too, since someone born in 1950 in a comune merged in 2014
still has its old code -- and of foreign states.

Sex is not asked: the day of birth is accepted as it is or +40.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from functools import lru_cache

from codicefiscale import codicefiscale as cf
from codicefiscale.data import get_countries_data, get_municipalities_data

_SYNTAX = re.compile(
    r"^[A-Z]{6}[0-9LMNPQRSTUV]{2}[ABCDEHLMPRST][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z]$"
)
_MONTHS = "ABCDEHLMPRST"
#: Omocodia: a digit replaced by a letter when two people share a code.
_OMOCODIA = str.maketrans("LMNPQRSTUV", "0123456789")


def normalize(code: str | None) -> str:
    return re.sub(r"\s+", "", code or "").upper()


def _fold(text: str) -> str:
    """Lowercase, no accents, no punctuation: what a search compares."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", plain.lower()).strip()


@lru_cache(maxsize=1)
def _places() -> tuple[dict, ...]:
    out: list[dict] = []
    for m in get_municipalities_data():
        out.append(
            {
                "code": m["code"],
                "name": m["name"],
                "province": m["province"],
                "foreign": False,
                "active": bool(m["active"]),
                "until": (m.get("date_deleted") or "")[:4] or None,
                "_fold": _fold(m["name"]),
            }
        )
    for c in get_countries_data():
        if not c.get("code"):
            continue
        out.append(
            {
                "code": c["code"],
                "name": c["name"],
                "province": "EE",
                "foreign": True,
                "active": bool(c.get("active", True)),
                "until": (c.get("date_deleted") or "")[:4] or None,
                "_fold": _fold(c["name"]),
            }
        )
    return tuple(out)


@lru_cache(maxsize=1)
def _by_code() -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = {}
    for place in _places():
        index.setdefault(place["code"], []).append(place)
    return index


def _public(place: dict) -> dict:
    return {k: v for k, v in place.items() if not k.startswith("_")}


def search_birthplaces(query: str, *, limit: int = 20) -> list[dict]:
    """Comuni (current first, then suppressed) and foreign states whose name
    starts with -- or, failing that, contains -- what was typed."""
    q = _fold(query)
    if len(q) < 2:
        return []
    starts = [p for p in _places() if p["_fold"].startswith(q)]
    contains = [p for p in _places() if q in p["_fold"] and not p["_fold"].startswith(q)]

    def rank(p: dict) -> tuple:
        return (p["_fold"] != q, not p["active"], p["foreign"], len(p["_fold"]), p["name"])

    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for place in sorted(starts, key=rank) + sorted(contains, key=rank):
        key = (place["code"], place["name"])
        if key in seen:
            continue
        seen.add(key)
        out.append(_public(place))
        if len(out) >= limit:
            break
    return out


def birthplace(code: str | None) -> dict | None:
    places = _by_code().get((code or "").upper())
    if not places:
        return None
    return _public(min(places, key=lambda p: not p["active"]))


def birthplace_label(place: dict) -> str:
    return f"{place['name']} ({'estero' if place['foreign'] else place['province']})"


def check(
    code: str | None,
    *,
    first_name: str,
    last_name: str,
    birth_date: date | None,
    birthplace_code: str | None,
) -> list[str]:
    """What does not match, in words for the person filling the form; an
    empty list means the code is right for this person."""
    value = normalize(code)
    if len(value) != 16:
        return ["il codice fiscale ha 16 caratteri"]
    if not _SYNTAX.match(value):
        return [
            "il codice fiscale non è scritto nel formato giusto (6 lettere, 2 cifre, 1 lettera, 2 cifre, 1 lettera, 3 cifre, 1 lettera)"
        ]
    if cf.encode_cin(value) != value[15]:
        return [
            "il codice fiscale non è valido: l'ultimo carattere (di controllo) non torna, controlla di averlo copiato bene"
        ]

    problems: list[str] = []
    if cf.encode_lastname(last_name) != value[0:3]:
        problems.append("il cognome non corrisponde al codice fiscale")
    if cf.encode_firstname(first_name) != value[3:6]:
        problems.append("il nome non corrisponde al codice fiscale")
    if birth_date is not None:
        year = int(value[6:8].translate(_OMOCODIA))
        month = _MONTHS.index(value[8]) + 1
        day = int(value[9:11].translate(_OMOCODIA))
        day = day - 40 if day > 40 else day
        if (year, month, day) != (birth_date.year % 100, birth_date.month, birth_date.day):
            problems.append("la data di nascita non corrisponde al codice fiscale")
    if birthplace_code:
        in_code = value[11] + value[12:15].translate(_OMOCODIA)
        if in_code != birthplace_code.upper():
            # The same place may appear with more than one code over time
            # (a comune that changed province): compare the names too.
            chosen = {p["_fold"] for p in _by_code().get(birthplace_code.upper(), [])}
            coded = {p["_fold"] for p in _by_code().get(in_code, [])}
            if not chosen & coded:
                problems.append("il luogo di nascita non corrisponde al codice fiscale")
    return problems

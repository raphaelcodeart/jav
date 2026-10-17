"""Il motore del combattimento (docs/games.md, «Combattimenti»): puro, senza
database, lo stato è un dict JSON che si salva in `game.fights.state`.

Un incontro è una serie di scambi. In ognuno il motore sceglie una
situazione (fight_content.py: lui attacca, hai l'iniziativa, lotta di presa,
a terra) e il judoca risponde con una delle opzioni; nel modo «simulato»
risponde il judoca da solo, con più probabilità di scegliere bene quanto più
ha tecnica e testa. L'esito lo decidono tre cose insieme:

- quanto è giusta la risposta (`q`);
- la differenza di forza tra i due in quel momento (`power`: tecnica,
  forza, testa, il fiato che resta e la salute: un infortunato vale meno);
- il caso.

Regole (IJF 2025, semplificate): 4 minuti; ippon, o due waza-ari, finiscono
l'incontro; gli yuko non si sommano; tre shido = hansoku-make. A punteggio
pari si va al golden score, dove vince il primo che segna; se dopo 3 minuti
di golden score non segna nessuno decide il gioco (meno shido, poi più fiato).
"""

import math
import random

from app.game import fight_content as fc

REGULATION = 240
GOLDEN_MAX = 180
MAX_EXCHANGES = 40
#: Secondi per rispondere nel passo a passo (più qualche secondo di rete).
STEP_SECONDS = 20
STEP_GRACE = 6

QUALITY_NAME = {3: "BEST", 2: "GOOD", 1: "RISKY", 0: "BAD"}
#: A parità di forza e di scelte, quanto spesso riesce la risposta: un
#: attacco riesce meno spesso di una difesa, così chi attacca e chi difende
#: hanno le stesse possibilità di segnare.
KIND_BASE = {"DEF": 0.6, "ATT": 0.37, "GRIP": 0.5, "NW_TOP": 0.45, "NW_BOT": 0.55}
#: Quanto pesa un punto di qualità della risposta rispetto a quella che
#: avrebbe giocato l'avversario.
QUALITY_WEIGHT = 0.9
#: Quanti punti di forza valgono un «logit» di vantaggio in ogni scambio:
#: il più forte vince più spesso, ma non sempre.
POWER_SCALE = 26


def clamp(v: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, v))


def fighter(name: str, belt: str, *, tec: float, str_: float, men: float, sta: float = 100, hp: float = 100,
            club: str | None = None) -> dict:
    """Un judoca per il motore: le statistiche tra 0 e 100."""
    def num(v: float) -> int:
        try:
            return int(clamp(float(v)))
        except (TypeError, ValueError):
            return 0
    return {"name": name, "belt": belt, "club": club, "tec": num(tec), "str": num(str_), "men": num(men),
            "sta": num(sta), "hp": num(hp)}


def power(f: dict, sta: float) -> float:
    """Come heroPower del motore della carriera, più la salute."""
    base = 0.45 * f["tec"] + 0.3 * f["str"] + 0.25 * f["men"]
    return base * (0.65 + 0.35 * clamp(sta) / 100) * (0.6 + 0.4 * clamp(f["hp"]) / 100)


def _empty_score() -> dict:
    return {"ippon": 0, "waza": 0, "yuko": 0, "shido": 0}


def new_state(me: dict, opp: dict, rng: random.Random) -> dict:
    state = {
        "me": me, "opp": opp, "clock": 0, "golden": False, "seq": 0,
        "score": {"me": _empty_score(), "opp": _empty_score()},
        "sta": {"me": me["sta"], "opp": opp["sta"]},
        "next": None, "current": None, "history": [],
        "over": False, "winner": None, "reason": None,
    }
    _ask(state, rng)
    return state


def _ask(state: dict, rng: random.Random) -> None:
    """Prepara lo scambio seguente: la situazione e l'ordine delle opzioni."""
    forced = state.pop("next", None)
    if forced in ("NW_TOP", "NW_BOT", "ATT", "DEF"):
        kind = forced
    else:
        p_me = power(state["me"], state["sta"]["me"])
        p_opp = power(state["opp"], state["sta"]["opp"])
        # chi è più forte ha più spesso l'iniziativa
        p_def = clamp(0.45 + (p_opp - p_me) / 120, 0.25, 0.7)
        r = rng.random()
        kind = "DEF" if r < p_def else "GRIP" if r < p_def + 0.18 else "ATT"
    pool = fc.BY_KIND[kind]
    last = state["history"][-1]["situation"] if state["history"] else None
    choices = [s for s in pool if s.id != last] or pool
    sit = rng.choice(choices)
    order = [o.id for o in sit.options]
    rng.shuffle(order)
    state["seq"] += 1
    state["current"] = {"seq": state["seq"], "situation": sit.id, "options": order}


def _option(sit: fc.Situation, option_id: str | None) -> fc.Option:
    if option_id is None:
        return fc.HESITATE[sit.kind]
    for o in sit.options:
        if o.id == option_id:
            return o
    raise ValueError("opzione non valida")


def valid_option(state: dict, option_id: str) -> bool:
    cur = state.get("current")
    return bool(cur) and option_id in cur["options"]


def _grade(code: str, edge: float, rng: random.Random) -> str:
    """Un esito «grande» non sempre arriva intero: un ippon può restare
    waza-ari o yuko, secondo il caso e il vantaggio di chi segna."""
    r = rng.random()
    if code == "IPPON":
        return "IPPON" if r < 0.42 + edge else "WAZA" if r < 0.82 else "YUKO"
    if code == "WAZA":
        return "WAZA" if r < 0.58 + edge else "YUKO"
    return code


def _score_key(s: dict) -> tuple[int, int, int]:
    return (s["ippon"], s["waza"], s["yuko"])


def _finish(state: dict, winner: str, reason: str) -> None:
    state.update(over=True, winner=winner, reason=reason, current=None)


def resolve(state: dict, option_id: str | None, rng: random.Random) -> dict:
    """Risolve lo scambio in corso con la risposta data (None = nessuna
    risposta in tempo) e prepara il seguente. Restituisce lo scambio."""
    cur = state["current"]
    if state["over"] or not cur:
        raise ValueError("incontro finito")
    if option_id is not None and option_id not in cur["options"]:
        raise ValueError("opzione non valida")
    sit = fc.BY_ID[cur["situation"]]
    opt = _option(sit, option_id)
    me, opp = state["me"], state["opp"]
    p_me, p_opp = power(me, state["sta"]["me"]), power(opp, state["sta"]["opp"])
    diff = p_me - p_opp
    base = KIND_BASE[sit.kind]
    # l'avversario non sceglie a voce, ma gioca anche lui: bene quanto più ha tecnica e testa
    logit = math.log(base / (1 - base)) + QUALITY_WEIGHT * (opt.q - _expected_q(sit, opp)) + diff / POWER_SCALE
    chance = 1 / (1 + math.exp(-logit))
    success = rng.random() < chance
    edge = clamp(diff / 100, -0.2, 0.2)
    code = _grade(opt.ok, edge, rng) if success else opt.ko
    if not success and code in ("OPP_IPPON", "OPP_WAZA"):
        code = "OPP_" + _grade(code[4:], -edge, rng)

    by, points, tech = None, None, None
    sc = state["score"]
    if code in ("IPPON", "WAZA", "YUKO"):
        by, points, tech = "me", code, opt.tech
    elif code in ("OPP_IPPON", "OPP_WAZA", "OPP_YUKO"):
        by, points = "opp", code[4:]
        tech = opt.opp_tech or sit.tech or "Ura-nage"
    elif code == "SHIDO_OPP":
        by, points = "opp", "SHIDO"
    elif code == "SHIDO_ME":
        by, points = "me", "SHIDO"
    if points in ("IPPON", "WAZA", "YUKO"):
        sc[by][{"IPPON": "ippon", "WAZA": "waza", "YUKO": "yuko"}[points]] += 1
    elif points == "SHIDO":
        sc[by]["shido"] += 1

    # il fiato: ogni scambio stanca, di più chi ha meno forza e chi rischia
    for side, f, risky in (("me", me, opt.q <= 1), ("opp", opp, False)):
        loss = 6 - f["str"] / 30 + (2 if risky else 0)
        state["sta"][side] = int(clamp(state["sta"][side] - max(2, loss)))
    seconds = 20 if sit.kind in ("NW_TOP", "NW_BOT") else rng.randint(14, 32)
    state["clock"] += seconds

    exchange = {
        "seq": cur["seq"], "situation": sit.id, "kind": sit.kind, "choice": opt.id, "quality": QUALITY_NAME[opt.q],
        "success": success, "outcome": code, "by": by, "points": points, "tech": tech, "clock": state["clock"],
    }
    state["history"].append(exchange)
    state["current"] = None

    # come va a finire
    other = {"me": "opp", "opp": "me"}
    if points == "IPPON":
        _finish(state, by, "IPPON")
    elif points == "WAZA" and sc[by]["waza"] >= 2:
        _finish(state, by, "AWASETE")
    elif points == "SHIDO" and sc[by]["shido"] >= 3:
        _finish(state, other[by], "HANSOKU")
    elif state["golden"] and points in ("WAZA", "YUKO"):
        _finish(state, by, "GOLDEN")
    elif not state["golden"] and state["clock"] >= REGULATION:
        a, b = _score_key(sc["me"]), _score_key(sc["opp"])
        if a != b:
            _finish(state, "me" if a > b else "opp", "TIME")
        else:
            state["golden"] = True
    if not state["over"] and state["golden"] and state["clock"] >= REGULATION + GOLDEN_MAX:
        _decide(state, rng)
    if not state["over"] and len(state["history"]) >= MAX_EXCHANGES:
        _decide(state, rng)
    if state["over"]:
        return exchange

    # dopo una proiezione che non chiude si può continuare a terra
    if code == "NEWAZA" or (by == "me" and points in ("WAZA", "YUKO") and sit.kind != "NW_TOP" and rng.random() < 0.4):
        state["next"] = "NW_TOP"
    elif by == "opp" and points in ("WAZA", "YUKO") and sit.kind != "NW_BOT" and rng.random() < 0.4:
        state["next"] = "NW_BOT"
    elif code == "INIT":
        state["next"] = "ATT"
    elif code == "OPP_INIT":
        state["next"] = "DEF"
    _ask(state, rng)
    return exchange


def _decide(state: dict, rng: random.Random) -> None:
    sc = state["score"]
    a, b = _score_key(sc["me"]), _score_key(sc["opp"])
    if a != b:
        _finish(state, "me" if a > b else "opp", "DECISION")
    elif sc["me"]["shido"] != sc["opp"]["shido"]:
        _finish(state, "me" if sc["me"]["shido"] < sc["opp"]["shido"] else "opp", "DECISION")
    elif state["sta"]["me"] != state["sta"]["opp"]:
        _finish(state, "me" if state["sta"]["me"] > state["sta"]["opp"] else "opp", "DECISION")
    else:
        _finish(state, rng.choice(["me", "opp"]), "DECISION")


def _weights(sit: fc.Situation, f: dict) -> list[float]:
    """Più tecnica e testa ha un judoca, più spesso sceglie la risposta giusta."""
    skill = (f["tec"] + f["men"]) / 2
    return [math.exp(o.q * (0.25 + skill / 45)) for o in sit.options]


def _expected_q(sit: fc.Situation, f: dict) -> float:
    w = _weights(sit, f)
    return sum(o.q * x for o, x in zip(sit.options, w, strict=True)) / sum(w)


def auto_choice(state: dict, rng: random.Random) -> str:
    """La risposta che sceglie da solo il judoca (modo simulato)."""
    sit = fc.BY_ID[state["current"]["situation"]]
    return rng.choices([o.id for o in sit.options], weights=_weights(sit, state["me"]))[0]


def simulate(state: dict, rng: random.Random) -> dict:
    while not state["over"]:
        resolve(state, auto_choice(state, rng), rng)
    return state


def forfeit(state: dict) -> None:
    """Chi abbandona perde (kiken-gachi per l'altro)."""
    if not state["over"]:
        _finish(state, "opp", "FORFEIT")


# --- Quello che vede il browser ----------------------------------------------------------------------------

def public_exchange(ex: dict, lang: str) -> dict:
    sit = fc.BY_ID[ex["situation"]]
    opt = _option(sit, None if ex["choice"] == "late" else ex["choice"])
    return {
        "seq": ex["seq"], "kind": ex["kind"], "prompt": sit.text[lang], "attack": sit.tech if sit.kind == "DEF" else None,
        "choice": opt.label[lang], "quality": ex["quality"], "success": ex["success"], "by": ex["by"],
        "points": ex["points"], "tech": ex["tech"], "why": opt.why[lang], "clock": ex["clock"],
    }


def public_prompt(state: dict, lang: str) -> dict | None:
    cur = state.get("current")
    if not cur or state["over"]:
        return None
    sit = fc.BY_ID[cur["situation"]]
    labels = {o.id: o.label[lang] for o in sit.options}
    return {"seq": cur["seq"], "kind": sit.kind, "text": sit.text[lang], "attack": sit.tech if sit.kind == "DEF" else None,
            "options": [{"id": i, "label": labels[i]} for i in cur["options"]], "seconds": STEP_SECONDS}


def timeline(state: dict) -> list[dict]:
    """Gli scambi come eventi della scena animata della carriera
    (FightEvent di engine.ts: A sei tu, B l'avversario)."""
    side = {"me": "A", "opp": "B"}
    out: list[dict] = [{"t": "GRIP", "by": "A"}]
    for ex in state["history"]:
        if ex["points"] in ("IPPON", "WAZA", "YUKO"):
            out.append({"t": "ATTACK", "by": side[ex["by"]], "technique": ex["tech"]})
            out.append({"t": {"IPPON": "IPPON", "WAZA": "WAZA_ARI", "YUKO": "YUKO"}[ex["points"]], "by": side[ex["by"]], "technique": ex["tech"]})
        elif ex["points"] == "SHIDO":
            out.append({"t": "SHIDO", "by": side[ex["by"]]})
    return out

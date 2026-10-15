"""Carica la tabella prezzi ufficiale 2026 nei club della rete (Lagos,
Albufeira, Alvor): i tre gruppi, le quote annuali, gli sconti e l'orario
dei corsi di Lagos e di Alvor (quello di Albufeira non lo conosciamo ancora).

Passa dal service layer, come l'interfaccia della segreteria: stesse
validazioni, stesso audit (attore vuoto = il sistema), e le quote già
emesse non cambiano, perché il prezzo è congelato su ogni quota
(CLAUDE.md §5). Le regole: docs/club-portal.md, "Prezzi e sconti".

**Di default non scrive niente**: stampa che cosa farebbe. Con `--apply`
lo fa. È idempotente: rilanciato, trova tutto a posto e non cambia nulla.
Riconosce piani e corsi dal nome; un piano attivo che non è nella tabella
non si tocca (lo segnala), salvo `--deactivate-others`: due piani che
coprono la stessa età si contendono gli atleti, e vince il più stretto.

Il sorgente non è nell'immagine: si lancia dal sorgente montato, con il
`.env` del server (cioè sul database vero):

    cd /opt/webapps/jav
    docker run --rm --network jav-dev_default -v "$PWD/apps/api:/src" -w /src \\
      --env-file .env --entrypoint python jav-dev-api \\
      -m scripts.load_official_prices --club judo-clube-de-lagos            # prova
    ...  -m scripts.load_official_prices --club judo-clube-de-lagos --apply  # scrive
"""

import argparse
import asyncio
import sys
from dataclasses import dataclass
from datetime import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.club import clubs as clubs_service
from app.domains.club import courses as courses_service
from app.domains.club import pricing as pricing_rules
from app.domains.club import service as club_service
from app.domains.club.models import Club, ClubCourseSlot
from app.domains.club.scope import ClubScope
from app.domains.club.site_models import ClubSite

OFFICIAL_CLUBS = ("judo-clube-de-lagos", "judo-clube-de-albufeira", "judo-team-matias-luwawa")

#: Quote annuali 2026, a pro rata dal mese d'ingresso (pricing.prorated).
#: Sócio Judoca e Taxa de Faltas aos Treinos sono due quote dello stesso
#: atleta, nello stesso anno, con la stessa regola: nel modello sono
#: un'iscrizione annuale sola (`enrollment_fee_cents`), e il testo dice
#: che cosa comprende.
SOCIO_JUDOCA_CENTS = 6000
TAXA_FALTAS_CENTS = 6000
ENROLLMENT_CENTS = SOCIO_JUDOCA_CENTS + TAXA_FALTAS_CENTS
DUE_DAY = 15


@dataclass(frozen=True)
class Group:
    name: str
    min_age: int
    max_age: int | None
    monthly_cents: int
    #: Le aule avulse (senza mensilità, su accordo) non sono una quota che
    #: il sistema emette: si dicono nella descrizione del piano, che il bot
    #: mostra insieme ai prezzi.
    description: str


GROUPS = (
    Group("Grupo 1 · Iniciação", 2, 7, 3500, "Aula avulsa (sem mensalidade, mediante acordo): 7,50 € por aula."),
    Group("Grupo 2 · Formação", 8, 12, 6000, "Aula avulsa (sem mensalidade, mediante acordo): 12,50 € por aula."),
    Group("Grupo 3 · Competição, Manutenção e Veteranos", 13, None, 8500,
          "Aula avulsa (sem mensalidade, mediante acordo): 17,50 € por aula."),
)

PRICING = {
    "tier_discount_pct": {"A": 25, "B": 15, "C": 5},
    "family_discount_cents": 500,
    "family_min_athletes": 2,
    "referral_credit_cents": 500,
    "parent_member_fee_cents": 6000,
    "enrollment_includes": (
        "Sócio Judoca (60 €) e Taxa de Faltas aos Treinos (60 €). Inscrição na FPJ e seguro desportivo "
        "incluídos sem custo adicional. Atletas com menos de 18 anos: pelo menos um dos pais é sócio."
    ),
}

MON, TUE, WED, THU, FRI = 0, 1, 2, 3, 4


@dataclass(frozen=True)
class Course:
    """Un corso con il suo orario settimanale. La fascia d'età è ciò che
    lega il corso ai gruppi (site.plan_slots): il bot e la pagina del club
    dicono "Grupo 1: terça e quinta 18:30–19:30" perché le età si toccano."""

    name: str
    min_age: int
    max_age: int | None
    slots: tuple[tuple[int, time, time], ...]


#: I corsi, club per club. Lagos: un corso per gruppo. Alvor (calendario
#: settimanale pubblicato dal club): il Grupo 1 il martedì e il giovedì, i
#: gruppi 2 e 3 insieme lunedì, mercoledì e venerdì, dagli 8 anni in su.
#: Albufeira: nessun orario finché il club non lo dà.
COURSES: dict[str, tuple[Course, ...]] = {
    "judo-clube-de-lagos": (
        Course(GROUPS[0].name, 2, 7, tuple((d, time(18, 30), time(19, 30)) for d in (MON, WED, FRI))),
        Course(GROUPS[1].name, 8, 12, tuple((d, time(19, 0), time(20, 0)) for d in (MON, WED, FRI))),
        Course(GROUPS[2].name, 13, None, tuple((d, time(20, 0), time(21, 30)) for d in (MON, WED, FRI))),
    ),
    "judo-team-matias-luwawa": (
        Course(GROUPS[0].name, 2, 7, tuple((d, time(18, 30), time(19, 30)) for d in (TUE, THU))),
        Course("Grupos 2 e 3 · Formação e Competição", 8, None,
               tuple((d, time(19, 0), time(22, 0)) for d in (MON, WED, FRI))),
    ),
}


async def load(db: AsyncSession, slug: str, *, apply: bool, show_prices: bool = False,
               deactivate_others: bool = False) -> list[str]:
    """Allinea un club alla tabella. Restituisce le cose fatte (o da fare,
    senza `apply`): una lista vuota vuol dire che era già tutto a posto."""
    club = (await db.execute(select(Club).where(Club.slug == slug))).scalars().first()
    if club is None:
        raise SystemExit(f"Nessun club con lo slug {slug!r}.")
    scope = ClubScope(organization_id=club.organization_id, club_id=club.id)
    done: list[str] = []

    plans = {p.name: p for p in await club_service.list_plans(db, scope=scope)}
    for group in GROUPS:
        wanted = {"min_age": group.min_age, "max_age": group.max_age, "monthly_fee_cents": group.monthly_cents,
                  "enrollment_fee_cents": ENROLLMENT_CENTS, "due_day": DUE_DAY, "description": group.description,
                  "active": True}
        plan = plans.get(group.name)
        if plan is None:
            done.append(f"piano nuovo: {group.name}")
            if apply:
                await club_service.create_plan(db, scope=scope, actor_user_id=None, data={"name": group.name, **wanted})
            continue
        changes = {k: v for k, v in wanted.items() if getattr(plan, k) != v}
        if changes:
            done.append(f"piano {group.name}: {sorted(changes)}")
            if apply:
                await club_service.update_plan(db, scope=scope, plan_id=plan.id, actor_user_id=None, changes=changes)
    names = {g.name for g in GROUPS}
    for plan in plans.values():
        if plan.active and plan.name not in names:
            if deactivate_others:
                done.append(f"piano disattivato: {plan.name}")
                if apply:
                    await club_service.update_plan(db, scope=scope, plan_id=plan.id, actor_user_id=None,
                                                   changes={"active": False})
            else:
                print(f"  attenzione: il piano {plan.name!r} resta attivo (--deactivate-others per spegnerlo)")

    current = pricing_rules.get_pricing(club)
    changes = {k: v for k, v in PRICING.items() if current.get(k) != v}
    if changes:
        done.append(f"prezzi e sconti: {sorted(changes)}")
        if apply:
            await clubs_service.update_club_pricing(db, scope=scope, actor_user_id=None, changes=changes)

    if show_prices:
        site = (await db.execute(select(ClubSite).where(ClubSite.club_id == club.id))).scalars().first()
        if site is None:
            print("  attenzione: il club non ha ancora la pagina pubblica, niente 'mostra i prezzi'")
        elif not site.show_prices:
            done.append("pagina pubblica: mostra i prezzi")
            if apply:
                site.show_prices = True
                await db.commit()

    courses = {c.name: c for c in await courses_service.list_courses(db, scope=scope, only_active=False)}
    for spec in COURSES.get(slug, ()):
        wanted_slots = list(spec.slots)
        course = courses.get(spec.name)
        if course is None:
            done.append(f"corso nuovo: {spec.name}")
            if apply:
                course = await courses_service.create_course(db, scope=scope, actor_user_id=None, data={
                    "name": spec.name, "min_age": spec.min_age, "max_age": spec.max_age,
                })
        else:
            changes = {k: v for k, v in (("min_age", spec.min_age), ("max_age", spec.max_age), ("active", True))
                       if getattr(course, k) != v}
            if changes:
                done.append(f"corso {spec.name}: {sorted(changes)}")
                if apply:
                    await courses_service.update_course(db, scope=scope, course_id=course.id, actor_user_id=None,
                                                        changes=changes)
        existing = set()
        if course is not None:
            existing = {
                (s.weekday, s.starts_at, s.ends_at)
                for s in (await db.execute(select(ClubCourseSlot).where(ClubCourseSlot.course_id == course.id))).scalars()
            }
        for weekday, start, end in wanted_slots:
            if (weekday, start, end) in existing:
                continue
            done.append(f"orario {spec.name}: giorno {weekday} {start:%H:%M}–{end:%H:%M}")
            if apply:
                await courses_service.add_slot(db, scope=scope, course_id=course.id, actor_user_id=None,
                                               weekday=weekday, starts_at=start, ends_at=end, room=None)
        for weekday, start, end in sorted(existing - set(wanted_slots)):
            print(f"  attenzione: {spec.name} ha anche l'orario giorno {weekday} {start:%H:%M}–{end:%H:%M} (lasciato)")
    return done


async def main(argv: list[str]) -> None:
    import app.main  # noqa: F401  (tutti i modelli registrati, vedi load_club_branding)
    from app.core.db import AsyncSessionLocal

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--club", action="append", help="slug del club (ripetibile); senza, i tre club ufficiali")
    parser.add_argument("--apply", action="store_true", help="scrive davvero (senza: solo cosa farebbe)")
    parser.add_argument("--show-prices", action="store_true", help="accende anche 'mostra i prezzi sul sito'")
    parser.add_argument("--deactivate-others", action="store_true", help="disattiva i piani attivi non in tabella")
    args = parser.parse_args(argv)
    async with AsyncSessionLocal() as db:
        for slug in args.club or OFFICIAL_CLUBS:
            print(f"{slug}{'' if args.apply else ' (prova, niente viene scritto)'}:")
            done = await load(db, slug, apply=args.apply, show_prices=args.show_prices,
                              deactivate_others=args.deactivate_others)
            print("\n".join(f"  - {line}" for line in done) or "  già tutto a posto")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))

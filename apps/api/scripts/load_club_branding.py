"""Mette sulla pagina pubblica dei club della rete (Lagos, Albufeira, Alvor)
il logo, i colori e i link ai social: la pagina del club diventa la sua
pagina (docs/club-portal.md, "La pagina del club").

I loghi sono quelli delle pagine Facebook dei club, ripuliti (fondo bianco,
quadrati, 512 px, senza metadati) e tenuti nel repository in
`scripts/club_branding/<slug>.jpg`. Si caricano come li carica la
segreteria dall'editor (site.upload_site_image, bucket pubblico dei media);
colori e social passano da site.update_site, con le stesse validazioni e lo
stesso audit (attore vuoto = il sistema). La copertina resta la foto che il
club ha già.

**Di default non scrive niente**: stampa che cosa farebbe. Con `--apply`
lo fa. È idempotente: rilanciato, trova tutto a posto. Un logo già presente
non si sostituisce (potrebbe averlo caricato la segreteria), salvo
`--replace-logo`; un colore o un link scritto dalla segreteria invece si
riallinea alla tabella qui sotto: lanciarlo vuol dire volere questi valori.

Il sorgente non è nell'immagine: si lancia dal sorgente montato, con il
`.env` del server (cioè sul database vero e sul MinIO vero):

    cd /opt/webapps/jav
    docker run --rm --network jav-dev_default -v "$PWD/apps/api:/src" -w /src \\
      --env-file .env -e S3_ENDPOINT_URL=http://minio:9000 --entrypoint python jav-dev-api \\
      -m scripts.load_club_branding                 # prova, tutti e tre i club
    ...  -m scripts.load_club_branding --apply       # scrive
"""

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.club import brand
from app.domains.club import site as site_service
from app.domains.club.models import Club
from app.domains.club.scope import ClubScope
from app.domains.club.site_models import ClubSite

ASSETS = Path(__file__).resolve().parent / "club_branding"

#: Colori e social, club per club. I colori vengono dai loghi: Lagos il blu
#: del judogi e il giallo pallido dell'arco; Albufeira il rosso e l'argento
#: del distintivo; Alvor è solo nero su bianco, e prende come accento il
#: rosso-arancio di JudoArteVida (il secondario, vuoto, ricade sull'accento).
BRANDING: dict[str, dict[str, str | None]] = {
    "judo-clube-de-lagos": {
        "brand_primary": "#6366F1",
        "brand_secondary": "#F8FF94",
        "brand_accent": "#F8FF94",
        "facebook_url": "https://www.facebook.com/judoclubedelagos/",
    },
    "judo-clube-de-albufeira": {
        "brand_primary": "#C92429",
        "brand_secondary": "#C4C4C6",
        "brand_accent": "#C4C4C6",
        "facebook_url": "https://www.facebook.com/judoclubedealbufeira/",
        "youtube_url": "https://www.youtube.com/channel/UCKyB7cQxPl56Mm3xsdxolFw",
    },
    "judo-team-matias-luwawa": {
        "brand_primary": "#000000",
        "brand_secondary": None,
        "brand_accent": "#E13F22",
        "facebook_url": "https://www.facebook.com/JudoTeamML/",
    },
}


def _wanted(value: str | None, field: str) -> str | None:
    """Il valore come lo salverebbe update_site, per confrontare mele con
    mele ("#e13f22" e "#E13F22" sono lo stesso colore)."""
    if field in brand.BRAND_FIELDS:
        return brand.normalize_hex(value)
    return site_service.check_social_url(value, field=field)


async def load(db: AsyncSession, slug: str, *, apply: bool, replace_logo: bool = False,
               assets: Path = ASSETS) -> list[str]:
    """Allinea un club alla tabella. Restituisce le cose fatte (o da fare,
    senza `apply`): una lista vuota vuol dire che era già tutto a posto."""
    club = (await db.execute(select(Club).where(Club.slug == slug))).scalars().first()
    if club is None:
        raise SystemExit(f"Nessun club con lo slug {slug!r}.")
    if slug not in BRANDING:
        raise SystemExit(f"Nessun colore in tabella per {slug!r}.")
    scope = ClubScope(organization_id=club.organization_id, club_id=club.id)
    done: list[str] = []

    # get_site crea la pagina (in bozza) se manca: senza --apply non si tocca.
    site = (await db.execute(select(ClubSite).where(ClubSite.club_id == club.id))).scalars().first()
    if site is None:
        done.append("pagina pubblica nuova (in bozza)")
        if apply:
            site = await site_service.get_site(db, scope=scope)

    changes = {}
    for field, value in BRANDING[slug].items():
        wanted = _wanted(value, field)
        # Una pagina che ancora non c'è nascerà vuota: si confronta con il vuoto.
        if (getattr(site, field) if site is not None else None) != wanted:
            changes[field] = wanted
    if changes:
        done.append(f"colori e social: {sorted(changes)}")
        if apply:
            site = await site_service.update_site(db, scope=scope, actor_user_id=None, changes=changes)

    logo = assets / f"{slug}.jpg"
    if site is None or not site.logo_url or replace_logo:
        if not logo.is_file():
            print(f"  attenzione: manca il logo {logo}")
        else:
            done.append(f"logo: {logo.name}")
            if apply:
                site, _url = await site_service.upload_site_image(
                    db, scope=scope, actor_user_id=None, slot="logo", file_bytes=logo.read_bytes(),
                    content_type="image/jpeg",
                )
    return done


async def main(argv: list[str]) -> None:
    # Tutti i modelli registrati (come nell'API): l'audit punta a tabelle di
    # altri domini, e senza di loro SQLAlchemy non sa ordinare gli INSERT.
    import app.main  # noqa: F401
    from app.core.db import AsyncSessionLocal

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--club", action="append", help="slug del club (ripetibile); senza, i tre club ufficiali")
    parser.add_argument("--apply", action="store_true", help="scrive davvero (senza: solo cosa farebbe)")
    parser.add_argument("--replace-logo", action="store_true", help="sostituisce anche un logo già caricato")
    args = parser.parse_args(argv)
    async with AsyncSessionLocal() as db:
        for slug in args.club or list(BRANDING):
            print(f"{slug}{'' if args.apply else ' (prova, niente viene scritto)'}:")
            done = await load(db, slug, apply=args.apply, replace_logo=args.replace_logo)
            print("\n".join(f"  - {line}" for line in done) or "  già tutto a posto")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))

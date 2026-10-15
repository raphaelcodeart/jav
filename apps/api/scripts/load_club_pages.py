"""Riempie il mini-sito dei club della rete (Lagos, Albufeira, Alvor) con
contenuti veri: presentazione, sede, anno di fondazione, i numeri, la
storia, i punti di forza, le novità, gli allenatori e le foto
(docs/club-portal.md, "La pagina del club").

Da dove vengono (ottobre 2026), così chi li rilegge sa che cosa verificare:

- **Albufeira**: storia e valori dal blog del club (jcalbufeira.blogspot.com,
  "Historial", 2015), sede attuale da judoartevida.com/judo/precos.php; le
  foto sono quelle pubblicate dal club sul suo blog (2014–2015);
- **Lagos**: costituzione da racius.com (03/12/2012), sede da precos.php,
  voto di lode della Câmara (postal.pt, agosto 2025), prémio Carreira alla
  Gala do Desporto 2026 (maisalgarve.pt); foto del blog di Albufeira
  (convívio di Natale 2014 e Treino Aberto 2015 con il JC Lagos);
- **Judo Team Matias Luwawa**: costituzione da racius.com (23/04/2019),
  indirizzo e orario da judoartevida.com; foto dei capi della squadra dal
  vecchio judoartevida.com (Wayback Machine).

Regole seguite: niente nomi di atleti minorenni (la scheda di un judoca
esce solo con il consenso della famiglia), niente foto di giornali (diritti
non nostri), niente foto ravvicinate di bambini; le foto stanno in
`scripts/club_pages/<slug>/`, ridotte a 1600 px e senza metadati. Facebook
e Instagram dei club non si leggono senza login: le foto recenti vanno
caricate dalla segreteria con l'editor.

Si scrive con site.update_site e site.upload_site_image, le stesse funzioni
dell'editor (stesse validazioni, stesso audit; attore vuoto = il sistema).
Contatti (email, telefono) e prezzi non si toccano.

**Di default non scrive niente**: stampa che cosa farebbe. Con `--apply` lo
fa. Le foto si caricano solo se la galleria non le ha già (si riconoscono
dalla didascalia): rilanciato, non duplica niente. Si lancia come
load_club_branding:

    docker run --rm --network jav-dev_default -v "$PWD/apps/api:/src" -w /src \\
      --env-file .env -e S3_ENDPOINT_URL=http://minio:9000 --entrypoint python jav-dev-api \\
      -m scripts.load_club_pages [--apply] [--club <slug>]
"""

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ASSETS = Path(__file__).resolve().parent / "club_pages"

MATIAS = {
    "name": "Matias Luwawa",
    "role": "Responsável técnico e treinador principal",
    "grade": "Cinto preto 2.º dan",
    "bio": "Pratica judo desde 1994, é treinador desde 2006 e árbitro desde 2009, hoje árbitro de elite.",
    "photo_url": None,
}

#: Tutto quello che si scrive, club per club. "hero" e "gallery" sono file
#: in ASSETS/<slug>/; la didascalia è anche ciò che rende idempotente il
#: caricamento.
PAGES: dict[str, dict] = {
    "judo-clube-de-albufeira": {
        "fields": {
            "tagline": "Desde 2004, o judo como modo de vida em Albufeira.",
            "founded_year": 2004,
            "venue": "Escola EB 2,3 Dr. Francisco Cabrita",
            "address": "8200-317 Albufeira",
            "about": (
                "O Judo Clube de Albufeira (JCAlb) nasceu da iniciativa de um grupo de amigos praticantes de judo desde "
                "1970 — Charters de Azevedo, José Costa e Mário Jonas — que, perante a inexistência de qualquer estrutura "
                "para a modalidade no concelho, decidiram criá-la. O clube foi fundado oficialmente a 30 de junho de 2004 "
                "e começou a treinar a 20 de setembro desse ano, no pavilhão da Escola Básica de Ferreiras.\n\n"
                "Filiado na Associação Distrital de Judo do Algarve e na Federação Portuguesa de Judo, o JCAlb é uma "
                "associação sem fins lucrativos que quer influenciar positivamente a personalidade, as aptidões físicas e "
                "a vida dos seus membros e da comunidade. Entre as suas convicções está a inclusão: nenhuma criança é "
                "recusada por motivos económicos.\n\n"
                "Ao longo dos anos, os judocas do clube somaram títulos regionais e pódios em torneios por todo o país, "
                "foram distinguidos na Gala do Desporto de Albufeira e participaram em estágios e treinos abertos com "
                "outros clubes do Algarve. Hoje, integrado na rede Judo Arte e Vida, o clube treina na Escola EB 2,3 "
                "Dr. Francisco Cabrita, em Albufeira."
            ),
            "highlights": [
                {"value": "1970", "label": "o judo dos fundadores começou"},
                {"value": "10", "label": "premiados na Gala do Desporto 2015"},
                {"value": "0", "label": "crianças recusadas por motivos económicos"},
            ],
            "pillars": [
                {"title": "Judo como modo de vida", "text": "Honra, respeito, amizade, disciplina e coragem: os valores do tatami levam-se para casa, para a escola e para a vida."},
                {"title": "Ninguém fica de fora", "text": "Uma associação sem fins lucrativos: nenhuma criança é recusada por motivos económicos."},
                {"title": "Federados e seguros", "text": "Clube filiado na ADJA e na Federação Portuguesa de Judo: a inscrição na FPJ e o seguro desportivo são oferecidos pelo clube."},
                {"title": "Uma rede no Algarve", "text": "Estágios, treinos abertos e provas com os outros clubes da rede Judo Arte e Vida."},
            ],
            "history": [
                {"year": 1970, "title": "Os fundadores começam no judo", "text": "Charters de Azevedo, José Costa e Mário Jonas praticam judo desde então."},
                {"year": 2004, "title": "Nasce o Judo Clube de Albufeira", "text": "Escritura a 30 de junho; os treinos começam a 20 de setembro no pavilhão da Escola Básica de Ferreiras."},
                {"year": 2014, "title": "Estágio e convívio de Natal com o Judo Clube de Lagos", "text": None},
                {"year": 2015, "title": "Dez judocas premiados na Gala do Desporto de Albufeira", "text": "No mesmo ano, o Treino Aberto de Ferreiras junta famílias, o JC Lagos e o Desporto Escolar."},
            ],
            "coaches": [MATIAS],
        },
        "hero": ("alinhamento-tatami-ferreiras-2015.jpg", "Saudação no tatami de Ferreiras"),
        "gallery": [
            ("dojo-ferreiras-tatami-1.jpg", "O nosso dojo em Ferreiras"),
            ("mini-estagio-ferragudo-2015.jpg", "Mini-estágio de Páscoa em Ferragudo, 2015"),
            ("treino-ne-waza-ferreiras-2015.jpg", "Treino de ne-waza"),
            ("saudacao-ferragudo-2015.jpg", "Rei: a saudação antes do treino"),
            ("treino-aberto-ferreiras-2015-1.jpg", "Treino Aberto de Ferreiras, 2015"),
            ("treino-aberto-ferreiras-2015-2.jpg", "Treino Aberto com as famílias"),
            ("alinhamento-ferragudo-2015.jpg", "Alinhados para o estágio de Ferragudo"),
            ("gala-desporto-albufeira-2015.jpg", "Gala do Desporto de Albufeira, 2015"),
            ("dojo-ferreiras-tatami-2.jpg", "O tatami pronto para o treino"),
        ],
    },
    "judo-clube-de-lagos": {
        "fields": {
            "tagline": "Judo em Lagos — dos benjamins aos veteranos, uma só equipa.",
            "founded_year": 2012,
            "venue": "Escola Secundária Gil Eanes",
            "address": "8600-614 Lagos",
            "about": (
                "O Judo Clube de Lagos (JCLGS) é uma associação desportiva de Lagos, constituída em dezembro de 2012, que "
                "treina na Escola Secundária Gil Eanes. Fundado pelo Mestre Matias Luwawa, o seu responsável técnico e "
                "treinador principal, o clube faz parte da rede Judo Arte e Vida, presente em várias cidades do Algarve.\n\n"
                "O trabalho do clube abrange todas as idades: na época 2024/2025 os seus judocas subiram ao pódio em "
                "provas regionais e nacionais, dos benjamins aos veteranos, com títulos de campeão nacional — resultados "
                "que valeram ao clube um voto de louvor da Câmara Municipal de Lagos. Em 2026, o Mestre Matias Luwawa foi "
                "distinguido na categoria Carreira da Gala do Desporto de Lagos.\n\n"
                "Para além da competição, o clube aposta no convívio e na abertura à comunidade, com treinos abertos, "
                "estágios partilhados com outros clubes algarvios e formação para os seus atletas: o judo é muito mais do "
                "que um desporto, é uma arte com princípios e um código moral para a vida."
            ),
            "highlights": [
                {"value": "3", "label": "títulos de campeão nacional em 2024/25"},
            ],
            "pillars": [
                {"title": "Para todas as idades", "text": "Grupos dos mais pequenos aos veteranos: cada um treina ao seu ritmo, todos na mesma equipa."},
                {"title": "Competição a sério", "text": "Pódios regionais e nacionais todas as épocas, com títulos de campeão nacional."},
                {"title": "Aberto à cidade", "text": "Treinos abertos, convívios e formação, como o curso de primeiros socorros no Treino Aberto de 2015."},
                {"title": "Federados e seguros", "text": "A inscrição na Federação Portuguesa de Judo e o seguro desportivo são oferecidos pelo clube."},
            ],
            "history": [
                {"year": 2012, "title": "Constituição do Judo Clube de Lagos", "text": "Fundado pelo Mestre Matias Luwawa, a 3 de dezembro."},
                {"year": 2014, "title": "Estágio e convívio de Natal com o Judo Clube de Albufeira", "text": None},
                {"year": 2015, "title": "Treino Aberto na Escola Secundária Gil Eanes", "text": "Judo, Zumba e formação em primeiros socorros, aberto a toda a cidade."},
                {"year": 2025, "title": "Voto de louvor da Câmara Municipal de Lagos", "text": "Pelos resultados da época 2024/2025, com títulos regionais e nacionais."},
                {"year": 2026, "title": "Prémio Carreira na Gala do Desporto de Lagos", "text": "Para o Mestre Matias Luwawa."},
            ],
            "news": [
                {"date": date(2026, 4, 10), "title": "Prémio Carreira para o Mestre Matias Luwawa",
                 "text": "Na Gala do Desporto de Lagos 2026, o fundador e treinador principal do clube foi distinguido na categoria Carreira. Obrigado, Mestre!",
                 "image_url": None, "link_url": None},
                {"date": date(2025, 8, 1), "title": "Voto de louvor da Câmara Municipal de Lagos",
                 "text": "A Câmara Municipal de Lagos aprovou um voto de louvor ao clube pela época 2024/2025: pódios regionais e nacionais dos benjamins aos veteranos, com títulos de campeão nacional — entre eles Anatolie Paiu (veteranos -81 kg) e Matias Luwawa (veteranos -100 kg).",
                 "image_url": None,
                 "link_url": "https://postal.pt/desporto/lagos-celebra-conquistas-desportivas-com-votos-de-louvor-a-atletas-e-clubes/"},
            ],
            "coaches": [MATIAS, {"name": "Marco", "role": "Monitor", "photo_url": None, "grade": None, "bio": None}],
        },
        "hero": None,
        "gallery": [
            ("convivio-natal-lagos-albufeira-2014.jpg", "Convívio de Natal com o JC Albufeira, 2014"),
            ("treino-aberto-lagos-2015-primeiros-socorros.jpg", "Primeiros socorros no Treino Aberto, 2015"),
            ("cartaz-treino-aberto-lagos-2015.jpg", "Treino Aberto na Gil Eanes: vem experimentar!"),
        ],
    },
    "judo-team-matias-luwawa": {
        "fields": {
            "tagline": "Judo Team Matias Luwawa — treino sério, valores para a vida.",
            "founded_year": 2019,
            "venue": "Alvor",
            "address": "Rua Padre Mendes, 7 C/V, 8500-022 Alvor, Portimão",
            "about": (
                "A Judo Team Matias Luwawa (JTML) é uma associação de judo constituída em abril de 2019, com sede em "
                "Alvor, no concelho de Portimão. Com a coordenação técnica do Mestre Matias Luwawa, faz parte da rede "
                "Judo Arte e Vida, que reúne salas de treino em várias localidades do Algarve.\n\n"
                "O horário semanal combina aulas de judo por grupos etários — iniciação, formação e competição — com "
                "sessões específicas de ne-waza, tachi-waza e randori, preparação física (Judo Fit) e momentos de "
                "alongamentos (Judo Relax), com treinos desde as primeiras horas da manhã até ao fim do dia.\n\n"
                "Na JTML, o judo é vivido como mais do que um desporto: é uma arte com princípios éticos e um código "
                "moral para a vida, que forma atletas e cidadãos."
            ),
            "highlights": [
                {"value": "6:00", "label": "o primeiro treino do dia"},
                {"value": "3", "label": "grupos: iniciação, formação, competição"},
            ],
            "pillars": [
                {"title": "Técnica a fundo", "text": "Sessões dedicadas a ne-waza, tachi-waza e randori, para além das aulas por grupos."},
                {"title": "Judo Fit", "text": "Preparação física específica para o judo, de manhã cedo ou ao fim da tarde."},
                {"title": "Judo Relax", "text": "Alongamentos e recuperação no fim do dia: o corpo também se treina a descansar."},
                {"title": "Federados e seguros", "text": "A inscrição na Federação Portuguesa de Judo e o seguro desportivo são oferecidos pelo clube."},
            ],
            "history": [
                {"year": 2019, "title": "Nasce a Judo Team Matias Luwawa", "text": "Associação de judo constituída a 23 de abril, em Alvor."},
            ],
            "coaches": [
                MATIAS,
                {"name": "Paul", "role": "Treinador adjunto", "photo_url": None, "grade": None, "bio": None},
                {"name": "Ariel", "role": "Monitor", "photo_url": None, "grade": None, "bio": None},
            ],
        },
        "hero": None,
        "gallery": [
            ("sweatshirt-jtml.jpg", "A sweatshirt da equipa"),
            ("tshirt-jtml.jpg", "A t-shirt JTML"),
        ],
    },
}


async def load(db: AsyncSession, slug: str, *, apply: bool) -> list[str]:
    from app.domains.club import site as site_service
    from app.domains.club.models import Club
    from app.domains.club.scope import ClubScope

    page = PAGES[slug]
    club = (await db.execute(select(Club).where(Club.slug == slug))).scalars().first()
    if club is None:
        return [f"attenzione: il club {slug} non esiste"]
    scope = ClubScope(organization_id=club.organization_id, club_id=club.id)
    site = await site_service.get_site(db, scope=scope)
    done: list[str] = []

    async def upload(slot: str, name: str, caption: str | None = None) -> str:
        path = ASSETS / slug / name
        _, url = await site_service.upload_site_image(
            db, scope=scope, actor_user_id=None, slot=slot, file_bytes=path.read_bytes(),
            content_type="image/jpeg", caption=caption,
        )
        return url

    fields = dict(page["fields"])
    # La galleria: le foto del club al posto di quelle generiche, nell'ordine
    # qui sopra; una foto già caricata (stessa didascalia) non si ricarica.
    have = {g.get("caption"): g["url"] for g in (site.gallery or [])}
    wanted = page["gallery"]
    missing = [(n, c) for n, c in wanted if c not in have]
    if missing:
        done.append(f"galleria: carica {len(missing)} foto")
    if apply:
        for name, caption in missing:
            have[caption] = await upload("coach", name)  # "coach": restituisce solo l'indirizzo
        fields["gallery"] = [{"url": have[c], "caption": c} for _, c in wanted]

    # La copertina si cambia solo al primo caricamento delle foto del club
    # (l'indirizzo caricato è casuale e non dice da quale file viene): dopo,
    # è della segreteria.
    if page["hero"] and len(missing) == len(wanted):
        name, _ = page["hero"]
        done.append(f"copertina: {name}")
        if apply:
            await upload("hero", name)

    done.append("testi e liste: " + ", ".join(sorted(k for k in fields if k != "gallery")))
    if apply:
        await site_service.update_site(db, scope=scope, actor_user_id=None, changes=fields)
    return done


async def main(argv: list[str]) -> None:
    import app.main  # noqa: F401  (tutti i modelli registrati, vedi load_club_branding)
    from app.core.db import AsyncSessionLocal

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--club", action="append", help="slug del club (ripetibile); senza, i tre club")
    parser.add_argument("--apply", action="store_true", help="scrive davvero (senza: solo cosa farebbe)")
    args = parser.parse_args(argv)
    async with AsyncSessionLocal() as db:
        for slug in args.club or list(PAGES):
            print(f"{slug}{'' if args.apply else ' (prova, niente viene scritto)'}:")
            print("\n".join(f"  - {line}" for line in await load(db, slug, apply=args.apply)))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))

"""Carica nello Shop JAV (lo shop unico della rete) il catalogo di
suplementos24.com: prodotti, categorie, foto. Specifica: docs/club-portal.md,
"Lo shop della rete".

I dati sono in `scripts/shop_import/suplementos24.json`, raccolti dalle pagine
pubbliche del sito: per ogni prodotto nome, marca, prezzo al pubblico (IVA
inclusa, in centesimi), descrizione breve, foto grande e i percorsi di
categoria. Le categorie dello shop sono piatte: si creano le cinque grandi
(Massa Muscular, Endurance, Perder Peso, Saúde, Equipamentos) e le
sottocategorie come «Grande › Sotto»; ogni prodotto va in tutte quelle dei suoi
percorsi.

Il prezzo: lo Shop JAV aggiunge l'IVA (marketplaces/rules.get_vat_percentage,
22 se non indicato) al prezzo del prodotto, quindi si salva il netto
`prezzo × 100 / (100 + IVA)`, così al cliente arriva il prezzo del sito. Le foto
si copiano nel bucket pubblico dei media (core/storage.upload_media): un link
a un sito altrui si romperebbe il giorno che lo cambiano.

**Di default non scrive niente**: stampa che cosa farebbe. Con `--apply` lo fa.
È idempotente: un prodotto che c'è già (stesso nome, shop della rete) non si
tocca, una categoria che c'è già si riusa. `--limit N` per provarne pochi.

    cd /opt/webapps/jav
    docker run --rm --network jav-dev_default -v "$PWD/apps/api:/src" -w /src \\
      --env-file .env -e S3_ENDPOINT_URL=http://minio:9000 --entrypoint python jav-dev-api \\
      -m scripts.import_suplementos24 --actor-email admin@…            # prova
    ...  -m scripts.import_suplementos24 --actor-email admin@… --apply  # scrive
"""

import argparse
import asyncio
import json
import sys
import urllib.request
from pathlib import Path

from sqlalchemy import func, select

DATA = Path(__file__).parent / "shop_import" / "suplementos24.json"


def _download(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as res:
            if res.headers.get_content_type() != "image/jpeg":
                return None
            return res.read()
    except Exception:  # noqa: BLE001 - una foto che non arriva non ferma l'importazione
        return None


def net_cents(gross_cents: int, vat: int) -> int:
    return max(1, round(gross_cents * 100 / (100 + vat)))


def category_names(paths: list[list[str]]) -> list[str]:
    names: list[str] = []
    for path in paths:
        if path:
            names.append(path[0])
        if len(path) >= 2:
            names.append(f"{path[0]} › {path[1]}")
    return list(dict.fromkeys(names))


async def main(argv: list[str]) -> None:
    import app.main  # noqa: F401 - tutti i modelli registrati, come nell'API
    from app.core import storage
    from app.core.db import AsyncSessionLocal
    from app.domains.jav_market import service as market
    from app.domains.jav_market.models import SHOP, JavMarketProduct
    from app.domains.marketplaces import rules
    from app.domains.shop_categories import service as categories
    from app.domains.shop_categories.models import ShopCategory
    from app.domains.users.models import User

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--actor-email", required=True, help="chi risulta autore (un amministratore)")
    parser.add_argument("--apply", action="store_true", help="scrive davvero (senza: solo cosa farebbe)")
    parser.add_argument("--limit", type=int, default=0, help="solo i primi N prodotti")
    args = parser.parse_args(argv)
    items = json.loads(DATA.read_text())
    if args.limit:
        items = items[: args.limit]

    async with AsyncSessionLocal() as db:
        actor = (await db.execute(select(User).where(func.lower(User.email) == args.actor_email.lower()))).scalar_one()
        org = actor.organization_id
        vat = await rules.get_vat_percentage(db, organization_id=org)
        existing_cats = {c.name: c.id for c in (await db.execute(
            select(ShopCategory).where(ShopCategory.organization_id == org, ShopCategory.shop == SHOP))).scalars()}
        existing_products = set((await db.execute(select(JavMarketProduct.name).where(
            JavMarketProduct.organization_id == org, JavMarketProduct.club_id.is_(None)))).scalars())

        wanted = list(dict.fromkeys(n for p in items for n in category_names(p["cats"])))
        new_cats = [n for n in wanted if n not in existing_cats]
        new_products = [p for p in items if p["name"].strip() not in existing_products]
        print(f"IVA dello shop {vat}%: {len(new_cats)} categorie e {len(new_products)} prodotti nuovi "
              f"({len(items) - len(new_products)} già presenti).{'' if args.apply else ' Prova: niente viene scritto.'}")
        if not args.apply:
            for p in new_products[:5]:
                print(f"  - {p['name']} ({p['brand']}): {p['price'] / 100:.2f} € → netto {net_cents(p['price'], vat) / 100:.2f} €")
            return

        tops = [n for n in wanted if "›" not in n]
        for name in new_cats:
            position = tops.index(name) * 100 if name in tops else tops.index(name.split(" › ")[0]) * 100 + 1 + wanted.index(name)
            cat = await categories.create_category(db, organization_id=org, shop=SHOP, name=name,
                                                   position=position, actor_user_id=actor.id)
            existing_cats[name] = cat.id

        done = 0
        for p in new_products:
            image_url = None
            if p.get("image"):
                data = await asyncio.to_thread(_download, p["image"])
                if data:
                    try:
                        image_url = storage.upload_media(file_bytes=data, content_type="image/jpeg", key_prefix="jav-market/import")
                    except storage.UploadValidationError:
                        image_url = None
            description = p.get("description") or ""
            if p.get("brand"):
                description = f"{description}\n\nMarca: {p['brand']}".strip()
            product = await market.create_product(db, organization_id=org, actor_user_id=actor.id, payload={
                "name": p["name"].strip(), "description": description[:8000], "image_url": image_url,
                "images": [image_url] if image_url else [], "status": "ACTIVE", "credit_discount_percentage": 0,
                "variants": [{"label": "Unica", "price_cents": net_cents(p["price"], vat)}],
            })
            await categories.replace_assignments(
                db, organization_id=org, shop=SHOP, product_id=product.id,
                category_ids=[existing_cats[n] for n in category_names(p["cats"])], actor_user_id=actor.id,
            )
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(new_products)}")
        print(f"Fatto: {len(new_cats)} categorie, {done} prodotti.")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))

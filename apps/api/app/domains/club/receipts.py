"""Il numero di una ricevuta: "MEN-2026-0042".

Il prefisso dice che cosa si è pagato (come nel gestionale di prima, che le
famiglie conoscono), l'anno è quello del pagamento, il numero è progressivo
per club, prefisso e anno. Lo si prende con un solo statement atomico su
`club_receipt_counters` (INSERT ... ON CONFLICT DO UPDATE ... RETURNING):
due caricamenti nello stesso istante ricevono due numeri diversi, e l'indice
UNIQUE su (club, numero) lo garantisce comunque. Il vecchio gestionale
contava le righe e poteva dare lo stesso numero due volte.
"""

import uuid

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.club.models import ClubReceiptCounter

#: Il prefisso di una quota, per tipo.
PREFIX_BY_KIND = {
    "MONTHLY": "MEN",
    "ENROLLMENT": "QUO",
    "MEMBERSHIP": "QUO",
    "COMPETITION": "PRO",
    "EQUIPMENT": "EQU",
    "FINE": "MUL",
}
#: Più tipi insieme in un pagamento solo.
MIXED_PREFIX = "PAG"


def prefix_for(kinds: list[str]) -> str:
    prefixes = {PREFIX_BY_KIND.get(k, MIXED_PREFIX) for k in kinds}
    return prefixes.pop() if len(prefixes) == 1 else MIXED_PREFIX


async def next_number(db: AsyncSession, *, club_id: uuid.UUID, prefix: str, year: int) -> str:
    """Il prossimo numero; vive nella transazione di chi chiama (se il
    pagamento non va a buon fine, il numero torna libero con il rollback)."""
    stmt = (
        insert(ClubReceiptCounter)
        .values(club_id=club_id, prefix=prefix, year=year, last_number=1)
        .on_conflict_do_update(
            index_elements=["club_id", "prefix", "year"],
            set_={"last_number": ClubReceiptCounter.last_number + 1},
        )
        .returning(ClubReceiptCounter.last_number)
    )
    number = (await db.execute(stmt)).scalar_one()
    return f"{prefix}-{year}-{number:04d}"

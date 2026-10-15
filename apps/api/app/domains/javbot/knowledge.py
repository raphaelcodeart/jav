"""La base di conoscenza di JAVBOT: i PDF che l'assistente dell'area
privata consulta prima di rispondere (assistant.py, strumento
`search_knowledge`).

Due livelli, sempre insieme:

- la base **comune** (`club_id` NULL): la carica la piattaforma ed è di
  tutti i club — regolamenti federali, il progetto JudoArteVida, le regole
  dei corsi;
- la base **del club**: la carica la sua segreteria (o la piattaforma
  entrando nel club) e la vedono solo i suoi utenti — orari speciali, il
  regolamento interno, la lista del materiale.

Lo stesso vale per le istruzioni (il "prompt"): una comune e una per club.

**Come si cerca, e perché così.** Niente embedding né modelli da far girare
sul server: il testo si divide in pezzi di qualche paragrafo, si salva
normalizzato (minuscolo, senza accenti) e si cerca con il full-text di
Postgres in configurazione `simple`, che non conosce le lingue e quindi va
bene per pt, it ed en insieme. Le parole della domanda valgono anche come
prefisso ("inscri" trova inscrição e inscrições). Chi formula la ricerca è
il modello, che può riprovare con altre parole o in un'altra lingua: è
questo che rende sufficiente una ricerca a parole.

Il PDF resta nel bucket privato (CLAUDE.md §5): l'assistente ne legge solo
il testo, e il file si apre solo con un URL presigned dato a chi lo
amministra.
"""

import asyncio
import io
import logging
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.db import utcnow
from app.domains.javbot.intents import normalize
from app.domains.javbot.models import JavbotInstructions, JavbotKnowledgeChunk, JavbotKnowledgeDocument

logger = logging.getLogger(__name__)

#: Quanto testo per pezzo: abbastanza per una regola intera con il suo
#: contesto, poco abbastanza da mandarne sei al modello senza sprechi.
CHUNK_CHARS = 1500
CHUNK_OVERLAP = 200
#: Quanti pezzi restituisce una ricerca.
SEARCH_LIMIT = 6
MAX_TITLE = 200
#: Le istruzioni sono un prompt, non un documento: per i documenti c'è il PDF.
MAX_INSTRUCTIONS = 8000
#: Quanti documenti può avere un livello (comune o club): oltre, è un
#: archivio, non una base di conoscenza, e la ricerca peggiora.
MAX_DOCUMENTS = 200

#: Parole troppo comuni per distinguere un pezzo da un altro, nelle tre lingue.
_STOPWORDS = frozenset("""
    che chi cosa come con del della dei delle per non una uno gli nel nella sono essere questo questa quale quando
    dove anche alla alle allo agli dal dalla ho hai devo posso mio mia miei mie suo sua
    que qual quais como com dos das para nao uma uns umas nos nas pelo pela sao ser este esta isso esse essa quando
    onde tambem aos meu minha meus minhas seu sua tenho posso devo
    the and for are was what which when where how who with from this that have has can does about your you
""".split())


class KnowledgeError(Exception):
    """Un problema da spiegare a chi carica (CLAUDE.md §6)."""


class KnowledgeNotFoundError(KnowledgeError):
    """Il documento non c'è, o è di un altro livello."""


@dataclass(frozen=True)
class Level:
    """Su quale livello si lavora: la base comune (`club_id` None) o un club."""

    organization_id: uuid.UUID
    club_id: uuid.UUID | None


# --- Dal PDF ai pezzi -----------------------------------------------------------------------------


def extract_pages(file_bytes: bytes) -> list[str]:
    """Il testo di ogni pagina. Una scansione senza testo dà pagine vuote:
    lo si dice a chi carica, non si inventa niente."""
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        if reader.is_encrypted:
            raise KnowledgeError("Il PDF è protetto da password: caricalo senza protezione.")
        return [(page.extract_text() or "") for page in reader.pages]
    except PdfReadError as exc:
        raise KnowledgeError("Non riesco a leggere questo PDF: prova a salvarlo di nuovo come PDF e ricaricalo.") from exc


def _clean(text: str) -> str:
    text = text.replace("\x00", "")
    # Le parole spezzate a fine riga ("inscri-\nção") si riattaccano.
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"[ \t\f\v]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def split_chunks(pages: list[str]) -> list[tuple[int, str]]:
    """(pagina da cui inizia, testo) per ogni pezzo. Si taglia a fine
    paragrafo o frase quando si può, mai a metà parola; i pezzi si
    sovrappongono un poco, così una regola a cavallo del taglio si trova
    intera almeno in uno dei due."""
    chunks: list[tuple[int, str]] = []
    for number, raw in enumerate(pages, start=1):
        text = _clean(raw)
        start = 0
        while start < len(text):
            end = min(len(text), start + CHUNK_CHARS)
            if end < len(text):
                window = text[start:end]
                cut = max(window.rfind("\n\n"), window.rfind(". "), window.rfind("\n"))
                if cut > CHUNK_CHARS // 2:
                    end = start + cut + 1
                else:
                    space = window.rfind(" ")
                    end = start + space if space > 0 else end
            piece = text[start:end].strip()
            if len(piece) >= 20:
                chunks.append((number, piece))
            if end >= len(text):
                break
            start = max(end - CHUNK_OVERLAP, start + 1)
            # Si riparte da inizio parola.
            while start < len(text) and not text[start - 1].isspace():
                start += 1
    return chunks


# --- Documenti ------------------------------------------------------------------------------------


def _level_filter(stmt, model, level: Level):
    stmt = stmt.where(model.organization_id == level.organization_id)
    return stmt.where(model.club_id.is_(None) if level.club_id is None else model.club_id == level.club_id)


async def list_documents(db: AsyncSession, *, level: Level) -> list[JavbotKnowledgeDocument]:
    stmt = _level_filter(select(JavbotKnowledgeDocument), JavbotKnowledgeDocument, level)
    return list((await db.execute(stmt.order_by(JavbotKnowledgeDocument.created_at.desc()))).scalars().all())


async def add_document(
    db: AsyncSession, *, level: Level, file_bytes: bytes, content_type: str, filename: str,
    title: str | None, actor_user_id: uuid.UUID,
) -> JavbotKnowledgeDocument:
    if content_type != "application/pdf" or not file_bytes.startswith(b"%PDF-"):
        raise KnowledgeError("Si possono caricare solo file PDF.")
    count = (await db.execute(
        _level_filter(select(func.count()).select_from(JavbotKnowledgeDocument), JavbotKnowledgeDocument, level)
    )).scalar_one()
    if count >= MAX_DOCUMENTS:
        raise KnowledgeError(f"Ci sono già {MAX_DOCUMENTS} documenti: togline qualcuno vecchio prima di aggiungerne.")
    # pypdf è CPU: fuori dal ciclo degli eventi, come il caricamento su MinIO.
    pages = await asyncio.to_thread(extract_pages, file_bytes)
    chunks = split_chunks(pages)
    try:
        key = await asyncio.to_thread(
            storage.upload_document, file_bytes=file_bytes, content_type=content_type,
            key_prefix=f"javbot-knowledge/{level.club_id or 'common'}",
        )
    except storage.UploadValidationError as exc:
        raise KnowledgeError("Il PDF è troppo grande: il massimo è 15 MB.") from exc

    name = (filename or "documento.pdf").strip()[:255]
    clean_title = " ".join((title or "").split())[:MAX_TITLE] or re.sub(r"\.pdf$", "", name, flags=re.I)[:MAX_TITLE]
    document = JavbotKnowledgeDocument(
        organization_id=level.organization_id, club_id=level.club_id, title=clean_title, filename=name,
        storage_key=key, size_bytes=len(file_bytes), page_count=len(pages),
        char_count=sum(len(text) for _page, text in chunks), status="READY" if chunks else "EMPTY",
        uploaded_by_user_id=actor_user_id,
    )
    db.add(document)
    await db.flush()
    db.add_all([
        JavbotKnowledgeChunk(
            document_id=document.id, organization_id=level.organization_id, club_id=level.club_id,
            ordinal=i, page=page, text=text, norm=normalize(text),
        )
        for i, (page, text) in enumerate(chunks)
    ])
    await db.commit()
    await db.refresh(document)
    return document


async def get_document(db: AsyncSession, *, level: Level, document_id: uuid.UUID) -> JavbotKnowledgeDocument:
    """Il documento, solo se è di questo livello: la segreteria di un club
    non tocca la base comune né quella di un altro club."""
    stmt = _level_filter(
        select(JavbotKnowledgeDocument).where(JavbotKnowledgeDocument.id == document_id),
        JavbotKnowledgeDocument, level,
    )
    document = (await db.execute(stmt)).scalars().first()
    if document is None:
        raise KnowledgeNotFoundError("Documento non trovato.")
    return document


async def remove_document(db: AsyncSession, *, level: Level, document_id: uuid.UUID) -> None:
    document = await get_document(db, level=level, document_id=document_id)
    key = document.storage_key
    await db.execute(delete(JavbotKnowledgeChunk).where(JavbotKnowledgeChunk.document_id == document.id))
    await db.delete(document)
    await db.commit()
    await asyncio.to_thread(storage.delete_document_object, storage_key=key)


def document_url(document: JavbotKnowledgeDocument) -> str:
    return storage.generate_presigned_document_url(storage_key=document.storage_key)


def document_dict(document: JavbotKnowledgeDocument) -> dict:
    return {
        "id": document.id, "title": document.title, "filename": document.filename,
        "size_bytes": document.size_bytes, "page_count": document.page_count, "status": document.status,
        "common": document.club_id is None, "created_at": document.created_at,
    }


# --- Ricerca --------------------------------------------------------------------------------------


def _query_terms(query: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", normalize(query))
    terms: list[str] = []
    for word in words:
        if len(word) < 3 or word in _STOPWORDS:
            continue
        # Un prefisso un po' più corto della parola: plurali e coniugazioni
        # ("inscricoes" trova "inscricao", "pagamenti" trova "pagamento").
        stem = word if len(word) <= 5 else word[: max(5, len(word) - 2)]
        if stem not in terms:
            terms.append(stem)
    return terms[:16]


async def search(
    db: AsyncSession, *, organization_id: uuid.UUID, club_id: uuid.UUID | None, query: str,
    limit: int = SEARCH_LIMIT,
) -> list[dict]:
    """I pezzi più pertinenti della base comune e di quella del club (mai di
    un altro club), i più rilevanti prima."""
    terms = _query_terms(query)
    if not terms:
        return []
    tsquery = func.to_tsquery("simple", " | ".join(f"{t}:*" for t in terms))
    vector = func.to_tsvector("simple", JavbotKnowledgeChunk.norm)
    rank = func.ts_rank_cd(vector, tsquery).label("rank")
    levels = [JavbotKnowledgeChunk.club_id.is_(None)]
    if club_id is not None:
        levels.append(JavbotKnowledgeChunk.club_id == club_id)
    stmt = (
        select(JavbotKnowledgeChunk, JavbotKnowledgeDocument.title, rank)
        .join(JavbotKnowledgeDocument, JavbotKnowledgeDocument.id == JavbotKnowledgeChunk.document_id)
        .where(JavbotKnowledgeChunk.organization_id == organization_id, or_(*levels), vector.op("@@")(tsquery))
        .order_by(rank.desc(), JavbotKnowledgeChunk.ordinal)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {"document": title, "page": chunk.page, "common": chunk.club_id is None, "text": chunk.text}
        for chunk, title, _rank in rows
    ]


#: Quanto è lungo un estratto mostrato senza modello: due o tre frasi.
EXCERPT_CHARS = 450


def _matched(terms: list[str], norm: str) -> int:
    """Quante parole della domanda (come prefisso) compaiono nel testo."""
    words = set(re.findall(r"[a-z0-9]+", norm))
    return sum(1 for t in terms if any(w.startswith(t) for w in words))


def excerpt(text: str, terms: list[str], limit: int = EXCERPT_CHARS) -> str:
    """Le frasi del pezzo che contengono più parole della domanda, con
    quelle vicine finché ci stanno: un pezzo intero è troppo da leggere sul
    telefono. Le frasi si tagliano sul testo vero, non su quello
    normalizzato, così accenti e a capo restano."""
    sentences = [x.strip() for x in re.split(r"(?<=[.!?;:])\s+|\n+", text) if x.strip()]
    if not sentences:
        return text[:limit]
    scores = [_matched(terms, normalize(x)) for x in sentences]
    best = max(range(len(sentences)), key=lambda i: (scores[i], -i))
    start = end = best
    length = len(sentences[best])
    while True:
        grown = False
        for i in (end + 1, start - 1):
            if 0 <= i < len(sentences) and length + len(sentences[i]) + 1 <= limit:
                start, end = min(start, i), max(end, i)
                length += len(sentences[i]) + 1
                grown = True
        if not grown:
            break
    out = " ".join(sentences[start:end + 1])
    if len(out) > limit:
        out = out[:limit].rsplit(" ", 1)[0] + "…"
    return ("… " if start > 0 else "") + out + (" …" if end < len(sentences) - 1 and not out.endswith("…") else "")


async def passages(
    db: AsyncSession, *, organization_id: uuid.UUID, club_id: uuid.UUID | None, query: str, limit: int = 2,
    strict: bool = False,
) -> list[dict]:
    """Gli estratti da mostrare quando risponde JAVBOT senza modello: i
    pezzi che contengono **almeno metà** delle parole della domanda (uno che
    ne ha solo una su quattro è rumore, meglio dire che non si sa), al più
    uno per documento e pagina, i più completi prima.

    `strict`: almeno due parole e almeno i due terzi. Serve quando la
    domanda ha già un'intenzione debole (una parola sola, planner.reply):
    i documenti la scavalcano solo se rispondono davvero."""
    terms = _query_terms(query)
    if not terms:
        return []
    hits = await search(db, organization_id=organization_id, club_id=club_id, query=query, limit=12)
    need = max(2, -(-len(terms) * 2 // 3)) if strict else max(1, -(-len(terms) // 2))
    seen: set[tuple[str, int]] = set()
    scored = []
    for rank, hit in enumerate(hits):
        matched = _matched(terms, normalize(hit["text"]))
        if matched < need or (hit["document"], hit["page"]) in seen:
            continue
        seen.add((hit["document"], hit["page"]))
        scored.append((-matched, rank, hit))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [
        {**hit, "excerpt": excerpt(hit["text"], terms)}
        for _m, _r, hit in scored[:limit]
    ]


async def has_documents(db: AsyncSession, *, organization_id: uuid.UUID, club_id: uuid.UUID | None) -> bool:
    levels = [JavbotKnowledgeDocument.club_id.is_(None)]
    if club_id is not None:
        levels.append(JavbotKnowledgeDocument.club_id == club_id)
    stmt = select(JavbotKnowledgeDocument.id).where(
        JavbotKnowledgeDocument.organization_id == organization_id, or_(*levels),
        JavbotKnowledgeDocument.status == "READY",
    ).limit(1)
    return (await db.execute(stmt)).first() is not None


async def catalog(db: AsyncSession, *, organization_id: uuid.UUID, club_id: uuid.UUID | None) -> list[str]:
    """I titoli dei documenti consultabili: il modello sa che cosa c'è
    prima di cercare, e lo cerca con le parole giuste."""
    levels = [JavbotKnowledgeDocument.club_id.is_(None)]
    if club_id is not None:
        levels.append(JavbotKnowledgeDocument.club_id == club_id)
    stmt = (
        select(JavbotKnowledgeDocument.title).where(
            JavbotKnowledgeDocument.organization_id == organization_id, or_(*levels),
            JavbotKnowledgeDocument.status == "READY",
        )
        .order_by(JavbotKnowledgeDocument.club_id.is_(None).desc(), JavbotKnowledgeDocument.title)
        .limit(MAX_DOCUMENTS)
    )
    return list((await db.execute(stmt)).scalars().all())


# --- Istruzioni -----------------------------------------------------------------------------------


async def get_instructions(db: AsyncSession, *, level: Level) -> str:
    stmt = _level_filter(select(JavbotInstructions.text), JavbotInstructions, level)
    return (await db.execute(stmt)).scalars().first() or ""


async def set_instructions(db: AsyncSession, *, level: Level, text: str, actor_user_id: uuid.UUID) -> str:
    text = (text or "").replace("\x00", "").strip()
    if len(text) > MAX_INSTRUCTIONS:
        raise KnowledgeError(
            f"Le istruzioni sono troppo lunghe (massimo {MAX_INSTRUCTIONS} caratteri): "
            "i testi lunghi caricali come PDF nella base di conoscenza."
        )
    row = (await db.execute(_level_filter(select(JavbotInstructions), JavbotInstructions, level))).scalars().first()
    if row is None:
        row = JavbotInstructions(organization_id=level.organization_id, club_id=level.club_id)
        db.add(row)
    row.text = text
    row.updated_at = utcnow()
    row.updated_by_user_id = actor_user_id
    await db.commit()
    return text

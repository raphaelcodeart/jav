"""Importa il gestionale che i club usano oggi ("judo-aev", PHP + MariaDB) in
Jav. Che cosa diventa che cosa: docs/legacy-judo-aev.md, "Come si importa".

    python -m app.legacy.judo_aev --dry-run      # legge tutto, scrive niente
    python -m app.legacy.judo_aev                # importa

Variabili: LEGACY_DB_HOST/PORT/USER/PASSWORD/NAME (il MariaDB della copia) e
LEGACY_UPLOADS (la cartella `judo/` del vecchio sito, per i file).

Le regole che contano:

- **Rilanciabile.** Ogni riga creata si registra in `legacy_import_map`
  (UNIQUE su fonte, tabella, id vecchio); rilanciando, una riga già
  importata si ritrova e si salta. Le righe nuove del vecchio gestionale si
  aggiungono.
- **Nessuna email, nessuna notifica.** Si scrive con il modello, non con i
  servizi che avvisano le famiglie. Le mensilità scoperte si emettono con
  `generate_monthly_fees` sui mesi passati, che non avvisa nessuno.
- **I soldi tornano al centesimo.** Ogni pagamento pagato diventa una prova
  di pagamento con lo stesso importo, e le quote che paga sono quelle che il
  vecchio aveva segnato pagate, con i loro importi. Ciò che restava da
  pagare di una quota annuale diventa una rata da pagare.
- **Niente dati nei log.** Il riepilogo finale conta righe e somme; nomi,
  email e documenti non escono.
"""

import argparse
import asyncio
import hashlib
import io
import json
import logging
import mimetypes
import os
import re
import secrets
import unicodedata
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.db import utcnow
from app.core.security import hash_password
from app.domains.club import belts as belts_catalog
from app.domains.club import seasons
from app.domains.club import service as club_service
from app.domains.club.models import (
    Club,
    ClubAthlete,
    ClubAttendance,
    ClubBeltGrade,
    ClubCompetition,
    ClubCompetitionEntry,
    ClubCourse,
    ClubCourseAthlete,
    ClubCourseSlot,
    ClubExpense,
    ClubFee,
    ClubPaymentProof,
    ClubPaymentProofFee,
    ClubPlan,
)
from app.domains.club.operations_models import (
    ClubCleaningLog,
    ClubEquipmentOrder,
    ClubExternalCoachFee,
    ClubReport,
)
from app.domains.club.records_models import (
    ClubApplication,
    ClubAthleteDocument,
    ClubAthleteRecord,
    ClubChangeRequest,
    ClubConsent,
)
from app.domains.club.scope import ClubScope
from app.domains.customers.models import Customer, CustomerProfile
from app.domains.rbac.models import Role, UserRole
from app.domains.users.models import User
from app.legacy.models import LegacyImportMap

logger = logging.getLogger("legacy.judo_aev")

SOURCE = "judo-aev"
MONTHS_PT = ("janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro",
             "outubro", "novembro", "dezembro")
#: Le quote annuali del vecchio: Sócio Judoca + Taxa de Faltas sono la
#: nostra iscrizione annuale; Sócio Pai/Mãe la quota socio del titolare.
ENROLLMENT_QUOTAS = ("quota_judoca", "taxa_faltas")
MEMBERSHIP_QUOTAS = ("quota_pai", "quota_mae")
METHOD = {"numerario": "CASH", "transferencia bancaria": "BANK_TRANSFER", "mb way": "MBWAY"}
EVENT_KIND = {"prova": "COMPETITION", "estagio": "STAGE", "arbitragem": "REFEREEING", "formacao": "EDUCATION",
              "reuniao": "MEETING", "outro": "OTHER"}
LEVEL = {"regional": "REGIONAL", "zonal": "ZONAL", "opens": "OPENS", "nacional": "NATIONAL",
         "taca_europa": "EUROPEAN_CUP", "campeonato_europa": "EUROPEAN_CHAMPIONSHIP",
         "campeonato_mundo": "WORLD_CHAMPIONSHIP", "jogos_olimpicos": "OLYMPIC_GAMES"}
MEDAL = {"ouro": 1, "prata": 2, "bronze": 3, "sem_medalha": 0}
TRANSPORT = {"clube": "CLUB", "proprio": "OWN", "a_confirmar": "TBC"}
KIMONO = {"judogi fij aprovado": "FIJ_APPROVED", "judogi de treino": "TRAINING",
          "judogi semi-competicao": "SEMI_COMPETITION", "judogi competicao (nao aprovado)": "COMPETITION_NOT_APPROVED"}
ORDER_STATUS = {"pendente": "PENDING", "em_preparacao": "IN_PREPARATION", "entregue": "DELIVERED",
                "cancelado": "CANCELLED"}
CHANGE_FIELD = {"grau": "BELT", "categoria_peso": "WEIGHT_CATEGORY", "peso": "WEIGHT"}
REQUEST_STATUS = {"pendente": "PENDING", "aprovado": "APPROVED", "rejeitado": "REJECTED"}
APPLICATION_STATUS = {"pendente": "PENDING", "aprovada": "APPROVED", "rejeitada": "REJECTED", "cancelada": "CANCELLED"}
DOC_KIND = {"seguranca social": "SOCIAL_SECURITY", "justificacao medica": "MEDICAL_JUSTIFICATION",
            "justificacao escolar": "SCHOOL_JUSTIFICATION", "declaracao de clube": "CLUB_DECLARATION",
            "autorizacao parental": "PARENTAL_AUTHORIZATION"}
ID_DOC = {"cartao de cidadao": "CITIZEN_CARD", "cartao cidadao": "CITIZEN_CARD", "passaporte": "PASSPORT",
          "autorizacao de residencia": "RESIDENCE_PERMIT", "titulo de residencia": "RESIDENCE_PERMIT",
          "certidao de nascimento": "BIRTH_CERTIFICATE"}
COACH_STATUS = {"pendente": "PENDING", "pago": "PAID", "parcial": "PARTIAL", "isento": "EXEMPT"}


def norm(value) -> str:
    """Minuscolo, senza accenti, spazi semplici."""
    folded = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", folded.lower()).strip()


def clean(value, limit: int | None = None) -> str | None:
    text = " ".join(str(value).split()) if value is not None else ""
    if not text:
        return None
    return text[:limit] if limit else text


def cents(value) -> int:
    return int((Decimal(str(value or 0)) * 100).quantize(Decimal(1)))


def split_name(full: str) -> tuple[str, str]:
    parts = (full or "").split()
    if not parts:
        return "Sem nome", "-"
    if len(parts) == 1:
        return parts[0][:80], "-"
    return parts[0][:80], " ".join(parts[1:])[:80]


def belt_code(grau: str | None) -> str | None:
    """Il grado del vecchio ("3º Kyu – Verde Azul (13 anos)") nel nostro codice."""
    g = norm(grau).replace("-", " ").replace("–", " ")
    if not g:
        return None
    dan = re.search(r"(\d+)\s*(?:o|º)?\s*dan", g)
    if dan:
        n = int(dan.group(1))
        return f"BLACK_{n}" if 1 <= n <= 10 else None
    bars = re.search(r"(\d+)\s*barras", g)
    if "branc" in g and bars:
        n = min((3, 6, 9, 12), key=lambda b: abs(b - int(bars.group(1))))
        return f"WHITE_BARS_{n}"
    for words, code in (
        (("branc", "amarel"), "WHITE_YELLOW"), (("amarel", "laranja"), "YELLOW_ORANGE"),
        (("laranja", "verde"), "ORANGE_GREEN"), (("verde", "azul"), "GREEN_BLUE"),
        (("azul", "castanh"), "BLUE_BROWN"),
    ):
        if all(w in g for w in words):
            return code
    for word, code in (("castanh", "BROWN"), ("azul", "BLUE"), ("verde", "GREEN"), ("laranja", "ORANGE"),
                       ("amarel", "YELLOW"), ("branc", "WHITE")):
        if word in g:
            return code
    return None


def height_cm(value) -> int | None:
    digits = re.findall(r"\d+(?:[.,]\d+)?", str(value or ""))
    if not digits:
        return None
    number = float(digits[0].replace(",", "."))
    cm = round(number * 100) if number < 3 else round(number)
    return cm if 40 < cm < 250 else None


def months_of(meses_ref: str | None) -> list[int]:
    out = []
    for token in re.split(r"[,;]", meses_ref or ""):
        name = norm(re.sub(r"\d{4}", "", token))
        if name in MONTHS_PT:
            out.append(MONTHS_PT.index(name) + 1)
    return out


def files_of(path_value: str | None) -> list[str]:
    """`ficheiro_path` è una stringa o un array JSON di path relativi a uploads/."""
    if not path_value:
        return []
    text = path_value.strip()
    if text.startswith("["):
        try:
            return [p for p in json.loads(text) if p]
        except json.JSONDecodeError:
            return []
    return [text]


@dataclass
class Totals:
    counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    money: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    skipped: dict[str, int] = field(default_factory=lambda: defaultdict(int))


class Legacy:
    """Il MariaDB della copia, in sola lettura."""

    def __init__(self) -> None:
        import pymysql

        self.conn = pymysql.connect(
            host=os.environ.get("LEGACY_DB_HOST", "legacy-mariadb"),
            port=int(os.environ.get("LEGACY_DB_PORT", "3306")),
            user=os.environ.get("LEGACY_DB_USER", "root"),
            password=os.environ["LEGACY_DB_PASSWORD"],
            database=os.environ.get("LEGACY_DB_NAME", "judo_aev"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )

    def rows(self, sql: str, *args) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            # MySQL accetta "0000-00-00" come data: arriva come stringa, ed è
            # un "non c'è".
            return [
                {k: (None if isinstance(v, str) and v.startswith("0000-00-00") else v) for k, v in row.items()}
                for row in cur.fetchall()
            ]


class Importer:
    def __init__(self, db: AsyncSession, legacy: Legacy, *, uploads: Path, dry_run: bool) -> None:
        self.db = db
        self.legacy = legacy
        self.uploads = uploads
        self.dry_run = dry_run
        self.totals = Totals()
        self.clubs: dict[int, Club] = {}
        self.roles: dict[str, uuid.UUID] = {}
        self.missing_files: list[str] = []
        #: Quanto di ogni prova è già stato attribuito a una quota: alla fine
        #: ogni prova deve avere quote per tutto il suo importo, perché la
        #: contabilità conta le quote pagate (accounting.py).
        self.allocated: dict[uuid.UUID, int] = defaultdict(int)
        #: Le prove importate di questo club: (riga vecchia, prova, atleta).
        self.proofs: dict[uuid.UUID, tuple[dict, ClubPaymentProof, ClubAthlete]] = {}

    # --- La corrispondenza ------------------------------------------------------------------------

    async def mapped(self, table: str, legacy_id) -> uuid.UUID | None:
        return (await self.db.execute(
            select(LegacyImportMap.target_id).where(
                LegacyImportMap.source == SOURCE, LegacyImportMap.source_table == table,
                LegacyImportMap.source_id == str(legacy_id),
            )
        )).scalar_one_or_none()

    def remember(self, table: str, legacy_id, target_table: str, target_id: uuid.UUID) -> None:
        self.db.add(LegacyImportMap(source=SOURCE, source_table=table, source_id=str(legacy_id),
                                    target_table=target_table, target_id=target_id))
        self.totals.counts[target_table] += 1

    # --- I file -----------------------------------------------------------------------------------

    def read_file(self, relative: str) -> tuple[bytes, str, str] | None:
        """(byte, content type, nome) di un file del vecchio sito; None se manca."""
        rel = relative.replace("\\/", "/").lstrip("/")
        rel = rel.split("/uploads/", 1)[-1] if "/uploads/" in rel else rel
        rel = rel[len("uploads/"):] if rel.startswith("uploads/") else rel
        path = (self.uploads / "uploads" / rel).resolve()
        if not str(path).startswith(str(self.uploads.resolve())) or not path.is_file():
            self.missing_files.append(rel)
            return None
        data = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix.lower() == ".heic":
            content_type = "image/heic"
        return data, content_type, path.name

    @staticmethod
    def merge_to_pdf(files: list[tuple[bytes, str, str]]) -> bytes:
        """Più ricevute di un pagamento in un PDF solo: la prova di Jav ha un
        file, e così nessuna pagina va persa."""
        from pypdf import PdfReader, PdfWriter
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas

        writer = PdfWriter()
        for data, content_type, _name in files:
            if content_type == "application/pdf":
                for page in PdfReader(io.BytesIO(data)).pages:
                    writer.add_page(page)
                continue
            buffer = io.BytesIO()
            pdf = canvas.Canvas(buffer, pagesize=A4)
            image = ImageReader(io.BytesIO(data))
            iw, ih = image.getSize()
            scale = min((A4[0] - 40) / iw, (A4[1] - 40) / ih, 1)
            pdf.drawImage(image, 20, A4[1] - 20 - ih * scale, iw * scale, ih * scale)
            pdf.showPage()
            pdf.save()
            for page in PdfReader(io.BytesIO(buffer.getvalue())).pages:
                writer.add_page(page)
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()

    def store_private(self, data: bytes, content_type: str, prefix: str) -> str:
        if self.dry_run:
            return f"dry-run/{prefix}/{uuid.uuid4().hex}"
        # stash_private_file: il bucket privato, senza i controlli di formato
        # del caricamento dal browser (una HEIC del vecchio resta una HEIC).
        return storage.stash_private_file(file_bytes=data, content_type=content_type, key_prefix=prefix)

    def store_public(self, data: bytes, content_type: str, prefix: str) -> str | None:
        if self.dry_run:
            return f"https://dry-run/{prefix}"
        try:
            return storage.upload_documentation_attachment(
                file_bytes=data, content_type=content_type, key_prefix=prefix,
            )
        except storage.UploadValidationError:
            return None

    # --- Il giro ----------------------------------------------------------------------------------

    async def run(self) -> Totals:
        await self.load_context()
        await self.import_events()
        for legacy_id, club in self.clubs.items():
            scope = ClubScope(organization_id=club.organization_id, club_id=club.id)
            await self.configure_club(legacy_id, club)
            await self.import_staff(legacy_id, scope)
            await self.import_athletes(legacy_id, scope)
            await self.import_payments(legacy_id, scope)
            await self.import_annual_quotas(legacy_id, scope)
            await self.import_entries(legacy_id, scope)
            await self.import_equipment_orders(legacy_id, scope)
            await self.import_courses_and_attendance(legacy_id, scope)
            await self.import_documents(legacy_id, scope)
            await self.import_consents(legacy_id, scope)
            await self.import_change_requests(legacy_id, scope)
            await self.import_applications(legacy_id, scope)
            await self.import_operations(legacy_id, scope)
            await self.import_reports(legacy_id, scope)
            await self.settle_proofs(scope)
            await self.db.flush()
            await self.emit_open_months(scope)
        return self.totals

    async def load_context(self) -> None:
        ours = {norm(c.name): c for c in (await self.db.execute(select(Club))).scalars()}
        for row in self.legacy.rows("SELECT id, nome FROM clubes WHERE ativo = 1"):
            club = ours.get(norm(row["nome"]))
            if club is not None:
                self.clubs[row["id"]] = club
            else:
                # Il club 4 (Judo Arte e Vida) è la piattaforma, non un club.
                self.totals.skipped[f"club senza corrispondenza: {row['id']}"] += 1
        for role in (await self.db.execute(select(Role).where(Role.code.in_(("SECRETARY", "CUSTOMER"))))).scalars():
            self.roles[role.code] = role.id
        if set(self.roles) != {"SECRETARY", "CUSTOMER"}:
            raise RuntimeError("Mancano i ruoli SECRETARY / CUSTOMER: lancia app.seed.bootstrap.")
        self.organization_id = next(iter(self.clubs.values())).organization_id
        self.today = utcnow().date()

    async def configure_club(self, legacy_id: int, club: Club) -> None:
        """Gli escalão come li applica il club, e i piani su 12 mesi: nel
        vecchio luglio e agosto si pagano (decisione del titolare)."""
        tiers = {}
        for row in self.legacy.rows("SELECT nome, valor FROM descontos WHERE tipo = 'percentagem' AND ativo = 1"):
            m = re.match(r"escalao ([a-d]) seg", norm(row["nome"]))
            if m:
                tiers[m.group(1).upper()] = int(Decimal(row["valor"]))
        if tiers:
            settings = dict(club.settings or {})
            pricing = dict(settings.get("pricing") or {})
            pricing["tier_discount_pct"] = {**(pricing.get("tier_discount_pct") or {}), **tiers}
            settings["pricing"] = pricing
            club.settings = settings
        for plan in (await self.db.execute(select(ClubPlan).where(ClubPlan.club_id == club.id))).scalars():
            plan.billing_months = list(range(1, 13))

    # --- Utenti -----------------------------------------------------------------------------------

    async def _user_by_email(self, email: str) -> User | None:
        return (await self.db.execute(
            select(User).where(User.organization_id == self.organization_id, func.lower(User.email) == email)
        )).scalar_one_or_none()

    async def _new_user(self, *, email: str, club_id: uuid.UUID, role: str) -> User:
        # Nessuna password: entrano con il codice via email (o "password
        # dimenticata"). Una password casuale che nessuno conosce.
        user = User(organization_id=self.organization_id, club_id=club_id, email=email,
                    password_hash=hash_password(secrets.token_urlsafe(32)), status="ACTIVE")
        self.db.add(user)
        await self.db.flush()
        self.db.add(UserRole(user_id=user.id, organization_id=self.organization_id, role_id=self.roles[role]))
        return user

    async def import_staff(self, legacy_id: int, scope: ClubScope) -> None:
        for row in self.legacy.rows(
            "SELECT id, nome, email FROM utilizadores WHERE nivel = 'clube' AND ativo = 1 AND clube_id = %s", legacy_id
        ):
            if await self.mapped("utilizadores", row["id"]):
                continue
            email = norm(row["email"])
            if "@" not in email:
                self.totals.skipped["staff senza email"] += 1
                continue
            user = await self._user_by_email(email) or await self._new_user(
                email=email, club_id=scope.club_id, role="SECRETARY"
            )
            self.remember("utilizadores", row["id"], "users", user.id)

    async def staff_user(self, legacy_user_id) -> uuid.UUID | None:
        return await self.mapped("utilizadores", legacy_user_id) if legacy_user_id else None

    async def guardian_for(self, email: str | None, *, scope: ClubScope, legacy_athlete_id: int,
                           customer_name: tuple[str, str]) -> User:
        key = norm(email) if email and "@" in email else f"sem-email-{legacy_athlete_id}@judo-aev.invalid"
        found = await self.mapped("portal_email", key)
        if found:
            return await self.db.get(User, found)
        user = await self._user_by_email(key)
        if user is None:
            user = await self._new_user(email=key, club_id=scope.club_id, role="CUSTOMER")
            customer = Customer(organization_id=self.organization_id, user_id=user.id, kind="PRIVATE", email=key)
            self.db.add(customer)
            await self.db.flush()
            self.db.add(CustomerProfile(customer_id=customer.id, first_name=customer_name[0],
                                        last_name=customer_name[1]))
        self.remember("portal_email", key, "users", user.id)
        return user

    # --- Atleti -----------------------------------------------------------------------------------

    async def import_athletes(self, legacy_id: int, scope: ClubScope) -> None:
        plans = [p for p in await club_service.list_plans(self.db, scope=scope) if p.active]
        discounts = {r["id"]: r for r in self.legacy.rows("SELECT * FROM descontos")}
        quota_codes = {r["id"]: r["codigo"] for r in self.legacy.rows("SELECT id, codigo FROM quotas_precos")}
        rows = self.legacy.rows("SELECT * FROM atletas WHERE clube_id = %s ORDER BY id", legacy_id)
        selves: set[uuid.UUID] = set()
        for row in rows:
            if await self.mapped("atletas", row["id"]):
                continue
            if not row["data_nascimento"]:
                self.totals.skipped["atleta senza data di nascita"] += 1
                continue
            first, last = split_name(row["nome"])
            age = seasons.age_on(row["data_nascimento"], self.today)
            adult = age >= 18
            email = row["portal_email"] or row["email"]
            responsible = split_name(row["nome_responsavel"]) if (not adult and row["nome_responsavel"]) else (first, last)
            guardian = await self.guardian_for(email, scope=scope, legacy_athlete_id=row["id"],
                                               customer_name=responsible)
            own_email = norm(row["email"]) if row["email"] else ""
            is_self = adult and guardian.id not in selves and (not row["email"] or own_email == norm(email)) and (
                await self.db.execute(select(func.count()).select_from(ClubAthlete).where(
                    ClubAthlete.guardian_user_id == guardian.id, ClubAthlete.is_self.is_(True)))
            ).scalar_one() == 0
            if is_self:
                selves.add(guardian.id)
            joined = date(row["ano_inscricao"] or (row["criado_em"] or utcnow()).year,
                          min(max(row["mes_inscricao"] or 1, 1), 12), 1)
            left = row["ativo"] != 1 or row["apagado"] == 1
            athlete = ClubAthlete(
                **scope.columns(), guardian_user_id=guardian.id, user_id=guardian.id if is_self else None,
                first_name=first, last_name=last, birth_date=row["data_nascimento"],
                sex="F" if row["genero"] == "F" else "M", fiscal_code=clean(row["nif"], 16), is_self=is_self,
                status="LEFT" if left else "ACTIVE",
                weight_kg=row["peso"] if row["peso"] and 10 < row["peso"] < 250 else None,
                federation_number=clean(row["licenca_fpj"], 32), joined_on=joined,
                left_on=(row["apagado_em"] or row["modificado_em"] or utcnow()).date() if left else None,
                member_number=clean(row["num_socio"], 20), kimono_name=clean(row["nome_fato"], 100),
                height_cm=height_cm(row["altura"]), nationality=clean(row["nacionalidade"], 80),
                # "-81" scritto nel peso è una categoria, non un peso.
                weight_category=clean(row["categoria_peso"], 30) or (
                    f"{row['peso']:.0f}kg" if row["peso"] and row["peso"] < 0 else None),
                federation_renewal_year=row["ano_revalidacao_fpj"] or None,
                created_at=row["criado_em"] or utcnow(),
            )
            plan = club_service.pick_plan(plans, age=seasons.federal_age(athlete.birth_date, self.today.year))
            athlete.plan_id = plan.id if plan else None
            self._apply_discounts(athlete, row, discounts, quota_codes)
            self.db.add(athlete)
            await self.db.flush()
            self.remember("atletas", row["id"], "club_athletes", athlete.id)
            self.db.add(self._record(athlete, row))
            belt = belt_code(row["grau"])
            self.db.add(ClubBeltGrade(**scope.columns(), athlete_id=athlete.id, grade=belt or belts_catalog.STARTING_BELT,
                                      awarded_on=joined, note="Dal gestionale precedente" if belt else None))
            if row["multa_ativa"] and row["multa_valor"]:
                self.db.add(ClubFee(
                    **scope.columns(), athlete_id=athlete.id, kind="FINE", period=f"legacy-multa-{row['id']}",
                    description=(clean(row["multa_descricao"], 200) or "Multa"), amount_cents=cents(row["multa_valor"]),
                    gross_amount_cents=cents(row["multa_valor"]), due_date=self.today, status="DUE",
                ))
                self.totals.money["multe da pagare"] += cents(row["multa_valor"])

    def _apply_discounts(self, athlete: ClubAthlete, row: dict, discounts: dict, quota_codes: dict) -> None:
        links = self.legacy.rows("SELECT * FROM atleta_descontos WHERE atleta_id = %s AND ativo = 1", row["id"])
        monthly = [d for d in links if d["tipo"] == "mensalidade"]
        ids = [d["desconto_id"] for d in monthly if d["desconto_id"]] or ([row["desconto_id"]] if row["desconto_id"] else [])
        if any(d["nao_aplicavel"] for d in monthly):
            athlete.exempt_monthly = True
        for discount_id in ids:
            d = discounts.get(discount_id)
            if not d:
                continue
            name = norm(d["nome"])
            tier = re.match(r"escalao ([a-d]) seg", name)
            if tier:
                athlete.social_tier = tier.group(1).upper()
            elif d["tipo"] == "percentagem" and Decimal(d["valor"]) >= 100:
                athlete.exempt_monthly = True
            elif "familia" in name:
                pass  # da noi lo sconto famiglia è automatico (pricing.py)
            elif athlete.custom_discount_kind is None:
                athlete.custom_discount_kind = "PERCENT" if d["tipo"] == "percentagem" else "FIXED"
                athlete.custom_discount_value = int(Decimal(d["valor"])) if d["tipo"] == "percentagem" else cents(d["valor"])
                athlete.custom_discount_scope = "MONTHLY"
                athlete.custom_discount_note = clean(d["etiqueta"] or d["nome"], 200)
        # Le quote obbligatorie (Sócio Judoca e Taxa de Faltas) entrambe "não
        # aplicável" o al 100%: esente dalle quote annuali.
        exempt_codes = set()
        for link in (d for d in links if d["tipo"] == "quota"):
            d = discounts.get(link["desconto_id"]) if link["desconto_id"] else None
            if link["nao_aplicavel"] or (d and d["tipo"] == "percentagem" and Decimal(d["valor"]) >= 100):
                exempt_codes.add(quota_codes.get(link["quota_id"]))
        if set(ENROLLMENT_QUOTAS) <= exempt_codes:
            athlete.exempt_annual = True
        if row["desconto_extra_ativo"] and row["desconto_extra_valor"]:
            kind = "PERCENT" if row["desconto_extra_tipo"] == "percentagem" else "FIXED"
            value = int(Decimal(row["desconto_extra_valor"])) if kind == "PERCENT" else cents(row["desconto_extra_valor"])
            scope = {"mensalidade": "MONTHLY", "quotas": "ANNUAL", "ambos": "BOTH"}.get(row["desconto_extra_aplica"], "MONTHLY")
            if kind == "PERCENT" and value >= 100:
                athlete.exempt_monthly = athlete.exempt_monthly or scope in ("MONTHLY", "BOTH")
                athlete.exempt_annual = athlete.exempt_annual or scope in ("ANNUAL", "BOTH")
            else:
                athlete.custom_discount_kind, athlete.custom_discount_value = kind, min(value, 100) if kind == "PERCENT" else value
                athlete.custom_discount_scope = scope
                athlete.custom_discount_note = clean(row["desconto_extra_descricao"], 200) or "Sconto"

    @staticmethod
    def _record(athlete: ClubAthlete, row: dict) -> ClubAthleteRecord:
        def doc_type(value):
            return ID_DOC.get(norm(value), "OTHER") if value else None

        return ClubAthleteRecord(
            athlete_id=athlete.id, organization_id=athlete.organization_id, club_id=athlete.club_id,
            address=clean(row["morada"], 250), postal_code=clean(row["codigo_postal"], 20),
            city=clean(row["localidade"], 100), phone=clean(row["telefone"], 30), mobile=clean(row["telemovel"], 30),
            email=clean(row["email"], 150), marital_status=clean(row["estado_civil"], 30),
            id_document_type=doc_type(row["tipo_doc"]), id_document_number=clean(row["num_documento"], 50),
            id_document_check_digits=clean(row["digitos_verificacao"], 20), id_document_expires_on=row["validade_doc"],
            passport_number=clean(row["num_passaporte"], 50), passport_country=clean(row["pais_passaporte"], 60),
            passport_expires_on=row["validade_passaporte"],
            guardian_name=clean(row["nome_responsavel"], 200), guardian_phone=clean(row["tel_responsavel"], 30),
            father_phone=clean(row["tel_pai"], 30), mother_phone=clean(row["tel_mae"], 30),
            guardian_fiscal_code=clean(row["nif_resp"], 20), guardian_id_document_type=doc_type(row["tipo_doc_resp"]),
            guardian_id_document_number=clean(row["num_documento_resp"], 50),
            guardian_id_document_check_digits=clean(row["digitos_verificacao_resp"], 20),
            guardian_id_document_expires_on=row["validade_doc_resp"],
            guardian_passport_number=clean(row["num_passaporte_resp"], 50),
            guardian_passport_country=clean(row["pais_passaporte_resp"], 60),
            guardian_passport_expires_on=row["validade_passaporte_resp"], notes=row["notas"] or None,
        )

    def _athlete_by_name(self, legacy_club_id: int, name: str | None) -> int | None:
        """Un pagamento scritto a mano senza atleta collegato: l'atleta del
        club con lo stesso nome (prima intero, poi nome + ultimo cognome), solo
        se è uno."""
        wanted = norm(name)
        if not wanted:
            return None
        rows = self.legacy.rows("SELECT id, nome FROM atletas WHERE clube_id = %s", legacy_club_id)
        exact = [r["id"] for r in rows if norm(r["nome"]) == wanted]
        if len(exact) == 1:
            return exact[0]
        parts = wanted.split()
        if len(parts) >= 2:
            loose = [r["id"] for r in rows if norm(r["nome"]).split()[:1] == parts[:1]
                     and norm(r["nome"]).split()[-1:] == parts[-1:]]
            if len(loose) == 1:
                return loose[0]
        return None

    async def athlete(self, legacy_athlete_id) -> ClubAthlete | None:
        target = await self.mapped("atletas", legacy_athlete_id) if legacy_athlete_id else None
        return await self.db.get(ClubAthlete, target) if target else None

    # --- Pagamenti --------------------------------------------------------------------------------

    async def import_payments(self, legacy_id: int, scope: ClubScope) -> None:
        """Ogni pagamento pagato o rifiutato diventa una prova di pagamento;
        le mensilità che paga diventano quote MONTHLY pagate."""
        used_numbers: set[str] = set()
        rows = self.legacy.rows(
            "SELECT * FROM pagamentos WHERE clube_id = %s AND apagado = 0 AND estado IN ('pago','rejeitado') "
            "ORDER BY data_pagamento, id", legacy_id,
        )
        for row in rows:
            if await self.mapped("pagamentos", row["id"]):
                continue
            athlete = await self.athlete(row["atleta_id"] or self._athlete_by_name(legacy_id, row["nome_atleta"]))
            if athlete is None:
                self.totals.skipped["pagamento senza atleta"] += 1
                self.totals.money["non importati (senza atleta)"] += cents(row["valor"])
                continue
            proof = await self._proof(row, athlete, scope, used_numbers)
            self.remember("pagamentos", row["id"], "club_payment_proofs", proof.id)
            self.proofs[proof.id] = (row, proof, athlete)
            if row["estado"] == "pago":
                self.totals.money[f"pagato · {row['tipo']}"] += cents(row["valor"])
            if row["tipo"] == "mensalidade" and row["estado"] == "pago":
                await self._monthly_fees(row, athlete, proof, scope)

    async def _proof(self, row: dict, athlete: ClubAthlete, scope: ClubScope, used: set[str]) -> ClubPaymentProof:
        method = METHOD.get(norm(row["forma_pagamento"]), "BANK_TRANSFER")
        files = [f for f in (self.read_file(p) for p in files_of(row["ficheiro_path"])) if f]
        storage_key = filename = content_type = None
        if files:
            if len(files) == 1:
                data, content_type, filename = files[0]
            else:
                data, content_type, filename = self.merge_to_pdf(files), "application/pdf", f"comprovativos-{row['id']}.pdf"
            storage_key = self.store_private(data, content_type, f"club-payment-proofs/{athlete.guardian_user_id}")
        if storage_key is None and method != "CASH":
            # Un bonifico senza file nel vecchio (segnato a mano dalla
            # segreteria): da noi una prova senza file è dei contanti, quindi
            # resta un bonifico con la nota.
            method = "CASH"
        note = clean(row["observacoes"], 500)
        receiver = None
        if note and note.lower().startswith("entregue a:"):
            receiver = clean(note.split("|", 1)[0].split(":", 1)[1], 120)
        if method == "CASH":
            receiver = receiver or "Secretaria do clube"
        number = clean(row["num_comprovativo"], 24)
        if number in used:
            number = f"{number}-{row['id']}"[:24]
        if number:
            used.add(number)
        reviewed_by = None
        proof = ClubPaymentProof(
            **scope.columns(), uploaded_by_user_id=athlete.guardian_user_id, storage_key=storage_key,
            original_filename=(clean(filename, 255) if storage_key else None), content_type=content_type,
            amount_cents=cents(row["valor"]), credit_cents=0, note=note,
            status="ACCEPTED" if row["estado"] == "pago" else "REJECTED",
            reviewed_by_user_id=reviewed_by, reviewed_at=row["verificado_em"],
            rejection_reason=clean(row["motivo_rejeicao"], 500) if row["estado"] == "rejeitado" else None,
            method=method, cash_received_by_name=receiver if method == "CASH" else None,
            receipt_number=number, paid_on=row["data_pagamento"], created_at=row["criado_em"] or utcnow(),
        )
        self.db.add(proof)
        await self.db.flush()
        return proof

    def _paid_at(self, row: dict) -> datetime:
        when = row["data_pagamento"] or (row["criado_em"] or utcnow()).date()
        return datetime.combine(when, time(12, 0)).astimezone()

    async def _pay(self, fee: ClubFee, proof: ClubPaymentProof, row: dict, amount: int | None = None) -> None:
        """Segna pagata la quota con la prova; `amount` è la parte della prova
        che va a questa quota (default: tutta la quota)."""
        self.allocated[proof.id] += fee.amount_cents if amount is None else amount
        fee.status = "PAID"
        fee.paid_at = self._paid_at(row)
        fee.paid_via_proof_id = proof.id
        fee.paid_by_user_id = proof.uploaded_by_user_id
        fee.payment_method = proof.method
        fee.cash_received_by_name = proof.cash_received_by_name
        self.db.add(ClubPaymentProofFee(proof_id=proof.id, fee_id=fee.id))

    async def _fee(self, **values) -> ClubFee:
        fee = ClubFee(**values)
        self.db.add(fee)
        await self.db.flush()
        return fee

    async def _monthly_fees(self, row: dict, athlete: ClubAthlete, proof: ClubPaymentProof, scope: ClubScope) -> None:
        parts = self.legacy.rows(
            "SELECT mes, ano FROM prestacoes_mensalidades WHERE pagamento_id = %s AND estado = 'pago'", row["id"]
        )
        # I mesi delle rate pagate e quelli scritti sul pagamento: il vecchio
        # considera pagato un mese se compare nell'una o nell'altra.
        year = int(row["epoca"] or row["data_pagamento"].year)
        found = sorted(
            {(int(p["ano"]), MONTHS_PT.index(norm(p["mes"])) + 1) for p in parts if norm(p["mes"]) in MONTHS_PT}
            | {(year, m) for m in months_of(row["meses_ref"])}
        )
        if not found:
            # Nessun mese scritto: non si indovina. Il pagamento resta una
            # mensilità "senza mese" (settle_proofs), e i mesi scoperti
            # restano scoperti, come nel vecchio.
            self.totals.skipped["mensilità senza mesi"] += 1
            return
        # L'importo vero del pagamento, diviso sui mesi (il resto dei
        # centesimi sull'ultimo): le rate del vecchio non sempre tornano.
        total = proof.amount_cents
        share = total // len(found)
        months = [(y, m, share + (total - share * len(found) if i == len(found) - 1 else 0))
                  for i, (y, m) in enumerate(found)]
        plan = await self.db.get(ClubPlan, athlete.plan_id) if athlete.plan_id else None
        for year, month, amount in months:
            period = f"{year:04d}-{month:02d}"
            fee = (await self.db.execute(select(ClubFee).where(
                ClubFee.athlete_id == athlete.id, ClubFee.kind == "MONTHLY", ClubFee.period == period
            ))).scalar_one_or_none()
            if fee is not None:
                # Un mese pagato in due volte: lo stesso mese, il secondo pagamento si somma.
                fee.amount_cents += amount
                fee.gross_amount_cents = max(fee.gross_amount_cents or 0, fee.amount_cents)
                self.db.add(ClubPaymentProofFee(proof_id=proof.id, fee_id=fee.id))
                self.allocated[proof.id] += amount
                continue
            fee = await self._fee(
                **scope.columns(), athlete_id=athlete.id, kind="MONTHLY", period=period,
                description=f"Quota di {seasons.month_label(year, month)}", amount_cents=amount,
                gross_amount_cents=max(amount, plan.monthly_fee_cents if plan else amount),
                discount_cents=max(0, (plan.monthly_fee_cents if plan else amount) - amount),
                due_date=date(year, month, plan.due_day if plan else 15), status="DUE",
            )
            await self._pay(fee, proof, row, amount)

    async def import_annual_quotas(self, legacy_id: int, scope: ClubScope) -> None:
        """Le quote annuali per atleta e anno: le rate pagate (con la loro
        prova) e, se resta qualcosa, una rata da pagare."""
        lines = self.legacy.rows(
            "SELECT pq.*, qp.codigo FROM pagamentos_quotas pq JOIN quotas_precos qp ON qp.id = pq.quota_id "
            "WHERE pq.clube_id = %s ORDER BY pq.atleta_id, pq.ano", legacy_id,
        )
        groups: dict[tuple, list[dict]] = defaultdict(list)
        for line in lines:
            athlete = await self.athlete(line["atleta_id"])
            if athlete is None:
                continue
            if line["codigo"] in ENROLLMENT_QUOTAS:
                groups[("ENROLLMENT", athlete.id, line["ano"])].append(line)
            elif line["codigo"] in MEMBERSHIP_QUOTAS:
                groups[("MEMBERSHIP", athlete.guardian_user_id, line["ano"])].append(line)
        for (kind, owner_id, year), group in groups.items():
            key = f"{kind}:{owner_id}:{year}"
            if await self.mapped("quotas", key):
                continue
            expected = sum(cents(g["valor_total"]) for g in group)
            parts = self.legacy.rows(
                "SELECT * FROM prestacoes_quotas WHERE pagamento_quota_id IN %s AND estado = 'pago' "
                "ORDER BY pagamento_id, num_prestacao", tuple(g["id"] for g in group),
            )
            by_payment: dict[int, int] = defaultdict(int)
            for p in parts:
                by_payment[p["pagamento_id"]] += cents(p["valor"])
            paid_total = sum(by_payment.values())
            remainder = max(0, expected - paid_total)
            instalments = [(pid, amount) for pid, amount in by_payment.items()] + ([(None, remainder)] if remainder else [])
            if not instalments:
                continue
            athlete = await self.db.get(ClubAthlete, owner_id) if kind == "ENROLLMENT" else None
            label = "Iscrizione" if kind == "ENROLLMENT" else "Quota socio genitore"
            total = len(instalments)
            first_fee = None
            for number, (payment_id, amount) in enumerate(instalments, start=1):
                proof_id = await self.mapped("pagamentos", payment_id) if payment_id else None
                proof = await self.db.get(ClubPaymentProof, proof_id) if proof_id else None
                if payment_id and proof is None:
                    # Una rata segnata pagata con un pagamento che non c'è più
                    # (cancellato): resta da pagare.
                    payment_id = None
                fee = await self._fee(
                    **scope.columns(), kind=kind, period=str(year) if total == 1 else f"{year}/{number}",
                    athlete_id=athlete.id if athlete else None, guardian_user_id=None if athlete else owner_id,
                    installment_no=None if total == 1 else number, installments_total=None if total == 1 else total,
                    description=f"{label} {year}" + (f" · rata {number}/{total}" if total > 1 else ""),
                    amount_cents=amount, gross_amount_cents=amount,
                    due_date=date(int(year), min(12, 1 + number), 15), status="DUE",
                )
                first_fee = first_fee or fee
                if proof is not None and proof.status == "ACCEPTED":
                    await self._pay(fee, proof, {"data_pagamento": proof.paid_on, "criado_em": proof.created_at})
                else:
                    self.totals.money[f"da pagare · {kind}"] += amount
            self.remember("quotas", key, "club_fees", first_fee.id)

    # --- Eventi e iscrizioni ----------------------------------------------------------------------

    async def import_events(self) -> None:
        for row in self.legacy.rows("SELECT * FROM eventos WHERE apagado = 0 ORDER BY data_inicio"):
            if await self.mapped("eventos", row["id"]):
                continue
            club_id = self.clubs[row["clube_id"]].id if row["clube_id"] in self.clubs else None
            starts = row["data_inicio"]
            ends = max(row["data_fim"] or starts, starts)
            deadline = min(row["prazo_inscricao"] or starts, starts)
            kind = EVENT_KIND.get(row["tipo"], "OTHER")
            status = {"aberto": "OPEN", "fechado": "CLOSED", "cancelado": "CLOSED"}[row["estado"]]
            if ends < self.today and status != "OPEN":
                status = "DONE"
            elif deadline < self.today and status == "OPEN":
                status = "CLOSED"
            circular_url = circular_name = None
            if row["circular_path"]:
                found = self.read_file(row["circular_path"])
                if found:
                    data, content_type, _name = found
                    circular_url = self.store_public(data, content_type, "network-events")
                    circular_name = clean(row["circular_nome"], 255)
            comp = ClubCompetition(
                organization_id=self.organization_id, club_id=club_id, name=clean(row["nome"], 200) or "Evento",
                description=row["descricao"] or None, starts_on=starts, ends_on=ends,
                location=clean(row["local"], 200), organizer=clean(row["organizador"], 200),
                level=LEVEL.get(row["nivel_competicao"] or "", "CLUB"), registration_deadline=deadline,
                fee_cents=cents(row["valor_inscricao"]), requires_agonistic_certificate=False,
                status=status, kind=kind, transport_mode=TRANSPORT.get(row["transporte"] or "", "TBC"),
                transport_info=clean(row["transporte_notas"], 300), starts_at_time=row["hora_inicio"] and _time(row["hora_inicio"]),
                ends_at_time=row["hora_fim"] and _time(row["hora_fim"]),
                registration_deadline_time=row["prazo_inscricao_hora"] and _time(row["prazo_inscricao_hora"]),
                places=row["vagas"] if row["vagas"] and row["vagas"] > 0 else None,
                age_groups=[g.strip() for g in (row["escaloes"] or "").split(",") if g.strip()],
                circular_url=circular_url, circular_filename=circular_name,
                created_at=row["criado_em"] or utcnow(),
            )
            self.db.add(comp)
            await self.db.flush()
            self.remember("eventos", row["id"], "club_competitions", comp.id)

    async def import_entries(self, legacy_id: int, scope: ClubScope) -> None:
        rows = self.legacy.rows(
            "SELECT * FROM inscricoes_eventos WHERE clube_id = %s AND apagado = 0 AND tipo_participante = 'atleta'",
            legacy_id,
        )
        for row in rows:
            if await self.mapped("inscricoes_eventos", row["id"]):
                continue
            athlete = await self.athlete(row["atleta_id"])
            comp_id = await self.mapped("eventos", row["evento_id"])
            if athlete is None or comp_id is None:
                self.totals.skipped["iscrizione senza atleta o evento"] += 1
                continue
            comp = await self.db.get(ClubCompetition, comp_id)
            twin = (await self.db.execute(select(ClubCompetitionEntry.id).where(
                ClubCompetitionEntry.competition_id == comp.id, ClubCompetitionEntry.athlete_id == athlete.id,
            ))).scalar_one_or_none()
            if twin is not None:
                # Lo stesso atleta iscritto due volte allo stesso evento: da noi
                # l'iscrizione è una (vincolo UNIQUE), la seconda si ricollega.
                self.remember("inscricoes_eventos", row["id"], "club_competition_entries", twin)
                self.totals.skipped["iscrizione doppia"] += 1
                continue
            placement = MEDAL.get(row["resultado_medalha"] or "")
            rank = row["resultado_classificacao"]
            if placement is None and rank:
                placement = rank if rank in (1, 2, 3, 5, 7) else 0
            if comp.kind != "COMPETITION":
                placement = None
            entry = ClubCompetitionEntry(
                **scope.columns(), competition_id=comp.id, athlete_id=athlete.id,
                status="WITHDRAWN" if row["estado"] == "cancelado" else "REGISTERED",
                registered_by_user_id=athlete.guardian_user_id, placement=placement,
                rank=rank if rank and rank not in (1, 2, 3, 5, 7) else None,
                result_notes=clean(row["resultado_notas"], 500), weight_kg=athlete.weight_kg,
                category=athlete.weight_category, created_at=row["criado_em"] or utcnow(),
            )
            self.db.add(entry)
            await self.db.flush()
            self.remember("inscricoes_eventos", row["id"], "club_competition_entries", entry.id)
            await self._entry_fee(row, entry, comp, athlete, scope)

    async def _entry_fee(self, row: dict, entry, comp: ClubCompetition, athlete: ClubAthlete, scope: ClubScope) -> None:
        proof_id = await self.mapped("pagamentos", row["pagamento_id"]) if row["pagamento_id"] else None
        proof = await self.db.get(ClubPaymentProof, proof_id) if proof_id else None
        paid = proof is not None and proof.status == "ACCEPTED"
        amount = proof.amount_cents if paid else (cents(row["valor_pago"]) or comp.fee_cents)
        if row["estado"] == "cancelado" or amount <= 0:
            return
        if row["estado"] == "liquidado" and not paid:
            # "Liquidado" a mano dalla segreteria: pagato, senza una ricevuta.
            fee = await self._fee(**scope.columns(), athlete_id=athlete.id, kind="COMPETITION", period=str(comp.id),
                                  competition_id=comp.id, description=f"Iscrizione: {comp.name}"[:200],
                                  amount_cents=amount, gross_amount_cents=amount, due_date=comp.registration_deadline,
                                  status="PAID", paid_at=self._paid_at({"data_pagamento": comp.starts_on, "criado_em": None}),
                                  payment_method="CASH", cash_received_by_name="Secretaria do clube",
                                  payment_note="Liquidado no gestionale anterior")
            return
        fee = await self._fee(**scope.columns(), athlete_id=athlete.id, kind="COMPETITION", period=str(comp.id),
                              competition_id=comp.id, description=f"Iscrizione: {comp.name}"[:200], amount_cents=amount,
                              gross_amount_cents=amount, due_date=comp.registration_deadline, status="DUE")
        if paid:
            await self._pay(fee, proof, {"data_pagamento": proof.paid_on, "criado_em": proof.created_at})
        else:
            self.totals.money["da pagare · eventi"] += amount

    # --- Ordini di judogi -------------------------------------------------------------------------

    async def import_equipment_orders(self, legacy_id: int, scope: ClubScope) -> None:
        for row in self.legacy.rows("SELECT * FROM pedidos_fatos WHERE clube_id = %s AND apagado = 0", legacy_id):
            if await self.mapped("pedidos_fatos", row["id"]):
                continue
            athlete = await self.athlete(row["atleta_id"])
            if athlete is None:
                self.totals.skipped["ordine senza atleta"] += 1
                continue
            size = int(re.sub(r"\D", "", str(row["tamanho"] or "")) or 0) or 150
            order = ClubEquipmentOrder(
                **scope.columns(), athlete_id=athlete.id, requested_by_user_id=athlete.guardian_user_id,
                kimono_name=clean(row["nome_atleta"], 100) or athlete.first_name,
                kimono_type=KIMONO.get(norm(row["tipo_fato"]), "TRAINING"), color=clean(row["cor"], 40) or "Branco",
                brand=clean(row["marca"], 60) or "Outra", size_cm=min(max(size, 80), 220),
                price_cents=cents(row["valor"]) if row["valor"] is not None else None, notes=row["observacoes"] or None,
                internal_notes=row["notas_internas"] or None, status=ORDER_STATUS.get(row["estado"], "PENDING"),
                created_at=row["criado_em"] or utcnow(),
            )
            self.db.add(order)
            await self.db.flush()
            self.remember("pedidos_fatos", row["id"], "club_equipment_orders", order.id)
            if order.price_cents and order.status != "CANCELLED":
                fee = await self._fee(**scope.columns(), athlete_id=athlete.id, kind="EQUIPMENT", period=str(order.id),
                                      description=f"Judogi {order.brand} {order.size_cm} cm"[:200],
                                      amount_cents=order.price_cents, gross_amount_cents=order.price_cents,
                                      due_date=(row["criado_em"] or utcnow()).date(), status="DUE")
                order.fee_id = fee.id
                proof_id = await self.mapped("pagamentos", row["pagamento_id"]) if row["pagamento_id"] else None
                proof = await self.db.get(ClubPaymentProof, proof_id) if proof_id else None
                if proof is not None and proof.status == "ACCEPTED":
                    await self._pay(fee, proof, {"data_pagamento": proof.paid_on, "criado_em": proof.created_at})
                elif row["pago"]:
                    fee.status, fee.paid_at, fee.payment_method = "PAID", self._paid_at(row), "CASH"
                    fee.cash_received_by_name, fee.payment_note = "Secretaria do clube", "Pago no gestionale anterior"
                else:
                    self.totals.money["da pagare · judogi"] += order.price_cents

    # --- Corsi e presenze -------------------------------------------------------------------------

    async def import_courses_and_attendance(self, legacy_id: int, scope: ClubScope) -> None:
        modalities = {r["id"]: r["nome"] for r in self.legacy.rows("SELECT id, nome FROM modalidades")}
        existing = list((await self.db.execute(select(ClubCourse).where(ClubCourse.club_id == scope.club_id))).scalars())
        plans = [p for p in await club_service.list_plans(self.db, scope=scope) if p.active]
        by_key: dict[tuple, ClubCourse] = {}

        async def course_for(modality: str, group: str) -> ClubCourse:
            key = (norm(modality), str(group))
            if key in by_key:
                return by_key[key]
            if norm(modality) == "judo":
                for course in existing:
                    name = norm(course.name)
                    if re.search(rf"grupos? (?:\d e )?{group}\b", name) or (group in ("2", "3") and "grupos 2 e 3" in name):
                        by_key[key] = course
                        return course
            plan = next((p for p in plans if norm(p.name).startswith(f"grupo {group}")), None)
            name = (plan.name if plan and norm(modality) == "judo" else f"{modality} · Grupo {group}")[:120]
            course = ClubCourse(**scope.columns(), name=name, level=None, active=True, published=False,
                                min_age=plan.min_age if plan else None, max_age=plan.max_age if plan else None)
            self.db.add(course)
            await self.db.flush()
            existing.append(course)
            by_key[key] = course
            self.totals.counts["club_courses"] += 1
            return course

        for row in self.legacy.rows("SELECT * FROM treinos_calendario WHERE clube_id = %s AND ativo = 1", legacy_id):
            if await self.mapped("treinos_calendario", row["id"]):
                continue
            course = await course_for(modalities.get(row["modalidade_id"], "Judo"), row["grupo"])
            # Gli slot si aggiungono solo ai corsi nati qui: quelli che c'erano
            # già hanno l'orario del sito del club.
            has_slots = (await self.db.execute(select(func.count()).select_from(ClubCourseSlot).where(
                ClubCourseSlot.course_id == course.id))).scalar_one()
            if not has_slots or await self.mapped("course_created", course.id):
                start, end = _time(row["hora_inicio"]), _time(row["hora_fim"])
                if end > start:
                    self.db.add(ClubCourseSlot(course_id=course.id, weekday=int(row["dia_semana"]) - 1,
                                               starts_at=start, ends_at=end, room=clean(row["local"], 80)))
                if not has_slots:
                    self.remember("course_created", course.id, "club_courses", course.id)
            self.remember("treinos_calendario", row["id"], "club_courses", course.id)
        # Gli atleti attivi nel corso del loro gruppo.
        athletes = (await self.db.execute(select(ClubAthlete).where(
            ClubAthlete.club_id == scope.club_id, ClubAthlete.status == "ACTIVE"))).scalars().all()
        legacy_groups = {r["id"]: (r["grupo"], modalities.get(r["modalidade_id"], "Judo")) for r in self.legacy.rows(
            "SELECT id, grupo, modalidade_id FROM atletas WHERE clube_id = %s", legacy_id)}
        mapped_ids = {(await self.mapped("atletas", lid)): lid for lid in legacy_groups}
        for athlete in athletes:
            lid = mapped_ids.get(athlete.id)
            if lid is None or not legacy_groups[lid][0]:
                continue
            group, modality = legacy_groups[lid]
            course = await course_for(modality, str(group))
            exists = (await self.db.execute(select(ClubCourseAthlete).where(
                ClubCourseAthlete.course_id == course.id, ClubCourseAthlete.athlete_id == athlete.id))).first()
            if not exists:
                self.db.add(ClubCourseAthlete(course_id=course.id, athlete_id=athlete.id))
        rows = self.legacy.rows(
            "SELECT p.id, p.atleta_id, p.registado_por_user_id, s.data, s.grupo, s.modalidade_id "
            "FROM presencas p JOIN treinos_sessoes s ON s.id = p.sessao_id "
            "WHERE s.clube_id = %s AND s.cancelado = 0", legacy_id,
        )
        for row in rows:
            if await self.mapped("presencas", row["id"]):
                continue
            athlete = await self.athlete(row["atleta_id"])
            if athlete is None:
                continue
            course = await course_for(modalities.get(row["modalidade_id"], "Judo"), str(row["grupo"]))
            exists = (await self.db.execute(select(ClubAttendance.id).where(
                ClubAttendance.athlete_id == athlete.id, ClubAttendance.course_id == course.id,
                ClubAttendance.date == row["data"]))).scalar_one_or_none()
            if exists is None:
                attendance = ClubAttendance(**scope.columns(), course_id=course.id, athlete_id=athlete.id,
                                            date=row["data"], present=True,
                                            recorded_by_user_id=await self.staff_user(row["registado_por_user_id"]),
                                            recorded_by_kind="STAFF")
                self.db.add(attendance)
                await self.db.flush()
                exists = attendance.id
            self.remember("presencas", row["id"], "club_attendances", exists)

    # --- Documenti, consensi, richieste, domande --------------------------------------------------

    async def import_documents(self, legacy_id: int, scope: ClubScope) -> None:
        for row in self.legacy.rows("SELECT * FROM atleta_documentos WHERE clube_id = %s", legacy_id):
            if await self.mapped("atleta_documentos", row["id"]):
                continue
            athlete = await self.athlete(row["atleta_id"])
            found = self.read_file(row["caminho"]) if athlete else None
            if athlete is None or found is None:
                self.totals.skipped["documento senza atleta o file"] += 1
                continue
            data, content_type, name = found
            doc = ClubAthleteDocument(
                **scope.columns(), athlete_id=athlete.id, kind=DOC_KIND.get(norm(row["tipo"]), "OTHER"),
                description=clean(row["descricao"], 250),
                storage_key=self.store_private(data, content_type, f"club-athlete-documents/{athlete.id}"),
                original_filename=clean(row["nome_original"], 255) or name, content_type=content_type,
                size_bytes=len(data), created_at=row["criado_em"] or utcnow(),
            )
            self.db.add(doc)
            await self.db.flush()
            self.remember("atleta_documentos", row["id"], "club_athlete_documents", doc.id)

    async def import_consents(self, legacy_id: int, scope: ClubScope) -> None:
        rows = self.legacy.rows(
            "SELECT c.* FROM consentimentos_rgpd c JOIN atletas a ON a.id = c.atleta_id WHERE a.clube_id = %s "
            "ORDER BY c.data_consentimento", legacy_id,
        )
        for row in rows:
            if await self.mapped("consentimentos_rgpd", row["id"]):
                continue
            athlete = await self.athlete(row["atleta_id"])
            if athlete is None:
                continue
            kind = {"politica_privacidade": "PRIVACY_POLICY", "fotografias": "PHOTOS", "marketing": "MARKETING"}.get(
                row["tipo_consentimento"])
            if kind is None:
                continue
            consent = ClubConsent(
                **scope.columns(), user_id=athlete.guardian_user_id if kind == "PRIVACY_POLICY" else None,
                athlete_id=None if kind == "PRIVACY_POLICY" else athlete.id, kind=kind,
                granted=bool(row["consentimento_dado"]), policy_version=f"judo-aev {row['versao_politica'] or '1.0'}",
                source="LEGACY",
                ip_hash=hashlib.sha256(row["ip_address"].encode()).hexdigest() if row["ip_address"] else None,
                given_at=row["data_consentimento"] or utcnow(),
                revoked_at=row["data_revogacao"] if row["revogado"] else None,
            )
            self.db.add(consent)
            await self.db.flush()
            self.remember("consentimentos_rgpd", row["id"], "club_consents", consent.id)

    async def import_change_requests(self, legacy_id: int, scope: ClubScope) -> None:
        rows = self.legacy.rows(
            "SELECT p.* FROM pedidos_alteracao p JOIN atletas a ON a.id = p.atleta_id WHERE a.clube_id = %s", legacy_id
        )
        for row in rows:
            if await self.mapped("pedidos_alteracao", row["id"]):
                continue
            athlete = await self.athlete(row["atleta_id"])
            if athlete is None or row["campo"] not in CHANGE_FIELD:
                continue
            request = ClubChangeRequest(
                **scope.columns(), athlete_id=athlete.id, requested_by_user_id=athlete.guardian_user_id,
                field=CHANGE_FIELD[row["campo"]], current_value=clean(row["valor_atual"], 200),
                requested_value=clean(row["valor_pedido"], 200) or "-", note=clean(row["notas"], 500),
                status=REQUEST_STATUS.get(row["estado"], "PENDING"), resolved_at=row["resolvido_em"],
                created_at=row["criado_em"] or utcnow(),
            )
            self.db.add(request)
            await self.db.flush()
            self.remember("pedidos_alteracao", row["id"], "club_change_requests", request.id)

    async def import_applications(self, legacy_id: int, scope: ClubScope) -> None:
        athletes_by_app = {r["inscricao_id"]: r["id"] for r in self.legacy.rows(
            "SELECT id, inscricao_id FROM atletas WHERE inscricao_id IS NOT NULL AND clube_id = %s", legacy_id)}
        for row in self.legacy.rows("SELECT * FROM inscricoes WHERE clube_id = %s AND apagado = 0", legacy_id):
            if await self.mapped("inscricoes", row["id"]):
                continue
            athlete = await self.athlete(athletes_by_app.get(row["id"]))
            data = {k: (v.isoformat() if isinstance(v, (date, datetime)) else v) for k, v in row.items()
                    if k not in ("id", "clube_id", "apagado", "apagado_por", "apagado_em")}
            app = ClubApplication(
                **scope.columns(), full_name=clean(row["nome_completo"], 200) or "-", birth_date=row["data_nascimento"],
                email=clean(row["email_responsavel"] or row["email"], 200),
                data=json.loads(json.dumps(data, default=str)), status=APPLICATION_STATUS.get(row["estado"], "PENDING"),
                internal_notes=row["notas_internas"] or None, athlete_id=athlete.id if athlete else None,
                referred_by=clean(row["referencia_atleta"], 200), first_time=bool(row["primeira_vez"]),
                joined_year=row["ano_inscricao"], created_at=row["criado_em"] or utcnow(),
            )
            self.db.add(app)
            await self.db.flush()
            self.remember("inscricoes", row["id"], "club_applications", app.id)

    # --- Pulizie, collaboratori, treinadores esterni, relatori ------------------------------------

    async def _expense(self, scope: ClubScope, *, spent_on: date, category: str, amount: int, description: str,
                       supplier: str | None, method: str = "CASH") -> ClubExpense | None:
        if amount <= 0:
            return None
        expense = ClubExpense(**scope.columns(), spent_on=spent_on, category=category, amount_cents=amount,
                              description=description[:200], supplier=(supplier or None) and supplier[:200],
                              payment_method=method)
        self.db.add(expense)
        await self.db.flush()
        self.totals.money[f"spese · {category}"] += amount
        return expense

    async def import_operations(self, legacy_id: int, scope: ClubScope) -> None:
        for row in self.legacy.rows("SELECT * FROM registos_limpeza WHERE clube_id = %s", legacy_id):
            if await self.mapped("registos_limpeza", row["id"]):
                continue
            signature = None
            match = re.match(r"data:image/png;base64,(.+)", row["assinatura"] or "", re.S)
            if match:
                import base64

                signature = self.store_private(base64.b64decode(match.group(1)), "image/png",
                                               f"club-cleaning-signatures/{scope.club_id}")
            total = cents(row["total"])
            log = ClubCleaningLog(
                **scope.columns(), performed_at=row["data_hora"], person_name=clean(row["nome_responsavel"], 150) or "-",
                hours=row["num_horas"], hourly_rate_cents=cents(row["valor_hora"]), total_cents=total,
                notes=row["observacoes"] or None, signature_storage_key=signature,
                paid_on=row["data_pagamento"] if row["pago"] else None,
                created_by_user_id=await self.staff_user(row["criado_por"]),
            )
            if row["pago"]:
                expense = await self._expense(scope, spent_on=row["data_pagamento"] or row["data_hora"].date(),
                                              category="CLEANING", amount=total,
                                              description=f"Limpeza {row['data_hora']:%d/%m/%Y}", supplier=log.person_name)
                log.expense_id = expense.id if expense else None
            self.db.add(log)
            await self.db.flush()
            self.remember("registos_limpeza", row["id"], "club_cleaning_logs", log.id)
        for row in self.legacy.rows("SELECT * FROM pagamentos_colaboradores WHERE clube_id = %s", legacy_id):
            if await self.mapped("pagamentos_colaboradores", row["id"]):
                continue
            expense = await self._expense(scope, spent_on=row["data_pagamento"], category="COLLABORATORS",
                                          amount=cents(row["valor_pago"]),
                                          description=clean(row["referencia_descricao"], 300) or "Colaborador",
                                          supplier=clean(row["nome_colaborador"], 150))
            if expense:
                self.remember("pagamentos_colaboradores", row["id"], "club_expenses", expense.id)
        for row in self.legacy.rows("SELECT * FROM pagamentos_treinadores_externos WHERE clube_id = %s", legacy_id):
            if await self.mapped("pagamentos_treinadores_externos", row["id"]):
                continue
            status = COACH_STATUS.get(row["estado"], "PENDING")
            fee = ClubExternalCoachFee(
                **scope.columns(), coach_name=clean(row["nome_treinador"], 150) or "-", month=row["mes_referencia"],
                weekday_hours=row["horas_semana"] or 0, weekday_rate_cents=cents(row["valor_hora_semana"]),
                weekend_hours=row["horas_fds"] or 0, weekend_rate_cents=cents(row["valor_hora_fds"]),
                students=row["num_alunos"] or 0, per_student_cents=cents(row["valor_por_aluno"]),
                total_cents=cents(row["total_a_pagar"]), status=status,
                paid_cents=cents(row["valor_pago"]) if row["valor_pago"] is not None else None,
                paid_on=row["data_pagamento"], payment_method=METHOD.get(norm(row["forma_pagamento"])),
                reference=clean(row["referencia"], 100), notes=row["observacoes"] or None,
            )
            if status in ("PAID", "PARTIAL") and (fee.paid_cents or fee.total_cents):
                expense = await self._expense(
                    scope, spent_on=row["data_pagamento"] or row["mes_referencia"], category="EXTERNAL_COACH",
                    amount=fee.paid_cents or fee.total_cents, description=f"Treinador externo {row['mes_referencia']:%m/%Y}",
                    supplier=fee.coach_name, method=fee.payment_method or "BANK_TRANSFER",
                )
                fee.expense_id = expense.id if expense else None
            self.db.add(fee)
            await self.db.flush()
            self.remember("pagamentos_treinadores_externos", row["id"], "club_external_coach_fees", fee.id)

    async def import_reports(self, legacy_id: int, scope: ClubScope) -> None:
        for row in self.legacy.rows("SELECT * FROM relatorios_gerados WHERE clube_id = %s", legacy_id):
            if await self.mapped("relatorios_gerados", row["id"]):
                continue
            path = self.uploads / "storage" / "relatorios" / str(row["ficheiro"])
            if not path.is_file():
                self.totals.skipped["relatorio senza file"] += 1
                continue
            params_path = Path(f"{path}.json")
            params = json.loads(params_path.read_text()) if params_path.is_file() else {}
            report = ClubReport(
                **scope.columns(), kind="ACTIVITIES", period_start=row["data_ini"], period_end=row["data_fim"],
                storage_key=self.store_private(path.read_bytes(), "application/pdf", f"club-reports/{scope.club_id}"),
                download_name=clean(row["nome_download"], 200) or path.name, params=params,
                created_by_user_id=await self.staff_user(row["criado_por_user_id"]),
                created_at=row["criado_em"] or utcnow(),
            )
            self.db.add(report)
            await self.db.flush()
            self.remember("relatorios_gerados", row["id"], "club_reports", report.id)

    # --- Ogni euro in una quota -------------------------------------------------------------------

    async def settle_proofs(self, scope: ClubScope) -> None:
        """Le prove con importo non (del tutto) attribuito a quote:
        - nessuna quota (un evento pagato senza iscrizione collegata, un
          equipamento senza ordine, una quota annuale senza rate): una quota
          del suo tipo, pagata con quella prova; per un evento si cerca prima
          l'iscrizione dell'atleta all'evento con quel nome;
        - una differenza (le rate del vecchio non tornano con il pagamento):
          la differenza va sull'ultima quota pagata da quella prova, con una
          nota. Così la contabilità incassa esattamente ciò che è entrato."""
        for proof_id, (row, proof, athlete) in list(self.proofs.items()):
            if proof.status != "ACCEPTED" or proof.amount_cents <= 0:
                continue
            missing = proof.amount_cents - self.allocated[proof_id]
            if missing == 0:
                continue
            if self.allocated[proof_id] == 0:
                await self._orphan_fee(row, proof, athlete, scope)
                continue
            fee = (await self.db.execute(
                select(ClubFee).where(ClubFee.paid_via_proof_id == proof_id).order_by(ClubFee.due_date.desc()).limit(1)
            )).scalar_one_or_none()
            if fee is None or fee.amount_cents + missing < 0:
                self.totals.skipped["differenza non attribuita"] += 1
                self.totals.money["differenza non attribuita"] += missing
                continue
            fee.amount_cents += missing
            fee.gross_amount_cents = max(fee.gross_amount_cents or 0, fee.amount_cents)
            fee.payment_note = "Importo allineato al pagamento del gestionale precedente"
            self.allocated[proof_id] += missing
            self.totals.money["differenze allineate"] += missing
        self.proofs.clear()

    async def _orphan_fee(self, row: dict, proof: ClubPaymentProof, athlete: ClubAthlete, scope: ClubScope) -> None:
        kind = {"evento": "COMPETITION", "prova": "COMPETITION", "equipamentos": "EQUIPMENT", "quotas": "ENROLLMENT",
                "mensalidade": "MONTHLY"}.get(row["tipo"])
        if kind == "COMPETITION" and row["nome_prova"]:
            due = (await self.db.execute(
                select(ClubFee).join(ClubCompetition, ClubCompetition.id == ClubFee.competition_id).where(
                    ClubFee.athlete_id == athlete.id, ClubFee.kind == "COMPETITION", ClubFee.status == "DUE",
                    func.lower(ClubCompetition.name) == (row["nome_prova"] or "").strip().lower(),
                ).limit(1)
            )).scalar_one_or_none()
            if due is not None:
                due.amount_cents = proof.amount_cents
                await self._pay(due, proof, row)
                self.totals.money["da pagare · eventi"] -= proof.amount_cents
                return
        year = (row["data_pagamento"] or self.today).year
        description = {
            "COMPETITION": f"Iscrizione: {row['nome_prova'] or 'evento'}",
            "EQUIPMENT": f"Equipamento: {row['desc_equipamento'] or 'material'}",
            "ENROLLMENT": f"Quotas {year}: {row['tipo_quota'] or 'pagamento'}",
            "MONTHLY": f"Mensalidade {year} (sem mês indicado)",
        }.get(kind, "Pagamento")
        fee = await self._fee(
            **scope.columns(), athlete_id=athlete.id, kind=kind or "EQUIPMENT",
            # Un periodo che nessuna generazione automatica userà mai, e che
            # per le quote annuali conta come "c'è già" (service._has_annual_fee).
            period=f"{year}/p{row['id']}" if kind == "ENROLLMENT" else f"legacy-p{row['id']}",
            description=description[:200], amount_cents=proof.amount_cents, gross_amount_cents=proof.amount_cents,
            due_date=row["data_pagamento"] or self.today, status="DUE",
            payment_note="Pagamento del gestionale precedente senza quota collegata",
        )
        await self._pay(fee, proof, row)
        self.totals.money["pagamenti senza quota (quota creata)"] += proof.amount_cents

    # --- Le mensilità scoperte --------------------------------------------------------------------

    async def emit_open_months(self, scope: ClubScope) -> None:
        """Da gennaio al mese in corso: i mesi che il vecchio non ha visto
        pagati diventano mensilità da pagare, con le regole di Jav (piano per
        età federale, sconti, mai prima dell'iscrizione). Senza avvisi:
        generate_monthly_fees su un mese passato non notifica nessuno, e sul
        mese in corso il piano è già quello giusto."""
        if self.dry_run:
            return
        await self.db.commit()
        for month in range(1, self.today.month + 1):
            created = await club_service.generate_monthly_fees(
                self.db, scope=scope, period=f"{self.today.year:04d}-{month:02d}", today=self.today
            )
            self.totals.counts["mensilità da pagare emesse"] += created


def _time(value) -> time:
    if isinstance(value, time):
        return value
    if isinstance(value, timedelta):
        seconds = int(value.total_seconds())
        return time(seconds // 3600 % 24, seconds // 60 % 60)
    return time.fromisoformat(str(value))


async def main(argv: list[str] | None = None) -> None:
    # Tutti i modelli, come nel worker: le chiavi esterne verso tabelle di
    # altri domini (organizations, users...) si risolvono solo così.
    from app import celery_app  # noqa: F401
    from app.core.db import AsyncSessionLocal

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="legge e controlla tutto, poi annulla")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    legacy = Legacy()
    uploads = Path(os.environ.get("LEGACY_UPLOADS", "/legacy/judo"))
    async with AsyncSessionLocal() as db:
        importer = Importer(db, legacy, uploads=uploads, dry_run=args.dry_run)
        try:
            totals = await importer.run()
            if args.dry_run:
                await db.rollback()
            else:
                await db.commit()
        except Exception:
            await db.rollback()
            raise
    print(json.dumps({
        "dry_run": args.dry_run,
        "creati": dict(sorted(totals.counts.items())),
        "euro": {k: round(v / 100, 2) for k, v in sorted(totals.money.items())},
        "saltati": dict(sorted(totals.skipped.items())),
        "file mancanti": len(importer.missing_files),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())

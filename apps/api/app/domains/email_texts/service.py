"""I testi delle email che il superadmin può personalizzare dalla console.
Specifica: docs/emails.md.

Ogni email ha un testo predefinito qui (in portoghese: la scrivono i club
alle famiglie) e, se il superadmin l'ha cambiato, la sua versione in
`email_template_overrides`. I segnaposto tra graffe (`{nome}`) li riempie il
codice; il testo resta testo semplice: l'escape lo fa
core/email_templates.text_to_html, quindi da qui non entra HTML. Un
segnaposto sconosciuto resta com'è, scritto, invece di far fallire l'invio.
"""

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.core.email_templates import EmailBrand, render_email, text_to_html
from app.domains.email_texts.models import EmailTemplateOverride


@dataclass(frozen=True)
class EmailText:
    key: str
    label: str
    audience: str
    subject: str
    heading: str
    body: str
    cta_label: str | None
    #: segnaposto → che cosa contiene (per l'editor) e un esempio (per l'anteprima).
    placeholders: dict[str, tuple[str, str]] = field(default_factory=dict)


TEXTS: dict[str, EmailText] = {t.key: t for t in (
    EmailText(
        "verify_email", "Conferma dell'email", "Chi si registra",
        "Confirme o seu email · {marca}", "Bem-vindo à {marca}!",
        "Obrigado por se registar. Para ativar a sua conta, confirme o seu endereço de email com o botão abaixo.\n\n"
        "O link é válido durante {horas} horas.",
        "Confirmar o meu email",
        {"marca": ("Il nome di chi scrive (il club o JudoArteVida)", "Judo Clube de Lagos"),
         "horas": ("Per quante ore vale il link", "48")},
    ),
    EmailText(
        "account_invite", "Invito: primo accesso", "Segreterie, istruttori e famiglie create dal club",
        "A sua conta {marca} está pronta", "A sua conta está pronta",
        "{introducao}\n\nPara entrar pela primeira vez, escolha já a sua palavra-passe pessoal com o botão abaixo. "
        "O link é válido durante 7 dias.",
        "Escolher a minha palavra-passe",
        {"marca": ("Il nome di chi scrive", "Judo Clube de Lagos"),
         "introducao": ("La frase d'apertura scritta dal sistema (chi ti ha invitato e per che cosa)",
                        "A sua conta para a secretaria do Judo Clube de Lagos está pronta.")},
    ),
    EmailText(
        "password_reset", "Nuova password", "Chi ha chiesto di cambiare la password",
        "Redefinir a palavra-passe · {marca}", "Redefinir a palavra-passe",
        "Pediu para redefinir a palavra-passe da sua conta.\n\n"
        "O link expira dentro de {minutos} minutos. Se não foi você, ignore este email: a palavra-passe fica igual.",
        "Escolher uma nova palavra-passe",
        {"marca": ("Il nome di chi scrive", "JudoArteVida"), "minutos": ("Quanti minuti vale il link", "60")},
    ),
    EmailText(
        "otp_code", "Codice di conferma", "Chi conferma un'operazione (pagamento con il credito, PIN...)",
        "O seu código de confirmação · {marca}", "Código de confirmação",
        "{contexto}\n\n⟦{codigo}⟧\n\nO código expira dentro de {minutos} minutos. Se não foi você que o pediu, ignore este email.",
        None,
        {"marca": ("Il nome di chi scrive", "JudoArteVida"), "contexto": ("Per che cosa serve il codice", "Para confirmar o pagamento com o crédito da carteira."),
         "codigo": ("Il codice (si mostra grande)", "482913"), "minutos": ("Quanti minuti vale", "10")},
    ),
    EmailText(
        "proof_rejected", "Prova di pagamento rifiutata", "Il genitore che l'ha caricata",
        "Comprovativo de pagamento não aceite", "Comprovativo não aceite",
        "A secretaria do {marca} não pôde aceitar o comprovativo de pagamento de: {quotas}.\n\n"
        "Motivo: {motivo}\n\nAs quotas voltam a estar por pagar: pode carregar um novo comprovativo no portal.",
        "Abrir o portal",
        {"marca": ("Il club", "Judo Clube de Lagos"), "quotas": ("Le quote", "Mensalidade outubro 2026 · Tiago"),
         "motivo": ("Il motivo scritto dalla segreteria", "O valor do comprovativo não corresponde.")},
    ),
    EmailText(
        "contact_message", "Messaggio dal sito", "Il club (o JudoArteVida) che riceve il messaggio",
        "Mensagem do site: {nome}", "Nova mensagem do site",
        "Nova mensagem enviada através de {onde}.\n\nNome: {nome}\nEmail: {email}\nTelefone: {telefone}\nAssunto: {assunto}\n\n"
        "{mensagem}\n\nPara responder, use «Responder»: a resposta vai diretamente para quem escreveu. "
        "A mensagem também está em «Mensagens» no portal.",
        "Abrir as mensagens",
        {"onde": ("Da quale pagina", "a página do Judo Clube de Lagos"), "nome": ("Chi scrive", "Ana Silva"),
         "email": ("La sua email", "ana@example.com"), "telefone": ("Il telefono (o —)", "+351 912 345 678"),
         "assunto": ("L'argomento", "Inscrições"), "mensagem": ("Il messaggio", "Olá! Gostaria de inscrever o meu filho.")},
    ),
)}

_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


def fill(text: str, values: dict[str, str]) -> str:
    return _PLACEHOLDER.sub(lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), text)


async def current(db: AsyncSession, key: str) -> tuple[EmailText, EmailTemplateOverride | None]:
    text = TEXTS[key]
    override = await db.get(EmailTemplateOverride, key)
    return text, override


@dataclass(frozen=True)
class Composed:
    subject: str
    html: str
    text: str


async def compose(
    db: AsyncSession, key: str, *, values: dict[str, str], brand: EmailBrand, cta_url: str | None = None,
) -> Composed:
    """L'email pronta: il testo (personalizzato o predefinito) con i
    segnaposto riempiti, nella veste del marchio."""
    text, override = await current(db, key)
    values = {"marca": brand.name, **values}
    subject = fill(override.subject if override else text.subject, values)
    heading = fill(override.heading if override else text.heading, values)
    body = fill(override.body if override else text.body, values)
    cta = (override.cta_label if override else text.cta_label) if cta_url else None
    html = render_email(preheader=subject, heading=heading, body_html=text_to_html(body), cta_label=cta,
                        cta_url=cta_url, brand=brand)
    plain = body.replace("⟦", "").replace("⟧", "") + (f"\n\n{cta_url}" if cta_url else "")
    return Composed(subject=subject, html=html, text=plain)


def text_dict(text: EmailText, override: EmailTemplateOverride | None) -> dict:
    return {
        "key": text.key, "label": text.label, "audience": text.audience,
        "subject": override.subject if override else text.subject,
        "heading": override.heading if override else text.heading,
        "body": override.body if override else text.body,
        "cta_label": (override.cta_label if override else text.cta_label),
        "has_cta": text.cta_label is not None,
        "customized": override is not None, "updated_at": override.updated_at if override else None,
        "default": {"subject": text.subject, "heading": text.heading, "body": text.body, "cta_label": text.cta_label},
        "placeholders": [{"name": k, "description": d, "example": e} for k, (d, e) in text.placeholders.items()],
    }


async def list_texts(db: AsyncSession) -> list[dict]:
    overrides = {o.key: o for o in (await db.execute(select(EmailTemplateOverride))).scalars()}
    return [text_dict(t, overrides.get(k)) for k, t in TEXTS.items()]


class EmailTextError(Exception):
    pass


async def save(db: AsyncSession, *, key: str, data: dict, actor_user_id: uuid.UUID) -> dict:
    if key not in TEXTS:
        raise EmailTextError("Email non trovata.")
    clean = {k: " ".join((data.get(k) or "").split()) for k in ("subject", "heading")}
    clean["body"] = (data.get("body") or "").strip()
    clean["cta_label"] = (" ".join((data.get("cta_label") or "").split()) or None) if TEXTS[key].cta_label else None
    if not clean["subject"] or not clean["heading"] or len(clean["body"]) < 5:
        raise EmailTextError("Oggetto, titolo e testo non possono essere vuoti.")
    if len(clean["subject"]) > 200 or len(clean["heading"]) > 200 or len(clean["body"]) > 8000:
        raise EmailTextError("Il testo è troppo lungo.")
    unknown = set(_PLACEHOLDER.findall(" ".join(clean[k] or "" for k in clean))) - set(TEXTS[key].placeholders)
    if unknown:
        raise EmailTextError(f"Segnaposto sconosciuti: {', '.join('{' + u + '}' for u in sorted(unknown))}.")
    override = await db.get(EmailTemplateOverride, key)
    if override is None:
        override = EmailTemplateOverride(key=key, **clean, updated_by_user_id=actor_user_id)
        db.add(override)
    else:
        for k, v in clean.items():
            setattr(override, k, v)
        override.updated_by_user_id = actor_user_id
        override.updated_at = utcnow()
    await db.commit()
    await db.refresh(override)
    return text_dict(TEXTS[key], override)


async def reset(db: AsyncSession, *, key: str) -> dict:
    if key not in TEXTS:
        raise EmailTextError("Email non trovata.")
    override = await db.get(EmailTemplateOverride, key)
    if override is not None:
        await db.delete(override)
        await db.commit()
    return text_dict(TEXTS[key], None)


def sample_values(key: str) -> dict[str, str]:
    return {k: e for k, (_d, e) in TEXTS[key].placeholders.items()}

"""La veste di ogni email in uscita (verifica, password, inviti, promemoria
del club, prove rifiutate, messaggi dal sito, ordini dello Shop...): un
guscio solo, così logo, colori e piè di pagina cambiano in un posto.

Due marchi (`EmailBrand`):

- **JudoArteVida** (predefinito): le comunicazioni della piattaforma;
- **il club** che scrive (logo e colori della sua pagina pubblica), con in
  fondo il marchio della rete «Rede JudoArteVida». Lo costruisce
  domains/club/email_brand.py.

Impaginazione a tabelle di proposito: deve reggere in Outlook, Gmail e Apple
Mail, che non supportano bene flexbox o grid nelle email. Colori e testi
sono sempre scritti in linea (style=...), mai in <style>, che Gmail toglie.
"""

import re
from dataclasses import dataclass, field
from html import escape

from app.core.config import get_settings

INK = "#0f172a"
MUTED = "#64748b"
PAGE_BG = "#eef1f6"


@dataclass(frozen=True)
class EmailBrand:
    """Chi firma l'email. `network` = mostra in fondo la rete JudoArteVida
    (le email di un club)."""

    name: str
    logo_url: str
    primary: str = "#e43f21"
    accent: str = "#f9e40f"
    on_primary: str = "#ffffff"
    tagline: str | None = None
    contact_lines: tuple[str, ...] = field(default_factory=tuple)
    website: str | None = None
    network: bool = False


def jav_brand() -> EmailBrand:
    base = get_settings().public_app_base_url
    return EmailBrand(
        name="JudoArteVida", logo_url=f"{base}/judoartevida-logo.jpg", primary="#e43f21", accent="#f9e40f",
        tagline="Judo Arte e Vida · Algarve", contact_lines=("info@judoartevida.com", "+351 931 148 585"),
        website=base,
    )


def text_to_html(body_text: str) -> str:
    """Testo semplice → paragrafi HTML, con l'escape. Una riga vuota separa i
    paragrafi, una riga singola va a capo. Un paragrafo che è solo un codice
    tra «⟦ ⟧» (il codice di conferma) diventa il riquadro grande."""
    paragraphs = [p for p in body_text.replace("\r\n", "\n").split("\n\n") if p.strip()]
    out = []
    for p in paragraphs:
        stripped = p.strip()
        if stripped.startswith("⟦") and stripped.endswith("⟧"):
            out.append(f"__HIGHLIGHT__{escape(stripped[1:-1].strip())}__")
            continue
        out.append(f"<p style=\"margin:0 0 16px 0;\">{'<br>'.join(escape(line) for line in p.split(chr(10)))}</p>")
    return "".join(out)


def _highlight(html: str, brand: EmailBrand) -> str:
    """Il riquadro del codice: grande, spaziato, nel colore del marchio."""
    def box(m: re.Match) -> str:
        return (
            f'<div style="margin:8px 0 22px 0; padding:18px; border-radius:16px; background:#f8fafc; '
            f'border:2px dashed {brand.primary}; text-align:center; font-size:32px; font-weight:800; '
            f'letter-spacing:8px; color:{brand.primary}; font-family:SFMono-Regular,Menlo,Consolas,monospace;">'
            f"{m.group(1)}</div>"
        )
    return re.sub(r"__HIGHLIGHT__(.*?)__", box, html)


def render_email(
    *,
    preheader: str,
    heading: str,
    body_html: str,
    cta_label: str | None = None,
    cta_url: str | None = None,
    brand: EmailBrand | None = None,
    eyebrow: str | None = None,
) -> str:
    """body_html è markup già sicuro di chi chiama (valori già con escape, o
    text_to_html): questo modulo possiede solo il guscio."""
    b = brand or jav_brand()
    settings = get_settings()
    body_html = _highlight(body_html, b)
    cta = ""
    if cta_label and cta_url:
        url = escape(cta_url, quote=True)
        cta = f"""
          <tr><td align="center" style="padding:6px 36px 34px 36px;">
            <table role="presentation" cellpadding="0" cellspacing="0"><tr>
              <td align="center" bgcolor="{b.primary}" style="border-radius:14px; background:{b.primary};">
                <a href="{url}" style="display:inline-block; padding:16px 34px; font-size:16px; font-weight:700;
                   color:{b.on_primary}; text-decoration:none; border-radius:14px;">{escape(cta_label)} &rarr;</a>
              </td></tr></table>
            <p style="margin:14px 0 0 0; font-size:12px; color:{MUTED};">
              Se o botão não funcionar, copie este endereço:<br><a href="{url}" style="color:{b.primary}; word-break:break-all;">{escape(cta_url)}</a>
            </p>
          </td></tr>"""
    contacts = " &middot; ".join(escape(c) for c in b.contact_lines)
    network = ""
    if b.network:
        jav = jav_brand()
        network = f"""
          <tr><td align="center" style="padding:18px 24px 0 24px;">
            <table role="presentation" cellpadding="0" cellspacing="0"><tr>
              <td style="padding-right:10px;"><img src="{jav.logo_url}" alt="JudoArteVida" height="26" style="height:26px; width:auto; border-radius:4px;"></td>
              <td style="font-size:12px; color:{MUTED};">Clube da <strong style="color:{INK};">Rede JudoArteVida</strong></td>
            </tr></table>
          </td></tr>"""
    eyebrow_html = (f'<p style="margin:0 0 6px 0; font-size:11px; font-weight:800; letter-spacing:2.5px; '
                    f'text-transform:uppercase; color:{b.primary};">{escape(eyebrow)}</p>') if eyebrow else ""
    tagline = f'<p style="margin:4px 0 0 0; font-size:12px; color:{b.on_primary}; opacity:0.85;">{escape(b.tagline)}</p>' if b.tagline else ""
    contacts_html = f'<p style="margin:4px 0 0 0; font-size:12px; color:{MUTED};">{contacts}</p>' if contacts else ""
    website_html = (f'<p style="margin:4px 0 0 0; font-size:12px;"><a href="{escape(b.website, quote=True)}" '
                    f'style="color:{b.primary}; text-decoration:none;">{escape(b.website.replace("https://", ""))}</a></p>') if b.website else ""
    return f"""<!doctype html>
<html lang="pt">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>{escape(heading)}</title>
</head>
<body style="margin:0; padding:0; background:{PAGE_BG}; font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif; -webkit-font-smoothing:antialiased;">
  <div style="display:none; max-height:0; overflow:hidden; opacity:0; color:transparent;">{escape(preheader)}</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAGE_BG}; padding:28px 12px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:580px;">
        <tr><td align="center" bgcolor="{b.primary}" style="border-radius:24px 24px 0 0; background:{b.primary}; background-image:linear-gradient(135deg,{b.primary} 0%,{b.primary} 55%,{INK} 140%); padding:30px 24px 26px 24px;">
          <table role="presentation" cellpadding="0" cellspacing="0"><tr><td align="center"
            style="background:#ffffff; border-radius:999px; width:86px; height:86px; text-align:center; vertical-align:middle; border:4px solid {b.accent};">
            <img src="{escape(b.logo_url, quote=True)}" alt="{escape(b.name)}" width="70" style="width:70px; height:auto; max-height:70px; border-radius:999px; display:block; margin:0 auto;">
          </td></tr></table>
          <p style="margin:14px 0 0 0; font-size:18px; font-weight:800; color:{b.on_primary}; letter-spacing:0.3px;">{escape(b.name)}</p>
          {tagline}
        </td></tr>
        <tr><td style="height:6px; line-height:6px; font-size:0; background:{b.accent};">&nbsp;</td></tr>
        <tr><td style="background:#ffffff; padding:34px 36px 8px 36px;">
          {eyebrow_html}
          <h1 style="margin:0 0 18px 0; font-size:24px; line-height:1.25; color:{INK}; font-weight:800;">{escape(heading)}</h1>
          <div style="font-size:16px; line-height:1.65; color:#1e293b;">{body_html}</div>
        </td></tr>
        <tr><td style="background:#ffffff;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{cta}</table>
        </td></tr>
        <tr><td align="center" style="background:#f8fafc; border-radius:0 0 24px 24px; padding:22px 24px 26px 24px; border-top:1px solid #e2e8f0;">
          <p style="margin:0; font-size:13px; font-weight:700; color:{INK};">{escape(b.name)}</p>
          {contacts_html}
          {website_html}
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{network}</table>
          <p style="margin:16px 0 0 0; font-size:11px; line-height:1.5; color:#94a3b8;">
            Email automática enviada por {escape(settings.smtp_from_address)} &middot; não responda a este endereço.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def render_letter(*, subject: str, body_text: str, brand: EmailBrand | None = None) -> str:
    """Una lettera scritta (o corretta) da una persona nell'anteprima -- la
    richiesta di trasporto al comune, l'avviso di un messaggio dal sito --
    nella stessa veste. `body_text` è testo semplice: l'escape lo fa
    text_to_html, quindi niente HTML iniettato."""
    return render_email(preheader=subject, heading=subject, body_html=text_to_html(body_text), brand=brand)

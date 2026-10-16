"""I testi delle email (domains/email_texts) e la loro veste (core/email_templates).

Le promesse: senza personalizzazione vale il testo predefinito; il
superadmin lo cambia e lo ripristina; un segnaposto sconosciuto si rifiuta;
niente HTML passa dai valori o dal testo; un club firma con il suo nome e la
rete JudoArteVida in fondo.
"""

import pytest

from app.core.email_templates import EmailBrand, jav_brand
from app.domains.club.email_brand import club_brand
from app.domains.email_texts import service
from tests.test_club_fees import _user


async def test_texts_can_be_customised_and_reset(db, scope):
    admin = await _user(db, scope, "admin")
    mail = await service.compose(db, "otp_code", values={"contexto": "Para <b>pagar</b>", "codigo": "123456", "minutos": "10"},
                                 brand=jav_brand())
    assert "123456" in mail.html and "<b>pagar</b>" not in mail.html and "&lt;b&gt;" in mail.html
    assert "JudoArteVida" in mail.subject

    saved = await service.save(db, key="proof_rejected", actor_user_id=admin.id, data={
        "subject": "Ops: {quotas}", "heading": "Comprovativo recusado", "body": "Motivo: {motivo}", "cta_label": "Ver",
    })
    assert saved["customized"] is True
    mail = await service.compose(db, "proof_rejected", values={"quotas": "Outubro", "motivo": "ilegível"},
                                 brand=EmailBrand(name="Clube X", logo_url="https://x/logo.png", network=True),
                                 cta_url="https://jav.ecodo.ai/area")
    assert mail.subject == "Ops: Outubro" and "Motivo: ilegível" in mail.text and "Rede JudoArteVida" in mail.html
    with pytest.raises(service.EmailTextError):
        await service.save(db, key="proof_rejected", actor_user_id=admin.id,
                           data={"subject": "{segredo}", "heading": "x", "body": "testo lungo"})
    assert (await service.reset(db, key="proof_rejected"))["customized"] is False
    assert len(await service.list_texts(db)) == len(service.TEXTS)


async def test_a_club_signs_its_emails(db, scope):
    brand = await club_brand(db, scope.club_id)
    assert brand.network is True and brand.name
    assert (await club_brand(db, None)).name == "JudoArteVida"

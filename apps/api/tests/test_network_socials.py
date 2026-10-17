"""I social: TikTok tra quelli del club, i social della rete nel piè di
pagina (Impostazioni dell'organizzazione) e la biografia lunga del judoca."""

import pytest

from app.domains.club import site
from app.domains.club.service import ClubValidationError
from app.domains.organizations import service as organizations
from app.domains.organizations.schemas import OrganizationSettingsUpdate


def test_tiktok_only_to_tiktok():
    assert site.check_social_url("tiktok.com/@judoclubedelagos", field="tiktok_url") == "https://tiktok.com/@judoclubedelagos"
    with pytest.raises(ClubValidationError):
        site.check_social_url("https://evil.example/@club", field="tiktok_url")


async def test_network_socials_default_youtube_and_saved_ones(db, organization_id):
    assert await organizations.network_socials(db, organization_id=organization_id) == {
        "youtube": "https://www.youtube.com/@ml8126"}
    await organizations.update_settings(db, organization_id=organization_id, payload=OrganizationSettingsUpdate(
        social_instagram_url="instagram.com/judoartevida", social_tiktok_url="https://www.tiktok.com/@judoartevida"))
    socials = await organizations.network_socials(db, organization_id=organization_id)
    assert socials["instagram"] == "https://instagram.com/judoartevida"
    assert socials["tiktok"] == "https://www.tiktok.com/@judoartevida" and "facebook" not in socials
    with pytest.raises(ClubValidationError):
        await organizations.update_settings(db, organization_id=organization_id, payload=OrganizationSettingsUpdate(
            social_facebook_url="https://instagram.com/notfacebook"))


def test_the_biography_can_be_long():
    assert site.BIO_MAX == 1500

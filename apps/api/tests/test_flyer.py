"""Il flyer del mese (club/calendar.py::render_flyer): sempre una pagina sola,
qualunque sia il numero di eventi, con i social cliccabili."""

from datetime import date

from app.domains.club import calendar


def _event(day: int, **kw) -> dict:
    base = {
        "kind": "COMPETITION", "level": "REGIONAL", "name": f"Torneio {day}", "starts_on": date(2026, 10, day),
        "ends_on": date(2026, 10, day), "location": "Lagos", "age_groups": ["juvenis"], "status": "OPEN",
        "registration_deadline": date(2026, 10, max(1, day - 3)), "organizer": None, "fee_cents": 0, "description": None,
    }
    return {**base, **kw}


def _pages(pdf: bytes) -> int:
    return pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page\r") + pdf.count(b"/Type /Page/") + pdf.count(b"/Type /Page ")


def test_the_flyer_is_always_one_page():
    for n in (0, 3, 20, 60):
        events = [_event(1 + i % 31) for i in range(n)]
        pdf = calendar.render_flyer(events=events, year=2026, month=10, club_name="Judo Clube de Lagos",
                                    generated_on=date(2026, 10, 17))
        assert pdf.startswith(b"%PDF")
        assert _pages(pdf) == 1, n


def test_the_flyer_links_the_network_socials_and_the_site():
    pdf = calendar.render_flyer(
        events=[_event(5)], year=2026, month=10, club_name="Judo Clube de Lagos", generated_on=date(2026, 10, 17),
        socials={"youtube": "https://www.youtube.com/@ml8126", "instagram": "https://instagram.com/judo.arte.e.vida"},
        site_url="https://jav.ecodo.ai",
    )
    for url in (b"https://www.youtube.com/@ml8126", b"https://instagram.com/judo.arte.e.vida", b"https://jav.ecodo.ai"):
        assert url in pdf

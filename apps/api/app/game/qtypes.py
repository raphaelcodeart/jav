"""I mattoni delle domande di Dojo Academy, a parte da content.py perché
le banche in questions/ li importano senza tirarsi dietro i quiz."""

from dataclasses import dataclass

LANGS = ("pt", "it", "en")

Text = dict[str, str]


def T(pt: str, it: str, en: str) -> Text:
    return {"pt": pt, "it": it, "en": en}


@dataclass(frozen=True)
class Question:
    id: str
    topic: str
    #: Il grado da cui la domanda entra negli esami (YELLOW … BLACK, DAN2 … DAN10).
    belt: str
    text: Text
    #: La giusta è la prima. Una stringa vale in tutte le lingue (un termine giapponese).
    choices: tuple
    why: Text

    def choice(self, index: int, lang: str) -> str:
        c = self.choices[index]
        return c if isinstance(c, str) else c[lang]


Q = Question

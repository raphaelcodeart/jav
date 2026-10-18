"""Che cosa di una persona può uscire dal server verso il modello (OpenAI).

**La regola**: al modello arrivano solo dati che non danneggiano nessuno se
finiscono fuori — nomi, età, cintura, tessera federale, altezza, peso,
risultati sportivi, nomi delle gare e dei corsi. **Mai**: importi (quote,
pagamenti, debiti, prezzi di qualcuno), IBAN, telefoni, email, indirizzi,
codice fiscale / NIF, documenti d'identità, date di nascita.

Come si risponde lo stesso con quei dati: lo strumento li trova nel
database, `mask` li sostituisce con un segnaposto (⟦V1⟧, ⟦V2⟧…) prima che
il risultato vada al modello, il modello scrive la risposta usando i
segnaposto, e `unmask` rimette i valori veri **sul server**, prima che la
risposta arrivi all'utente. L'utente legge i suoi dati; il modello non li
ha mai visti.

Lo stesso vale per lo storico della conversazione che si rimanda al
modello: `redact_text` toglie importi, IBAN, email, telefoni e NIF dalle
risposte già date (quelle delle regole li contengono).
"""

import re
from decimal import Decimal

#: Le chiavi i cui valori non escono mai (per nome, o per fine del nome).
SENSITIVE_KEYS = frozenset({
    "iban", "phone", "mobile", "email", "address", "street", "postal_code", "fiscal_code", "nif", "tax_number",
    "document", "document_number", "id_number", "birth_date", "payee", "holder", "recipient_phone",
    "recipient_name", "address_line1", "address_line2", "residence_street", "residence_postal_code",
})
SENSITIVE_SUFFIXES = ("_cents", "_iban", "_phone", "_email", "_address")

_EURO = re.compile(r"\d{1,3}(?:[.\s]\d{3})*(?:[.,]\d{2})\s?€|€\s?\d+(?:[.,]\d{2})?")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,4})?\b")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\d)(?:\+\d{2,3}\s?)?(?:\d[\s-]?){9,12}(?!\d)")


def _sensitive(key: str) -> bool:
    k = key.lower()
    return k in SENSITIVE_KEYS or k.endswith(SENSITIVE_SUFFIXES)


def _display(key: str, value) -> str:
    if key.lower().endswith("_cents") and isinstance(value, int | float | Decimal):
        return f"{Decimal(value) / 100:.2f} €".replace(".", ",")
    return str(value)


class Vault:
    """I valori tolti, per rimetterli nella risposta."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def token(self, display: str) -> str:
        for token, value in self.values.items():
            if value == display:
                return token
        token = f"⟦V{len(self.values) + 1}⟧"
        self.values[token] = display
        return token


def mask(data, vault: Vault):
    """Una copia di `data` con i valori sensibili sostituiti da segnaposto."""
    if isinstance(data, dict):
        out = {}
        for key, value in data.items():
            if _sensitive(str(key)) and value is not None and not isinstance(value, dict | list):
                out[key] = vault.token(_display(str(key), value))
            elif _sensitive(str(key)) and isinstance(value, dict):
                # Un indirizzo intero: si toglie tutto il blocco.
                out[key] = vault.token(", ".join(str(v) for v in value.values() if v))
            else:
                out[key] = mask(value, vault)
        return out
    if isinstance(data, list):
        return [mask(item, vault) for item in data]
    return data


def unmask(text: str, vault: Vault) -> str:
    for token, value in vault.values.items():
        text = text.replace(token, value)
    # Un segnaposto inventato dal modello non arriva all'utente.
    return re.sub(r"⟦V\d+⟧", "—", text)


def redact_text(text: str) -> str:
    """Il testo di una battuta già detta, senza i dati che non escono."""
    text = _IBAN.sub("[IBAN]", text)
    text = _EMAIL.sub("[email]", text)
    text = _EURO.sub("[valor]", text)
    text = _PHONE.sub("[telefone]", text)
    return text

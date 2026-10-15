"""Capire che cosa chiede l'utente, senza un modello linguistico.

Parole chiave in portoghese (pt-PT), italiano e inglese, cercate nel testo
"normalizzato" (minuscolo, senza accenti): "Não consigo carregar o
comprovativo" e "non riesco a caricare la ricevuta" arrivano entrambe a
`upload_proof`. Ogni intenzione ha un peso per parola trovata; vince il
punteggio più alto, a pari merito l'ordine di `INTENTS` (le più specifiche
prima). È volutamente semplice: quando al posto di questo modulo ci sarà un
modello vero (vedi planner.py), le intenzioni diventano la scelta dello
strumento, e questo file sparisce.

Una parola ambigua tra le lingue sta solo nella lingua in cui non lo è:
"prova" in italiano è la ricevuta, in portoghese è una gara.
"""

import re
import unicodedata
from dataclasses import dataclass


def normalize(text: str) -> str:
    """Minuscolo, senza accenti, spazi semplici: "Já PAGUEI!" -> "ja paguei!"."""
    folded = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", folded.lower()).strip()


@dataclass(frozen=True)
class Intent:
    code: str
    #: Parole o frasi valide in ogni lingua (già normalizzate).
    words: tuple[str, ...]
    #: Parole che valgono solo se l'utente scrive in quella lingua.
    by_lang: dict | None = None


#: Nell'ordine in cui vincono a pari punteggio: le più specifiche prima.
INTENTS: tuple[Intent, ...] = (
    Intent("staff_unpaid", (
        "chi non ha pagato", "chi deve pagare", "morosi", "non hanno pagato", "insoluti",
        "quem nao pagou", "quem deve", "devedores", "em divida", "nao pagaram",
        "who hasn't paid", "who has not paid", "who didn't pay", "unpaid", "owing", "debtors",
    )),
    Intent("upload_proof", (
        "ricevuta", "carica", "caricare", "caricato", "bonifico fatto", "foto del bonifico",
        "comprovativo", "comprovante", "carregar", "enviar o comprovativo", "talao",
        "proof", "receipt", "upload", "uploading",
    ), {"it": ("prova",)}),
    # Prima delle domande sui soldi da dare: "quanto ho pagato" non è "quanto
    # devo". "Ho pagato ma non riesco a caricare la ricevuta" resta alla
    # ricevuta (a pari punteggio vince upload_proof, che viene prima).
    Intent("payments_made", (
        "quanto ho pagato", "cosa ho pagato", "ho pagato", "ho gia pagato", "quanto ho speso", "ho speso",
        "storico pagamenti", "storico dei pagamenti", "ultimi pagamenti", "pagamenti fatti",
        "quanto paguei", "o que paguei", "quanto gastei", "gastei", "historico de pagamentos",
        "ultimos pagamentos", "pagamentos feitos", "pagamentos efetuados",
        "how much have i paid", "how much did i pay", "what have i paid", "have i paid", "i paid", "i've paid",
        "payment history", "past payments", "last payments", "spent",
    )),
    # "Che cosa sai di me?": il riepilogo di tutto, prima dei dati anagrafici.
    Intent("overview", (
        "cosa sai di me", "che sai di me", "cosa sai su di me", "tutto su di me", "riepilogo", "la mia situazione",
        "situazione", "o que sabes de mim", "o que sabes sobre mim", "tudo sobre mim", "resumo",
        "a minha situacao", "situacao", "what do you know about me", "everything about me", "summary", "overview",
        "my situation",
    )),
    Intent("my_profile", (
        "i miei dati", "miei dati", "dati personali", "il mio profilo", "profilo", "chi sono", "anagrafica",
        "la mia email", "il mio indirizzo", "codice fiscale", "tessera", "tesseramento", "il mio piano", "che piano",
        "data di nascita", "peso",
        "os meus dados", "meus dados", "dados pessoais", "o meu perfil", "perfil", "quem sou", "o meu email",
        "a minha morada", "morada", "nif", "contribuinte", "o meu plano", "que plano", "federado", "licenca",
        "data de nascimento",
        "my data", "my details", "personal data", "personal details", "my profile", "profile", "who am i",
        "my email", "my address", "tax number", "my plan", "which plan", "membership card", "date of birth",
        "weight",
    )),
    Intent("belts", (
        "cintura", "cinture", "esame di cintura", "passaggio di grado", "che grado", "kyu", "dan",
        "cinto", "cintos", "graduacao", "exame de graduacao",
        "belt", "belts", "grading",
    )),
    Intent("ranking", (
        "ranking", "classifica", "punti", "punteggio", "medaglie", "medaglia", "livello", "conquiste", "traguardi",
        "risultati", "classificacao", "pontos", "pontuacao", "medalhas", "medalha", "nivel", "conquistas",
        "resultados", "points", "medals", "medal", "level", "achievements", "results", "standings",
    )),
    Intent("judogi", (
        "judogi", "kimono", "quimono", "judo gi", "fato de judo", "divisa", "taglia del judogi", "uniform",
        "dogi",
    )),
    Intent("shop", (
        "negozio", "shop", "loja", "materiale", "comprare", "comprar", "buy", "acquistare", "ordinare",
        "encomenda", "encomendar", "ordine", "order", "store",
    )),
    Intent("certificates", (
        "certificato", "certificati", "visita medica", "atestado", "certificado", "exame medico",
        "medical", "certificate", "certificates",
    )),
    Intent("competitions", (
        "gara", "gare", "competizione", "torneo", "competicao", "competicoes", "torneio", "campeonato",
        "competition", "competitions", "tournament", "iscrivere a una gara",
    ), {"pt": ("prova", "provas")}),
    Intent("mark_attendance", (
        "segna la presenza", "segnare la presenza", "segna presente", "presente oggi",
        "marcar presenca", "marcar a presenca", "marca presenca",
        "mark attendance", "mark present", "check in",
    )),
    # Il conto delle presenze, prima delle lezioni di oggi: "quante presenze"
    # pesa due, "presenze" da sola uno.
    Intent("attendance_stats", (
        "quante presenze", "quanti allenamenti", "quante lezioni", "quante volte", "frequenza", "assiduita",
        "quantas presencas", "quantos treinos", "quantas aulas", "quantas vezes", "assiduidade",
        "how many trainings", "how many lessons", "how many classes", "how many times", "attendance record",
    )),
    Intent("lessons_today", (
        "lezione", "lezioni", "allenamento", "allenamenti", "oggi", "presenza", "presenze",
        "aula", "aulas", "treino", "treinos", "hoje", "presenca", "presencas",
        "lesson", "lessons", "class", "classes", "training", "today", "attendance",
    )),
    Intent("invite", (
        "invita", "invito", "invitare", "amico", "amici", "convidar", "convite", "amigo", "amigos",
        "invite", "friend", "friends", "referral",
    )),
    Intent("wallet", (
        "wallet", "credito", "saldo", "javcash", "carteira", "balance", "credit",
    )),
    Intent("secretary", (
        "segreteria", "segretaria", "parlare con", "contattare", "contatto", "telefono",
        "secretaria", "falar com", "contactar", "contacto",
        "secretary", "talk to", "speak to", "contact", "human", "a person",
    )),
    Intent("fees_due", (
        "quanto devo", "devo pagare", "da pagare", "quote", "quota", "mensilita", "pagare", "pagamento", "pagamenti",
        "iban", "scadut*", "dovuto", "debito", "debiti", "in debito", "arretrati", "in regola", "sono in regola",
        "devo ancora",
        "quanto devo pagar", "tenho de pagar", "tenho que pagar", "mensalidade", "mensalidades", "quotas",
        "pagar", "pagamentos", "em atraso", "divida", "dividas", "tenho dividas", "estou em divida", "em dia",
        "ainda devo",
        "how much do i owe", "owe", "fees", "fee", "pay", "payment", "payments", "due", "overdue", "debt", "in debt",
        "up to date",
    )),
    Intent("help", (
        "aiuto", "cosa sai fare", "cosa puoi fare", "menu", "ajuda", "o que sabes fazer", "o que podes fazer",
        "help", "what can you do",
    )),
    Intent("greet", (
        "ciao", "buongiorno", "buonasera", "salve", "ola", "bom dia", "boa tarde", "boa noite",
        "hello", "hi", "hey", "good morning", "good evening",
    )),
    Intent("thanks", ("grazie", "obrigado", "obrigada", "thanks", "thank you")),
)

#: Le intenzioni del sito pubblico: un altro vocabolario, nessun dato personale.
PUBLIC_INTENTS: tuple[Intent, ...] = (
    # I corsi JAV nelle scuole (club/kinds.py): prima delle altre, perché
    # "iscrivere a un corso a scuola" deve parlare dei corsi, non dei club.
    Intent("courses", (
        "scuola", "scuole", "a scuola", "corsi jav", "extrascolastico", "doposcuola",
        "escola", "escolas", "na escola", "cursos jav", "extracurricular", "atividade extracurricular", "extraescolar",
        "school", "schools", "at school", "jav courses", "after school",
    )),
    # Gli sconti prima dei prezzi: "come ho uno sconto sulla mensilità?"
    # chiede degli sconti, anche se nomina la mensilità.
    Intent("discounts", (
        "sconto", "sconti", "scontata", "riduzione", "agevolazione", "agevolazioni", "escalao", "judo adattato",
        "fratelli", "fratello", "famiglia", "invitare un amico", "invita un amico",
        "desconto", "descontos", "escaloes", "abono", "judo adaptado", "irmaos", "irmao", "familia",
        "convidar", "convidar um amigo", "convida um amigo",
        "discount", "discounts", "sibling", "siblings", "family discount", "adapted judo", "invite a friend",
        "refer a friend",
    )),
    # "Inscrição" da sola è il prezzo dell'iscrizione più spesso che il modo
    # di iscriversi: a pari punteggio vince "prices" (viene prima), e la
    # scheda dei prezzi porta comunque il bottone per iscriversi. "Como me
    # inscrevo?" resta a "signup" (inscrev*).
    Intent("prices", (
        "prezzo", "prezzi", "costo", "costa", "quanto costa", "mensilita", "quota", "quote", "tariffe", "listino",
        "quota di iscrizione", "costo dell'iscrizione", "iscrizione annuale",
        "preco", "precos", "custa", "quanto custa", "mensalidade", "mensalidades", "valor", "valores", "quotas",
        "propina", "propinas", "tabela de precos", "inscricao", "taxa de inscricao", "inscricao anual",
        "price", "prices", "cost", "how much", "fee", "fees", "price list", "enrolment fee", "enrollment fee",
    )),
    # Gruppi ed età: la stessa scheda dei prezzi (public.py::_prices), che
    # senza "mostra i prezzi" dice comunque gruppi, età e orari.
    Intent("groups", (
        "gruppi", "gruppo", "eta", "che eta", "quale eta", "fasce d'eta", "fascia d'eta", "da che eta", "quanti anni",
        "grupos", "grupo", "idade", "idades", "que idade", "que idades", "a partir de que idade", "escaloes etarios",
        "groups", "group", "age", "ages", "age groups", "what age", "how old",
    )),
    Intent("schedule", (
        "orario", "orari", "quando", "giorni", "horario", "horarios", "dias", "que horas",
        "schedule", "timetable", "when", "hours", "times",
    )),
    Intent("signup", (
        "iscriv*", "iscrizione", "iniziare", "provare", "inscrev*", "inscricao", "comecar",
        "experimentar", "sign up", "signup", "register", "join", "enrol", "enroll", "start",
    )),
    Intent("events", (
        "eventi", "evento", "gare", "gara", "stage", "eventos", "competicoes", "torneio",
        "events", "event", "competition", "competitions", "tournament",
    )),
    Intent("benefits", (
        "benefici", "perche il judo", "fa bene", "bambini", "beneficios", "porque judo", "porque o judo", "criancas",
        "faz bem", "benefits", "why judo", "kids", "children",
    )),
    Intent("clubs", (
        "club", "clube", "clubes", "dove", "onde", "palestra", "dojo", "where", "near", "vicino", "perto",
    )),
    Intent("about", (
        "judoartevida", "judo arte e vida", "progetto", "chi siete", "projeto", "quem sao", "project",
        "who are you", "about",
    )),
    Intent("contacts", (
        "contatto", "contatti", "telefono", "email", "contacto", "contactos", "telefone",
        "contact", "phone",
    )),
    Intent("help", ("aiuto", "ajuda", "help", "menu", "cosa sai fare", "o que sabes fazer", "what can you do")),
    Intent("greet", (
        "ciao", "buongiorno", "salve", "ola", "bom dia", "boa tarde", "hello", "hi", "hey",
    )),
    Intent("thanks", ("grazie", "obrigado", "obrigada", "thanks", "thank you")),
)

YES = (
    "si", "sì", "confermo", "conferma", "ok", "va bene", "certo", "procedi",
    "sim", "confirmo", "confirmar", "pode ser", "claro", "avanca",
    "yes", "confirm", "sure", "go ahead", "yep",
)
NO = (
    "no", "annulla", "lascia stare", "non ora", "nao", "cancelar", "cancela", "agora nao",
    "cancel", "stop", "not now", "nope",
)


def _contains(norm: str, word: str) -> bool:
    # Parola intera (o frase intera): "pagare" non deve accendersi su
    # "pagarei". Con l'asterisco finale è una radice: "iscriv*" vale per
    # iscrivo, iscriversi, iscrivere.
    if word.endswith("*"):
        return re.search(rf"(?<![a-z0-9]){re.escape(word[:-1])}", norm) is not None
    return re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", norm) is not None


def _score(intent: Intent, norm: str, lang: str) -> int:
    words = intent.words + tuple((intent.by_lang or {}).get(lang, ()))
    # Le frasi di più parole pesano di più: "chi non ha pagato" batte "pagare".
    return sum(1 + word.count(" ") for word in words if _contains(norm, normalize(word)))


def detect(text: str, *, lang: str, catalog: tuple[Intent, ...] = INTENTS) -> tuple[str | None, int]:
    """(intenzione, punteggio); (None, 0) se nessuna parola nota."""
    norm = normalize(text)
    best, best_score = None, 0
    for intent in catalog:
        score = _score(intent, norm, lang)
        if score > best_score:
            best, best_score = intent.code, score
    return best, best_score


def is_yes(text: str) -> bool:
    norm = normalize(text).strip(" .!")
    return any(norm == w or norm.startswith((w + " ", w + ",")) for w in map(normalize, YES))


def is_no(text: str) -> bool:
    norm = normalize(text).strip(" .!")
    return any(norm == w or norm.startswith((w + " ", w + ",")) for w in map(normalize, NO))


def mentions(text: str, *words: str) -> bool:
    norm = normalize(text)
    return any(_contains(norm, normalize(w)) for w in words)


def extract_height_cm(text: str) -> int | None:
    """L'altezza in centimetri: "145", "145 cm", "1,45 m", "1.45". Fuori da
    80–215 cm non è un'altezza (è un anno, un prezzo, un errore)."""
    norm = normalize(text)
    metres = re.search(r"(?<![0-9])([12])[.,]([0-9]{1,2})\s*(m|mt|metri|metros|metres|meters)?(?![0-9])", norm)
    if metres:
        cm = int(metres.group(1)) * 100 + int(metres.group(2).ljust(2, "0"))
        if 80 <= cm <= 215:
            return cm
    for match in re.finditer(r"(?<![0-9.,])([0-9]{2,3})(?![0-9.,])", norm):
        cm = int(match.group(1))
        if 80 <= cm <= 215:
            return cm
    return None

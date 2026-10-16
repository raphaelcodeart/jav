# Le email

## La veste

`apps/api/app/core/email_templates.py::render_email`: un guscio solo per
tutte le email (tabelle e stili in linea, per Outlook e Gmail). Due marchi:

- **JudoArteVida** (`jav_brand()`): le comunicazioni della piattaforma
  (Shop di JudoArteVida, supporto, wallet, conferme dell'account senza club);
- **il club** (`domains/club/email_brand.py::club_brand`): logo e colori
  della sua pagina pubblica, contatti, e in fondo «Clube da Rede
  JudoArteVida» con il logo della rete. Un'email a una persona di un club
  (inviti, conferma dell'email, nuova password, codici, promemoria, prove
  rifiutate) usa il marchio del suo club (`brand_for_user`); i messaggi dal
  sito e la richiesta di trasporto quello del club che li riceve o li manda.

## I testi personalizzabili

`apps/api/app/domains/email_texts/`: per le email principali (conferma
dell'email, invito, nuova password, codice di conferma, prova rifiutata,
messaggio dal sito) c'è un testo predefinito in portoghese e il superadmin
lo cambia dalla console (📧 Email): oggetto, titolo, testo e bottone, con i
segnaposto tra graffe (`{marca}`, `{codigo}`...), l'anteprima con il marchio
di JudoArteVida o di un club e l'invio di una prova a sé. Il testo è testo
semplice (l'escape lo fa `text_to_html`); un segnaposto sconosciuto si
rifiuta al salvataggio. Senza personalizzazione vale il predefinito
(`email_template_overrides` vuota).

## Le altre email del club

Con la veste del club ma testo fisso (in portoghese, da `club_service.email_guardian`):
gli **avvisi della mensilità** del 1, 10 e 15 e la **multa** del 16
(`club/payment_reminders.py`), il **«Quero participar»** dell'atleta al
titolare del conto (`athlete_router.wish_to_compete`). La **richiesta di un
nuovo club** è un messaggio dal sito (`contact_message`) con l'oggetto
«Novo clube — …».

## SMTP

`.env`: `SMTP_HOST=smtp.hostinger.com`, `SMTP_PORT=587` (STARTTLS; la 465
da questo server non è raggiungibile), `SMTP_USERNAME`/`SMTP_FROM_ADDRESS`
= `noreply@judoartevida.com`, `SMTP_PASSWORD`. Dopo una modifica al `.env`
si ricreano `api`, `celery-worker` e `celery-beat`. Se l'invio non riesce le
operazioni riescono comunque (`send_html_email_best_effort`) e i messaggi
restano nelle caselle del portale.

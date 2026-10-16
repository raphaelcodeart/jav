# Guida Utente — Jav

Jav è il portale del club: le famiglie gestiscono iscrizioni, quote, prove di
pagamento, certificati e gare dei propri figli; la segreteria tiene in ordine
il club; gli istruttori segnano presenze e cinture. Questa guida descrive cosa
si può fare **oggi** (il dettaglio tecnico è in `docs/implementation-progress.md`
e `docs/club-portal.md`).

> L'interfaccia è in fase di ridisegno: nomi dei pulsanti e posizione delle
> sezioni possono cambiare leggermente, le funzioni descritte qui no.

## 1. Come accedere

Apri il browser (dal telefono va benissimo) sull'indirizzo del club, per
esempio `https://jav.ecodo.ai/login`.

**Lingua.** In alto a destra c'è una bandierina: tocca e scegli **portoghese**,
**inglese** o **italiano**. Si parte in portoghese; la scelta resta salvata sul
dispositivo (anche dopo l'uscita). Per ora sono tradotti l'accesso e l'area
famiglie; il resto e i messaggi che arrivano dal server sono ancora in
italiano.

Servono **Organization ID** (te lo comunica la segreteria), **email** e
**password**.

- Se sbagli, il messaggio è sempre lo stesso ("email o password non validi"),
  sia che l'email non esista sia che la password sia sbagliata: è una scelta
  di sicurezza. Dopo **5 tentativi falliti** l'account si blocca per 15 minuti.
- **Password dimenticata?** Link sotto il campo password → Organization ID ed
  email → arriva un link per sceglierne una nuova, valido 60 minuti e
  utilizzabile una volta sola. Il link arriva sempre alla casella dell'account.
- Al primo accesso ti viene chiesto di completare il profilo (dati anagrafici,
  privacy): è normale, serve una volta sola.

**Registrazione.** Non esiste un modulo aperto a chiunque: si entra con il
**link del proprio club** (per esempio `https://jav.ecodo.ai/c/judo-clube-de-lagos`,
lo dà la segreteria) o con il link di invito di chi ti ha presentato. Chi si
registra dal link del club entra in quel club. L'account creato è quello del
**genitore** (o dell'atleta adulto): i figli si aggiungono dopo,
dall'interno. Arriva un'email per confermare l'indirizzo.

## 2. Per i genitori (e gli atleti adulti)

**Solo il genitore accede.** I figli non hanno un account: sono *atleti*
gestiti da te. Se ti alleni anche tu, aggiungi te stesso come atleta
("me stesso").

### 2.1 La pagina della famiglia

È la prima cosa che vedi. Per ogni figlio c'è una **card** con foto, cintura,
piano, prossima quota da pagare, stato del certificato medico, prossima gara,
punti nel Jav Ranking, livello e medaglie conquistate. Sotto, il **riepilogo
della famiglia**: quanto c'è da pagare, cosa è scaduto, quanto hai pagato in
questa stagione e le ultime prove caricate.

### 2.2 Aggiungere un figlio

Nome, cognome, data di nascita, sesso: basta. **Il piano lo sceglie il
sistema dall'età federale**: gli anni che il ragazzo compie entro il 31
dicembre (chi è nato a novembre conta già con l'età che avrà a novembre). A
gennaio l'età federale sale di uno: se il ragazzo entra nella fascia del
gruppo dopo, dalla mensilità di gennaio paga quella del gruppo nuovo, e ti
arriva un avviso. Appena aggiunto compaiono la quota d'iscrizione della stagione e
la quota del mese.

Nei **corsi JAV nelle scuole** si sceglie anche il corso (la scuola): se
sei arrivato da «Inscrever» sul sito è già scelto. Lì non c'è iscrizione,
solo la mensilità, e non ci sono cinture, gare e ranking: chi vuole
continuare può chiedere alla segreteria di passare a un club.

### 2.3 Pagare: carica la prova

Premi **Carica un pagamento**: per prima cosa scegli **che cosa** hai pagato.

**Quote del club** (mensilità, iscrizione, gare):

1. Fai il bonifico all'IBAN del club (lo trovi nella schermata di pagamento,
   con le istruzioni per la causale).
2. Scegli le quote che quel bonifico paga — anche di più figli insieme — e
   scatta una foto della ricevuta (o carica il PDF).
3. Fatto: **le quote risultano subito pagate.**

**Sconti e credito.** Sulla mensilità puoi avere lo sconto dell'escalão
(A/B/C, o judo adattato: lo imposta la segreteria quando vede il documento) e
lo sconto famiglia se hai più figli iscritti: la quota mostra il prezzo di
listino e gli sconti. Se hai credito nel wallet (per esempio dagli inviti),
spunta **Usa il credito**: confermi con il PIN o il codice via email, e se il
credito copre tutto non serve la ricevuta.

**Iscrizione annuale.** Vale dal 1° gennaio al 31 dicembre; se entri a metà
anno paghi solo i mesi che restano. Per un atleta minorenne anche il genitore
diventa socio (una quota per famiglia).

**Invita un amico.** Nella pagina della famiglia c'è il tuo link: quando una
famiglia che hai invitato paga una mensilità, ricevi credito nel wallet.

**Ordine dello Shop** (judogi, materiale): scegli l'ordine in attesa di
bonifico, fai il bonifico alle coordinate dello Shop che vedi lì e allega la
ricevuta. L'ordine parte quando il pagamento è confermato.

**Contanti.** Se hai dato i soldi a qualcuno del club, nella stessa finestra
scegli **Contanti** e indica a chi (o scrivi il nome). Niente foto: la quota
risulta pagata e quella persona riceve un avviso. **Carta online** c'è ma è
spenta: arriverà quando il club avrà il pagamento online.

**Le mensilità mese per mese.** Nella scheda di ogni figlio, scheda
**Quote**, c'è il calendario della stagione: dodici caselle da settembre ad
agosto. Verde pagata, giallo da pagare, **rosso scaduta**, tratteggiata la
prevista (con l'importo che avrà, compreso il cambio di gruppo a gennaio).
Tocca un mese per il dettaglio — gruppo ed età federale, scadenza, sconti,
quando e come è stata pagata, la ricevuta — e per pagarlo. Sopra, due
grafici: quanto della stagione è pagato e le presenze di ogni mese. Nella
pagina della famiglia una barra per figlio mostra pagato, da pagare e
scaduto. Anche l'atleta, dalla sua area, vede il suo calendario (senza
poter pagare).

La segreteria può controllare le prove. Se una non va bene, ricevi una
notifica e un'email con il motivo, e le quote tornano da pagare.

Le quote mensili si creano da sole il 1° del mese, solo per i mesi previsti
dal piano (di solito settembre–giugno). Se una quota scade, ti arriva un
promemoria.

### 2.4 Certificato medico

Dalla scheda dell'atleta: tipo (agonistico o non agonistico), date di
rilascio e scadenza, foto o PDF. Ti avvisiamo **30 e 7 giorni prima** della
scadenza e quando è scaduto. Senza certificato agonistico valido alla data
della gara non ci si può iscrivere alle gare che lo richiedono.

### 2.5 Gare

**Iscrivi a una gara**: vedi le gare aperte e, per ogni figlio, se può
iscriversi (e perché no, se non può: età, certificato, iscrizioni chiuse).
Se la gara ha una quota, compare tra le quote da pagare e si paga come le
altre, con la prova. Puoi ritirare l'iscrizione fino alla scadenza; dopo la
scadenza nessuno può più iscriversi.

**Giustificazione per la scuola.** Se la gara cade in un giorno di scuola,
la segreteria prepara la giustificazione delle assenze: quando è pronta,
accanto al nome di tuo figlio compare **Giustificazione per la scuola**, che
scarica il PDF da portare a scuola.

### 2.6 Jav Ranking, cinture, medaglie

- **Jav Ranking**: la classifica del club per stagione, sesso e fascia
  d'età. I punti arrivano dai piazzamenti in gara (1° 100, 2° 70, 3° 50,
  5° 30, 7° 20, partecipazione 10) moltiplicati per il livello della gara
  (club ×1, regionale ×2, nazionale ×3, internazionale ×4).
- **Cinture**: lo storico dei passaggi di grado di ogni figlio; le assegna
  l'istruttore.
- **Livello e medaglie**: crescono con presenze, cinture e gare (prima gara,
  primo podio, 50 e 100 presenze, …).

### 2.6 bis Bacheca

Le notizie del club (foto, video, link) e i documenti che il club condivide
con te (regolamento, calendario): li apri con un tocco. Quelle uscite dopo
la tua ultima visita hanno «Nuovo». Anche l'atleta con il suo accesso la
vede nella sua area.

### 2.7 Corsi

L'elenco dei corsi con giorni e orari; puoi iscrivere o togliere un figlio da
un corso.

### 2.8 Materiale (judogi, cinture, attrezzatura)

**Ordina materiale** apre lo Shop del club: scegli prodotto e taglia, indica
per quale figlio è, e paghi con bonifico (con l'eventuale credito JavCash).
Lo stato dell'ordine lo vedi in "I miei Ordini".

### 2.9 Il resto

- **JavCash**: il credito interno (bonus di benvenuto, cashback). Si spende
  nello Shop, mai per l'intero prezzo; per usarlo serve un codice via email
  o il tuo PIN.
- **Contabilità**: tutti i tuoi movimenti, in euro e in JavCash, con il
  dettaglio di ciascuno.
- **Assistenza**: apri una richiesta alla segreteria e segui la risposta.
- **JAVBOT** (il bottone rosso in basso a destra): conosce la tua
  situazione. Chiedigli «quanto ho pagato?», «ho debiti?», «cosa sai di
  me?», «i miei dati», «che cintura ha Luca?», «quante presenze?» o
  «quanti punti ho nel ranking?»: risponde con i tuoi numeri, gli stessi di
  «I miei conti» e della scheda dell'atleta. Vede solo la tua famiglia.
  Conosce anche i documenti del club e di JudoArteVida (regolamenti,
  orari speciali, regole degli esami): chiedigli «cosa serve per l'esame di
  cintura?» o «il dojo è aperto ad agosto?»: ti mostra il passaggio del
  documento che risponde, con il titolo e la pagina.
- **Invita un amico**: il tuo link personale e chi si è iscritto con quello;
  ogni 5 amici con un contratto attivo puoi richiedere un omaggio, che
  consegna la segreteria.

## 3. Per la segreteria

Ogni club ha la sua segreteria (ruolo **Segreteria**), che vede **solo il
proprio club**: entrando, l'area si apre direttamente sul club. Le sezioni:

- **Atleti**: elenco con filtri (stato, piano, ricerca), scheda con famiglia,
  quote, certificati, cinture, gare. Si può fissare a mano il piano di un
  atleta (non cambierà più da solo con l'età), cambiarne lo stato (attivo,
  sospeso, uscito), registrare il tesseramento federale.
- **Piani**: le fasce d'età con quota mensile, iscrizione annuale, giorno di
  scadenza e mesi fatturati. Un piano in uso non si cancella.
- **Quote**: elenco con filtri. Su una quota: **segna pagata** — scegli come
  (contanti, carta, bonifico) e, per i contanti, a chi sono stati dati (una
  persona dello staff o un nome scritto) —, **condona**, **riapri**. Sotto
  lo stato di ogni quota pagata c'è come è stata pagata. Nella scheda di un
  atleta (sezione Atleti) c'è il suo calendario delle mensilità, mese per
  mese, da cui segnarle pagate. Si possono anche generare a mano le quote di un
  mese (lo fa comunque il sistema il 1° del mese).
- **Prove caricate**: le prove dei genitori, già accettate: ricevute di
  bonifico, o contanti dichiarati con il nome di chi li ha presi (quella
  persona riceve un avviso). Se una non va (per esempio i contanti non sono
  mai arrivati), **rifiutala** con un motivo: le quote tornano da pagare e il genitore viene
  avvisato.
- **Certificati**: chi è in scadenza o scaduto.
- **Gare & risultati**: crea la gara (data, luogo, livello, scadenza,
  quota, età, certificato agonistico richiesto), segui gli iscritti, chiudi o
  riapri le iscrizioni, inserisci i piazzamenti a gara finita: il ranking si
  aggiorna da solo. In **Iscritti e risultati**, accanto a ogni iscritto,
  🏫 **Giustificazione**: il sistema propone la lettera alla scuola (il club
  ha selezionato l'atleta per la gara, si chiede di giustificare le assenze)
  con i suoi dati e quelli della gara; la correggi (la classe, la scuola) e
  premi **Genera e scarica il PDF**. Il PDF è su carta intestata del club,
  resta salvato nell'area privata e il genitore lo scarica dalla sua pagina
  delle gare. Rigenerarla sostituisce la precedente.
- **Corsi & presenze**: corsi, orari, istruttori, iscritti. Per correggere
  un orario (es. finisce alle 19:00 e non alle 18:30) **tocca l'orario ✎**:
  giorno, ore e sala si cambiano senza toglierlo e rifarlo.
- **Gare e stage, trasporto**: un evento può essere una gara o uno stage
  (che non dà punti). Spunta "Chiedere il trasporto" e indica ente, email,
  partenza e accompagnatori: quando le iscrizioni si chiudono la lettera al
  comune si scrive da sola e ti arriva una notifica; dal pulsante 🚌
  **Richiesta trasporto** la rileggi, la correggi e la mandi con un clic.
- **Prezzi e sconti** (in Impostazioni): percentuali degli escalão, sconto
  famiglia, credito per invito, quota socio del genitore, che cosa comprende
  l'iscrizione. Sulla scheda dell'atleta: escalão e judo adattato.
- **Ordini Shop**: gli ordini di judogi e materiale fatti dalle famiglie del
  club, con lo stato (in attesa di pagamento, pagato, spedito). Solo
  consultazione: lo Shop è della piattaforma, che conferma i bonifici e
  spedisce.
- **Documenti del club**: certidões delle Finanze e della Segurança Social,
  atas, rivalidazione alla federazione, assicurazioni, statuto. Con la
  scadenza, ricevi un avviso 30 giorni prima. Li vedi solo tu e
  JudoArteVida, a meno che spunti **«Condividi con atleti e famiglie»**
  (regolamento, calendario della stagione): allora compaiono anche nella
  loro **Bacheca**.
- **📰 Notizie**: scrivi una notizia come un post — titolo, testo, una
  foto, un video (YouTube o Vimeo si vedono dentro la notizia) o un link —
  e compare nella **Bacheca** di atleti e famiglie (non sul sito pubblico).
  Con l'anteprima mentre scrivi; puoi metterla in evidenza in cima,
  salvarla come bozza, nasconderla o eliminarla.
- **JAVBOT**: che cosa sa l'assistente dei tuoi soci. Carica i **PDF del
  club** (regolamento interno, orari speciali, materiale, procedure: PDF con
  testo, fino a 15 MB; una scansione compare come «Senza testo» e non si
  usa) e scrivi le **istruzioni per il club** (come deve rispondere: «il
  dojo è al primo piano», «per le gare rimanda alla segreteria»). Si
  aggiungono ai documenti e alle istruzioni comuni di JudoArteVida, che
  vedi in fondo alla pagina. La console della piattaforma ha la stessa
  pagina per la base comune a tutti i club (JudoArteVida → JAVBOT).
- **Impostazioni**: IBAN, intestatario e istruzioni per il bonifico delle
  quote (li vedono i genitori quando pagano), l'email di contatto del club,
  il **link di registrazione** da dare alle famiglie (con il pulsante per
  copiarlo), e lo **staff**: si aggiungono istruttori o altre persone di
  segreteria, che ricevono l'email per scegliersi la password.

**Persone**: atleti, genitori, segreteria, treinador e monitor in un elenco,
ognuno con il suo simbolo (🥋 atleta, 👪 genitore, 🗂️ segreteria, 🧑‍🏫 treinador,
🤝 treinador adjunto, 🎽 monitor, 🎗️ monitor adjunto, 🧑‍⚖️ árbitro). Chi è più
cose ha più simboli (un adulto che si allena, ha figli, insegna e arbitra:
🥋 👪 🧑‍🏫 🧑‍⚖️), e gli stessi simboli piccoli compaiono accanto ai nomi negli
altri elenchi (atleti, quote, certificati, iscritti alle gare, presenze).
Tocca un nome: debiti, pagamenti, risultati, investimenti, la funzione e la
casella «È anche árbitro». **Taxa de falta**: chi ha
fatto poche lezioni nel mese, con un clic metà mensilità o niente. **Ore
dello staff** e **Registro presenze**: il cartellino e chi è venuto. **Sito
del club**: testi, foto, contatti, judoka pubblicati (solo con il consenso
della famiglia), pulsante Pubblica.

**La pagina del club, un piccolo sito.** In **Sito del club**, oltre a
testi, foto, colori e contatti: *Sede degli allenamenti* e *Anno di
fondazione* (sul sito: "desde 2004" e gli anni di judo); **Il club in
numeri** (fino a 6: un numero e che cosa, es. *3 · títulos nacionais*);
**Perché allenarsi con noi** (fino a 6 punti di forza); **La storia** (le
tappe, il sito le mette in ordine di anno); **Novità** (come i post di
Facebook: data, titolo, testo, una foto, un link; la più recente in alto);
**Video scelti** (link di YouTube). Per ogni allenatore anche il **grado**
e due righe. Una parte lasciata vuota non compare sul sito. Se il link
YouTube del club è un canale (`youtube.com/channel/...`) gli ultimi video
compaiono da soli. Ricorda **Salva** in fondo.

**La pagina pubblica di un judoka.** Ogni judoka sul sito ha la sua pagina,
come le schede della Federazione Internazionale: foto, cintura e passaggi,
risultati, prossime gare, posto nel ranking, medaglie, foto e video. Quasi
tutto arriva da solo dal gestionale; tu aggiungi il resto. Apri l'atleta
(**Atleti** → tocca il nome, oppure **Sito del club** → *Judoka sul sito* →
**Pagina pubblica**) e nella sezione **Pagina pubblica**:

1. **Profilo IJF**: se il judoka ha una scheda sul sito della Federazione
   Internazionale, aprila su ijf.org (o su JudoBase) e incolla l'indirizzo
   (per esempio `https://www.ijf.org/judoka/12345`). Altri indirizzi non sono
   accettati. Sul sito compare il bottone «Ver perfil IJF».
2. **Due righe**, **tecnica preferita** (es. *Seoi-nage*) e **guardia**
   (destra o sinistra), poi **Salva i testi**. Le due righe sono le stesse
   che il genitore scrive dal suo portale: le vedete e correggete entrambi.
3. **Foto**: **Aggiungi foto** (JPG, PNG o WebP fino a 5 MB, al massimo 24).
   Ogni foto arriva *non pubblicata*: guardala e tocca **Pubblica** quando va
   bene; **Togli dal sito** la nasconde, **Togli** la cancella.
4. **Video**: solo YouTube. Su YouTube tocca *Condividi*, copia il link,
   incollalo e tocca **Aggiungi video** (al massimo 12); poi **Pubblica**.

In alto vedi se la pagina è già visibile, con il link **Vedi la pagina
pubblica**. Se non lo è, la riga dice perché: la famiglia non ha ancora dato
il consenso, oppure devi ancora accendere l'atleta in *Judoka sul sito*.
Puoi preparare la pagina prima: nessuno la vede finché manca il consenso.
**Foto e video compaiono solo se la famiglia ha permesso la foto**; se la
famiglia ritira il consenso, tornano tutti non pubblicati. Nei **Cursos
JAV** la sezione non c'è: gli atleti dei corsi non compaiono mai sul sito.

**I colori e il logo della pagina del club.** In **Sito del club**:

1. **Foto**: carica la **copertina** (la foto grande in alto: meglio
   orizzontale, una foto del tatami o della squadra) e il **logo** (meglio
   quadrato, su fondo bianco). Sulla pagina il logo compare in un cerchio
   che sporge dalla copertina, come su Facebook.
2. **Colori del club**: scegli il **colore principale** (di solito il colore
   più forte del logo), il **secondario** e l'**accento** dalla tavolozza,
   oppure scrivili (per esempio `#C92429`). A destra vedi subito come sarà
   la copertina. Non serve preoccuparsi della leggibilità: il testo dei
   bottoni diventa bianco o nero da solo, e se un colore è troppo chiaro
   per i titoli la pagina ne usa una versione più scura (te lo dice un
   avviso giallo). **Usa i colori di JudoArteVida** toglie i colori del club.
3. **Contatti e social**: Facebook, Instagram e YouTube accettano solo
   indirizzi di quei siti. Apri la pagina del club su Facebook e copia
   l'indirizzo dalla barra del browser (va bene anche senza `https://`).
4. **Salva**. Se la pagina è pubblicata, i cambiamenti si vedono subito.

**I messaggi dal sito.** In fondo alla pagina pubblica del club c'è il
modulo «Envie uma mensagem ao clube». Quando qualcuno scrive, ricevi una
notifica (la campanella) e il messaggio arriva in **Messaggi** ✉️ (nel
menu, gruppo *Club*) e, se nella pagina c'è l'email di contatto, anche per
email. In **Messaggi**:

- **Rispondi via email** apre il tuo programma di posta già compilato:
  la risposta va direttamente a chi ha scritto;
- **Segna come letto** / **Segna da leggere**, e **Archivia** quando hai
  finito (gli archiviati restano nella scheda *Archiviati*);
- la riga grigia «arrivato solo qui» vuol dire che l'email di avviso non è
  partita (per esempio perché l'invio delle email non è ancora attivo): il
  messaggio è comunque qui.

Vedi solo i messaggi scritti al tuo club. Chi scrive deve accettare di
essere ricontattato: usa quei dati solo per rispondere.

### 3.1 Per il superadmin: i club

**Messaggi a JudoArteVida.** Chi scrive dalla pagina **Contactos** del sito
(`/contactos`) scrive a JudoArteVida: il messaggio arriva in console →
**JudoArteVida** → **Messaggi** ✉️ (con la notifica) e per email a
info@judoartevida.com. Lo vedono gli amministratori della piattaforma; il
superadmin, dal menu in alto della casella, può guardare anche i messaggi
di un club o tutti. Si risponde, si segna letto e si archivia come nella
casella di un club.

Nell'area amministrazione la sezione **Club** elenca tutti i club, con atleti
attivi, staff e stato. Da qui:

- **Nuovo club**: nome, indirizzo per le famiglie (proposto dal nome),
  email della segreteria, IBAN e intestatario delle quote. La segreteria
  riceve l'email per scegliersi la password. Se l'invio delle email non è
  configurato, compare il link di primo accesso: copialo e mandalo tu (vale
  7 giorni).
- **Entra**: apri la gestione del club come la vede la sua segreteria; una
  fascia in alto ricorda in che club sei e riporta all'elenco.
- **Aggiungi staff**, **Sospendi / Riattiva**: un club sospeso non è più
  accessibile alle sue famiglie e alla sua segreteria, i dati restano.

Restano tue anche le funzioni generali della piattaforma: utenti e ruoli,
Shop e ordini, JavCash, contratti, rete promoter e provvigioni, assistenza,
contabilità.

#### I corsi JAV nelle scuole

I corsi di judo che JudoArteVida tiene nelle scuole non sono un club: hanno
un'entrata loro nella console, **Cursos JAV** 🏫, accanto a «Tutti i club».

- La prima volta premi **«Crea l'unità Cursos JAV»**: nasce con un piano da
  25 € al mese, senza iscrizione (lo cambi da «Piani e prezzi»). Gli sconti
  partono spenti; la commissione della piattaforma è sempre 0%.
- **«Gestisci i corsi»** apre l'elenco dei corsi, ognuno con il suo
  cruscotto del mese: iscritti, presenze, incassato, parte del treinador,
  parte di JAV, ancora da incassare, debiti. Il mese si sceglie in alto.
- **Nuovo corso / Modifica**: nome, scuola, indirizzo, città, età, il
  treinador responsabile e la sua percentuale (default 50%), il nome con cui
  il treinador compare sul sito (solo se è d'accordo), il testo per le
  famiglie, «Mostra sul sito», gli orari della settimana. Una percentuale
  nuova vale per le quote emesse da quel momento.
- **Iscritti** mostra chi frequenta il corso e permette di iscrivere o
  togliere un atleta; **Quote** le mensilità del corso. Le «Quote senza
  corso» sono di atleti aggiunti senza scegliere un corso: iscrivili e le
  quote ancora da pagare passano al corso.
- Il link da dare alle scuole e alle famiglie è quello dell'unità
  («Copia il link d'iscrizione»); dal sito, «Inscrever» su un corso porta
  allo stesso link con il corso già scelto.
- Nella **Panoramica** della piattaforma i corsi hanno una riga a parte: ciò
  che JAV tiene (incassi meno la parte dei treinador), questo mese, nell'anno
  e da sempre.

**Passare una famiglia a un club.** Nei corsi, da **Persone** apri il
genitore (o l'atleta adulto) e premi **«Passa a un club»**, poi scegli il
club. Si può solo se la famiglia non ha quote da pagare nei corsi. I figli
lasciano i corsi ed entrano nel club con la cintura bianca e il piano per
età: iscrizione dell'anno a pro rata e mensilità dal mese prossimo. Le quote
già pagate restano nei conti dei corsi.

### 3.2 Lo Shop: fornitori e «Fornitori da avvisare»

Nell'area amministrazione, pagina dello Shop («Fai la Spesa con Jav»):

- **Impostazioni del negozio**: oltre a spedizione e ordine minimo, l'**email
  da cui scrivere ai fornitori** (per esempio info@…: le loro risposte
  tornano lì e la casella tiene una copia di ogni ordine mandato) e la
  **firma** in fondo alle email.
- **Fornitori**: le aziende che fanno la merce (integratori, attrezzatura,
  judogi…). Per ognuna nome, email per gli ordini, telefono, partita IVA,
  sede e una descrizione che vede il cliente. «Modifica» corregge una
  scheda, email compresa. Senza email gli ordini non le si possono mandare.
- **Categorie e fornitori**: le categorie con cui il cliente filtra i
  prodotti. Accanto a ogni categoria scegli il **fornitore**: tutti i
  prodotti della categoria che non hanno un fornitore loro vanno a lui. Da
  qui puoi anche mettere più prodotti in una categoria in un colpo solo.
- **Prodotti in catalogo**: ogni prodotto mostra a quale fornitore andranno
  i suoi ordini, e se lo eredita dalla categoria («dalla categoria …»). Nel
  prodotto puoi scegliere un fornitore diverso, che vale al posto di quello
  della categoria, e le sue categorie.
- **Fornitori da avvisare**: gli ordini pagati che i fornitori non hanno
  ancora ricevuto, una scheda per fornitore con quanti ordini e quanti pezzi.
  Premi **«Prepara email»**: si apre l'email già scritta — tutti gli ordini
  di quel fornitore, ciascuno con i prodotti, l'indirizzo di consegna, il
  telefono e le note del cliente, e la richiesta di rispondere con corriere
  e tracking. Non ci sono prezzi. Puoi cambiare destinatario, oggetto e
  testo, poi premi **«Invia»**: l'email parte e quegli ordini risultano
  mandati, quindi spariscono dalla lista. Se l'email non parte (per esempio
  perché l'invio delle email non è ancora configurato) te lo dice e nessun
  ordine viene segnato: puoi riprovare senza rischio di doppioni. Sotto
  trovi le **righe senza fornitore** — prodotti che non sanno a chi andare:
  scegli il fornitore sul prodotto o sulla sua categoria e compaiono subito
  sotto quel fornitore — e lo **storico degli invii**, con il testo esatto
  di ogni email.
- **Ordini**: il pulsante «Invia alle aziende per email» su un singolo
  ordine manda solo quello che non è ancora partito; un ordine mandato dalla
  lista dei fornitori non ripartirà da qui. Quando il fornitore risponde con
  il tracking, «Segna come spedito» avvisa il cliente.

## 4. Per i treinador (e gli adjunto)

Entrando si apre **Presenze di oggi**: la lezione in corso è già scelta; un
tocco sul cerchio segna l'entrata dell'atleta, 📝 aggiunge una nota per la
segreteria. Si può scegliere un altro giorno per correggere. **Calendario**
mostra le lezioni della settimana dei tuoi corsi; **Cartellino** ha il
pulsante Entro / Esco e le ore di oggi e del mese.

Le famiglie, dalla loro pagina, possono segnare "È arrivato" solo per oggi.

**Nei corsi JAV nelle scuole** non ci sono cinture né ranking; al loro posto
c'è **I miei guadagni**: per ogni mese e ogni tuo corso, quanto è entrato
dalle mensilità e quanto ti spetta (la tua percentuale), più quanto arriverà
quando le famiglie avranno pagato le quote già emesse.

**Il mio lavoro**: le tue ore del mese, la tua tariffa e quanto valgono; sotto
scrivi i **compiti** che hai svolto (montato il tatami, accompagnato alla
gara…) con data e, se vuoi, i minuti. Finché non sono pagati puoi toglierli.
**Messaggi**: due conversazioni, con la **segreteria del club** (turni,
assenze, materiale) e con **JudoArteVida** (formazione, rete, portale); ti
arriva una notifica quando ti rispondono.

## 4bis. Per gli istruttori (vecchia sezione)

Ruolo **Istruttore**. Vedi i tuoi corsi:

- **Presenze**: apri il corso e il giorno, un tocco per atleta presente o
  assente. Non si segnano presenze nel futuro.
- **Cinture**: dalla scheda di un atleta registri un passaggio di grado (solo
  verso un grado superiore), con data e nota.

## 5. Rete promoter, contratti e provvigioni

Il gestionale conserva la sua parte commerciale, utile se il club ha
procacciatori o affiliati che portano iscritti:

- **Promoter**: hanno un link personale, vedono la propria rete, i propri
  clienti e le proprie provvigioni.
- **Contratti e pratiche**: un cliente può sottoscrivere più servizi in una
  pratica sola (dati e documenti una volta, un bonifico solo); paga in unica
  soluzione, 3 o 12 rate. Ogni bonifico lo conferma l'amministrazione.
- **Provvigioni**: si calcolano **solo** quando un contratto diventa attivo
  (pagato **e** approvato), sulla catena degli sponsor com'era in quel
  momento; con le rate partono una quota alla volta. Prima di approvare,
  l'amministrazione vede e conferma un'anteprima di chi riceve cosa.
- **IVA**: un privato non paga IVA sui contratti; un'azienda paga prezzo + IVA.

## 6. Domande frequenti

**"Ho dimenticato l'Organization ID."** Chiedilo alla segreteria: non è
recuperabile dalla pagina di login.

**"Ho caricato la prova ma la quota è tornata da pagare."** La segreteria ha
rifiutato la prova: il motivo è nella notifica e nell'email che hai ricevuto.

**"Mio figlio non si può iscrivere a una gara."** Accanto al suo nome c'è il
motivo: di solito il certificato agonistico manca o scade prima della gara,
oppure l'età non rientra, oppure le iscrizioni sono chiuse.

**"Perché mio figlio è in quel piano?"** Il piano dipende dall'età al 1°
settembre della stagione. Se serve un'eccezione, la segreteria può fissarlo a
mano.

**"Posso usarlo dal telefono?"** Sì: il portale è pensato prima di tutto per
il telefono, compresa la foto della ricevuta e del certificato.

## Sito pubblico: ranking, coppa dei club, sponsor, messaggi

- **Ranking** (`/ranking`): scegli *Anno* (quello che conta), *Mese* o
  *Sempre*, l'anno e il mese; cerca un judoca o un club nella casella e
  tocca un nome per aprire la sua scheda (completa se la famiglia l'ha
  pubblicata, ridotta altrimenti). La scheda **Taça dos Clubes** mette in
  fila i club per i punti dei loro atleti: a fine anno il primo vince la
  coppa, e l'albo d'oro ricorda i vincitori.
- **Sponsor** (console → 🤝 Sponsor): aggiungi nome, logo, sito, colore e
  descrizione; compaiono nella barra di loghi della home e ognuno ha la sua
  pagina con il bottone verso il suo sito. «Nascondi» lo toglie dal sito.
- **Messaggi**: da `/contactos` chi scrive sceglie se scrivere a
  JudoArteVida o a un club e l'argomento; da `/patrocinadores` arrivano le
  richieste di sponsorizzazione. Tutto finisce in **Messaggi** (della
  console o della segreteria del club) anche se l'email non parte; filtra
  per argomento, rispondi con ↩.

## Il mese: chi deve ancora pagare

- **Segreteria**: in **Panoramica** e in **Quote → 📅 Il mese** trovi il mese
  corrente in grande, la barra di quanto è già incassato e un riquadro per
  ogni atleta: gruppo, quanto paga e se ha pagato. Parti da «Da pagare»:
  tocca **✓ Segna pagato**, scegli come (contanti e a chi, MB Way, bonifico,
  carta) e il riquadro passa in «Pagati». Se la persona deve anche mesi
  vecchi, una gara o un judogi, li vedi nel riquadro e li chiudi insieme.
  Con ‹ › vai ai mesi prima e dopo; filtra per gruppo o cerca un nome.
  L'elenco di tutte le quote resta in **Quote → 📋 Tutte le quote**.
- **Famiglia**: in cima alla pagina c'è «Questo mese», con la mensilità di
  ogni figlio (pagata o da pagare) e il totale; **Paga** apre il pagamento
  con quelle quote già scelte.
- **Prove**: nella gara (Modifica) puoi caricare una foto o la locandina;
  senza, accanto al nome c'è l'icona del tipo.


## L'area dell'atleta

- A sinistra il menu: Home, Lezioni, **Gare e stage**, Bacheca, Quote,
  Certificato medico, Traguardi, Giochi, Invita un amico.
- **Gare e stage**: le prove in arrivo. Ti piacerebbe andare? Premi
  **🙋 Voglio partecipare**: chi ti iscrive (il titolare del conto) riceve
  un'email e una notifica. Il titolare vede invece **Iscrivi**.
- In Home il riquadro dei **soldi**: saldo del wallet della famiglia, quanto
  il club ha pagato per l'atleta (trasporto, materiale, gare, esami, stage) e
  gli investimenti del club.
- **Invita un amico**: il tuo link con i bottoni WhatsApp, Facebook,
  Telegram, X, email e «Copia».

## Segreteria: aiuto del club, avvisi, personale

- **Aiuto del club**: Persone → l'atleta → 💚 Aiuto del club. Scegli che cosa
  (trasporto, materiale, iscrizione a una prova, esame, stage, altro),
  l'importo e la data. La famiglia lo vede nel wallet e nella scheda
  dell'atleta; il saldo non cambia.
- **Avvisi della mensilità e multa**: Impostazioni → ⏰. Accesi, il 1°, il 10
  e il 15 alle 9:00 parte un'email a chi non ha pagato la mensilità del mese;
  il 16 alle 9:00 si aggiunge la multa (15 € o quella che scrivi).
- **👥 Personale**: «Il mese» con ore, costo delle ore, compiti e lavoretti e
  il totale; **Lavoretto o compito** per scrivere un lavoro (anche di chi non
  ha un account) con il costo; **Paga** lo mette nella contabilità come
  spesa. «Cartellino» sono le ore di sempre; «Messaggi» le conversazioni con
  lo staff.
- **Calendario**: accanto a «Scarica PDF» scegli il mese e premi **🎨 Scarica
  flyer del mese**: una pagina con il logo JAV da appendere o mandare.

## Sito: shop e «Crea il tuo club»

- **Loja** (`/loja`): lo shop di JudoArteVida si guarda senza account, con
  ricerca e categorie e i prezzi IVA compresa. «Comprar» spiega che bisogna
  essere soci di un club e mostra i club della rete. Lo shop va acceso dalla
  console (Shop → impostazioni).
- **Crea il tuo club** (`/criar-clube`): chi ha già un club e vuole il
  portale, o chi vuole partire da zero con il Judo Team Matias Luwawa (solo in
  Portogallo), manda la richiesta. Arriva in console → Messaggi con
  l'argomento «Creare un club».
- **Console → 💬 Messaggi dello staff**: i messaggi che treinadores, monitor
  e segreterie dei club scrivono a JudoArteVida, con la risposta.

## Eventi, pagine, privacy

- **Eventi nell'area**: famiglie in «Gare» → 🗓️ Eventi, atleti in «Gare e
  stage» → 🗓️ Eventi. È lo stesso calendario del sito: lista (in alto i
  prossimi), mese e anno, con ricerca e filtri.
- Gli elenchi lunghi hanno le **pagine 1 2 3** in fondo.
- **Il sito pubblico**: ogni atleta compare con nome e iniziale, club,
  cintura, medaglie e risultati, senza foto. Il genitore, dalla scheda del
  figlio → «Sito pubblico JudoArteVida», può premere **Mi oppongo**: sparisce
  dal sito e dalle classifiche. La foto si mostra solo spuntandola.
- **Cookie**: la prima volta il sito chiede se caricare anche i video di
  YouTube e Vimeo; «Gerir cookies» in fondo alla pagina cambia la scelta.
  Privacy, cookie e termini sono linkati in fondo a ogni pagina.

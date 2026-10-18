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
**inglese**, **italiano**, **spagnolo**, **francese**, **tedesco** o **ucraino**.
Si parte in portoghese; la scelta resta salvata sul dispositivo (anche dopo
l'uscita). Sono tradotti il sito, l'accesso, le aree di famiglie, atleti e
staff e quasi tutta la segreteria; la console della piattaforma, l'area
promoter e i messaggi che arrivano dal server (email, notifiche, errori) sono
ancora in italiano. JAVBOT e i giochi rispondono in portoghese a chi sceglie
lo spagnolo e in inglese a chi sceglie francese, tedesco o ucraino.

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

**La foto** si cambia toccando il cerchio: scelta la foto, la sposti col dito
(o col mouse) e la ingrandisci con il cursore o con due dita, vedendo subito
come starà nel cerchio; poi **Usa questa foto**. Lo stesso nella scheda
dell'atleta della segreteria, per le foto degli allenatori nel sito del club e
per clienti e promoter nella console. Le foto si salvano già ridotte e senza i
dati nascosti del telefono (come la posizione GPS).

Negli **eventi** (Gare / Gare e stage), aprendo un evento compare in alto
**← Torna al calendario**: riporta allo stesso punto del calendario (vista,
mese, filtri, pagina).

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

Per il **judogi del club** c'è il calcolatore: in cima allo Shop premi
**Calcula o teu judogui** e scegli figlio, tipo, colore, marca e taglia (con
l'altezza ti suggerisce quella giusta) ed eventualmente il judogi usato che
restituisci (vale la metà del suo prezzo). L'ordine diventa una quota del
figlio, da pagare come le altre. Vedi "Judogi e lista dei desideri" più sotto.

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

- **Atleti**: la tabella dell'anagrafe. Colonne: **ruolo** (🥋 atleta,
  👪 genitore, 🧑‍🏫 treinador…), **nº de sócio**, **licença FPJ** (con la
  scadenza: verde, ⏳ in scadenza, ⛔ scaduta), **nome** (sotto: chi l'ha
  portato nel club — chi l'ha invitato col suo link, il nome scritto nel
  modulo, o «iscritto dal club»), **nascita**, **età federativa**,
  **género**, cintura e piano, **encarregado** (nome ed email), **contatto**
  (telefono, WhatsApp), certificato e quanto deve. Si cerca per nome, nº de
  sócio, licenza o email dell'encarregado; si ordina toccando le
  intestazioni con ▲; i filtri rapidi mostrano chi ha debiti, il certificato
  o la licenza da sistemare, chi è senza nº de sócio; **CSV** scarica
  l'elenco filtrato (per Excel). Il nome resta fermo a sinistra quando si
  scorre. Toccando una riga si apre la scheda: famiglia, quote, certificati,
  cinture, gare; si può fissare a mano il piano (non cambierà più con l'età),
  cambiare lo stato (attivo, sospeso, uscito), registrare il tesseramento.
- **Comprovativos** (prove di pagamento): in alto quanto è entrato nel
  periodo (totale, numero, bonifico/MB Way, contanti). Si cerca per atleta,
  email, nº della ricevuta, nota o chi ha preso i contanti; si filtra per
  metodo e periodo (mese, 3 mesi, stagione, sempre) e per stato
  (registrate/rifiutate, con i conteggi). Ogni scheda dice importo, metodo,
  nº della ricevuta, quando e chi, e le quote coperte atleta per atleta.
  **Vedi ricevuta** la apre dentro la pagina (foto o PDF); **Rifiuta**
  chiede un motivo (ce ne sono di pronti) che la famiglia riceve, e le quote
  tornano da pagare.
- **Piani e prezzi**: i gruppi del club, ognuno in una scheda con la fascia
  nel **suo colore** (si sceglie nel popup: 8 colori pronti o «Altro
  colore»), l'età, la mensilità grande, l'iscrizione annuale, quanti atleti
  ha, il giorno di scadenza e i mesi in cui si paga (si accendono e spengono
  toccandoli). Un gruppo in uso non si cancella: si disattiva. Sotto ogni
  gruppo, **🗓️ Turmas e horários** mostra in sintesi i giorni della
  settimana; con **Gerir** si vedono le turmas del gruppo (treinador, età,
  iscritti), si aggiungono o tolgono orari e si crea una turma nuova con le
  età del gruppo già scritte. La pagina **Turmas e horários** resta per
  vedere e gestire tutti gli orari insieme. Una turma appartiene a un gruppo
  quando le loro età si toccano (la stessa regola del sito e di JAVBOT); una
  turma senza età non è di nessun gruppo, e la pagina lo segnala.
  Nella scheda di una turma scegli il treinador principale, gli **adjunto**
  e, se serve, i **treinador che NON vedono questa turma**: di regola ogni
  treinador vede tutte le turmas e i loro atleti, quindi non c'è niente da
  assegnare perché un treinador trovi i suoi allievi; si spunta qualcuno
  solo per togliergli quella turma.
- **Marcar presenças**: in alto i giorni del mese con lezioni, come bottoni
  (verdi se le presenze sono già segnate, gialli se mancano, grigi i
  prossimi; frecce per cambiare mese): un tocco apre la giornata. Resta anche
  il campo della data.
- **Atleti**: la pagina è a tutta larghezza e la tabella sta nello schermo a
  1440 px (con il menu ridotto anche su schermi più piccoli).
- **Quote**: nel quadro del mese e nell'elenco, una quota che ha una prova di
  pagamento mostra **🧾 Vedi la prova di pagamento** (in rosso se era stata
  rifiutata): la ricevuta si apre lì, da controllare prima di segnare pagata.
  Elenco con filtri. Su una quota: **segna pagata** — scegli come
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
  segreteria, che ricevono l'email per scegliersi la password. Un genitore o un atleta adulto **già del club** (per esempio un papà che insegna) si aggiunge con la sua email: lo stesso account diventa anche treinador, con la password che ha già; poi in **Persone** gli si dà la funzione «Treinador». Chi ha più ruoli passa da un'area all'altra (famiglia, atleta, treinador, segreteria) dal **menu utente** in alto a destra.

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

**Il tuo currículo** (voce «Currículo»): è tuo, non del club, e lo vedi solo
tu. In **Documentos** carichi diplomi di treinador, certificazioni, attestati
e primo soccorso, con ente, date e scadenza (ti avvisa quando sta per
scadere). In **Curriculum Vitae** scrivi presentazione, esperienze,
formazione, competenze, lingue e specializzazioni: nome, foto, club in cui
alleni, cintura e certificazioni arrivano da soli. Il **Currículo
Desportivo** si costruisce dalle gare, dai risultati, dalle cinture e dalle
prove a cui hai accompagnato gli atleti; quello che manca (gare di anni fa,
stage) lo aggiungi a mano: resta solo nel tuo curriculum, segnato come
«declarado», e non entra nel calendario né nel ranking del club. Per tutti e
due: anteprima, PDF da scaricare o stampare, e versioni salvate.

**Più club con un account solo.** Se alleni in più club, entrando vedi il
saluto con la tua foto (toccala per cambiarla) e un bottone per ogni club,
con il logo, gli atleti e i tuoi corsi: scegli dove entrare. «Trocar de
clube» in alto per passare a un altro. In un club che non è il tuo sei solo
treinador. Ti assegna ai club il superadmin; la segreteria di un club può
chiederti (aggiungendo la tua email come istruttore) e il superadmin
approva. Nell'elenco degli atleti di ogni club chi è treinador ha la sua
icona.

**Vedi tutte le turmas del club** e tutti i loro atleti, anche se non te ne
hanno assegnata nessuna: le turmas che insegni vengono per prime, con
★ «minha». Se la segreteria ti ha tolto una turma, quella turma e gli atleti
che stanno solo lì non li vedi.

Entrando si apre **Presenze di oggi**: la lezione in corso è già scelta; un
tocco sul cerchio segna l'entrata dell'atleta, 📝 aggiunge una nota per la
segreteria. Si può scegliere un altro giorno per correggere. **Calendario**
mostra le lezioni della settimana delle turmas che vedi; **Cartellino** ha il
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
  flyer del mese**: una pagina sola (anche con tanti eventi) con la barra
  dorata del mese, il logo JudoArteVida, i social e il sito, e una riga per
  evento; da appendere o mandare su WhatsApp.

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

## Social, WhatsApp e pagine del sito

- **Social della rete**: console → Impostazioni → «Social della rete».
  Incolla gli indirizzi di Facebook, Instagram, YouTube e TikTok: le icone
  compaiono in fondo a ogni pagina del sito. Vuoto = nessuna icona.
- **Social del club**: Sito del club → contatti, anche TikTok.
- **WhatsApp**: subito sotto il telefono, con l'icona di WhatsApp, nella
  pagina Contactos, nel piè di pagina e nelle informazioni di ogni club.
  Apre la chat con quel numero.
- **Scheda del judoca**: la segreteria (o il superadmin entrato nel club)
  carica foto, video e biografia dalla scheda dell'atleta → «Pagina
  pubblica», o da Sito → Judoka; sul sito compaiono nelle schede Foto, Video
  e Biografia.


## Gare: risultati dal telefono, scheda dell'evento, relatórios

- **Scheda dell'evento**: tocca il nome di una prova (nel calendário, in
  «Eventos e provas» o nei risultati) e si apre tutto: descrizione, date,
  luogo, scadenza, età, quota, circolare e gli atleti del club iscritti. Lo
  staff vede anche i contatti (del genitore se l'atleta è minorenne) e può
  chiamare, scrivere o aprire WhatsApp con un tocco. Le famiglie vedono la
  scheda senza contatti.
- **Risultati (treinador e segreteria)**: scegli la gara, poi per ogni atleta
  scrivi alla pesata **peso** e **categoria**, e dopo la gara tocca la
  medaglia 🥇🥈🥉 (o 5º, 7º, partecipazione) e aggiungi una nota. Si salva da
  solo. I punti del Jav Ranking si aggiornano subito, come quando li mette
  la segreteria.
- **Relatórios**: dopo un evento, «Novo relatório» → scegli l'evento →
  scrivi titolo, descrizione, come è andata, le spese voce per voce
  (alloggio, viaggio, carburante, pasti, iscrizioni, altro) e aggiungi le
  foto. I risultati degli atleti compaiono da soli. Ogni treinador vede i
  suoi; la segreteria li vede tutti in «Eventos e provas» → «Relatórios de
  eventos» e scarica il **PDF** di un mese, di un anno o di un periodo.
- **Relatório final**: finito il relatório, tocca **📰 Gerar relatório
  final** (sulla scheda del relatório o in fondo all'editor): esce un breve
  articolo, come sul giornale, con risultati, racconto, spese e foto.
  Correggilo come vuoi e salva. Il bottone **✨ Gerar com IA** è pronto ma
  resta spento finché il club non attiva l'IA. Nella schermata **Relatórios
  finais** trovi solo gli articoli, da leggere impaginati, e **Descarregar
  todos (PDF)** li mette tutti in un PDF (solo quelli trovati dalla
  ricerca, se ne hai scritta una).
- In alto ci sono i pulsanti grandi delle schermate e la ricerca; nel popup
  **Novo relatório** cerca l'evento per nome e lascia acceso «Só com
  inscritos e já concluídos» per vedere solo le gare finite con atleti
  iscritti.

## L'area del treinador

- **Início**: appena entri vedi le lezioni di oggi e il bottone grande
  **Marcar presenças**, i registri delle presenze rimasti vuoti (toccane uno
  per completarlo), il tuo cartellino, le prossime gare, i messaggi da
  leggere e gli atleti da tenere d'occhio (assenti da tre settimane o con il
  certificato medico da rinnovare).
- **Presenze**: puoi tornare ai giorni passati (frecce del mese o
  calendario) e correggere. 📓 accanto a un atleta apre la sua scheda con le
  note; «Nota da aula» scrive che cosa avete fatto.
- **Caderno**: le note delle lezioni (tema, tecniche, osservazioni) come una
  linea del tempo, con la ricerca e le tecniche più lavorate; e «Os meus
  atletas», con la scheda di ognuno e le tue note personali. Le note sugli
  atleti le vedono solo i treinadores dei suoi corsi e la segreteria.
- **Cartellino**: nei «turnos do mês» tocca ✎ per correggere entrata, uscita
  o nota, o togliere un turno; «Turno esquecido» aggiunge quello che non hai
  timbrato. Vale per questo mese e il mese scorso; la segreteria vede che il
  turno è stato modificato.
- **Mural**: puoi pubblicare anche tu un post per i soci del club (avviso,
  foto, video). Correggi e togli i tuoi; la segreteria li vede e li può
  nascondere.

## Pagamento parziale, mese esente e relatórios

- **Pagamento parziale**: nel riquadro dell'atleta (Quote → 📅 Il mese)
  tocca **½ Pagamento parcial**, scrivi quanto ti hanno dato, come (e per i
  contanti a chi) e **perché** non tutto. Vedi subito quanto resta. La parte
  pagata ha la sua ricevuta; il resto resta da pagare: lo vede la famiglia,
  arrivano gli avvisi, e lo chiudi con **✓ Segna pagato** quando arriva. Se
  hai sbagliato, **↶ Anular parcial** rimette la quota com'era.
- **Mese esente**: **🎗️ Isenta este mês** quando un atleta quel mese non deve
  pagare (assente, infortunato). Scrivi il motivo: quel mese non conta più né
  da incassare né come debito. Si annulla con **↶ Anular isenção**. Funziona
  anche per i mesi futuri (vai avanti con ›).
- **Relatórios**: in **Contabilità → 📑 Relatórios** scegli la stagione o
  l'anno e il relatório: la tabella atleti × mesi (chi ha pagato che cosa,
  mese per mese, con i colori), gli incassi per metodo, i debiti per famiglia,
  esenzioni e condoni con il motivo, i contanti ricevuti da ogni persona,
  entrate e uscite mese per mese. **⬇ CSV** o **⬇ Excel** li scaricano, pronti
  per il commercialista o la direzione.

## JAV Games: Judo Career, combattimenti e Randori del club

Si aprono da **Jogos/Giochi**. Tutto quello che succede nei giochi è finto:
cinture, club e punti del gioco non sono quelli veri.

- **⛶ Schermo intero**: ogni gioco ha il bottone in alto a destra; si esce
  con ✕ o con Esc. Sull'iPhone il gioco occupa tutta la pagina.
- **Dojo Academy**: in alto la **caderneta** con il tuo grado del gioco, il
  bottone del prossimo esame e le qualifiche (Curso de arbitragem, Árbitro,
  Treinador Grau I). Tre schede:
  - **Graduações**: in alto i tuoi numeri (esami superati, media,
    tentativi, prossimo obiettivo), poi tutte le cinture da scorrere: tocca una
    cintura per vedere il programma, i tuoi risultati (data e percentuale del
    superamento, record, grafico degli ultimi tentativi) e scaricare il
    diploma. La scala va dalle cinture intermedie della FPJ al 10° dan; ogni esame ha più domande del precedente (gialla 10 … 1° dan
    60 … 10° dan 375). Sopra c'è il **medagliere**: tocca una medaglia per
    scaricare il diploma del gioco (c'è scritto fac-simile: non vale come
    graduação federativa).
  - **Cursos e qualificações**: il corso di arbitraggio (dalla verde), poi
    il corso per arbitro (dalla blu); il corso Treinador Grau I dal 1° dan,
    12 moduli da 30 domande.
  - **Percursos de estudo**: quiz per tema per allenarsi.
- **Judo Career**: in alto resta sempre visibile il banner con la tua
  cintura e i contatori (tecnica, forza, mental, energia, salute, soldi,
  fama). Sul computer a sinistra c'è il **piano della settimana** (scegli
  fino a 2 azioni e premi **Avança**), a destra le schede (Progressi,
  Calendario, Club, Soldi, Avvisi, Trofei, Diario). Sul telefono tutto è a
  schede e il bottone della settimana resta in basso.
- **Le gare**: nella settimana di una gara a cui sei iscritto, **Avança** ti
  chiede come combattere: **Simulato** (guardi il combattimento animato) o
  **Passo a passo**: a ogni scambio il gioco ti mostra che cosa succede
  («Ele ataca com O-goshi!») e tu scegli la risposta entro 20 secondi.
  Dopo ogni scambio vedi se la scelta era buona e **perché**. Contano anche
  la tua tecnica, la forza, l'energia e la salute: stanco o infortunato
  combatti peggio. Un turno perso non si rifà.
- **Randori del Club**: sfidi i compagni del tuo club che giocano anche
  loro (non devono essere collegati: combattono con le loro statistiche).
  Scegli simulato o passo a passo; se vinci prendi punti al tuo amico (di
  più se è più forte di te), se perdi li prende lui. Al massimo 3 incontri
  al giorno con lo stesso amico e 10 sfide al giorno; un combattimento
  lasciato a metà conta come perso. Vedi la classifica del club e gli
  ultimi incontri.

## Quero participar (e le quote da pagare)

- Su ogni evento c'è il bottone **Quero participar**. Se non sei entrato ti
  porta al login; se sei già iscritto vedi **Inscrito**.
- Premendolo vedi i tuoi atleti: chi può andare si iscrive con un tocco
  (l'atleta con il suo accesso invece avvisa il genitore).
- **Con quote scadute non ci si iscrive agli eventi**: la finestra mostra
  quali sono e il totale, e puoi pagarle subito con **Pagar agora**.
- Segreteria: se una quota scaduta non deve impedire le gare (es. un judogi
  pagato a rate), nella lista delle quote premi **🔓 Não bloquear provas**
  sotto lo stato. Resta da pagare, ma non blocca più.
- I relatórios: la segreteria trova quelli degli eventi in **Eventos e provas
  → Relatórios** e quelli delle lezioni in **Relatórios das aulas**; il
  treinador li scrive nelle sue schede **Eventos** e **Caderno**.

## La Loja del club: judogi ed equipaggiamento

- **La Loja** (area della famiglia e area dell'atleta) mostra, per l'atleta
  scelto in alto, solo quello che è per lui: i modelli femminili a una
  ragazza, quelli maschili a un ragazzo, le taglie giuste per la sua altezza.
  L'**equipaggiamento di alta competizione** e il **judogi aprovado FIJ** (con
  il backnumber ufficiale PT) si vedono con il lucchetto: li compra solo chi
  la segreteria o il treinador hanno segnato di alta competizione. Il judogi
  **rosa** si vede ma lo comprano solo le ragazze.
- **Il kit del club**: che cosa l'atleta ha già, che cosa è in arrivo e che
  cosa manca.
- **Il judogi, passo a passo**: atleta (la taglia viene dall'altezza), tipo,
  colore e modello con le foto, nome da ricamare (sotto i 13 anni solo il nome
  proprio), judogi usato da restituire (uno di quelli che il club sa che ha,
  o descritto a mano: vale metà del suo prezzo di listino), riepilogo. Il
  prezzo lo calcola il club. Alla fine **Adicionar ao carrinho** o **Comprar
  já e pagar**.
- **Il carrello** raccoglie judogi ed equipaggiamento, anche di più figli.
  All'ordine **ogni articolo diventa un'encomenda separata** (la segreteria
  li prepara e consegna uno per uno) e si paga **tutto insieme**: «Encomendar
  e pagar já» apre il pagamento con tutte le quote già scelte; «Encomendar,
  pago depois» le lascia nella home, da pagare quando vuoi. Le trovi anche in
  **As minhas encomendas**, con lo stato.
- **L'atleta minorenne** non compra: mette **♡ Quero** e il genitore trova i
  desideri nella Loja, da mettere nel carrello o rifiutare.
- **Segreteria → Judogi**: le encomendas della Loja (judogi ed
  equipaggiamento) per stato, con ricerca, avanzamento (→ Em preparação →
  Entregue), annullamento e **CSV per il fornitore**; le **foto dei modelli**
  di judogi; il **listino** e le **regole** (personalizzazione, % della
  permuta). Nello **shop del club**, per ogni prodotto: **Para quem é**
  (feminino / masculino / para todos, só alta competição, kit do clube,
  personalizado com o nome) e per ogni taglia l'altezza fino a cui va bene.
- **Piani e prezzi**: «Permite alta competição» sul piano del Grupo 3.
- **Judogis dos atletas** (segreteria e treinador): chi ha il judogi bianco,
  l'azul, il FIJ, e quali sono piccoli. **Para a próxima prova** mostra solo
  gli iscritti e chi non ha il bianco o l'azul: il treinador lo porta dal
  club. Da qui si segna l'**alta competizione** (solo per il Grupo 3), si
  aggiunge un judogi che l'atleta aveva già e si toglie uno piccolo o perso.

## Corsi esterni nelle scuole

I corsi esterni (oggi: Torraltinha, Externato Jardim Infantil da Torraltinha,
Lagos) sono un **sistema a parte dai club**: anagrafica, mensilità, prove,
presenze e conti propri. Niente Shop, judogi, gare, cinture, giochi, wallet,
promoter né JAVBOT. Chi vuole anche un club si iscrive al club normalmente.

- **Il genitore** si iscrive dalla scheda del corso sul sito
  (`/cursos-externos/<corso>`, «Inscrever»): nome, telefono, email,
  password e i figli (fino a 6), ognuno va nel gruppo della sua età.
  Entra in **/cursos**: gli avvisi della scuola (es. «lunedì niente
  lezione»), il bottone **Carregar comprovativo** (sceglie le mensilità,
  bonifico / MB WAY / contanti, vede l'IBAN), poi una scheda per figlio con
  scuola, gruppo, orario e presenze. Le schede «Mensalidades» (storico e
  prove, con il motivo se rifiutate) e «Inscrever» (un altro figlio o un
  altro corso).
- **Una famiglia già in un club** che vuole un corso esterno deve
  **reiscrivere i figli**: dal sito con la stessa email chiede di entrare,
  poi da dentro «Inscrever os meus filhos». L'anagrafica del corso è
  separata da quella del club, una per ogni corso.
- **La segreteria della scuola** entra in **/escola**: Participantes (con i
  contatti del genitore), Presenças, Pagamentos (mensilità per mese, segna
  pagato, apre o rifiuta una prova) e Avisos. Il superadmin la aggiunge al
  corso con la sua email e le manda il link d'invito.
- **Il treinador** del corso trova il corso tra i bottoni dei suoi club
  («Curso externo») e in /escola ha Participantes, Presenças, Avisos,
  **Entrada/Saída** e **Os meus ganhos** (la sua quota, 50% per Marco, delle
  mensilità pagate). Non vede i contatti né i pagamenti.
- **Il superadmin** dalla console, «Cursos externos»: crea e modifica i
  corsi (mesi di pagamento, quota, scadenza, logo, gruppi per età e orario),
  aggiunge treinador (con la percentuale) e segreteria, apre il corso «come
  scuola», e vede i conti per anno: incassato, parte del treinador, parte di
  JudoArteVida. Le mensilità nascono da sole ogni mese (03:20).

## L'atleta maggiorenne prende il suo conto, il genitore resta

Quando un figlio compie 18 anni (età federale), nell'area dell'atleta il
genitore vede il riquadro **«… pode ter a sua própria conta»** («… è già
maggiorenne»): scrive l'email del figlio, che riceve l'invito (se l'email
non parte, il link compare da copiare). Il figlio, entrato, vede in alto il
bottone **«Ficar com a minha conta»** («Tengo il mio conto»). Dopo, il
conto è suo, ma il genitore **resta collegato**: lo vede ancora nella
famiglia e può continuare ad amministrarlo.

## JAVBOT: solo per gli adulti, e che cosa sa

- Un atleta **minore di 18 anni (età federale)** che entra con il suo conto
  non ha JAVBOT. Il genitore sì.
- Un genitore può chiedere tutto di sé e dei suoi figli (anche altezza,
  peso, categoria, licenza); un atleta solo di sé; nessuno di un altro.
- I dati sensibili (telefono, indirizzo, NIF, documenti, IBAN, importi
  pagati o da pagare) **non escono dal server**: JAVBOT li mostra a chi ne
  ha diritto, ma al modello AI arrivano solo come segnaposto. Escono solo
  dati pubblici: nome, licenza federale, altezza, risultati.
- Il manuale completo del club è nella base di conoscenza: JAVBOT risponde
  sulle regole citando il manuale.

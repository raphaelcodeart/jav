# JAV Games

L'area giochi dell'area riservata: **Dojo Academy** (quiz a tempo ed esami
di cintura del gioco) e **Judo Career** (la simulazione della carriera di un
judoca fino ad aprire e gestire un club). Si apre da «Jogos/Giochi» nel menu
della famiglia e da `/giochi` (link nell'area dell'atleta).

## Un progetto a parte, con dati finti

- Codice: `apps/api/app/game/` (modelli, contenuti, servizio, API `/game/...`)
  e `apps/dashboard/components/game/`. Nessun import dal gestionale, tranne
  una lettura in `service._identity`: nome da mostrare («Nome I.») e nome del
  club, copiati come testo nel giocatore.
- Dati: schema Postgres **`game`** (stesso database, schema separato), con
  una `MetaData` sua (`app.game.models.GameBase`), **nessuna chiave esterna
  verso le tabelle del gestionale**. `players.user_id` è l'id dell'account,
  senza FK. Le cinture, i club e gli atleti del gioco **non sono** quelli
  veri: un esame superato nel gioco non cambia la cintura vera.
- Migrazioni: le tabelle del gioco non stanno in `Base.metadata`, quindi
  l'autogenerate del gestionale non le vede. Una modifica ai modelli del
  gioco va scritta a mano in una migrazione nuova (come `0021_giochi.py`,
  `schema="game"`). I test creano lo schema a parte (`tests/conftest.py`).
- Per togliere tutto: `DROP SCHEMA game CASCADE` non tocca nient'altro.

## Dojo Academy

- Contenuti in `app/game/content.py`: una banca di domande (storia, etichetta,
  tecniche, regole, vocabolario) in portoghese, italiano e inglese, i
  **percorsi** (un quiz per tema) e gli **esami di cintura** del gioco
  (giallo → nero, in ordine; passa il 70%, il nero l'80%).
- Il server sceglie domande e ordine delle risposte e corregge ogni
  risposta (`POST /game/attempts/{id}/answer`): il browser non riceve mai la
  risposta giusta prima di aver risposto. Punti: 10 per risposta giusta più
  fino a 5 di velocità. Il tempo per domanda è di **30 secondi** (28 nell'esame
  di cintura nera).
- XP: di un percorso solo il **miglioramento** del record (rifarlo non
  fabbrica XP); un esame superato la prima volta dà il suo premio.

## Judo Career

- Lo stato della partita lo calcola il browser
  (`components/game/career/engine.ts`, settimane di gioco) e si salva in
  `game.careers` come JSON (`PUT /game/career`).
- Controlli del server: dimensione massima, XP che cresce al massimo di
  1500 per salvataggio, cintura del personaggio mai oltre l'ultimo esame
  superato in Dojo Academy (per passare di cintura nella carriera si studia
  e si fa l'esame nell'altro gioco).

## Classifica

`GET /game/leaderboard`: tutti i giocatori per XP (quiz + carriera), quelli
del proprio club, e i club per somma dell'XP dei loro giocatori.

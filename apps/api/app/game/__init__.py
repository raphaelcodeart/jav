"""JAV Games: l'area giochi dell'area riservata (Dojo Academy, i quiz e gli
esami di cintura; Judo Career, la simulazione della carriera). Specifica:
docs/games.md.

**È un progetto a parte dentro jav, e i suoi dati sono finti per
definizione.** Le tabelle stanno nello schema Postgres `game`, con una loro
`MetaData` (models.GameBase): nessuna chiave esterna verso il gestionale,
nessuna query del gestionale le legge, nessuna query del gioco scrive nel
gestionale. Il solo legame è l'id dell'account (`user_id`, senza FK) e il
nome e il club copiati come testo quando il giocatore entra la prima volta,
per la classifica. Una cintura, un club o un atleta del gioco non sono mai
quelli della vita reale.
"""

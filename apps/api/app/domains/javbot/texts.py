"""Le frasi di JAVBOT, in italiano, portoghese (pt-PT) ed inglese.

Il backend scrive le risposte già nella lingua dell'utente (quella del
cookie `jav_lang`, che la dashboard manda con ogni messaggio): un genitore
che legge portoghese non deve trovarsi una risposta in italiano. Le chiavi
sono di questo catalogo, non dei file di traduzione della dashboard: il bot
le compone con i dati, e il browser le mostra e basta.

Ogni voce è (italiano, portoghese, inglese). I segnaposto sono `{nome}`.
"""

from datetime import date

LANGS = ("it", "pt", "en")
DEFAULT_LANG = "pt"

T: dict[str, tuple[str, str, str]] = {
    # --- Saluto, aiuto, ripiego -------------------------------------------------------------------
    "greet": (
        "Ciao! Sono JAVBOT, l'assistente di {club}. Conosco la tua situazione: posso dirti quanto hai pagato e quanto c'è da pagare, i tuoi dati, cinture e presenze, aiutarti a caricare una ricevuta, trovare il judogi della taglia giusta e ordinarlo per te, e molto altro. Di che cosa hai bisogno?",
        "Olá! Sou o JAVBOT, o assistente do {club}. Conheço a tua situação: posso dizer-te quanto pagaste e quanto há para pagar, os teus dados, cintos e presenças, ajudar a carregar um comprovativo, encontrar o judogi do tamanho certo e encomendá-lo por ti, e muito mais. Em que posso ajudar?",
        "Hi! I'm JAVBOT, {club}'s assistant. I know your account: I can tell you what you've paid and what's due, your details, belts and attendance, help you upload a payment receipt, find a judogi in the right size and order it for you, and more. What do you need?",
    ),
    "greetNoClub": (
        "Ciao! Sono JAVBOT, l'assistente di Jav. Posso aiutarti con lo Shop, il tuo credito e i contatti. Di che cosa hai bisogno?",
        "Olá! Sou o JAVBOT, o assistente da Jav. Posso ajudar com a Loja, o teu crédito e os contactos. Em que posso ajudar?",
        "Hi! I'm JAVBOT, Jav's assistant. I can help with the Shop, your credit and contacts. What do you need?",
    ),
    "greetStaff": (
        "Ciao! Sono JAVBOT. Posso dirti chi non ha ancora pagato il mese, le lezioni di oggi e i certificati da rinnovare. Che cosa ti serve?",
        "Olá! Sou o JAVBOT. Posso dizer-te quem ainda não pagou o mês, as aulas de hoje e os atestados a renovar. Do que precisas?",
        "Hi! I'm JAVBOT. I can tell you who hasn't paid this month, today's lessons and which certificates need renewing. What do you need?",
    ),
    "help": (
        "Ecco cosa so fare: un riepilogo di tutto («cosa sai di me?»), quanto hai pagato e quanto devi pagare con l'IBAN del club, i tuoi dati e quelli degli atleti, cinture, presenze, punti e medaglie, guidarti a caricare una ricevuta, trovare e ordinare un judogi della taglia giusta, mostrarti le lezioni di oggi e segnare la presenza, i certificati, le gare aperte, il tuo link «invita un amico», il tuo credito, e mandare un messaggio alla segreteria.",
        "Eis o que sei fazer: um resumo de tudo («o que sabes de mim?»), quanto pagaste e quanto tens a pagar com o IBAN do clube, os teus dados e os dos atletas, cintos, presenças, pontos e medalhas, guiar-te a carregar um comprovativo, encontrar e encomendar um judogi do tamanho certo, mostrar as aulas de hoje e marcar a presença, os atestados, as provas abertas, o teu link «convida um amigo», o teu crédito, e enviar uma mensagem à secretaria.",
        "Here's what I can do: a summary of everything (“what do you know about me?”), what you've paid and what you owe with the club's IBAN, your and your athletes' details, belts, attendance, points and medals, guide you through uploading a receipt, find and order a judogi in the right size, show today's lessons and mark attendance, certificates, open competitions, your invite-a-friend link, your credit, and send a message to the club office.",
    ),
    "fallback": (
        "Scusa, non ho capito bene. Prova a chiedermi una di queste cose:",
        "Desculpa, não percebi bem. Experimenta perguntar-me uma destas coisas:",
        "Sorry, I didn't quite get that. Try asking me one of these:",
    ),
    "thanks": (
        "Di niente! Se ti serve altro, sono qui.",
        "De nada! Se precisares de mais alguma coisa, estou aqui.",
        "You're welcome! I'm here if you need anything else.",
    ),
    "reask": (
        "Scusa, non ho capito. {question}",
        "Desculpa, não percebi. {question}",
        "Sorry, I didn't get that. {question}",
    ),
    # --- Risposte rapide --------------------------------------------------------------------------
    "qr.fees": ("Quanto devo pagare?", "Quanto tenho de pagar?", "What do I owe?"),
    "qr.upload": ("Come carico la ricevuta?", "Como carrego o comprovativo?", "How do I upload a receipt?"),
    "qr.judogi": ("Comprare un judogi", "Comprar um judogi", "Buy a judogi"),
    "qr.lessons": ("Lezioni di oggi", "Aulas de hoje", "Today's lessons"),
    "qr.certs": ("Certificati medici", "Atestados médicos", "Medical certificates"),
    "qr.competitions": ("Gare aperte", "Provas abertas", "Open competitions"),
    "qr.invite": ("Invita un amico", "Convidar um amigo", "Invite a friend"),
    "qr.wallet": ("Il mio credito", "O meu crédito", "My credit"),
    "qr.secretary": ("Parlare con la segreteria", "Falar com a secretaria", "Talk to the club office"),
    "qr.staffUnpaid": ("Chi non ha pagato?", "Quem não pagou?", "Who hasn't paid?"),
    "qr.staffCerts": ("Certificati scaduti", "Atestados caducados", "Expired certificates"),
    "qr.overview": ("Cosa sai di me?", "O que sabes de mim?", "What do you know about me?"),
    "qr.paid": ("Quanto ho pagato?", "Quanto paguei?", "How much have I paid?"),
    "qr.myData": ("I miei dati", "Os meus dados", "My details"),
    "qr.belts": ("Cinture", "Cintos", "Belts"),
    "qr.attendance": ("Quante presenze?", "Quantas presenças?", "How many trainings?"),
    "qr.yes": ("Sì, confermo", "Sim, confirmo", "Yes, confirm"),
    "qr.no": ("No, annulla", "Não, cancela", "No, cancel"),
    "qr.kindFees": ("Quote del club", "Quotas do clube", "Club fees"),
    "qr.kindOrder": ("Ordine dello Shop", "Encomenda da Loja", "Shop order"),
    "qr.problems": ("Non funziona", "Não funciona", "It doesn't work"),
    # --- Bottoni ----------------------------------------------------------------------------------
    "act.pay": ("Carica un pagamento", "Carregar um pagamento", "Upload a payment"),
    "act.club": ("Vai al club", "Ir para o clube", "Go to the club"),
    "act.shop": ("Apri lo Shop", "Abrir a Loja", "Open the Shop"),
    "act.orders": ("I miei ordini", "As minhas encomendas", "My orders"),
    "act.settings": ("Completa il profilo", "Completar o perfil", "Complete your profile"),
    "act.competitions": ("Vedi le gare", "Ver as provas", "See competitions"),
    "act.wallet": ("Apri il wallet", "Abrir a carteira", "Open the wallet"),
    "act.invite": ("Copia il link", "Copiar o link", "Copy the link"),
    "act.accounts": ("I miei conti", "As minhas contas", "My accounts"),
    "act.myData": ("Modifica i miei dati", "Alterar os meus dados", "Edit my details"),
    "act.confirmOrder": ("Conferma l'ordine", "Confirmar a encomenda", "Confirm the order"),
    "act.cancel": ("Annulla", "Cancelar", "Cancel"),
    "act.notify": ("Avvisa la segreteria", "Avisar a secretaria", "Tell the club office"),
    "act.send": ("Invia il messaggio", "Enviar a mensagem", "Send the message"),
    "act.mark": ("Segna {name} presente", "Marcar {name} presente", "Mark {name} present"),
    # --- Quote ------------------------------------------------------------------------------------
    "fees.none": (
        "Non hai niente da pagare in questo momento. 🎉",
        "Não tens nada para pagar neste momento. 🎉",
        "You have nothing to pay right now. 🎉",
    ),
    "fees.total": ("In totale hai {total} da pagare.", "No total tens {total} para pagar.", "In total you owe {total}."),
    "fees.totalOverdue": (
        "In totale hai {total} da pagare, di cui {overdue} già scaduti.",
        "No total tens {total} para pagar, dos quais {overdue} já em atraso.",
        "In total you owe {total}, of which {overdue} is overdue.",
    ),
    "fees.line": ("• {name}: {amount} ({count})", "• {name}: {amount} ({count})", "• {name}: {amount} ({count})"),
    "fees.countOne": ("1 quota", "1 quota", "1 fee"),
    "fees.countMany": ("{n} quote", "{n} quotas", "{n} fees"),
    "fees.overdueSuffix": (", {n} scadute", ", {n} em atraso", ", {n} overdue"),
    "fees.overdueOne": (", 1 scaduta", ", 1 em atraso", ", 1 overdue"),
    "fees.family": ("Quota socio", "Quota de sócio", "Membership fee"),
    "fees.next": ("La prossima scadenza è il {date}.", "O próximo vencimento é a {date}.", "The next due date is {date}."),
    "fees.bank": (
        "Bonifico a {holder}\nIBAN: {iban}",
        "Transferência para {holder}\nIBAN: {iban}",
        "Bank transfer to {holder}\nIBAN: {iban}",
    ),
    "fees.noBank": (
        "Il club non ha ancora indicato l'IBAN: chiedilo alla segreteria.",
        "O clube ainda não indicou o IBAN: pede-o à secretaria.",
        "The club hasn't set its IBAN yet: ask the club office.",
    ),
    "fees.howTo": (
        "Quando hai pagato, tocca «Carica un pagamento» e allega la ricevuta: le quote risultano pagate subito.",
        "Quando tiveres pago, toca em «Carregar um pagamento» e junta o comprovativo: as quotas ficam pagas logo.",
        "Once you've paid, tap \"Upload a payment\" and attach the receipt: the fees are marked paid straight away.",
    ),
    # --- Ricevute ---------------------------------------------------------------------------------
    "upload.ask": (
        "Che cosa hai pagato? Le quote del club (mensilità, iscrizione, gare) o un ordine dello Shop (judogi, materiale)? Vanno in due posti diversi.",
        "O que pagaste? As quotas do clube (mensalidades, inscrição, provas) ou uma encomenda da Loja (judogi, material)? Vão para sítios diferentes.",
        "What did you pay for? Club fees (monthly, enrolment, competitions) or a Shop order (judogi, gear)? They go to different places.",
    ),
    "upload.feesNothing": (
        "Non risultano quote da pagare, quindi non c'è niente da caricare. Se hai pagato in palestra, la segreteria lo segna a mano.",
        "Não há quotas por pagar, por isso não há nada para carregar. Se pagaste no clube, a secretaria regista-o.",
        "There are no fees due, so there's nothing to upload. If you paid at the club, the office records it by hand.",
    ),
    "upload.feesSteps": (
        "Ecco come fare:\n1. Tocca «Carica un pagamento».\n2. Scegli «Quote del club».\n3. Spunta le quote che hai pagato (ora ne hai {n}, per {amount}).\n4. Scatta una foto della ricevuta o allega il PDF.\n5. Invia: le quote risultano subito pagate.",
        "Faz assim:\n1. Toca em «Carregar um pagamento».\n2. Escolhe «Quotas do clube».\n3. Marca as quotas que pagaste (agora tens {n}, no valor de {amount}).\n4. Tira uma foto do comprovativo ou junta o PDF.\n5. Envia: as quotas ficam logo pagas.",
        "Here's how:\n1. Tap \"Upload a payment\".\n2. Choose \"Club fees\".\n3. Tick the fees you paid (you have {n}, for {amount}).\n4. Take a photo of the receipt or attach the PDF.\n5. Send: the fees are marked paid straight away.",
    ),
    "upload.orderNothing": (
        "Non hai ordini dello Shop in attesa di bonifico. Se l'hai già pagato, controlla in «I miei ordini»: forse la ricevuta c'è già o il pagamento è già confermato.",
        "Não tens encomendas da Loja à espera de transferência. Se já pagaste, vê em «As minhas encomendas»: talvez o comprovativo já lá esteja ou o pagamento já esteja confirmado.",
        "You have no Shop orders awaiting a bank transfer. If you've already paid, check \"My orders\": the receipt may already be there or the payment already confirmed.",
    ),
    "upload.orderSteps": (
        "Ordini in attesa di bonifico: {list}.\n1. Tocca «Carica un pagamento».\n2. Scegli «Ordine dello Shop» e poi l'ordine.\n3. Allega la ricevuta del bonifico.\nLa merce parte quando la piattaforma conferma il bonifico: la ricevuta serve proprio a questo.",
        "Encomendas à espera de transferência: {list}.\n1. Toca em «Carregar um pagamento».\n2. Escolhe «Encomenda da Loja» e depois a encomenda.\n3. Junta o comprovativo da transferência.\nA encomenda segue quando a plataforma confirmar a transferência: o comprovativo serve para isso.",
        "Orders awaiting a bank transfer: {list}.\n1. Tap \"Upload a payment\".\n2. Choose \"Shop order\", then the order.\n3. Attach the transfer receipt.\nThe goods ship once the platform confirms the transfer: that's what the receipt is for.",
    ),
    "upload.orderItem": ("{number} ({amount})", "{number} ({amount})", "{number} ({amount})"),
    "upload.orderItemProof": (
        "{number} ({amount}, ricevuta già caricata: puoi sostituirla)",
        "{number} ({amount}, comprovativo já carregado: podes substituí-lo)",
        "{number} ({amount}, receipt already uploaded: you can replace it)",
    ),
    "upload.problems": (
        "Se qualcosa non va:\n• il file deve essere JPG, PNG o PDF, al massimo {mb} MB;\n• le foto dell'iPhone in formato HEIC non passano: fai uno screenshot della ricevuta, oppure in Impostazioni → Fotocamera → Formati scegli «Più compatibile»;\n• se il bottone resta grigio, non hai scelto nessuna quota o nessun ordine;\n• con la rete lenta, aspetta la conferma prima di chiudere.",
        "Se algo correr mal:\n• o ficheiro tem de ser JPG, PNG ou PDF, até {mb} MB;\n• as fotos do iPhone em formato HEIC não passam: tira um screenshot do comprovativo, ou em Definições → Câmara → Formatos escolhe «Mais compatível»;\n• se o botão ficar cinzento, não escolheste nenhuma quota ou encomenda;\n• com a rede lenta, espera pela confirmação antes de fechar.",
        "If something goes wrong:\n• the file must be JPG, PNG or PDF, up to {mb} MB;\n• iPhone photos in HEIC format aren't accepted: take a screenshot of the receipt, or in Settings → Camera → Formats choose \"Most Compatible\";\n• if the button stays grey, you haven't picked any fee or order;\n• on a slow connection, wait for the confirmation before closing.",
    ),
    # --- Judogi -----------------------------------------------------------------------------------
    "judogi.whichAthlete": ("Per chi è il judogi?", "Para quem é o judogi?", "Who is the judogi for?"),
    "judogi.askHeight": (
        "Quanto è alto/a {name}? Scrivimi l'altezza in centimetri, per esempio 145.",
        "Quanto mede {name}? Escreve-me a altura em centímetros, por exemplo 145.",
        "How tall is {name}? Write the height in centimetres, for example 145.",
    ),
    "judogi.askHeightSelf": (
        "Quanto sei alto/a? Scrivimi l'altezza in centimetri, per esempio 172.",
        "Quanto medes? Escreve-me a altura em centímetros, por exemplo 172.",
        "How tall are you? Write your height in centimetres, for example 172.",
    ),
    "judogi.size": (
        "Per {height} cm la taglia giusta è la {size}{number}: si prende la decina sopra, perché il cotone si ritira un po' e si cresce.",
        "Para {height} cm o tamanho certo é o {size}{number}: escolhe-se a dezena acima, porque o algodão encolhe um pouco e cresce-se.",
        "For {height} cm the right size is {size}{number}: you round up to the next ten, because cotton shrinks a little and kids grow.",
    ),
    "judogi.number": (" (numero {n} in molte marche)", " (número {n} em muitas marcas)", " (size {n} in many brands)"),
    "judogi.found": ("Ho trovato «{product}», taglia {label}.", "Encontrei «{product}», tamanho {label}.", "I found \"{product}\", size {label}."),
    "judogi.foundBigger": (
        "La {size} non c'è: ho trovato «{product}» in taglia {label}, una misura sopra.",
        "O {size} não há: encontrei «{product}» no tamanho {label}, um acima.",
        "Size {size} isn't available: I found \"{product}\" in size {label}, one size up.",
    ),
    "judogi.price": (
        "Prezzo: {items} + IVA {vat} + spedizione {shipping} = {total}.",
        "Preço: {items} + IVA {vat} + envio {shipping} = {total}.",
        "Price: {items} + VAT {vat} + shipping {shipping} = {total}.",
    ),
    "judogi.priceFreeShipping": (
        "Prezzo: {items} + IVA {vat}, spedizione inclusa = {total}.",
        "Preço: {items} + IVA {vat}, envio incluído = {total}.",
        "Price: {items} + VAT {vat}, shipping included = {total}.",
    ),
    "judogi.transfer": (
        "Pagando con bonifico: {amount} (sconto {pct}%).",
        "Pagando por transferência: {amount} (desconto de {pct}%).",
        "Paying by bank transfer: {amount} ({pct}% off).",
    ),
    "judogi.shipTo": (
        "Lo spedisco a {name}, {line1}, {postal} {city} ({province}).",
        "Envio para {name}, {line1}, {postal} {city} ({province}).",
        "I'll ship it to {name}, {line1}, {postal} {city} ({province}).",
    ),
    "judogi.confirm": (
        "Confermi l'ordine? Lo creo solo se mi rispondi «sì». Poi si paga con bonifico.",
        "Confirmas a encomenda? Só a crio se me responderes «sim». Depois paga-se por transferência.",
        "Shall I place the order? I'll only create it if you say \"yes\". You then pay by bank transfer.",
    ),
    "judogi.addressMissing": (
        "Per spedirlo mi manca l'indirizzo completo nel tuo profilo. Completalo nelle Impostazioni e poi chiedimi di nuovo il judogi: ci vuole un attimo.",
        "Para o enviar falta-me a morada completa no teu perfil. Completa-a nas Definições e depois pede-me de novo o judogi: é rápido.",
        "To ship it I need your full address in your profile. Complete it in Settings, then ask me for the judogi again: it only takes a moment.",
    ),
    "judogi.notFound": (
        "Al momento nello Shop non c'è un judogi in taglia {size}.",
        "Neste momento não há na Loja um judogi no tamanho {size}.",
        "Right now the Shop has no judogi in size {size}.",
    ),
    "judogi.none": (
        "Al momento nello Shop non ci sono judogi.",
        "Neste momento não há judogis na Loja.",
        "Right now there are no judogis in the Shop.",
    ),
    "judogi.offerNotify": (
        "Se vuoi, avviso la segreteria del club che ti serve un judogi taglia {size}: ti faranno sapere loro.",
        "Se quiseres, aviso a secretaria do clube de que precisas de um judogi tamanho {size}: eles dizem-te alguma coisa.",
        "If you like, I'll tell the club office you need a size {size} judogi: they'll get back to you.",
    ),
    "judogi.notifyText": (
        "Buongiorno, cerco un judogi taglia {size}{for} ma nello Shop non c'è. Potete aiutarmi?",
        "Bom dia, procuro um judogi tamanho {size}{for} mas não há na Loja. Podem ajudar-me?",
        "Hello, I'm looking for a size {size} judogi{for} but the Shop doesn't have it. Can you help?",
    ),
    "judogi.for": (" per {name}", " para {name}", " for {name}"),
    "judogi.shopClosed": (
        "Lo Shop al momento è chiuso: riprova più tardi o chiedi alla segreteria.",
        "A Loja está fechada de momento: tenta mais tarde ou pergunta à secretaria.",
        "The Shop is closed right now: try again later or ask the club office.",
    ),
    "judogi.minOrder": (
        "Da solo questo articolo non arriva all'ordine minimo dello Shop: aprilo e aggiungi altro al carrello.",
        "Sozinho, este artigo não chega à encomenda mínima da Loja: abre-a e junta mais coisas ao carrinho.",
        "On its own this item doesn't reach the Shop's minimum order: open the Shop and add more to the cart.",
    ),
    "judogi.noTransfer": (
        "Lo Shop al momento non accetta ordini con bonifico: riprova più tardi.",
        "A Loja não aceita encomendas por transferência de momento: tenta mais tarde.",
        "The Shop isn't taking bank-transfer orders right now: try again later.",
    ),
    "shop.text": (
        "Nello Shop trovi judogi, cinture e materiale, con pagamento a bonifico. Se cerchi un judogi, la taglia te la trovo io: chiedimi «comprare un judogi».",
        "Na Loja encontras judogis, cintos e material, com pagamento por transferência. Se procuras um judogi, eu encontro o tamanho: pede-me «comprar um judogi».",
        "In the Shop you'll find judogis, belts and gear, paid by bank transfer. If you need a judogi, I'll find the size for you: ask me to \"buy a judogi\".",
    ),
    # --- Compiti ----------------------------------------------------------------------------------
    "task.orderDone": (
        "Fatto! Ho creato l'ordine {number}. Da pagare con bonifico: {amount}. Quando hai pagato, carica la ricevuta da «Carica un pagamento» → «Ordine dello Shop». I dati del bonifico sono anche nell'email che ti ho appena mandato.",
        "Feito! Criei a encomenda {number}. A pagar por transferência: {amount}. Quando pagares, carrega o comprovativo em «Carregar um pagamento» → «Encomenda da Loja». Os dados da transferência estão também no email que acabei de enviar.",
        "Done! I created order {number}. To pay by bank transfer: {amount}. Once paid, upload the receipt via \"Upload a payment\" → \"Shop order\". The transfer details are also in the email I just sent you.",
    ),
    "task.messageDone": (
        "Messaggio inviato alla segreteria: ti risponderanno appena possono.",
        "Mensagem enviada à secretaria: vão responder-te assim que puderem.",
        "Message sent to the club office: they'll reply as soon as they can.",
    ),
    "task.attendanceDone": (
        "Fatto: {name} risulta presente a {course}.",
        "Feito: {name} ficou presente em {course}.",
        "Done: {name} is marked present at {course}.",
    ),
    "task.already": (
        "Questa richiesta l'ho già eseguita: non la ripeto.",
        "Este pedido já foi feito: não o repito.",
        "I've already done this: I won't do it twice.",
    ),
    "task.alreadyOrder": (
        "L'ordine {number} è già stato creato: non ne creo un altro.",
        "A encomenda {number} já foi criada: não crio outra.",
        "Order {number} has already been created: I won't create another one.",
    ),
    "task.cancelled": ("Va bene, non faccio niente.", "Está bem, não faço nada.", "OK, I won't do anything."),
    "task.expired": (
        "Questa proposta è scaduta (nel frattempo i prezzi possono cambiare). Ricominciamo?",
        "Esta proposta expirou (entretanto os preços podem mudar). Recomeçamos?",
        "This offer has expired (prices may have changed meanwhile). Shall we start again?",
    ),
    "task.failed": ("Non ci sono riuscito: {reason}", "Não consegui: {reason}", "I couldn't do it: {reason}"),
    "task.notFound": ("Non trovo questa richiesta.", "Não encontro este pedido.", "I can't find this request."),
    # --- Certificati, gare, lezioni, inviti, wallet -----------------------------------------------
    "certs.none": (
        "Non ci sono atleti attivi nella tua famiglia.",
        "Não há atletas ativos na tua família.",
        "There are no active athletes in your family.",
    ),
    "certs.VALID": ("• {name}: valido fino al {date}", "• {name}: válido até {date}", "• {name}: valid until {date}"),
    "certs.EXPIRING": (
        "• {name}: scade il {date}, rinnovalo presto",
        "• {name}: caduca a {date}, renova-o em breve",
        "• {name}: expires on {date}, renew it soon",
    ),
    "certs.EXPIRED": ("• {name}: scaduto il {date}", "• {name}: caducado a {date}", "• {name}: expired on {date}"),
    "certs.MISSING": ("• {name}: manca", "• {name}: em falta", "• {name}: missing"),
    "certs.allOk": ("Tutti i certificati sono in regola. 👍", "Todos os atestados estão em dia. 👍", "All certificates are in order. 👍"),
    "certs.howTo": (
        "Il nuovo certificato si carica dalla scheda dell'atleta, nella pagina del club.",
        "O novo atestado carrega-se na ficha do atleta, na página do clube.",
        "Upload the new certificate from the athlete's card on the club page.",
    ),
    "competitions.notInCourses": (
        "Nei corsi JAV nelle scuole non ci sono gare né ranking: si impara giocando. Chi vuole gareggiare può passare a un club di JudoArteVida: chiedilo alla segreteria.",
        "Nos cursos JAV nas escolas não há provas nem ranking: aprende-se a brincar. Quem quiser competir pode passar para um clube da JudoArteVida: pede à secretaria.",
        "JAV school courses have no competitions or ranking: kids learn through play. Anyone who wants to compete can move to a JudoArteVida club: ask the office.",
    ),
    "competitions.none": (
        "Al momento non ci sono gare o stage con le iscrizioni aperte.",
        "De momento não há provas ou estágios com inscrições abertas.",
        "There are no competitions or training camps open for registration right now.",
    ),
    "competitions.intro": ("Iscrizioni aperte:", "Inscrições abertas:", "Open for registration:"),
    "competitions.line": (
        "• {name}, {date}{location}: iscrizioni fino al {deadline}",
        "• {name}, {date}{location}: inscrições até {deadline}",
        "• {name}, {date}{location}: register by {deadline}",
    ),
    "competitions.eligible": ("  possono iscriversi: {names}", "  podem inscrever-se: {names}", "  can register: {names}"),
    "competitions.nobody": (
        "  nessuno della famiglia può iscriversi",
        "  ninguém da família se pode inscrever",
        "  nobody in the family can register",
    ),
    "competitions.more": ("…e altre {n}.", "…e mais {n}.", "…and {n} more."),
    "lessons.none": (
        "Oggi non ci sono lezioni per la tua famiglia.",
        "Hoje não há aulas para a tua família.",
        "There are no lessons for your family today.",
    ),
    "lessons.intro": ("Le lezioni di oggi:", "As aulas de hoje:", "Today's lessons:"),
    "lessons.line": ("• {name}: {course}, {start}–{end}{status}", "• {name}: {course}, {start}–{end}{status}", "• {name}: {course}, {start}–{end}{status}"),
    "lessons.present": (" ✅ presente", " ✅ presente", " ✅ present"),
    "lessons.markHint": (
        "Vuoi segnare la presenza? Tocca il bottone e te la segno io.",
        "Queres marcar a presença? Toca no botão e eu marco.",
        "Want to mark attendance? Tap the button and I'll do it.",
    ),
    "staffLessons.none": ("Oggi non ci sono lezioni.", "Hoje não há aulas.", "There are no lessons today."),
    "staffLessons.intro": ("Le lezioni di oggi:", "As aulas de hoje:", "Today's lessons:"),
    "staffLessons.line": (
        "• {start}–{end} {course}: {present} presenti su {enrolled}{now}",
        "• {start}–{end} {course}: {present} presentes de {enrolled}{now}",
        "• {start}–{end} {course}: {present} of {enrolled} present{now}",
    ),
    "staffLessons.now": (" ← adesso", " ← agora", " ← now"),
    "invite.text": (
        "Il tuo link per invitare un amico:\n{url}\nPer ogni mensilità pagata dalla famiglia che inviti ricevi {credit} di credito. Finora hai invitato {n} persone e guadagnato {earned}.",
        "O teu link para convidar um amigo:\n{url}\nPor cada mensalidade paga pela família que convidas recebes {credit} de crédito. Até agora convidaste {n} pessoas e ganhaste {earned}.",
        "Your invite-a-friend link:\n{url}\nFor every monthly fee paid by the family you invite you get {credit} in credit. So far you've invited {n} people and earned {earned}.",
    ),
    # --- Quanto ho pagato ------------------------------------------------------------------------
    "paid.nothing": (
        "Non risulta ancora nessun pagamento al club a tuo nome.",
        "Ainda não há nenhum pagamento ao clube em teu nome.",
        "There are no payments to the club in your name yet.",
    ),
    "paid.total": (
        "Nel {year} hai pagato {amount} al club ({all} da quando sei iscritto).",
        "Em {year} pagaste {amount} ao clube ({all} desde que te inscreveste).",
        "In {year} you've paid {amount} to the club ({all} since you joined).",
    ),
    "paid.person": ("• {name}: {amount}", "• {name}: {amount}", "• {name}: {amount}"),
    "paid.recent": ("Gli ultimi pagamenti:", "Os últimos pagamentos:", "Your latest payments:"),
    "paid.line": ("• {date} — {label}: {amount}", "• {date} — {label}: {amount}", "• {date} — {label}: {amount}"),
    "paid.of": ("{label} di {name}", "{label} de {name}", "{label} for {name}"),
    "paid.more": (
        "… e altri {n} in «I miei conti».",
        "… e mais {n} em «As minhas contas».",
        "… and {n} more in “My accounts”.",
    ),
    "paid.shop": (
        "Nello Shop quest'anno hai speso {amount} ({n} ordini).",
        "Na Loja este ano gastaste {amount} ({n} encomendas).",
        "In the Shop this year you've spent {amount} ({n} orders).",
    ),
    "paid.savings": (
        "Quest'anno hai risparmiato {amount} tra sconti e assenze.",
        "Este ano poupaste {amount} entre descontos e faltas.",
        "This year you've saved {amount} through discounts and absences.",
    ),
    "paid.allClear": (
        "Sei in regola: non c'è niente da pagare.",
        "Tens tudo em dia: não há nada para pagar.",
        "You're all up to date: nothing to pay.",
    ),
    "paid.due": ("Da pagare restano {due}.", "Falta pagar {due}.", "Still to pay: {due}."),
    "paid.dueOverdue": (
        "Da pagare restano {due}, di cui {overdue} già scaduti.",
        "Falta pagar {due}, dos quais {overdue} já em atraso.",
        "Still to pay: {due}, of which {overdue} is overdue.",
    ),
    "paid.wallet": ("Il tuo credito: {amount}.", "O teu crédito: {amount}.", "Your credit: {amount}."),
    "feeKind.MONTHLY": ("Mensilità", "Mensalidade", "Monthly fee"),
    "feeKind.ENROLLMENT": ("Iscrizione", "Inscrição", "Enrolment"),
    "feeKind.COMPETITION": ("Gara", "Prova", "Competition"),
    "feeKind.MEMBERSHIP": ("Quota socio", "Quota de sócio", "Membership fee"),
    # --- I miei dati ------------------------------------------------------------------------------
    "profile.intro": ("Ecco i dati che abbiamo:", "Estes são os dados que temos:", "Here are the details we have:"),
    "profile.name": ("• Nome: {v}", "• Nome: {v}", "• Name: {v}"),
    "profile.email": ("• Email: {v}", "• Email: {v}", "• Email: {v}"),
    "profile.phone": ("• Telefono: {v}", "• Telefone: {v}", "• Phone: {v}"),
    "profile.fiscal": ("• Codice fiscale: {v}", "• NIF: {v}", "• Tax number: {v}"),
    "profile.address": ("• Residenza: {v}", "• Morada: {v}", "• Address: {v}"),
    "profile.you": ("Tu", "Tu", "You"),
    "profile.athlete": (
        "{name} — nato/a il {birth} ({age} anni)",
        "{name} — nascido/a a {birth} ({age} anos)",
        "{name} — born {birth} ({age} years old)",
    ),
    "profile.plan": ("• Piano: {plan}, {fee} al mese", "• Plano: {plan}, {fee} por mês", "• Plan: {plan}, {fee} a month"),
    "profile.federation": (
        "• Tessera federale: {n}{until}", "• Licença federativa: {n}{until}", "• Federation licence: {n}{until}",
    ),
    "profile.until": (" (valida fino al {date})", " (válida até {date})", " (valid until {date})"),
    "profile.weight": ("• Peso: {kg} kg", "• Peso: {kg} kg", "• Weight: {kg} kg"),
    "profile.joined": ("• Iscritto/a dal {date}", "• Inscrito/a desde {date}", "• Member since {date}"),
    "profile.suspended": ("• Iscrizione sospesa", "• Inscrição suspensa", "• Membership suspended"),
    "profile.fix": (
        "Se qualcosa non è giusto, i tuoi dati li correggi nelle Impostazioni; quelli degli atleti li corregge la segreteria.",
        "Se algo não estiver certo, os teus dados corriges nas Definições; os dos atletas corrige a secretaria.",
        "If anything is wrong, you can fix your own details in Settings; the club office fixes the athletes' details.",
    ),
    "cert.VALID": ("certificato valido fino al {date}", "atestado válido até {date}", "certificate valid until {date}"),
    "cert.EXPIRING": ("certificato in scadenza il {date}", "atestado a caducar a {date}", "certificate expiring on {date}"),
    "cert.EXPIRED": ("certificato scaduto il {date}", "atestado caducado a {date}", "certificate expired on {date}"),
    "cert.MISSING": ("certificato medico mancante", "atestado médico em falta", "medical certificate missing"),
    # --- Cinture, presenze, ranking ---------------------------------------------------------------
    "progress.none": (
        "Non vedo atleti iscritti nella tua famiglia.",
        "Não vejo atletas inscritos na tua família.",
        "I don't see any athletes enrolled in your family.",
    ),
    "belts.intro": ("Le cinture:", "Os cintos:", "Belts:"),
    "belts.line": ("• {name}: cintura {belt}{since}", "• {name}: cinto {belt}{since}", "• {name}: {belt} belt{since}"),
    "belts.since": (" (dal {date})", " (desde {date})", " (since {date})"),
    "belts.how": (
        "I passaggi di grado li decide il treinador e li segna il club: la cintura si aggiorna da sola.",
        "As graduações decide-as o treinador e regista-as o clube: o cinto atualiza-se sozinho.",
        "Gradings are decided by the coach and recorded by the club: the belt updates by itself.",
    ),
    "belts.notInCourses": (
        "Nei corsi JAV nelle scuole non ci sono cinture: per i passaggi di grado serve un club.",
        "Nos cursos JAV nas escolas não há cintos: para as graduações é preciso um clube.",
        "JAV school courses don't have belts: gradings happen in a club.",
    ),
    "beltName.WHITE": ("bianca", "branco", "white"),
    "beltName.WHITE_YELLOW": ("bianco-gialla", "branco-amarelo", "white-yellow"),
    "beltName.YELLOW": ("gialla", "amarelo", "yellow"),
    "beltName.YELLOW_ORANGE": ("giallo-arancio", "amarelo-laranja", "yellow-orange"),
    "beltName.ORANGE": ("arancio", "laranja", "orange"),
    "beltName.ORANGE_GREEN": ("arancio-verde", "laranja-verde", "orange-green"),
    "beltName.GREEN": ("verde", "verde", "green"),
    "beltName.BLUE": ("blu", "azul", "blue"),
    "beltName.BROWN": ("marrone", "castanho", "brown"),
    "beltName.BLACK": ("nera {n}° dan", "preto {n}.º dan", "black {n} dan"),
    "attendance.intro": ("Le presenze:", "As presenças:", "Attendance:"),
    "attendance.line": (
        "• {name}: {month} allenamenti questo mese, {season} nella stagione {label}, {all} in tutto",
        "• {name}: {month} treinos este mês, {season} na época {label}, {all} no total",
        "• {name}: {month} trainings this month, {season} in the {label} season, {all} in total",
    ),
    "ranking.line": (
        "• {name}: {points} punti nel ranking {label} · medaglie 🥇 {gold} 🥈 {silver} 🥉 {bronze} · livello {level}, {n} traguardi",
        "• {name}: {points} pontos no ranking {label} · medalhas 🥇 {gold} 🥈 {silver} 🥉 {bronze} · nível {level}, {n} conquistas",
        "• {name}: {points} ranking points in {label} · medals 🥇 {gold} 🥈 {silver} 🥉 {bronze} · level {level}, {n} achievements",
    ),
    "ranking.next": ("  prossima gara: {name}, il {date}", "  próxima prova: {name}, a {date}", "  next competition: {name}, on {date}"),
    "ranking.levelOnly": (
        "• {name}: livello {level}, {n} traguardi",
        "• {name}: nível {level}, {n} conquistas",
        "• {name}: level {level}, {n} achievements",
    ),
    # --- Che cosa sai di me -----------------------------------------------------------------------
    "overview.intro": (
        "Ciao{name}! Ecco la tua situazione a {club}:",
        "Olá{name}! Esta é a tua situação no {club}:",
        "Hi{name}! Here's where you stand at {club}:",
    ),
    "overview.age": ("{n} anni", "{n} anos", "{n} years old"),
    "overview.belt": ("cintura {belt}", "cinto {belt}", "{belt} belt"),
    "overview.month": ("{n} allenamenti questo mese", "{n} treinos este mês", "{n} trainings this month"),
    "overview.paid": (
        "Nel {year} hai pagato {amount}.",
        "Em {year} pagaste {amount}.",
        "In {year} you've paid {amount}.",
    ),
    "overview.more": (
        "Chiedimi pure il dettaglio: pagamenti, dati, cinture, presenze o ranking.",
        "Pergunta-me o detalhe: pagamentos, dados, cintos, presenças ou ranking.",
        "Ask me for details: payments, personal data, belts, attendance or ranking.",
    ),
    "wallet.text": (
        "Il tuo credito è di {amount}. Puoi usarlo per pagare le quote del club (con il PIN o il codice via email) e in parte nello Shop.",
        "O teu crédito é de {amount}. Podes usá-lo para pagar as quotas do clube (com o PIN ou o código por email) e em parte na Loja.",
        "Your credit is {amount}. You can use it to pay club fees (with your PIN or the email code) and partly in the Shop.",
    ),
    "secretary.contacts": ("Ecco i contatti di {club}:", "Eis os contactos do {club}:", "Here's how to reach {club}:"),
    "secretary.email": ("• Email: {v}", "• Email: {v}", "• Email: {v}"),
    "secretary.phone": ("• Telefono: {v}", "• Telefone: {v}", "• Phone: {v}"),
    "secretary.address": ("• Indirizzo: {v}", "• Morada: {v}", "• Address: {v}"),
    "secretary.noContacts": (
        "Il club non ha ancora pubblicato i suoi contatti.",
        "O clube ainda não publicou os contactos.",
        "The club hasn't published its contacts yet.",
    ),
    "secretary.ask": (
        "Se vuoi, scrivimi qui il messaggio e lo giro io alla segreteria.",
        "Se quiseres, escreve-me aqui a mensagem e eu passo-a à secretaria.",
        "If you like, write your message here and I'll pass it on to the club office.",
    ),
    "secretary.confirm": (
        "Mando questo messaggio alla segreteria?\n«{text}»",
        "Envio esta mensagem à secretaria?\n«{text}»",
        "Shall I send this message to the club office?\n\"{text}\"",
    ),
    "secretary.tooShort": (
        "Scrivimi il messaggio per la segreteria in qualche parola.",
        "Escreve-me a mensagem para a secretaria em algumas palavras.",
        "Write your message for the club office in a few words.",
    ),
    # --- Segreteria -------------------------------------------------------------------------------
    "staffUnpaid.none": (
        "Tutti hanno pagato la mensilità di {month}. 👏",
        "Todos pagaram a mensalidade de {month}. 👏",
        "Everyone has paid for {month}. 👏",
    ),
    "staffUnpaid.intro": (
        "Mensilità di {month} ancora da pagare: {n}, per {total}.",
        "Mensalidades de {month} por pagar: {n}, no valor de {total}.",
        "Monthly fees for {month} still unpaid: {n}, totalling {total}.",
    ),
    "staffUnpaid.line": ("• {name}: {amount}{overdue}", "• {name}: {amount}{overdue}", "• {name}: {amount}{overdue}"),
    "staffUnpaid.overdue": (" (scaduta)", " (em atraso)", " (overdue)"),
    "staffUnpaid.more": ("…e altri {n}.", "…e mais {n}.", "…and {n} more."),
    "staffCerts.none": (
        "Tutti i certificati degli atleti attivi sono in regola. 👍",
        "Todos os atestados dos atletas ativos estão em dia. 👍",
        "All active athletes' certificates are in order. 👍",
    ),
    "staffCerts.EXPIRED": ("Scaduti ({n}): {names}", "Caducados ({n}): {names}", "Expired ({n}): {names}"),
    "staffCerts.MISSING": ("Mancanti ({n}): {names}", "Em falta ({n}): {names}", "Missing ({n}): {names}"),
    "staffCerts.EXPIRING": (
        "In scadenza entro 30 giorni ({n}): {names}",
        "A caducar nos próximos 30 dias ({n}): {names}",
        "Expiring within 30 days ({n}): {names}",
    ),
    # --- Permessi ---------------------------------------------------------------------------------
    "denied.family": (
        "Questo riguarda le famiglie del club: dal tuo account non lo vedo.",
        "Isto diz respeito às famílias do clube: a partir da tua conta não o vejo.",
        "That's about club families: I can't see it from your account.",
    ),
    "denied.staff": (
        "Questa informazione la vede solo la segreteria del club.",
        "Esta informação só a secretaria do clube a vê.",
        "Only the club office can see that.",
    ),
    "denied.noClub": (
        "Il tuo account non è collegato a un club (o non sei entrato in nessun club): da qui non posso vederlo.",
        "A tua conta não está ligada a um clube (ou não entraste em nenhum clube): daqui não consigo ver isso.",
        "Your account isn't linked to a club (or you haven't entered one): I can't see that from here.",
    ),
    "denied.needsConfirmation": (
        "Prima di farlo mi serve la tua conferma.",
        "Antes de o fazer preciso da tua confirmação.",
        "I need your confirmation before doing that.",
    ),
    # --- Sito pubblico (nessun dato personale) ----------------------------------------------------
    "pub.greet": (
        "Ciao! Sono JAVBOT di JudoArteVida. Posso raccontarti il progetto, mostrarti i club, gli orari, come iscriversi e i prossimi eventi. Che cosa cerchi?",
        "Olá! Sou o JAVBOT da JudoArteVida. Posso falar-te do projeto, mostrar os clubes, os horários, como te inscreveres e os próximos eventos. O que procuras?",
        "Hi! I'm JAVBOT from JudoArteVida. I can tell you about the project, the clubs, schedules, how to sign up and upcoming events. What are you looking for?",
    ),
    "pub.help": (
        "Posso parlarti del progetto JudoArteVida, dei club, dei loro gruppi per età e degli orari, di come iscriversi, dei prezzi (quando il club li pubblica) e dei prossimi eventi. Per quote e pagamenti entra nella tua area: qui non vedo i dati di nessuno.",
        "Posso falar-te do projeto JudoArteVida, dos clubes, dos grupos por idade e dos horários, de como te inscreveres, dos preços (quando o clube os publica) e dos próximos eventos. Para quotas e pagamentos entra na tua área: aqui não vejo os dados de ninguém.",
        "I can tell you about the JudoArteVida project, the clubs, their age groups and schedules, how to sign up, prices (when a club publishes them) and upcoming events. For fees and payments, log in to your area: here I can't see anyone's data.",
    ),
    "pub.about": (
        "JudoArteVida è una rete di club di judo che lavorano insieme: stesse regole, eventi comuni e un ranking di tutti i judoca. Ogni club ha la sua pagina con orari, allenatori e contatti, e le famiglie gestiscono tutto dal telefono: quote, certificati, gare.",
        "A JudoArteVida é uma rede de clubes de judo que trabalham juntos: as mesmas regras, eventos comuns e um ranking de todos os judocas. Cada clube tem a sua página com horários, treinadores e contactos, e as famílias tratam de tudo pelo telemóvel: quotas, atestados, provas.",
        "JudoArteVida is a network of judo clubs working together: shared rules, joint events and a ranking of all judoka. Each club has its own page with schedules, coaches and contacts, and families manage everything from their phone: fees, certificates, competitions.",
    ),
    "pub.clubsIntro": ("I club della rete:", "Os clubes da rede:", "The network's clubs:"),
    "pub.clubLine": ("• {name}{city}", "• {name}{city}", "• {name}{city}"),
    "pub.clubsNone": (
        "Non ci sono ancora club pubblicati sul portale.",
        "Ainda não há clubes publicados no portal.",
        "There are no clubs published on the portal yet.",
    ),
    "pub.whichClub": ("Di quale club? Scegline uno:", "De que clube? Escolhe um:", "Which club? Pick one:"),
    "pub.scheduleIntro": ("Orario della settimana di {club}:", "Horário semanal do {club}:", "{club}'s weekly schedule:"),
    "pub.scheduleDay": ("{day}: {slots}", "{day}: {slots}", "{day}: {slots}"),
    "pub.scheduleNone": (
        "{club} non ha ancora pubblicato l'orario: chiedilo al club.",
        "O {club} ainda não publicou o horário: pergunta ao clube.",
        "{club} hasn't published its schedule yet: ask the club.",
    ),
    # La scheda prezzi (public.py::_prices): solo ciò che il club ha
    # configurato, una riga per cosa; ciò che è a zero non si nomina.
    "pub.pricesIntro": ("Gruppi e prezzi di {club}:", "Grupos e preços do {club}:", "{club}'s groups and prices:"),
    "pub.groupsIntro": ("I gruppi di {club}, per età:", "Os grupos do {club}, por idade:", "{club}'s groups, by age:"),
    "pub.groupLine": ("• {name}{ages}", "• {name}{ages}", "• {name}{ages}"),
    "pub.priceLine": ("• {name}{ages}: {monthly} al mese{enrollment}", "• {name}{ages}: {monthly} por mês{enrollment}", "• {name}{ages}: {monthly} a month{enrollment}"),
    "pub.priceEnrollment": (", iscrizione annuale {amount}", ", inscrição anual {amount}", ", yearly enrolment {amount}"),
    "pub.priceDue": (
        "  Si paga entro il giorno {day} di ogni mese{months}.",
        "  Paga-se até ao dia {day} de cada mês{months}.",
        "  Due by day {day} of each month{months}.",
    ),
    "pub.monthsRange": (", da {first} a {last}", ", de {first} a {last}", ", {first} to {last}"),
    "pub.monthsList": (" ({months})", " ({months})", " ({months})"),
    "pub.groupSchedule": ("  Allenamenti: {slots}", "  Treinos: {slots}", "  Training: {slots}"),
    "pub.planNote": ("  {text}", "  {text}", "  {text}"),
    "pub.feesIntro": ("Altre quote:", "Outras quotas:", "Other fees:"),
    "pub.feeParent": (
        "• Quota socio di un genitore, per chi ha figli sotto i {age} anni: {amount} all'anno, una per famiglia.",
        "• Quota de sócio de um dos pais, para quem tem filhos com menos de {age} anos: {amount} por ano, uma por família.",
        "• Parent membership, for families with children under {age}: {amount} a year, one per family.",
    ),
    "pub.feeProrata": (
        "• Le quote annuali sono dell'anno solare (gennaio–dicembre): chi entra a metà anno paga solo i mesi che restano, quello d'ingresso compreso.",
        "• As quotas anuais são do ano civil (janeiro–dezembro): quem entra a meio do ano paga só os meses que faltam, incluindo o da entrada.",
        "• Yearly fees cover the calendar year (January–December): joining mid-year you pay only the remaining months, the joining month included.",
    ),
    "pub.feeIncludes": ("• L'iscrizione comprende: {text}", "• A inscrição inclui: {text}", "• The enrolment includes: {text}"),
    "pub.discountsIntro": ("Sconti:", "Descontos:", "Discounts:"),
    "pub.discountsHow": (
        "Gli sconti di {club} e come averli:",
        "Os descontos do {club} e como os ter:",
        "{club}'s discounts and how to get them:",
    ),
    "pub.discountTier": (
        "• Escalão: {tiers} sulla mensilità. Porta il documento dell'escalão alla segreteria: lo registra lei.",
        "• Escalão: {tiers} na mensalidade. Entrega o documento do escalão na secretaria: é ela que o regista.",
        "• Income band (escalão): {tiers} off the monthly fee. Bring the escalão document to the club office: they record it.",
    ),
    "pub.discountAdapted": (
        "• Judo adattato: lo stesso sconto dell'escalão A (−{pct}%), registrato dalla segreteria. Con escalão e judo adattato vale lo sconto maggiore: non si sommano.",
        "• Judo adaptado: o mesmo desconto do escalão A (−{pct}%), registado pela secretaria. Com escalão e judo adaptado vale o desconto maior: não se somam.",
        "• Adapted judo: the same discount as escalão A (−{pct}%), recorded by the club office. With both escalão and adapted judo the larger discount applies: they don't add up.",
    ),
    "pub.discountFamily": (
        "• Famiglia: con {n} o più atleti nello stesso account di famiglia (fratelli, cugini, papà, mamma), {amount} in meno sulla mensilità di ognuno.",
        "• Família: com {n} ou mais atletas na mesma conta de família (irmãos, primos, pai, mãe), menos {amount} na mensalidade de cada um.",
        "• Family: with {n} or more athletes in the same family account (siblings, cousins, father, mother), {amount} off each one's monthly fee.",
    ),
    "pub.discountReferral": (
        "• Invita un amico: dalla tua area condividi il tuo link; ogni volta che la famiglia che hai invitato paga una mensilità ricevi {amount} di credito, che usi per pagare le tue quote.",
        "• Convida um amigo: na tua área partilha o teu link; sempre que a família que convidaste paga uma mensalidade recebes {amount} de crédito, que usas para pagar as tuas quotas.",
        "• Invite a friend: share your link from your area; every time the family you invited pays a monthly fee you get {amount} credit, which you use to pay your fees.",
    ),
    "pub.discountsHidden": (
        "{club} ha questi sconti: {names}. Gli importi li dà il club:",
        "O {club} tem estes descontos: {names}. Os valores são dados pelo clube:",
        "{club} has these discounts: {names}. The club gives the amounts:",
    ),
    "pub.discountsNone": (
        "{club} non ha sconti impostati sul portale. Per casi particolari chiedi al club:",
        "O {club} não tem descontos configurados no portal. Para casos especiais pergunta ao clube:",
        "{club} has no discounts set up on the portal. For special cases ask the club:",
    ),
    "pub.dname.tier": ("escalão", "escalão", "income band (escalão)"),
    "pub.dname.adapted": ("judo adattato", "judo adaptado", "adapted judo"),
    "pub.dname.family": ("famiglia", "família", "family"),
    "pub.dname.referral": ("invita un amico", "convida um amigo", "invite a friend"),
    "pub.pricesHidden": (
        "I prezzi li dà direttamente {club}: chiedili al club, ti risponderanno volentieri.",
        "Os preços são dados diretamente pelo {club}: pergunta ao clube, vão responder-te com gosto.",
        "Prices are given directly by {club}: ask the club, they'll be happy to tell you.",
    ),
    "pub.groupsNone": (
        "{club} non ha ancora pubblicato i gruppi e le età. Chiedi al club:",
        "O {club} ainda não publicou os grupos e as idades. Pergunta ao clube:",
        "{club} hasn't published its groups and ages yet. Ask the club:",
    ),
    "pub.signup": (
        "Per iscriverti a {club} apri la pagina d'iscrizione: crei l'account della famiglia e aggiungi chi si allena. Il piano lo sceglie il sistema in base all'età.",
        "Para te inscreveres no {club} abre a página de inscrição: crias a conta da família e juntas quem treina. O plano é escolhido pelo sistema conforme a idade.",
        "To join {club}, open its sign-up page: you create the family account and add whoever trains. The plan is chosen automatically by age.",
    ),
    "pub.signupGeneric": (
        "Per iscriverti scegli il club più vicino a te e apri la sua pagina d'iscrizione.",
        "Para te inscreveres escolhe o clube mais perto de ti e abre a página de inscrição.",
        "To sign up, pick the club nearest to you and open its sign-up page.",
    ),
    "pub.eventsIntro": ("Prossimi eventi:", "Próximos eventos:", "Upcoming events:"),
    "pub.eventLine": ("• {name}, {date}{location} ({club})", "• {name}, {date}{location} ({club})", "• {name}, {date}{location} ({club})"),
    "pub.eventsNone": (
        "Al momento non ci sono eventi in programma.",
        "De momento não há eventos marcados.",
        "There are no upcoming events right now.",
    ),
    "pub.benefits": (
        "Il judo insegna rispetto, disciplina e fiducia in sé. Migliora equilibrio, coordinazione e forza, e insegna a cadere senza farsi male: utile a ogni età. Si comincia da piccoli (di solito dai 4 anni), ma non è mai tardi: ci sono corsi anche per adulti.",
        "O judo ensina respeito, disciplina e confiança. Melhora o equilíbrio, a coordenação e a força, e ensina a cair sem se magoar: útil em qualquer idade. Começa-se cedo (normalmente a partir dos 4 anos), mas nunca é tarde: há aulas também para adultos.",
        "Judo teaches respect, discipline and self-confidence. It improves balance, coordination and strength, and teaches you to fall without getting hurt: useful at any age. Kids usually start from age 4, but it's never too late: there are adult classes too.",
    ),
    "pub.contactsGeneric": (
        "Ogni club ha i suoi contatti nella sua pagina. Dimmi quale club ti interessa.",
        "Cada clube tem os contactos na sua página. Diz-me que clube te interessa.",
        "Each club has its contacts on its page. Tell me which club you're interested in.",
    ),
    "pub.fallback": (
        "Scusa, non ho capito bene. Posso parlarti di questo:",
        "Desculpa, não percebi bem. Posso falar-te disto:",
        "Sorry, I didn't quite get that. I can tell you about:",
    ),
    "pub.coursesIntro": (
        "I corsi JAV nelle scuole: judo per bambini come attività extrascolastica, senza iscrizione, solo la mensilità. Dove e quando:",
        "Os cursos JAV nas escolas: judo para crianças como atividade extracurricular, sem inscrição, só a mensalidade. Onde e quando:",
        "JAV courses in schools: judo for kids as an after-school activity, no enrolment fee, just the monthly fee. Where and when:",
    ),
    "pub.coursesFee": (
        "Mensilità: {amount} al mese, senza iscrizione né quota socio.",
        "Mensalidade: {amount} por mês, sem inscrição nem quota de sócio.",
        "Monthly fee: {amount} a month, no enrolment or membership fee.",
    ),
    "pub.coursesFees": (
        "Mensilità, senza iscrizione né quota socio:",
        "Mensalidades, sem inscrição nem quota de sócio:",
        "Monthly fees, no enrolment or membership fee:",
    ),
    "pub.courseLine": ("• {name} — {venue}{ages}: {slots}", "• {name} — {venue}{ages}: {slots}", "• {name} — {venue}{ages}: {slots}"),
    "pub.coursesNone": (
        "Al momento non ci sono corsi nelle scuole aperti alle iscrizioni. Intanto puoi guardare i club.",
        "De momento não há cursos nas escolas abertos a inscrições. Entretanto podes ver os clubes.",
        "There are no school courses open for sign-up right now. Meanwhile you can look at the clubs.",
    ),
    "pub.qr.courses": ("Corsi nelle scuole", "Cursos nas escolas", "Courses in schools"),
    "pub.act.courses": ("Tutti i corsi nelle scuole", "Todos os cursos nas escolas", "All school courses"),
    "pub.act.courseSignup": ("Iscriviti: {course}", "Inscrever: {course}", "Sign up: {course}"),
    "pub.qr.about": ("Cos'è JudoArteVida?", "O que é a JudoArteVida?", "What is JudoArteVida?"),
    "pub.qr.clubs": ("I club", "Os clubes", "The clubs"),
    "pub.qr.schedule": ("Orari", "Horários", "Schedules"),
    "pub.qr.prices": ("Prezzi", "Preços", "Prices"),
    "pub.qr.groups": ("Gruppi ed età", "Grupos e idades", "Groups and ages"),
    "pub.qr.discounts": ("Sconti", "Descontos", "Discounts"),
    "pub.qr.signup": ("Come iscriversi", "Como me inscrevo", "How to sign up"),
    "pub.qr.events": ("Prossimi eventi", "Próximos eventos", "Upcoming events"),
    "pub.qr.benefits": ("Perché il judo?", "Porquê o judo?", "Why judo?"),
    "pub.act.club": ("Pagina di {club}", "Página do {club}", "{club} page"),
    "pub.act.signup": ("Iscriviti a {club}", "Inscrever-me no {club}", "Join {club}"),
    "pub.act.clubs": ("Tutti i club", "Todos os clubes", "All clubs"),
    "pub.act.events": ("Tutti gli eventi", "Todos os eventos", "All events"),
    "pub.act.login": ("Entra nella tua area", "Entrar na minha área", "Log in to your area"),
    "ages.range": (" ({min}–{max} anni)", " ({min}–{max} anos)", " (ages {min}–{max})"),
    "ages.from": (" (dai {min} anni)", " (a partir dos {min} anos)", " (ages {min}+)"),
}

MONTHS = {
    "it": ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
           "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"),
    "pt": ("janeiro", "fevereiro", "março", "abril", "maio", "junho",
           "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"),
    "en": ("January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"),
}

WEEKDAYS = {
    "it": ("Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"),
    "pt": ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"),
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
}


def lang_of(value: str | None) -> str:
    return value if value in LANGS else DEFAULT_LANG


def say(lang: str, key: str, **values) -> str:
    """La frase `key` nella lingua `lang`, con i segnaposto riempiti."""
    text = T[key][LANGS.index(lang_of(lang))]
    return text.format(**values) if values else text


def euro(cents: int, lang: str) -> str:
    """12,50 € in italiano e portoghese, €12.50 in inglese. Formatta un
    importo calcolato altrove: qui non si fanno conti."""
    whole, rest = divmod(abs(int(cents)), 100)
    sign = "-" if cents < 0 else ""
    if lang_of(lang) == "en":
        return f"{sign}€{whole:,}.{rest:02d}"
    return f"{sign}{whole:,}".replace(",", ".") + f",{rest:02d} €"


def day(value: date | None, lang: str) -> str:
    return value.strftime("%d/%m/%Y") if value else "—"


def month_label(period: str) -> str:
    """"2026-10" -> "10/2026"."""
    year, month = period.split("-")
    return f"{month}/{year}"


def ages(lang: str, min_age: int | None, max_age: int | None) -> str:
    if min_age is None and max_age is None:
        return ""
    if max_age is None:
        return say(lang, "ages.from", min=min_age)
    return say(lang, "ages.range", min=min_age or 0, max=max_age)


def billing_months(lang: str, months: list[int]) -> str:
    """I mesi in cui si paga la mensilità, solo se non è tutto l'anno:
    ", de setembro a junho" per un periodo di fila (anche a cavallo di
    dicembre), altrimenti l'elenco."""
    chosen = sorted({m for m in months if 1 <= m <= 12})
    if not chosen or len(chosen) == 12:
        return ""
    names = MONTHS[lang_of(lang)]
    # Il primo mese di un periodo è quello il cui precedente non c'è: se ce
    # n'è uno solo, i mesi sono di fila.
    starts = [m for m in chosen if (m - 2) % 12 + 1 not in chosen]
    if len(starts) == 1 and len(chosen) > 1:
        first = starts[0]
        last = (first + len(chosen) - 2) % 12 + 1
        return say(lang, "pub.monthsRange", first=names[first - 1], last=names[last - 1])
    return say(lang, "pub.monthsList", months=", ".join(names[m - 1] for m in chosen))

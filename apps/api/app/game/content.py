"""Le domande di Dojo Academy: la banca delle domande, i percorsi (quiz a
tema) e gli esami di cintura del gioco. In portoghese, italiano e inglese;
i termini giapponesi sono gli stessi in tutte le lingue.

Ogni domanda ha la risposta giusta per prima (`choices[0]`): l'ordine
mostrato si mescola a ogni tentativo e si salva nel tentativo, così il
browser non sa mai qual è la giusta prima di rispondere. `belt` è la
cintura da cui la domanda entra negli esami (chi prepara il verde deve
sapere anche le cose del giallo e dell'arancione).
"""

from dataclasses import dataclass, field

from app.game.qtypes import LANGS, Q, Question, T, Text  # noqa: F401

#: Le cinture del gioco, in ordine. Sono le cinture del personaggio, non
#: quelle vere del judoca (il gestionale ha le sue, più fini).
BELTS = ("WHITE", "YELLOW", "ORANGE", "GREEN", "BLUE", "BROWN", "BLACK")

BASE_QUESTIONS: tuple[Question, ...] = (
    # --- Storia ---------------------------------------------------------------------------------------
    Q("h01", "history", "YELLOW", T("Quem criou o judo?", "Chi ha creato il judo?", "Who created judo?"),
      ("Jigoro Kano", "Morihei Ueshiba", "Gichin Funakoshi", "Mitsuyo Maeda"),
      T("Jigoro Kano criou o judo em 1882, a partir do jujutsu.", "Jigoro Kano creò il judo nel 1882, partendo dal jujutsu.",
        "Jigoro Kano created judo in 1882, building on jujutsu.")),
    Q("h02", "history", "YELLOW", T("Em que ano nasceu o judo?", "In che anno è nato il judo?", "In which year was judo born?"),
      ("1882", "1912", "1945", "1964"),
      T("Em 1882 Kano fundou o Kodokan, em Tóquio.", "Nel 1882 Kano fondò il Kodokan, a Tokyo.", "In 1882 Kano founded the Kodokan in Tokyo.")),
    Q("h03", "history", "YELLOW", T("O que significa «judo»?", "Che cosa significa «judo»?", "What does “judo” mean?"),
      (T("Caminho suave", "Via della cedevolezza", "Gentle way"), T("Arte da guerra", "Arte della guerra", "Art of war"),
       T("Mão vazia", "Mano vuota", "Empty hand"), T("Força e coragem", "Forza e coraggio", "Strength and courage")),
      T("Ju = suave, flexível; Do = caminho.", "Ju = cedevole, flessibile; Do = via.", "Ju = gentle, yielding; Do = way.")),
    Q("h04", "history", "ORANGE", T("Como se chama a escola fundada por Jigoro Kano?", "Come si chiama la scuola fondata da Jigoro Kano?",
                                   "What is the name of the school founded by Jigoro Kano?"),
      ("Kodokan", "Butokukai", "Shotokan", "Aikikai"),
      T("Kodokan: «a escola para ensinar o caminho».", "Kodokan: «la scuola per insegnare la via».", "Kodokan: “the school for teaching the way”.")),
    Q("h05", "history", "GREEN", T("Em que Jogos Olímpicos o judo estreou?", "In quali Giochi Olimpici ha debuttato il judo?",
                                  "At which Olympic Games did judo debut?"),
      (T("Tóquio 1964", "Tokyo 1964", "Tokyo 1964"), T("Berlim 1936", "Berlino 1936", "Berlin 1936"),
       T("Roma 1960", "Roma 1960", "Rome 1960"), T("Munique 1972", "Monaco 1972", "Munich 1972")),
      T("O judo masculino entrou nos Jogos em Tóquio 1964.", "Il judo maschile entrò ai Giochi a Tokyo 1964.",
        "Men's judo entered the Games at Tokyo 1964.")),
    Q("h06", "history", "BLUE", T("Quem venceu a categoria aberta em Tóquio 1964, surpreendendo o Japão?",
                                 "Chi vinse la categoria open a Tokyo 1964, sorprendendo il Giappone?",
                                 "Who won the open category at Tokyo 1964, stunning Japan?"),
      ("Anton Geesink", "Akio Kaminaga", "Wilhelm Ruska", "Yasuhiro Yamashita"),
      T("O neerlandês Anton Geesink venceu Akio Kaminaga na final.", "L'olandese Anton Geesink batté Akio Kaminaga in finale.",
        "Dutchman Anton Geesink beat Akio Kaminaga in the final.")),
    Q("h07", "history", "GREEN", T("Desde que Jogos o judo feminino é olímpico (com medalhas)?",
                                  "Da quali Giochi il judo femminile è olimpico (con medaglie)?",
                                  "Since which Games has women's judo been an Olympic medal sport?"),
      (T("Barcelona 1992", "Barcellona 1992", "Barcelona 1992"), "Seoul 1988", T("Tóquio 1964", "Tokyo 1964", "Tokyo 1964"),
       T("Atlanta 1996", "Atlanta 1996", "Atlanta 1996")),
      T("Em Seul 1988 foi demonstração; em Barcelona 1992 entrou oficialmente.",
        "A Seul 1988 fu dimostrativo; a Barcellona 1992 entrò ufficialmente.",
        "Seoul 1988 was a demonstration; Barcelona 1992 made it official.")),
    Q("h08", "history", "BROWN", T("De que escolas de jujutsu Kano partiu?", "Da quali scuole di jujutsu partì Kano?",
                                  "Which jujutsu schools did Kano build on?"),
      ("Tenjin Shin'yō-ryū e Kitō-ryū", "Daitō-ryū e Yagyū-ryū", "Shotokan e Goju-ryu", "Katori Shintō-ryū e Itto-ryu"),
      T("Kano estudou Tenjin Shin'yō-ryū e Kitō-ryū antes de criar o judo.",
        "Kano studiò Tenjin Shin'yō-ryū e Kitō-ryū prima di creare il judo.",
        "Kano trained in Tenjin Shin'yō-ryū and Kitō-ryū before creating judo.")),
    Q("h09", "history", "BLUE", T("Que judoca portuguesa ganhou o bronze olímpico no Rio 2016?",
                                 "Quale judoka portoghese vinse il bronzo olimpico a Rio 2016?",
                                 "Which Portuguese judoka won Olympic bronze at Rio 2016?"),
      ("Telma Monteiro", "Joana Ramos", "Patrícia Sampaio", "Bárbara Timo"),
      T("Telma Monteiro, -57 kg, no Rio 2016.", "Telma Monteiro, -57 kg, a Rio 2016.", "Telma Monteiro, -57 kg, at Rio 2016.")),
    Q("h10", "history", "BROWN", T("Que judoca português foi campeão do mundo em 2019 e 2021 (-100 kg)?",
                                  "Quale judoka portoghese fu campione del mondo nel 2019 e nel 2021 (-100 kg)?",
                                  "Which Portuguese judoka was world champion in 2019 and 2021 (-100 kg)?"),
      ("Jorge Fonseca", "Nuno Delgado", "Pedro Soares", "Célio Dias"),
      T("Jorge Fonseca, bicampeão do mundo e bronze em Tóquio 2020.", "Jorge Fonseca, due volte campione del mondo e bronzo a Tokyo 2020.",
        "Jorge Fonseca, two-time world champion and Tokyo 2020 bronze.")),
    Q("h11", "history", "BLUE", T("Em que ano foi fundada a Federação Internacional de Judo (IJF)?",
                                 "In che anno fu fondata la Federazione Internazionale di Judo (IJF)?",
                                 "In which year was the International Judo Federation (IJF) founded?"),
      ("1951", "1882", "1964", "1992"),
      T("A IJF nasceu em 1951.", "La IJF nacque nel 1951.", "The IJF was founded in 1951.")),
    Q("h12", "history", "BLACK", T("Qual destes NÃO é um princípio do judo de Kano?", "Quale di questi NON è un principio del judo di Kano?",
                                  "Which of these is NOT one of Kano's judo principles?"),
      (T("Vencer a qualquer custo", "Vincere a ogni costo", "Win at any cost"), "Seiryoku Zen'yō", "Jita Kyōei",
       T("Educação física, mental e moral", "Educazione fisica, mentale e morale", "Physical, mental and moral education")),
      T("Seiryoku Zen'yō (máxima eficácia) e Jita Kyōei (bem-estar mútuo) são os princípios.",
        "Seiryoku Zen'yō (massima efficacia) e Jita Kyōei (mutuo benessere) sono i principi.",
        "Seiryoku Zen'yō (maximum efficiency) and Jita Kyōei (mutual welfare) are the principles.")),
    # --- Etichetta e valori ------------------------------------------------------------------------------
    Q("e01", "etiquette", "YELLOW", T("Como se chama a saudação do judo?", "Come si chiama il saluto del judo?", "What is the judo bow called?"),
      ("Rei", "Hajime", "Matte", "Osu"),
      T("Rei: cumprimenta-se ao entrar no dojo, no tapete e ao parceiro.", "Rei: si saluta entrando nel dojo, sul tatami e il compagno.",
        "Rei: you bow entering the dojo, the mat and to your partner.")),
    Q("e02", "etiquette", "YELLOW", T("Como se chama o lugar onde se pratica judo?", "Come si chiama il luogo dove si pratica judo?",
                                     "What is the place where judo is practised called?"),
      ("Dojo", "Tatami", "Judogi", "Obi"),
      T("Dojo: o lugar onde se estuda o caminho.", "Dojo: il luogo dove si studia la via.", "Dojo: the place where the way is studied.")),
    Q("e03", "etiquette", "YELLOW", T("O que é o «judogi»?", "Che cos'è il «judogi»?", "What is a “judogi”?"),
      (T("O fato de judo", "La divisa da judo", "The judo uniform"), T("O tapete", "Il tappeto", "The mat"),
       T("O professor", "Il maestro", "The teacher"), T("A cintura", "La cintura", "The belt")),
      T("Judogi: casaco, calças e cinto (obi).", "Judogi: giacca, pantaloni e cintura (obi).", "Judogi: jacket, trousers and belt (obi).")),
    Q("e04", "etiquette", "ORANGE", T("Como se chama a saudação de joelhos?", "Come si chiama il saluto in ginocchio?",
                                     "What is the kneeling bow called?"),
      ("Zarei", "Ritsurei", "Mokuso", "Seiza"),
      T("Zarei é de joelhos; Ritsurei é de pé. Seiza é a posição sentada sobre os calcanhares.",
        "Zarei è in ginocchio; Ritsurei in piedi. Seiza è la posizione seduta sui talloni.",
        "Zarei is kneeling; Ritsurei standing. Seiza is the kneeling posture.")),
    Q("e05", "etiquette", "ORANGE", T("O que é «mokuso»?", "Che cos'è «mokuso»?", "What is “mokuso”?"),
      (T("Um momento de meditação", "Un momento di meditazione", "A moment of meditation"), T("Uma projeção", "Una proiezione", "A throw"),
       T("Uma penalização", "Una penalità", "A penalty"), T("Um aquecimento", "Un riscaldamento", "A warm-up")),
      T("No início e no fim da aula, fecham-se os olhos e acalma-se a respiração.", "All'inizio e alla fine della lezione si chiudono gli occhi e si calma il respiro.",
        "At the start and end of class you close your eyes and calm your breathing.")),
    Q("e06", "etiquette", "YELLOW", T("Quem é o «sensei»?", "Chi è il «sensei»?", "Who is the “sensei”?"),
      (T("O professor", "Il maestro", "The teacher"), T("O árbitro", "L'arbitro", "The referee"),
       T("O campeão", "Il campione", "The champion"), T("O aluno mais novo", "L'allievo più giovane", "The youngest student")),
      T("Sensei: «aquele que nasceu antes», o professor.", "Sensei: «colui che è nato prima», il maestro.", "Sensei: “one who was born before”, the teacher.")),
    Q("e07", "etiquette", "ORANGE", T("No judo, «Jita Kyōei» quer dizer…", "Nel judo, «Jita Kyōei» vuol dire…", "In judo, “Jita Kyōei” means…"),
      (T("Bem-estar e benefício mútuos", "Mutuo benessere e prosperità", "Mutual welfare and benefit"),
       T("Vencer sempre", "Vincere sempre", "Always win"), T("Treinar sozinho", "Allenarsi da soli", "Train alone"),
       T("Obedecer ao árbitro", "Obbedire all'arbitro", "Obey the referee")),
      T("Progredimos juntos: o parceiro não é um inimigo.", "Si cresce insieme: il compagno non è un nemico.", "We grow together: your partner is not an enemy.")),
    Q("e08", "etiquette", "GREEN", T("«Seiryoku Zen'yō» significa…", "«Seiryoku Zen'yō» significa…", "“Seiryoku Zen'yō” means…"),
      (T("Máxima eficácia com o mínimo esforço", "Massima efficacia con il minimo sforzo", "Maximum efficiency, minimum effort"),
       T("Força máxima", "Forza massima", "Maximum strength"), T("Respeito ao mais velho", "Rispetto per il più anziano", "Respect for elders"),
       T("Atacar primeiro", "Attaccare per primo", "Attack first")),
      T("Usar bem a energia, a nossa e a do adversário.", "Usare bene l'energia, la nostra e quella dell'avversario.",
        "Use energy well, both yours and your opponent's.")),
    Q("e09", "etiquette", "YELLOW", T("Antes de subir ao tapete deves…", "Prima di salire sul tatami devi…", "Before stepping onto the mat you should…"),
      (T("Ter unhas cortadas, estar limpo e tirar objetos", "Avere unghie corte, essere pulito e togliere oggetti",
         "Have short nails, be clean and remove objects"),
       T("Calçar sapatilhas", "Mettere le scarpe", "Put on shoes"), T("Comer bem", "Mangiare tanto", "Eat a big meal"),
       T("Correr à volta do dojo", "Correre attorno al dojo", "Run around the dojo")),
      T("Higiene e segurança protegem-te a ti e ao parceiro.", "Igiene e sicurezza proteggono te e il compagno.",
        "Hygiene and safety protect you and your partner.")),
    Q("e10", "etiquette", "BROWN", T("Que cinto usam os 6.º, 7.º e 8.º dan?", "Che cintura usano i 6°, 7° e 8° dan?",
                                    "What belt do 6th, 7th and 8th dan wear?"),
      (T("Vermelho e branco", "Bianca e rossa", "Red and white"), T("Vermelho", "Rossa", "Red"),
       T("Preto com riscas douradas", "Nera con strisce d'oro", "Black with gold stripes"), T("Azul", "Blu", "Blue")),
      T("O cinto vermelho e branco é do 6.º ao 8.º dan; o vermelho, do 9.º e 10.º.",
        "La cintura bianca e rossa va dal 6° all'8° dan; la rossa al 9° e 10°.",
        "Red-and-white is for 6th to 8th dan; red is for 9th and 10th.")),
    # --- Tecniche ------------------------------------------------------------------------------------------
    Q("t01", "techniques", "YELLOW", T("O que é o «ukemi»?", "Che cos'è l'«ukemi»?", "What is “ukemi”?"),
      (T("A técnica de queda", "La tecnica di caduta", "The breakfall technique"), T("Uma imobilização", "Un'immobilizzazione", "A hold-down"),
       T("Uma saudação", "Un saluto", "A bow"), T("Um estrangulamento", "Uno strangolamento", "A strangle")),
      T("Saber cair bem é a primeira coisa que se aprende.", "Saper cadere bene è la prima cosa che si impara.", "Falling safely is the first thing you learn.")),
    Q("t02", "techniques", "YELLOW", T("Quem projeta chama-se «tori». E quem cai?", "Chi proietta si chiama «tori». E chi cade?",
                                      "The one who throws is “tori”. And the one who falls?"),
      ("Uke", "Sensei", "Shiai", "Randori"),
      T("Uke recebe a técnica; tori executa.", "Uke riceve la tecnica; tori la esegue.", "Uke receives the technique; tori performs it.")),
    Q("t03", "techniques", "YELLOW", T("O-soto-gari é…", "O-soto-gari è…", "O-soto-gari is…"),
      (T("Uma grande ceifa por fora", "Una grande falciata esterna", "A major outer reap"),
       T("Uma projeção de anca", "Una proiezione d'anca", "A hip throw"), T("Uma imobilização", "Un'immobilizzazione", "A hold-down"),
       T("Uma projeção de ombro", "Una proiezione di spalla", "A shoulder throw")),
      T("O = grande, soto = fora, gari = ceifar.", "O = grande, soto = fuori, gari = falciare.", "O = major, soto = outer, gari = reap.")),
    Q("t04", "techniques", "YELLOW", T("O-goshi é uma projeção de…", "O-goshi è una proiezione di…", "O-goshi is a throw using the…"),
      (T("Anca", "Anca", "Hip"), T("Perna", "Gamba", "Leg"), T("Ombro", "Spalla", "Shoulder"), T("Sacrifício", "Sacrificio", "Sacrifice")),
      T("Goshi/koshi = anca.", "Goshi/koshi = anca.", "Goshi/koshi = hip.")),
    Q("t05", "techniques", "YELLOW", T("Qual destas é uma imobilização (osaekomi-waza)?", "Quale di queste è un'immobilizzazione (osaekomi-waza)?",
                                      "Which of these is a hold-down (osaekomi-waza)?"),
      ("Kesa-gatame", "Seoi-nage", "Uchi-mata", "Tomoe-nage"),
      T("Kesa-gatame imobiliza de lado, como uma «faixa» de monge.", "Kesa-gatame immobilizza di fianco, come una «sciarpa» da monaco.",
        "Kesa-gatame pins from the side, like a monk's scarf.")),
    Q("t06", "techniques", "ORANGE", T("Qual destas técnicas é do 1.º grupo do Gokyo?", "Quale di queste tecniche è del 1° gruppo del Gokyo?",
                                      "Which technique is in the 1st group of the Gokyo?"),
      ("De-ashi-barai", "Uchi-mata", "Tomoe-nage", "Sumi-gaeshi"),
      T("1.º grupo: de-ashi-barai, hiza-guruma, sasae-tsurikomi-ashi, uki-goshi, o-soto-gari, o-goshi, o-uchi-gari, seoi-nage.",
        "1° gruppo: de-ashi-barai, hiza-guruma, sasae-tsurikomi-ashi, uki-goshi, o-soto-gari, o-goshi, o-uchi-gari, seoi-nage.",
        "1st group: de-ashi-barai, hiza-guruma, sasae-tsurikomi-ashi, uki-goshi, o-soto-gari, o-goshi, o-uchi-gari, seoi-nage.")),
    Q("t07", "techniques", "ORANGE", T("Seoi-nage é uma projeção de…", "Seoi-nage è una proiezione di…", "Seoi-nage is a… throw"),
      (T("Ombro (por cima das costas)", "Spalla (sopra la schiena)", "Shoulder (over the back)"), T("Perna", "Gamba", "Leg"),
       T("Sacrifício", "Sacrificio", "Sacrifice"), T("Pé", "Piede", "Foot")),
      T("Seou = carregar às costas.", "Seou = caricare sulla schiena.", "Seou = carry on the back.")),
    Q("t08", "techniques", "GREEN", T("Qual destas técnicas é do 2.º grupo do Gokyo?", "Quale di queste tecniche è del 2° gruppo del Gokyo?",
                                     "Which technique is in the 2nd group of the Gokyo?"),
      ("Harai-goshi", "O-goshi", "Kata-guruma", "Ura-nage"),
      T("2.º grupo: ko-soto-gari, ko-uchi-gari, koshi-guruma, tsurikomi-goshi, okuri-ashi-harai, tai-otoshi, harai-goshi, uchi-mata.",
        "2° gruppo: ko-soto-gari, ko-uchi-gari, koshi-guruma, tsurikomi-goshi, okuri-ashi-harai, tai-otoshi, harai-goshi, uchi-mata.",
        "2nd group: ko-soto-gari, ko-uchi-gari, koshi-guruma, tsurikomi-goshi, okuri-ashi-harai, tai-otoshi, harai-goshi, uchi-mata.")),
    Q("t09", "techniques", "ORANGE", T("As três fases de uma projeção são…", "Le tre fasi di una proiezione sono…", "The three phases of a throw are…"),
      ("Kuzushi, tsukuri, kake", "Rei, hajime, matte", "Tori, uke, sensei", "Ippon, waza-ari, shido"),
      T("Desequilibrar (kuzushi), entrar (tsukuri), executar (kake).", "Squilibrare (kuzushi), entrare (tsukuri), eseguire (kake).",
        "Unbalance (kuzushi), fit in (tsukuri), execute (kake).")),
    Q("t10", "techniques", "GREEN", T("Katame-waza inclui imobilizações, estrangulamentos e…", "Il katame-waza comprende immobilizzazioni, strangolamenti e…",
                                     "Katame-waza includes hold-downs, strangles and…"),
      (T("Chaves de articulação", "Leve articolari", "Joint locks"), T("Projeções de anca", "Proiezioni d'anca", "Hip throws"),
       T("Quedas", "Cadute", "Breakfalls"), T("Saudações", "Saluti", "Bows")),
      T("Osaekomi-waza, shime-waza e kansetsu-waza.", "Osaekomi-waza, shime-waza e kansetsu-waza.", "Osaekomi-waza, shime-waza and kansetsu-waza.")),
    Q("t11", "techniques", "BLUE", T("Em competição, as chaves (kansetsu-waza) só são permitidas…", "In gara, le leve (kansetsu-waza) sono permesse solo…",
                                    "In competition, joint locks (kansetsu-waza) are allowed only…"),
      (T("No cotovelo", "Sul gomito", "On the elbow"), T("No joelho", "Sul ginocchio", "On the knee"),
       T("No ombro", "Sulla spalla", "On the shoulder"), T("No pulso", "Sul polso", "On the wrist")),
      T("Só o cotovelo, e não para os escalões jovens.", "Solo il gomito, e non per le categorie giovanili.", "Only the elbow, and not for young age groups.")),
    Q("t12", "techniques", "BLUE", T("Qual destas técnicas é do 3.º grupo do Gokyo?", "Quale di queste tecniche è del 3° gruppo del Gokyo?",
                                    "Which technique is in the 3rd group of the Gokyo?"),
      ("Tomoe-nage", "Seoi-nage", "Tai-otoshi", "Sumi-otoshi"),
      T("3.º grupo: ko-soto-gake, tsuri-goshi, yoko-otoshi, ashi-guruma, hane-goshi, harai-tsurikomi-ashi, tomoe-nage, kata-guruma.",
        "3° gruppo: ko-soto-gake, tsuri-goshi, yoko-otoshi, ashi-guruma, hane-goshi, harai-tsurikomi-ashi, tomoe-nage, kata-guruma.",
        "3rd group: ko-soto-gake, tsuri-goshi, yoko-otoshi, ashi-guruma, hane-goshi, harai-tsurikomi-ashi, tomoe-nage, kata-guruma.")),
    Q("t13", "techniques", "BROWN", T("Qual destas técnicas é do 4.º grupo do Gokyo?", "Quale di queste tecniche è del 4° gruppo del Gokyo?",
                                     "Which technique is in the 4th group of the Gokyo?"),
      ("Sumi-gaeshi", "Hiza-guruma", "Ko-uchi-gari", "Hane-goshi"),
      T("4.º grupo: sumi-gaeshi, tani-otoshi, hane-makikomi, sukui-nage, utsuri-goshi, o-guruma, soto-makikomi, uki-otoshi.",
        "4° gruppo: sumi-gaeshi, tani-otoshi, hane-makikomi, sukui-nage, utsuri-goshi, o-guruma, soto-makikomi, uki-otoshi.",
        "4th group: sumi-gaeshi, tani-otoshi, hane-makikomi, sukui-nage, utsuri-goshi, o-guruma, soto-makikomi, uki-otoshi.")),
    Q("t14", "techniques", "BLACK", T("Nage-no-kata tem quantas projeções?", "Il nage-no-kata ha quante proiezioni?", "How many throws are in the Nage-no-kata?"),
      ("15", "8", "10", "40"),
      T("Cinco grupos de três técnicas, executadas à direita e à esquerda.", "Cinque gruppi di tre tecniche, eseguite a destra e a sinistra.",
        "Five groups of three techniques, done on both sides.")),
    Q("t15", "techniques", "BLACK", T("O primeiro grupo do Nage-no-kata (te-waza) é…", "Il primo gruppo del nage-no-kata (te-waza) è…",
                                     "The first group of the Nage-no-kata (te-waza) is…"),
      ("Uki-otoshi, seoi-nage, kata-guruma", "O-goshi, harai-goshi, tsurikomi-goshi", "Tomoe-nage, ura-nage, sumi-gaeshi",
       "Okuri-ashi-harai, sasae-tsurikomi-ashi, uchi-mata"),
      T("Te-waza: técnicas de braço.", "Te-waza: tecniche di braccio.", "Te-waza: hand techniques.")),
    Q("t16", "techniques", "GREEN", T("Kami-shiho-gatame imobiliza…", "Kami-shiho-gatame immobilizza…", "Kami-shiho-gatame pins…"),
      (T("Por cima da cabeça do uke", "Dalla parte della testa di uke", "From above uke's head"),
       T("De lado, com o braço à volta do pescoço", "Di fianco, col braccio attorno al collo", "From the side, arm around the neck"),
       T("Sentado sobre a barriga", "Seduti sulla pancia", "Sitting on the stomach"), T("De pé", "In piedi", "Standing")),
      T("Kami = em cima; shiho = quatro direções.", "Kami = sopra; shiho = quattro direzioni.", "Kami = upper; shiho = four quarters.")),
    # --- Regole ------------------------------------------------------------------------------------------------
    Q("r01", "rules", "YELLOW", T("O árbitro diz «Hajime». Quer dizer…", "L'arbitro dice «Hajime». Vuol dire…", "The referee says “Hajime”. It means…"),
      (T("Começar", "Iniziare", "Begin"), T("Parar", "Fermarsi", "Stop"), T("Fim", "Fine", "End"), T("Imobilização", "Immobilizzazione", "Hold")),
      T("Hajime: começa. Matte: para. Sore-made: acabou.", "Hajime: inizia. Matte: fermi. Sore-made: è finito.", "Hajime: begin. Matte: stop. Sore-made: that's all.")),
    Q("r02", "rules", "YELLOW", T("«Matte» quer dizer…", "«Matte» vuol dire…", "“Matte” means…"),
      (T("Parar", "Fermarsi", "Stop"), T("Começar", "Iniziare", "Begin"), T("Ponto", "Punto", "Point"), T("Saudar", "Salutare", "Bow")),
      T("Matte: para; o combate recomeça com hajime.", "Matte: fermi; il combattimento riprende con hajime.", "Matte: stop; the contest resumes with hajime.")),
    Q("r03", "rules", "ORANGE", T("Qual é a pontuação máxima, que acaba o combate?", "Qual è il punteggio massimo, che chiude il combattimento?",
                                 "What is the top score that ends the contest?"),
      ("Ippon", "Waza-ari", "Yuko", "Shido"),
      T("Ippon acaba o combate; dois waza-ari também.", "Ippon chiude il combattimento; anche due waza-ari.", "Ippon ends the contest; so do two waza-ari.")),
    Q("r04", "rules", "GREEN", T("Quantos segundos de imobilização dão ippon?", "Quanti secondi di immobilizzazione danno ippon?",
                                "How many seconds of hold-down score ippon?"),
      ("20", "10", "25", "30"),
      T("20 s = ippon; 10 s = waza-ari.", "20 s = ippon; 10 s = waza-ari.", "20 s = ippon; 10 s = waza-ari.")),
    Q("r05", "rules", "GREEN", T("O que é um «shido»?", "Che cos'è uno «shido»?", "What is a “shido”?"),
      (T("Uma penalização leve", "Una penalità lieve", "A minor penalty"), T("Uma projeção", "Una proiezione", "A throw"),
       T("Um ponto", "Un punto", "A point"), T("Uma saudação", "Un saluto", "A bow")),
      T("Três shido dão hansoku-make: perde-se o combate.", "Tre shido danno hansoku-make: si perde il combattimento.",
        "Three shido mean hansoku-make: you lose the contest.")),
    Q("r06", "rules", "BLUE", T("Quantos shido levam à desclassificação (hansoku-make)?", "Quanti shido portano alla squalifica (hansoku-make)?",
                               "How many shido lead to disqualification (hansoku-make)?"),
      ("3", "2", "4", "5"),
      T("Ao terceiro shido o combate acaba.", "Al terzo shido il combattimento finisce.", "On the third shido the contest ends.")),
    Q("r07", "rules", "BLUE", T("Quanto dura um combate de seniores (tempo regular)?", "Quanto dura un combattimento seniores (tempo regolare)?",
                               "How long is a senior contest (regular time)?"),
      (T("4 minutos", "4 minuti", "4 minutes"), T("3 minutos", "3 minuti", "3 minutes"), T("5 minutos", "5 minuti", "5 minutes"),
       T("2 minutos", "2 minuti", "2 minutes")),
      T("4 minutos, para homens e mulheres; depois, golden score.", "4 minuti, per uomini e donne; poi golden score.",
        "4 minutes for men and women; then golden score.")),
    Q("r08", "rules", "BLUE", T("O que é o «golden score»?", "Che cos'è il «golden score»?", "What is “golden score”?"),
      (T("O prolongamento sem limite: quem pontua primeiro ganha", "Il supplementare senza limite: chi segna per primo vince",
         "Overtime with no limit: first score wins"),
       T("Uma medalha de ouro", "Una medaglia d'oro", "A gold medal"), T("Um prémio do árbitro", "Un premio dell'arbitro", "A referee's award"),
       T("O tempo de aquecimento", "Il tempo di riscaldamento", "Warm-up time")),
      T("Em empate, continua até ao primeiro ponto ou penalização decisiva.", "In parità si continua fino al primo punto o penalità decisiva.",
        "If tied, it goes on until the first score or deciding penalty.")),
    Q("r09", "rules", "GREEN", T("Como o árbitro sinaliza waza-ari?", "Come segnala l'arbitro un waza-ari?", "How does the referee signal waza-ari?"),
      (T("Braço estendido de lado, à altura do ombro", "Braccio teso di lato, all'altezza della spalla", "Arm stretched sideways at shoulder height"),
       T("Braço levantado bem alto", "Braccio alzato in alto", "Arm raised high overhead"),
       T("Mãos na cabeça", "Mani sulla testa", "Hands on the head"), T("Apito", "Fischio", "Whistle")),
      T("Ippon: braço bem alto. Waza-ari: braço de lado.", "Ippon: braccio in alto. Waza-ari: braccio di lato.", "Ippon: arm high. Waza-ari: arm to the side.")),
    Q("r10", "rules", "BROWN", T("«Toketa» quer dizer…", "«Toketa» vuol dire…", "“Toketa” means…"),
      (T("A imobilização acabou", "L'immobilizzazione è rotta", "The hold is broken"), T("Começar", "Iniziare", "Begin"),
       T("Penalização", "Penalità", "Penalty"), T("Ippon", "Ippon", "Ippon")),
      T("Osaekomi começa a imobilização; toketa diz que se soltou.", "Osaekomi avvia l'immobilizzazione; toketa dice che si è liberato.",
        "Osaekomi starts the hold; toketa says it's broken.")),
    # --- Vocabolario -----------------------------------------------------------------------------------------
    Q("v01", "vocabulary", "YELLOW", T("«Obi» é…", "«Obi» è…", "“Obi” is…"),
      (T("O cinto", "La cintura", "The belt"), T("O casaco", "La giacca", "The jacket"), T("O tapete", "Il tappeto", "The mat"), T("O dojo", "Il dojo", "The dojo")),
      T("O obi mostra o grau do judoca.", "L'obi mostra il grado del judoka.", "The obi shows a judoka's grade.")),
    Q("v02", "vocabulary", "YELLOW", T("«Tatami» é…", "«Tatami» è…", "“Tatami” is…"),
      (T("O tapete", "Il tappeto", "The mat"), T("O professor", "Il maestro", "The teacher"), T("A queda", "La caduta", "The fall"), T("O combate", "Il combattimento", "The contest")),
      T("Tatami: os tapetes onde se treina.", "Tatami: i tappeti su cui ci si allena.", "Tatami: the mats you train on.")),
    Q("v03", "vocabulary", "ORANGE", T("«Randori» é…", "«Randori» è…", "“Randori” is…"),
      (T("Treino livre de combate", "Allenamento libero di combattimento", "Free practice sparring"), T("Uma kata", "Un kata", "A kata"),
       T("Uma saudação", "Un saluto", "A bow"), T("Uma penalização", "Una penalità", "A penalty")),
      T("Randori: praticar livremente com o parceiro.", "Randori: praticare liberamente con il compagno.", "Randori: free practice with a partner.")),
    Q("v04", "vocabulary", "ORANGE", T("«Kata» é…", "«Kata» è…", "“Kata” is…"),
      (T("Uma forma: sequência codificada de técnicas", "Una forma: sequenza codificata di tecniche", "A form: a set sequence of techniques"),
       T("Um combate oficial", "Un combattimento ufficiale", "An official contest"), T("Uma cintura", "Una cintura", "A belt"), T("Um aquecimento", "Un riscaldamento", "A warm-up")),
      T("As kata preservam os princípios do judo.", "I kata custodiscono i principi del judo.", "Kata preserve judo's principles.")),
    Q("v05", "vocabulary", "GREEN", T("«Shiai» é…", "«Shiai» è…", "“Shiai” is…"),
      (T("Uma competição", "Una gara", "A competition"), T("Um estrangulamento", "Uno strangolamento", "A strangle"),
       T("Uma queda", "Una caduta", "A fall"), T("Um professor", "Un maestro", "A teacher")),
      T("Shiai: o combate a sério, em competição.", "Shiai: il combattimento vero, in gara.", "Shiai: real contest, in competition.")),
    Q("v06", "vocabulary", "GREEN", T("«Nage-waza» são…", "Le «nage-waza» sono…", "“Nage-waza” are…"),
      (T("Técnicas de projeção", "Tecniche di proiezione", "Throwing techniques"), T("Técnicas de chão", "Tecniche a terra", "Ground techniques"),
       T("Saudações", "Saluti", "Bows"), T("Quedas", "Cadute", "Breakfalls")),
      T("Nage = projetar.", "Nage = proiettare.", "Nage = throw.")),
    Q("v07", "vocabulary", "BLUE", T("«Ne-waza» são…", "Le «ne-waza» sono…", "“Ne-waza” are…"),
      (T("Técnicas de chão", "Tecniche a terra", "Ground techniques"), T("Técnicas de pé", "Tecniche in piedi", "Standing techniques"),
       T("Técnicas de queda", "Tecniche di caduta", "Breakfall techniques"), T("Técnicas de kata", "Tecniche di kata", "Kata techniques")),
      T("Ne = deitado: o trabalho no chão.", "Ne = sdraiato: il lavoro a terra.", "Ne = lying down: groundwork.")),
    Q("v08", "vocabulary", "BLUE", T("«Kumikata» é…", "«Kumikata» è…", "“Kumikata” is…"),
      (T("A forma de agarrar o judogi", "Il modo di prendere il judogi", "How you grip the judogi"), T("Uma projeção", "Una proiezione", "A throw"),
       T("Uma penalização", "Una penalità", "A penalty"), T("O tempo do combate", "Il tempo del combattimento", "Contest time")),
      T("Uma boa pega é metade da técnica.", "Una buona presa è metà della tecnica.", "A good grip is half the technique.")),
    Q("v09", "vocabulary", "BROWN", T("«Tai-sabaki» é…", "«Tai-sabaki» è…", "“Tai-sabaki” is…"),
      (T("O movimento de rotação do corpo", "Il movimento di rotazione del corpo", "Turning body movement"),
       T("Uma imobilização", "Un'immobilizzazione", "A hold-down"), T("Uma saudação de pé", "Un saluto in piedi", "A standing bow"),
       T("Um estrangulamento", "Uno strangolamento", "A strangle")),
      T("Mexer o corpo para criar o ângulo da técnica.", "Muovere il corpo per creare l'angolo della tecnica.", "Moving the body to create the angle for a technique.")),
    Q("v10", "vocabulary", "BLACK", T("«Kaeshi-waza» são…", "Le «kaeshi-waza» sono…", "“Kaeshi-waza” are…"),
      (T("Contra-ataques", "Contrattacchi", "Counter techniques"), T("Combinações", "Combinazioni", "Combinations"),
       T("Técnicas de sacrifício", "Tecniche di sacrificio", "Sacrifice techniques"), T("Técnicas proibidas", "Tecniche proibite", "Forbidden techniques")),
      T("Kaeshi: virar o ataque do adversário. Renraku-waza são as combinações.", "Kaeshi: ribaltare l'attacco avversario. Renraku-waza sono le combinazioni.",
        "Kaeshi: turning the opponent's attack. Renraku-waza are combinations.")),
)

from app.game.questions import (  # noqa: E402
    coach_a, coach_b, coach_c, dan_high, dan_low, dan_mid, kata_intro, kyu, portugal, referee,
)

QUESTIONS: tuple[Question, ...] = BASE_QUESTIONS + tuple(
    q for bank in (kyu, kata_intro, dan_low, dan_mid, dan_high, portugal, referee, coach_a, coach_b, coach_c) for q in bank.QUESTIONS
)
BY_ID = {q.id: q for q in QUESTIONS}

# --- I gradi ------------------------------------------------------------------------------------------------
#
# La scala degli esami della Dojo Academy segue il Manuale de Graduações
# della FPJ: le mezze cinture fino alla marrone, poi i dan fino al 10°.
# Ogni esame ha 5 domande più del precedente fino alla marrone (bianca-gialla
# 5 … marrone 50); il 1° dan ne aggiunge 10, il 2° 15, il 3° 20 e così via
# fino al 10° (375). Le domande portano il grado da cui entrano (`belt`):
# solo i gradi pieni, una mezza cintura pesca fino alla cintura che prepara.

#: I gradi delle domande, dal più facile.
LEVELS = ("YELLOW", "ORANGE", "GREEN", "BLUE", "BROWN", "BLACK", "DAN2", "DAN3", "DAN4", "DAN5", "DAN6", "DAN7", "DAN8",
          "DAN9", "DAN10")
#: La scala degli esami. BLACK è il 1° dan (il codice resta quello degli esami già superati).
GRADES = ("WHITE", "WHITE_YELLOW", "YELLOW", "YELLOW_ORANGE", "ORANGE", "ORANGE_GREEN", "GREEN", "GREEN_BLUE", "BLUE",
          "BLUE_BROWN", "BROWN", "BLACK", "DAN2", "DAN3", "DAN4", "DAN5", "DAN6", "DAN7", "DAN8", "DAN9", "DAN10")
DANS = GRADES[GRADES.index("BLACK"):]


def grade_level(grade: str) -> str:
    """Fin dove pesca l'esame: una mezza cintura prepara quella dopo."""
    if grade in LEVELS:
        return grade
    return GRADES[GRADES.index(grade) + 1]


def career_belt(grade: str) -> str:
    """La cintura del personaggio di Judo Career per un grado della Academy:
    una mezza cintura vale quella sotto, ogni dan la nera."""
    if grade in BELTS:
        return grade
    if grade in DANS:
        return "BLACK"
    return grade.split("_")[0] if grade in GRADES else "WHITE"


def _sizes() -> dict[str, int]:
    sizes, n, step = {}, 0, 5
    for grade in GRADES[1:]:
        if grade in DANS:
            step = 10 if grade == "BLACK" else step + 5
        n += step
        sizes[grade] = n
    return sizes


EXAM_SIZES = _sizes()

GRADE_NAMES = {
    "WHITE": T("Branco", "Bianca", "White"),
    "WHITE_YELLOW": T("Branco e amarelo", "Bianca e gialla", "White-yellow"),
    "YELLOW": T("Amarelo", "Gialla", "Yellow"),
    "YELLOW_ORANGE": T("Amarelo e laranja", "Gialla e arancione", "Yellow-orange"),
    "ORANGE": T("Laranja", "Arancione", "Orange"),
    "ORANGE_GREEN": T("Laranja e verde", "Arancione e verde", "Orange-green"),
    "GREEN": T("Verde", "Verde", "Green"),
    "GREEN_BLUE": T("Verde e azul", "Verde e blu", "Green-blue"),
    "BLUE": T("Azul", "Blu", "Blue"),
    "BLUE_BROWN": T("Azul e castanho", "Blu e marrone", "Blue-brown"),
    "BROWN": T("Castanho", "Marrone", "Brown"),
    **{d: T(f"{i}.º Dan", f"{i}° Dan", f"{i}{'st' if i == 1 else 'nd' if i == 2 else 'rd' if i == 3 else 'th'} Dan")
       for i, d in enumerate(DANS, start=1)},
}
#: Il grado in giapponese (kyu e dan), come nel manuale FPJ.
GRADE_JP = {"WHITE": "Rokukyu", "YELLOW": "Gokyu", "ORANGE": "Yonkyu", "GREEN": "Sankyu", "BLUE": "Nikyu", "BROWN": "Ikyu",
            "BLACK": "Shodan", "DAN2": "Nidan", "DAN3": "Sandan", "DAN4": "Yondan", "DAN5": "Godan", "DAN6": "Rokudan",
            "DAN7": "Shichidan", "DAN8": "Hachidan", "DAN9": "Kudan", "DAN10": "Judan"}

#: Che cosa chiede ogni dan: i kata dalla tabella 6.3 «Exame de Katas» del
#: regolamento FPJ (via normale; la via competizione ne chiede uno in meno), poi oltre.
DAN_FOCUS = {
    "BLACK": T("Nage-no-kata, Gokyo, katame-waza, história do Kodokan", "Nage-no-kata, Gokyo, katame-waza, storia del Kodokan",
               "Nage-no-kata, Gokyo, katame-waza, Kodokan history"),
    "DAN2": T("Nage-no-kata e Katame-no-kata, shinmeisho-no-waza, arbitragem", "Nage-no-kata e Katame-no-kata, shinmeisho-no-waza, arbitraggio",
              "Nage-no-kata and Katame-no-kata, shinmeisho-no-waza, refereeing"),
    "DAN3": T("Nage, Katame e Kime-no-kata, shime e kansetsu-waza, IJF e EJU", "Nage, Katame e Kime-no-kata, shime e kansetsu-waza, IJF ed EJU",
              "Nage, Katame and Kime-no-kata, shime and kansetsu-waza, IJF and EJU"),
    "DAN4": T("Kime-no-kata, Kodokan-goshin-jutsu, Ju-no-kata, atemi-waza", "Kime-no-kata, Kodokan-goshin-jutsu, Ju-no-kata, atemi-waza",
              "Kime-no-kata, Kodokan-goshin-jutsu, Ju-no-kata, atemi-waza"),
    "DAN5": T("Goshin-jutsu, Ju-no-kata, Koshiki-no-kata, kyusho", "Goshin-jutsu, Ju-no-kata, Koshiki-no-kata, kyusho",
              "Goshin-jutsu, Ju-no-kata, Koshiki-no-kata, kyusho"),
    "DAN6": T("Ju-no-kata, Koshiki-no-kata, Itsutsu-no-kata, altas graduações", "Ju-no-kata, Koshiki-no-kata, Itsutsu-no-kata, alti gradi",
              "Ju-no-kata, Koshiki-no-kata, Itsutsu-no-kata, high grades"),
    "DAN7": T("Atemi-waza a fundo, todos os kata do Kodokan", "Atemi-waza a fondo, tutti i kata del Kodokan",
              "Atemi-waza in depth, every Kodokan kata"),
    "DAN8": T("Mestres do Kodokan, filosofia de Kano", "Maestri del Kodokan, filosofia di Kano", "Kodokan masters, Kano's philosophy"),
    "DAN9": T("Detalhe dos kata e da história do judo", "Dettaglio dei kata e della storia del judo", "Kata and judo history in detail"),
    "DAN10": T("Tudo: o exame do mestre", "Tutto: l'esame del maestro", "Everything: the master's exam"),
}


#: Domande che un esame contiene sempre (una per gruppo, a caso): il judo in Algarve per la
#: marrone, la nascita dell'ADJA (Lagoa, 14 agosto 1979) per il 1° dan.
EXAM_FEATURED = {
    "BROWN": (("p036", "p071", "p086", "p087"),),
    "BLACK": (("p081", "p089"), ("p052", "p054", "p088", "p090")),
}


@dataclass(frozen=True)
class Quiz:
    id: str
    kind: str  # TOPIC, EXAM o COURSE
    icon: str
    title: Text
    description: Text
    #: TOPIC: il tema; COURSE: i temi da cui pescare; EXAM: il grado (`belt`).
    topic: str | None = None
    topics: tuple = ()
    belt: str | None = None
    size: int = 10
    seconds: int = 30
    pass_pct: int = 70
    #: XP per un esame o un modulo superato la prima volta.
    pass_xp: int = 0
    #: COURSE: la qualifica che dà, il percorso a cui appartiene, il grado minimo e le qualifiche che servono prima.
    qualification: str | None = None
    group: str | None = None
    min_grade: str | None = None
    requires: tuple = ()
    #: COURSE: fino a quale grado di domanda si pesca (None = tutte).
    level_cap: str | None = None
    tags: tuple = field(default_factory=tuple)


TOPICS = {
    "history": ("🏯", T("História do judo", "Storia del judo", "Judo history"),
                T("Jigoro Kano, o Kodokan, os Jogos Olímpicos e os campeões portugueses.",
                  "Jigoro Kano, il Kodokan, le Olimpiadi e i campioni portoghesi.",
                  "Jigoro Kano, the Kodokan, the Olympics and Portuguese champions.")),
    "etiquette": ("🙇", T("Etiqueta e valores", "Etichetta e valori", "Etiquette and values"),
                  T("Rei, dojo, sensei e os princípios do caminho suave.", "Rei, dojo, sensei e i principi della via cedevole.",
                    "Rei, dojo, sensei and the principles of the gentle way.")),
    "techniques": ("🥋", T("Técnicas", "Tecniche", "Techniques"),
                   T("Ukemi, o Gokyo, imobilizações e kata.", "Ukemi, il Gokyo, immobilizzazioni e kata.", "Ukemi, the Gokyo, hold-downs and kata.")),
    "rules": ("⚖️", T("Regras de competição", "Regole di gara", "Competition rules"),
              T("Hajime, ippon, shido, golden score: pensa como um árbitro.", "Hajime, ippon, shido, golden score: ragiona da arbitro.",
                "Hajime, ippon, shido, golden score: think like a referee.")),
    "vocabulary": ("🗾", T("Vocabulário japonês", "Vocabolario giapponese", "Japanese vocabulary"),
                   T("As palavras que ouves todos os dias no tapete.", "Le parole che senti ogni giorno sul tatami.",
                     "The words you hear on the mat every day.")),
    "kata": ("📜", T("Os kata do Kodokan", "I kata del Kodokan", "The Kodokan kata"),
             T("Nage, Katame, Kime, Ju, Goshin-jutsu, Itsutsu e Koshiki-no-kata.",
               "Nage, Katame, Kime, Ju, Goshin-jutsu, Itsutsu e Koshiki-no-kata.",
               "Nage, Katame, Kime, Ju, Goshin-jutsu, Itsutsu and Koshiki-no-kata.")),
    "pt_history": ("🇵🇹", T("Judo em Portugal", "Il judo in Portogallo", "Judo in Portugal"),
                   T("Os pioneiros, a Federação, as associações e os campeões portugueses.",
                     "I pionieri, la Federazione, le associazioni e i campioni portoghesi.",
                     "The pioneers, the Federation, the associations and Portugal's champions.")),
    "fpj_rules": ("📘", T("Regulamento de graduações", "Regolamento dei gradi", "Grading regulations"),
                  T("O Manual e Regulamento de Graduações da FPJ: idades, tempos, programas.",
                    "Il Manuale e Regolamento dei gradi della FPJ: età, tempi, programmi.",
                    "The FPJ grading manual and regulations: ages, times, programmes.")),
}
#: I temi degli esami di grado (i corsi hanno i loro).
GRADE_TOPICS = frozenset(TOPICS)

#: I corsi: chi li supera ha una qualifica. Il corso di treinador è fatto di moduli; la qualifica arriva con l'ultimo.
COURSE_MODULES = {
    "physiology": ("🫀", T("Fisiologia do esforço", "Fisiologia dello sforzo", "Exercise physiology"), ("physiology",), None),
    "methodology": ("📈", T("Metodologia do treino", "Metodologia dell'allenamento", "Training methodology"), ("methodology",), None),
    "anatomy": ("🦴", T("Anatomia e corpo humano", "Anatomia e corpo umano", "Anatomy and the human body"), ("anatomy",), None),
    "technique": ("🥋", T("Técnica e kata", "Tecnica e kata", "Technique and kata"), ("techniques", "kata"), "DAN3"),
    "ethics": ("🤝", T("Ética desportiva", "Etica sportiva", "Sports ethics"), ("ethics",), None),
    "antidoping": ("🧪", T("Antidopagem", "Antidoping", "Anti-doping"), ("antidoping",), None),
    "psychology": ("🧠", T("Psicologia do desporto", "Psicologia dello sport", "Sport psychology"), ("psychology",), None),
    "pt_history": ("🇵🇹", T("História do judo em Portugal", "Storia del judo in Portogallo", "History of judo in Portugal"),
                   ("pt_history",), None),
    "adapted": ("♿", T("Judo adaptado", "Judo adattato", "Adapted judo"), ("adapted",), None),
    "refereeing": ("⚖️", T("Arbitragem", "Arbitraggio", "Refereeing"), ("ref_basic", "ref_adv"), None),
    "fpj_rules": ("📘", T("Regulamentos da FPJ", "Regolamenti della FPJ", "FPJ regulations"), ("fpj_rules",), None),
    "first_aid": ("⛑️", T("Primeiros socorros", "Primo soccorso", "First aid"), ("first_aid",), None),
}
COACH1_MODULES = tuple(f"coach1-{key}" for key in COURSE_MODULES)

QUALIFICATIONS = {
    "REF_COURSE": ("🟨", T("Curso de arbitragem", "Corso di arbitraggio", "Refereeing course")),
    "REFEREE": ("🧑‍⚖️", T("Árbitro", "Arbitro", "Referee")),
    "COACH1": ("🎓", T("Treinador de Judo Grau I", "Allenatore di Judo 1° livello", "Judo Coach Level 1")),
}


def _exam(grade: str) -> Quiz:
    i = GRADES.index(grade)
    dan = DANS.index(grade) + 1 if grade in DANS else 0
    name = GRADE_NAMES[grade]
    if dan:
        title = T(f"Exame de {name['pt']}", f"Esame di {name['it']}", f"{name['en']} exam")
        desc = DAN_FOCUS[grade]
    else:
        title = T(f"Exame de cinto {name['pt'].lower()}", f"Esame di cintura {name['it'].lower()}", f"{name['en']} belt exam")
        desc = T("Passa no exame para subir de graduação e desbloquear o cinto no Judo Career.",
                 "Supera l'esame per salire di grado e sbloccare la cintura in Judo Career.",
                 "Pass the exam to move up a grade and unlock the belt in Judo Career.")
    # Più si sale, meno tempo e soglia più alta.
    seconds = 30 if i <= GRADES.index("BLUE_BROWN") else 28 if not dan else 26 if dan <= 3 else 24 if dan <= 6 else 22
    pass_pct = (70 if i <= GRADES.index("BLUE_BROWN") else 75 if not dan else 80 if dan <= 5 else 85 if dan <= 8 else 90)
    return Quiz(id=f"exam-{grade.lower()}", kind="EXAM", icon="🎖️", title=title, description=desc, belt=grade,
                size=EXAM_SIZES[grade], seconds=seconds, pass_pct=pass_pct, pass_xp=100 + 40 * i)


def _course(qid: str, icon: str, title: Text, desc: Text, topics: tuple, *, size: int, pass_pct: int, pass_xp: int,
            qualification: str | None, group: str | None, min_grade: str, requires: tuple = (), level_cap: str | None = None,
            seconds: int = 30) -> Quiz:
    return Quiz(id=qid, kind="COURSE", icon=icon, title=title, description=desc, topics=topics, size=size, seconds=seconds,
                pass_pct=pass_pct, pass_xp=pass_xp, qualification=qualification, group=group, min_grade=min_grade,
                requires=requires, level_cap=level_cap)


QUIZZES: dict[str, Quiz] = {
    **{
        f"topic-{key}": Quiz(id=f"topic-{key}", kind="TOPIC", icon=icon, title=title, description=desc, topic=key,
                             size=10, seconds=30, pass_pct=60)
        for key, (icon, title, desc) in TOPICS.items()
    },
    **{f"exam-{grade.lower()}": _exam(grade) for grade in GRADES[1:]},
    "course-ref-basic": _course(
        "course-ref-basic", "🟨", QUALIFICATIONS["REF_COURSE"][1],
        T("Gestos, pontuações, penalizações e tempos: o primeiro passo para arbitrar. Desde o cinto verde.",
          "Gesti, punteggi, penalità e tempi: il primo passo per arbitrare. Dalla cintura verde.",
          "Signals, scores, penalties and times: the first step to refereeing. From green belt."),
        ("ref_basic",), size=30, pass_pct=75, pass_xp=300, qualification="REF_COURSE", group="referee", min_grade="GREEN"),
    "course-referee": _course(
        "course-referee", "🧑‍⚖️", T("Curso de árbitro", "Corso per arbitro", "Referee course"),
        T("As regras da IJF a fundo, o CARE system e a mecânica do árbitro. Depois do curso de arbitragem.",
          "Le regole IJF a fondo, il CARE system e la meccanica dell'arbitro. Dopo il corso di arbitraggio.",
          "IJF rules in depth, the CARE system and referee mechanics. After the refereeing course."),
        ("ref_basic", "ref_adv"), size=50, pass_pct=80, pass_xp=600, qualification="REFEREE", group="referee",
        min_grade="BLUE", requires=("REF_COURSE",), seconds=28),
    **{
        f"coach1-{key}": _course(
            f"coach1-{key}", icon, title,
            T(f"Módulo do curso de Treinador de Judo Grau I. Passa os {len(COURSE_MODULES)} módulos para obter a qualificação.",
              f"Modulo del corso Allenatore di Judo 1° livello. Supera i {len(COURSE_MODULES)} moduli per la qualifica.",
              f"Module of the Judo Coach Level 1 course. Pass all {len(COURSE_MODULES)} modules to qualify."),
            topics, size=30, pass_pct=75, pass_xp=250, qualification=None, group="coach1", min_grade="BLACK", level_cap=cap)
        for key, (icon, title, topics, cap) in COURSE_MODULES.items()
    },
}


def questions_for(quiz: Quiz) -> list[Question]:
    """Le domande da cui pescare: quelle del tema; per un esame quelle dei
    temi di grado fino al suo livello; per un corso quelle dei suoi temi."""
    if quiz.kind == "TOPIC":
        return [q for q in QUESTIONS if q.topic == quiz.topic]
    if quiz.kind == "COURSE":
        cap = LEVELS.index(quiz.level_cap) if quiz.level_cap else len(LEVELS)
        return [q for q in QUESTIONS if q.topic in quiz.topics and LEVELS.index(q.belt) <= cap]
    level = LEVELS.index(grade_level(quiz.belt))
    return [q for q in QUESTIONS if q.topic in GRADE_TOPICS and LEVELS.index(q.belt) <= level]

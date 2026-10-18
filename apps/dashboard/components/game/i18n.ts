"use client";

import { useI18n } from "@/lib/i18n/provider";

// I testi di JAV Games (vetrina, Dojo Academy, classifica): un dizionario
// suo, separato dai messaggi del gestionale come i dati del gioco sono
// separati dai suoi (docs/games.md). Portoghese, italiano, inglese; le
// altre lingue ricadono su una di queste (gameLangIndex).

const D = {
  hubEyebrow: ["JAV Games", "JAV Games", "JAV Games"],
  hubTitle: ["Joga, aprende e sobe de nível", "Gioca, impara e sali di livello", "Play, learn and level up"],
  hubText: ["Prepara os exames de cinto, simula a tua carreira e compete na classificação com judocas de todos os clubes.",
    "Prepara gli esami di cintura, simula la tua carriera e sfida in classifica i judoka di tutti i club.",
    "Prepare your belt exams, simulate your career and climb the leaderboard with judokas from every club."],
  level: ["Nível", "Livello", "Level"],
  xp: ["XP", "XP", "XP"],
  rank: ["Posição", "Posizione", "Rank"],
  beltGame: ["Cinto no jogo", "Cintura nel gioco", "In-game belt"],
  apps: ["Os jogos", "I giochi", "The games"],
  play: ["Jogar", "Gioca", "Play"],
  soon: ["Em breve", "Presto", "Soon"],
  academyName: ["Dojo Academy", "Dojo Academy", "Dojo Academy"],
  academyTag: ["Questionários a tempo e exames de cinto", "Quiz a tempo ed esami di cintura", "Timed quizzes and belt exams"],
  academyText: ["Do cinto branco e amarelo ao 10.º Dan, com o programa da FPJ, e os cursos de árbitro e de treinador. Cada exame desbloqueia o cinto na tua carreira.",
    "Dalla cintura bianca e gialla al 10° Dan, con il programma della FPJ, e i corsi per arbitro e allenatore. Ogni esame sblocca la cintura nella tua carriera.",
    "From white-yellow belt to 10th Dan, following the FPJ programme, plus referee and coach courses. Every exam unlocks the belt in your career."],
  careerName: ["Judo Career", "Judo Career", "Judo Career"],
  careerTag: ["Simula a tua carreira e gere o teu clube", "Simula la tua carriera e gestisci il tuo club", "Simulate your career and run your club"],
  careerText: ["De cinto branco a treinador: treina, compete, torna-te árbitro, abre o teu clube e aprende como é difícil geri-lo.",
    "Da cintura bianca ad allenatore: allenati, gareggia, diventa arbitro, apri il tuo club e scopri quanto è difficile gestirlo.",
    "From white belt to coach: train, compete, become a referee, open your club and learn how hard it is to run."],
  leaderboard: ["Classificação", "Classifica", "Leaderboard"],
  everyone: ["Todos", "Tutti", "Everyone"],
  myClub: ["O meu clube", "Il mio club", "My club"],
  clubsCup: ["Clubes", "Club", "Clubs"],
  players: ["jogadores", "giocatori", "players"],
  you: ["tu", "tu", "you"],
  noPlayers: ["Ainda ninguém na classificação: sê o primeiro!", "Ancora nessuno in classifica: sii il primo!", "Nobody on the board yet: be the first!"],
  back: ["Voltar aos jogos", "Torna ai giochi", "Back to games"],
  disclaimer: ["Tudo o que acontece nos jogos é a fingir: os cintos e os clubes do jogo não são os verdadeiros.",
    "Tutto quello che succede nei giochi è finto: cinture e club del gioco non sono quelli veri.",
    "Everything in the games is make-believe: in-game belts and clubs aren't the real ones."],
  paths: ["Percursos", "Percorsi", "Paths"],
  exams: ["Exames de cinto", "Esami di cintura", "Belt exams"],
  questions: ["perguntas", "domande", "questions"],
  seconds: ["s por pergunta", "s a domanda", "s per question"],
  best: ["Recorde", "Record", "Best"],
  passed: ["Aprovado", "Superato", "Passed"],
  locked: ["Passa primeiro o exame anterior", "Prima supera l'esame precedente", "Pass the previous exam first"],
  start: ["Começar", "Inizia", "Start"],
  retry: ["Tentar de novo", "Riprova", "Try again"],
  ready: ["Pronto?", "Pronto?", "Ready?"],
  readyText: ["Cada pergunta tem tempo. Responde depressa para ganhar pontos de velocidade!",
    "Ogni domanda ha un tempo. Rispondi in fretta per i punti velocità!", "Every question is timed. Answer fast for speed points!"],
  question: ["Pergunta", "Domanda", "Question"],
  of: ["de", "di", "of"],
  timeUp: ["Tempo esgotado!", "Tempo scaduto!", "Time's up!"],
  right: ["Certo!", "Giusto!", "Correct!"],
  wrong: ["Errado", "Sbagliato", "Wrong"],
  next: ["Seguinte", "Avanti", "Next"],
  finish: ["Ver resultado", "Vedi il risultato", "See result"],
  streak: ["seguidas", "di fila", "in a row"],
  points: ["pontos", "punti", "points"],
  resultPassed: ["Aprovado!", "Superato!", "Passed!"],
  resultFailed: ["Quase! Treina e tenta outra vez", "Quasi! Allenati e riprova", "Almost! Practise and try again"],
  needed: ["Precisavas de", "Serviva il", "You needed"],
  xpEarned: ["XP ganhos", "XP guadagnati", "XP earned"],
  newBelt: ["Desbloqueaste o cinto", "Hai sbloccato la cintura", "You unlocked the belt"],
  levelUp: ["Subiste de nível!", "Sei salito di livello!", "Level up!"],
  noNewXp: ["Bate o teu recorde para ganhar mais XP.", "Batti il tuo record per guadagnare altri XP.", "Beat your best score to earn more XP."],
  backToAcademy: ["Voltar à Academy", "Torna all'Academy", "Back to the Academy"],
  error: ["Algo correu mal", "Qualcosa è andato storto", "Something went wrong"],
  randoriName: ["Randori do Clube", "Randori del Club", "Club Randori"],
  randoriTag: ["Desafia os amigos do teu clube", "Sfida gli amici del tuo club", "Challenge your club mates"],
  randoriText: ["Combate com os teus colegas de clube, simulado ou passo a passo: se ganhas, ficas com os pontos deles.",
    "Combatti con i compagni del tuo club, simulato o passo a passo: se vinci, prendi i loro punti.",
    "Fight your club mates, simulated or step by step: win and you take their points."],
  passbook: ["Caderneta do judoca", "Libretto del judoka", "Judoka record book"],
  currentGrade: ["Graduação atual", "Grado attuale", "Current grade"],
  gradeOf: ["Grau", "Grado", "Grade"],
  nextExam: ["Próximo exame", "Prossimo esame", "Next exam"],
  allGrades: ["Chegaste ao topo: 10.º Dan!", "Sei in cima: 10° Dan!", "You reached the top: 10th Dan!"],
  qualifications: ["Qualificações", "Qualifiche", "Qualifications"],
  tabGrades: ["Graduações", "Gradi", "Grades"],
  tabCourses: ["Cursos e qualificações", "Corsi e qualifiche", "Courses and qualifications"],
  tabPaths: ["Percursos de estudo", "Percorsi di studio", "Study paths"],
  kyuTitle: ["Kyu: cintos de cor", "Kyu: cinture colorate", "Kyu: coloured belts"],
  kyuText: ["Com os cintos intermédios da FPJ: cada exame tem mais 5 perguntas.",
    "Con le mezze cinture della FPJ: ogni esame ha 5 domande in più.", "With the FPJ half belts: each exam adds 5 questions."],
  danTitle: ["Dan: cinto preto, vermelho e branco, vermelho", "Dan: cintura nera, bianca e rossa, rossa", "Dan: black, red-and-white, red belt"],
  danText: ["Programa de kata da FPJ: Nage, Katame, Kime, Goshin-jutsu, Ju, Koshiki-no-kata e mais.",
    "Programma kata della FPJ: Nage, Katame, Kime, Goshin-jutsu, Ju, Koshiki-no-kata e oltre.",
    "FPJ kata programme: Nage, Katame, Kime, Goshin-jutsu, Ju, Koshiki-no-kata and more."],
  available: ["Disponível", "Disponibile", "Available"],
  nextBadge: ["Próximo", "Prossimo", "Next"],
  needGrade: ["Precisas de", "Serve", "Requires"],
  needQual: ["Precisas do", "Serve il", "Requires the"],
  refPath: ["Arbitragem", "Arbitraggio", "Refereeing"],
  refPathText: ["Do cinto verde: o curso de arbitragem; depois, com o azul, o curso de árbitro.",
    "Dalla verde: il corso di arbitraggio; poi, con la blu, il corso per arbitro.",
    "From green belt: the refereeing course; then, from blue, the referee course."],
  coachPath: ["Treinador de Judo Grau I", "Allenatore di Judo 1° livello", "Judo Coach Level 1"],
  coachPathText: ["Do 1.º Dan: 12 módulos de 30 perguntas. Passa todos para obter a qualificação.",
    "Dal 1° Dan: 12 moduli da 30 domande. Superali tutti per avere la qualifica.",
    "From 1st Dan: 12 modules of 30 questions. Pass all of them to qualify."],
  modulesDone: ["módulos aprovados", "moduli superati", "modules passed"],
  earned: ["Obtida", "Ottenuta", "Earned"],
  notYet: ["Ainda não", "Non ancora", "Not yet"],
  newQualification: ["Nova qualificação:", "Nuova qualifica:", "New qualification:"],
  examProgress: ["Progresso do exame", "Avanzamento dell'esame", "Exam progress"],
  statPassed: ["Exames aprovados", "Esami superati", "Exams passed"],
  statAverage: ["Média nos aprovados", "Media negli esami superati", "Average on passed exams"],
  statAttempts: ["Tentativas", "Tentativi", "Attempts"],
  statNext: ["Próximo objetivo", "Prossimo obiettivo", "Next goal"],
  beltRack: ["Os teus cintos", "Le tue cinture", "Your belts"],
  beltRackText: ["Toca num cinto para ver o programa e os teus resultados.", "Tocca una cintura per vedere il programma e i tuoi risultati.",
    "Tap a belt to see the programme and your results."],
  yourResults: ["Os teus resultados", "I tuoi risultati", "Your results"],
  passedOn: ["Aprovado em", "Superato il", "Passed on"],
  bestResult: ["Melhor resultado", "Miglior risultato", "Best result"],
  noAttempts: ["Ainda não tentaste este exame.", "Non hai ancora provato questo esame.", "You haven't tried this exam yet."],
  history: ["Últimas tentativas", "Ultimi tentativi", "Recent attempts"],
  passMark: ["mínimo", "minimo", "pass mark"],
  takeExam: ["Fazer o exame", "Fai l'esame", "Take the exam"],
  retakeExam: ["Repetir para melhorar", "Rifai per migliorare", "Retake to improve"],
  programme: ["Programa", "Programma", "Programme"],
  scrollLeft: ["Cintos anteriores", "Cinture precedenti", "Previous belts"],
  scrollRight: ["Cintos seguintes", "Cinture successive", "Next belts"],
  diplomaHint: ["O teu diploma (do jogo) está no Medalheiro da Academy.", "Il tuo diploma (del gioco) è nel Medagliere dell'Academy.",
    "Your (game) diploma is in the Academy medal case."],
  certificate: ["Certificado da Dojo Academy", "Attestato della Dojo Academy", "Dojo Academy certificate"],
  fullscreen: ["Ecrã inteiro", "Schermo intero", "Full screen"],
  exitFullscreen: ["Sair do ecrã inteiro", "Esci dallo schermo intero", "Exit full screen"],
} as const;

export type GameKey = keyof typeof D;

export const BELT_LABELS: Record<string, [string, string, string]> = {
  WHITE: ["Branco", "Bianca", "White"], YELLOW: ["Amarelo", "Gialla", "Yellow"], ORANGE: ["Laranja", "Arancione", "Orange"],
  GREEN: ["Verde", "Verde", "Green"], BLUE: ["Azul", "Blu", "Blue"], BROWN: ["Castanho", "Marrone", "Brown"], BLACK: ["Preto", "Nera", "Black"],
};

/** I gradi della Dojo Academy (app/game/content.py::GRADES): mezze cinture fino alla marrone, poi i dan. */
export const GRADE_LABELS: Record<string, [string, string, string]> = {
  ...BELT_LABELS,
  WHITE_YELLOW: ["Branco e amarelo", "Bianca e gialla", "White-yellow"],
  YELLOW_ORANGE: ["Amarelo e laranja", "Gialla e arancione", "Yellow-orange"],
  ORANGE_GREEN: ["Laranja e verde", "Arancione e verde", "Orange-green"],
  GREEN_BLUE: ["Verde e azul", "Verde e blu", "Green-blue"],
  BLUE_BROWN: ["Azul e castanho", "Blu e marrone", "Blue-brown"],
  BLACK: ["1.º Dan", "1° Dan", "1st Dan"],
  DAN2: ["2.º Dan", "2° Dan", "2nd Dan"], DAN3: ["3.º Dan", "3° Dan", "3rd Dan"], DAN4: ["4.º Dan", "4° Dan", "4th Dan"],
  DAN5: ["5.º Dan", "5° Dan", "5th Dan"], DAN6: ["6.º Dan", "6° Dan", "6th Dan"], DAN7: ["7.º Dan", "7° Dan", "7th Dan"],
  DAN8: ["8.º Dan", "8° Dan", "8th Dan"], DAN9: ["9.º Dan", "9° Dan", "9th Dan"], DAN10: ["10.º Dan", "10° Dan", "10th Dan"],
};

export const QUALIFICATION_LABELS: Record<string, { icon: string; label: [string, string, string] }> = {
  REF_COURSE: { icon: "🟨", label: ["Curso de arbitragem", "Corso di arbitraggio", "Refereeing course"] },
  REFEREE: { icon: "🧑‍⚖️", label: ["Árbitro", "Arbitro", "Referee"] },
  COACH1: { icon: "🎓", label: ["Treinador Grau I", "Allenatore 1° livello", "Coach Level 1"] },
};

export const BELT_COLORS: Record<string, string> = {
  WHITE: "#f8fafc", YELLOW: "#facc15", ORANGE: "#f97316", GREEN: "#16a34a", BLUE: "#2563eb", BROWN: "#78350f", BLACK: "#0a0a0a",
};

/** La lingua dei testi del gioco (pt, it, en): lo spagnolo legge il
 *  portoghese, francese, tedesco e ucraino l'inglese, come il backend
 *  (game/service.py::_lang). 0 = pt, 1 = it, 2 = en. */
export function gameLangIndex(locale: string): 0 | 1 | 2 {
  if (locale === "it") return 1;
  if (locale === "en" || locale === "fr" || locale === "de" || locale === "uk") return 2;
  return 0;
}

export const GAME_LANGS = ["pt", "it", "en"] as const;
export type GameLang = (typeof GAME_LANGS)[number];

/** Il tag Intl della lingua del gioco, per date e importi. */
export const GAME_INTL: Record<GameLang, string> = { pt: "pt-PT", it: "it-IT", en: "en-GB" };

export function useGameText() {
  const { locale } = useI18n();
  const i = gameLangIndex(locale);
  const g = (key: GameKey) => D[key][i];
  const belt = (code: string) => BELT_LABELS[code]?.[i] ?? code;
  const grade = (code: string) => GRADE_LABELS[code]?.[i] ?? code;
  const qualification = (code: string) => QUALIFICATION_LABELS[code]?.label[i] ?? code;
  const lang = GAME_LANGS[i];
  return { g, belt, grade, qualification, lang };
}

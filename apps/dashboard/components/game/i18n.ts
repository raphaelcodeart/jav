"use client";

import { useI18n } from "@/lib/i18n/provider";

// I testi di JAV Games (vetrina, Dojo Academy, classifica): un dizionario
// suo, separato dai messaggi del gestionale come i dati del gioco sono
// separati dai suoi (docs/games.md). Portoghese, italiano, inglese.

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
  academyText: ["História, etiqueta, técnicas, regras e vocabulário. Passa os exames para desbloquear os cintos da tua carreira.",
    "Storia, etichetta, tecniche, regole e vocabolario. Supera gli esami per sbloccare le cinture della tua carriera.",
    "History, etiquette, techniques, rules and vocabulary. Pass exams to unlock belts in your career."],
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
} as const;

export type GameKey = keyof typeof D;

export const BELT_LABELS: Record<string, [string, string, string]> = {
  WHITE: ["Branco", "Bianca", "White"], YELLOW: ["Amarelo", "Gialla", "Yellow"], ORANGE: ["Laranja", "Arancione", "Orange"],
  GREEN: ["Verde", "Verde", "Green"], BLUE: ["Azul", "Blu", "Blue"], BROWN: ["Castanho", "Marrone", "Brown"], BLACK: ["Preto", "Nera", "Black"],
};

export const BELT_COLORS: Record<string, string> = {
  WHITE: "#f8fafc", YELLOW: "#facc15", ORANGE: "#f97316", GREEN: "#16a34a", BLUE: "#2563eb", BROWN: "#78350f", BLACK: "#0a0a0a",
};

export function useGameText() {
  const { locale } = useI18n();
  const i = locale === "it" ? 1 : locale === "en" ? 2 : 0;
  const g = (key: GameKey) => D[key][i];
  const belt = (code: string) => BELT_LABELS[code]?.[i] ?? code;
  const lang = (["pt", "it", "en"] as const)[i];
  return { g, belt, lang };
}

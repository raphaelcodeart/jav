"use client";

import { useCallback } from "react";
import { gameLangIndex } from "@/components/game/i18n";
import { useI18n } from "@/lib/i18n/provider";

// I testi dei combattimenti (arena passo a passo, randori del club):
// pt, it, en come il resto del gioco; le altre lingue ricadono su una di
// queste (gameLangIndex). I nomi delle tecniche sono giapponesi ovunque.

const D = {
  hajime: ["Hajime!", "Hajime!", "Hajime!"],
  whatDo: ["O que fazes?", "Che cosa fai?", "What do you do?"],
  kind_DEF: ["🛡️ Defesa", "🛡️ Difesa", "🛡️ Defence"],
  kind_ATT: ["⚔️ Iniciativa", "⚔️ Iniziativa", "⚔️ Initiative"],
  kind_GRIP: ["✋ Kumi-kata", "✋ Kumi-kata", "✋ Kumi-kata"],
  kind_NW_TOP: ["🤼 Ne-waza, por cima", "🤼 Ne-waza, sopra", "🤼 Ne-waza, on top"],
  kind_NW_BOT: ["🆘 Ne-waza, por baixo", "🆘 Ne-waza, sotto", "🆘 Ne-waza, underneath"],
  attack: ["Ataque: {tech}", "Attacco: {tech}", "Attack: {tech}"],
  seconds: ["{n} s", "{n} s", "{n} s"],
  timeHint: ["Responde antes que acabe o tempo: hesitar custa caro.", "Rispondi prima che scada il tempo: esitare costa caro.", "Answer before time runs out: hesitating costs."],
  out_IPPON: ["IPPON!", "IPPON!", "IPPON!"],
  out_WAZA: ["WAZA-ARI!", "WAZA-ARI!", "WAZA-ARI!"],
  out_YUKO: ["YUKO!", "YUKO!", "YUKO!"],
  shidoMe: ["Shido para ti", "Shido a te", "Shido for you"],
  shidoOpp: ["Shido para {name}", "Shido a {name}", "Shido for {name}"],
  matte: ["Matte! Sem pontuação", "Matte! Nessun punteggio", "Matte! No score"],
  scoredBy: ["{name} pontua com {tech}", "{name} segna con {tech}", "{name} scores with {tech}"],
  youScored: ["Pontuaste com {tech}", "Hai segnato con {tech}", "You scored with {tech}"],
  q_BEST: ["✅ Ótima escolha", "✅ Scelta ottima", "✅ Great choice"],
  q_GOOD: ["👍 Boa escolha", "👍 Buona scelta", "👍 Good choice"],
  q_RISKY: ["🎲 Escolha arriscada", "🎲 Scelta rischiosa", "🎲 Risky choice"],
  q_BAD: ["❌ Escolha errada", "❌ Scelta sbagliata", "❌ Wrong choice"],
  worked: ["e resultou", "ed è riuscita", "and it worked"],
  failed: ["mas não resultou", "ma non è riuscita", "but it didn't work"],
  yourAnswer: ["A tua resposta", "La tua risposta", "Your answer"],
  why: ["Porquê", "Perché", "Why"],
  next: ["Continuar", "Avanti", "Continue"],
  seeResult: ["Ver resultado", "Vedi il risultato", "See result"],
  golden: ["Golden score", "Golden score", "Golden score"],
  you: ["Tu", "Tu", "You"],
  stamina: ["Fôlego", "Fiato", "Stamina"],
  health: ["Saúde", "Salute", "Health"],
  technique: ["Técnica", "Tecnica", "Technique"],
  strength: ["Força", "Forza", "Strength"],
  mind: ["Mental", "Testa", "Mind"],
  won: ["Venceste! 🎉", "Hai vinto! 🎉", "You won! 🎉"],
  lost: ["Perdeste… mas aprendeste!", "Hai perso… ma hai imparato!", "You lost… but you learned!"],
  reason_IPPON: ["por ippon", "per ippon", "by ippon"],
  reason_AWASETE: ["por dois waza-ari (awasete-waza-ari)", "per due waza-ari (awasete-waza-ari)", "by two waza-ari (awasete-waza-ari)"],
  reason_HANSOKU: ["por hansoku-make (3 shido)", "per hansoku-make (3 shido)", "by hansoku-make (3 shido)"],
  reason_TIME: ["aos pontos, no fim do tempo", "ai punti, a fine tempo", "on points at the end of time"],
  reason_GOLDEN: ["no golden score", "al golden score", "in golden score"],
  reason_DECISION: ["por decisão dos árbitros", "per decisione arbitrale", "by referees' decision"],
  reason_FORFEIT: ["por desistência (kiken)", "per abbandono (kiken)", "by withdrawal (kiken)"],
  pointsWon: ["+{n} pontos de randori", "+{n} punti randori", "+{n} randori points"],
  pointsLost: ["−{n} pontos de randori", "−{n} punti randori", "−{n} randori points"],
  close: ["Fechar", "Chiudi", "Close"],
  abandon: ["Desistir", "Abbandona", "Withdraw"],
  abandonConfirm: ["Desistir conta como derrota. Tens a certeza?", "Abbandonare conta come sconfitta. Sei sicuro?", "Withdrawing counts as a defeat. Are you sure?"],
  skip: ["Saltar ⏭", "Salta ⏭", "Skip ⏭"],
  lessons: ["O que aprendeste", "Che cosa hai imparato", "What you learned"],
  replay: ["Combate simulado", "Combattimento simulato", "Simulated fight"],
  error: ["Algo correu mal", "Qualcosa è andato storto", "Something went wrong"],
  retry: ["Tentar outra vez", "Riprova", "Try again"],
  // randori do clube
  r_eyebrow: ["Randori do Clube", "Randori del Club", "Club Randori"],
  r_title: ["Desafia os teus amigos do clube", "Sfida i tuoi amici del club", "Challenge your club mates"],
  r_points: ["pontos", "punti", "points"],
  r_position: ["#{n} no clube", "#{n} nel club", "#{n} in the club"],
  r_left: ["Desafios hoje: {n}/{max}", "Sfide oggi: {n}/{max}", "Challenges today: {n}/{max}"],
  r_myJudoka: ["O teu judoca", "Il tuo judoka", "Your judoka"],
  r_fromCareer: ["As estatísticas vêm da tua Judo Career: treina lá para ficares mais forte.", "Le statistiche vengono dalla tua Judo Career: allenati lì per diventare più forte.", "Your stats come from your Judo Career: train there to get stronger."],
  r_goCareer: ["Treinar na Judo Career", "Allenati in Judo Career", "Train in Judo Career"],
  r_injured: ["Estás lesionado: combates a {n}%.", "Sei infortunato: combatti al {n}%.", "You're injured: you fight at {n}%."],
  r_tired: ["Estás cansado: vais ter menos fôlego.", "Sei stanco: avrai meno fiato.", "You're tired: you'll have less stamina."],
  r_friends: ["Amigos do clube", "Amici del club", "Club mates"],
  r_noClub: ["Para o randori precisas de um clube: os teus colegas aparecem aqui quando também jogam.", "Per il randori serve un club: i tuoi compagni compaiono qui quando giocano anche loro.", "Randori needs a club: your club mates appear here when they play too."],
  r_noFriends: ["Ainda nenhum colega do teu clube joga. Convida-os para os JAV Games!", "Nessun compagno del tuo club gioca ancora. Invitali ai JAV Games!", "None of your club mates play yet. Invite them to JAV Games!"],
  r_edge_STRONGER: ["💪 Mais forte", "💪 Più forte", "💪 Stronger"],
  r_edge_EVEN: ["⚖️ Equilibrado", "⚖️ Alla pari", "⚖️ Even match"],
  r_edge_WEAKER: ["🌱 Menos forte", "🌱 Meno forte", "🌱 Weaker"],
  r_leftPair: ["{n} combates hoje", "{n} incontri oggi", "{n} fights left today"],
  r_noneLeft: ["Já combateram hoje", "Avete già combattuto oggi", "Already fought today"],
  r_challenge: ["Desafiar", "Sfida", "Challenge"],
  r_stakes: ["Ganhas +{win} · Perdes −{loss}", "Vinci +{win} · Perdi −{loss}", "Win +{win} · Lose −{loss}"],
  r_modeTitle: ["Randori com {name}", "Randori con {name}", "Randori with {name}"],
  r_modeText: ["Como queres combater?", "Come vuoi combattere?", "How do you want to fight?"],
  r_sim: ["🎬 Simulado", "🎬 Simulato", "🎬 Simulated"],
  r_simText: ["O combate decide-se com as vossas estatísticas e vês o filme, troca a troca.", "Il combattimento si decide con le vostre statistiche e lo guardi, scambio per scambio.", "The fight is decided by your stats and you watch it, exchange by exchange."],
  r_step: ["🧠 Passo a passo", "🧠 Passo a passo", "🧠 Step by step"],
  r_stepText: ["Tu decides cada ação e cada contra-ataque. As estatísticas também contam.", "Decidi tu ogni azione e ogni contrattacco. Contano anche le statistiche.", "You decide every action and counter. Stats count too."],
  r_active: ["Tens um combate a meio", "Hai un combattimento a metà", "You have a fight in progress"],
  r_activeText: ["Se não o acabares, conta como derrota.", "Se non lo finisci, conta come sconfitta.", "If you don't finish it, it counts as a defeat."],
  r_resume: ["Continuar", "Continua", "Resume"],
  r_board: ["Classificação do clube", "Classifica del club", "Club ranking"],
  r_history: ["Últimos combates", "Ultimi incontri", "Recent fights"],
  r_noHistory: ["Ainda sem combates. Desafia alguém!", "Ancora nessun incontro. Sfida qualcuno!", "No fights yet. Challenge someone!"],
  r_youChallenged: ["Desafiaste {name}", "Hai sfidato {name}", "You challenged {name}"],
  r_challengedYou: ["{name} desafiou-te", "{name} ti ha sfidato", "{name} challenged you"],
  r_wl: ["{w}V · {l}D", "{w}V · {l}S", "{w}W · {l}L"],
  r_rules: ["Até {pair} combates por dia com o mesmo amigo e {max} desafios por dia. Os pontos que ganhas são os que o teu amigo perde (mais se ele for mais forte). Quem desafias não precisa de estar ligado: combate com as suas estatísticas.",
    "Fino a {pair} incontri al giorno con lo stesso amico e {max} sfide al giorno. I punti che vinci sono quelli che perde il tuo amico (di più se è più forte). Chi sfidi non deve essere collegato: combatte con le sue statistiche.",
    "Up to {pair} fights a day with the same mate and {max} challenges a day. The points you win are the ones your mate loses (more if they're stronger). Whoever you challenge needn't be online: they fight with their stats."],
  r_review: ["Rever", "Rivedi", "Review"],
  r_hint: ["Escolhe um amigo e desafia-o para um randori.", "Scegli un amico e sfidalo a un randori.", "Pick a mate and challenge them to randori."],
} as const;

export type FightKey = keyof typeof D;
export type FightT = (key: FightKey, vars?: Record<string, string | number>) => string;

export function useFightT(): FightT {
  const i = gameLangIndex(useI18n().locale);
  return useCallback<FightT>((key, vars) => {
    let s: string = D[key][i];
    if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v));
    return s;
  }, [i]);
}

/** mm:ss del cronometro: il tempo che resta, o quello del golden score. */
export function clockText(clock: number, regulation: number, golden: boolean): string {
  const secs = golden ? Math.max(0, clock - regulation) : Math.max(0, regulation - clock);
  return `${golden ? "+" : ""}${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`;
}

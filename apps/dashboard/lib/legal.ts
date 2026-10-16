/** Chi risponde dei dati e del sito (docs/legal.md). JudoArteVida non è una
 *  società: è la rete dei tre club, coordinata da Matias Rosário Luwawa
 *  (persona singola, senza partita IVA). Il **responsabile del trattamento**
 *  della piattaforma e del sito è il Judo Clube de Lagos; ogni club è
 *  corresponsabile per i dati dei suoi soci (art. 26.º RGPD).
 *
 *  DA COMPLETARE: NIPC e sede legale completa del Judo Clube de Lagos (e
 *  degli altri due club). Finché un campo è null la pagina non lo mostra. */
export const LEGAL = {
  version: "2026-10-16",
  controller: {
    name: "Judo Clube de Lagos",
    nipc: null as string | null,
    address: "8600-614 Lagos, Portugal" as string,
    email: "info@judoartevida.com",
    phone: "+351 931 148 585",
  },
  coordinator: "Matias Rosário Luwawa",
  jointControllers: [
    { name: "Judo Clube de Lagos", city: "Lagos" },
    { name: "Judo Clube de Albufeira", city: "Albufeira" },
    { name: "Judo Team Matias Luwawa", city: "Alvor" },
  ],
  site: "jav.ecodo.ai",
  authority: { name: "Comissão Nacional de Proteção de Dados (CNPD)", url: "https://www.cnpd.pt" },
  disputes: { name: "Livro de Reclamações Eletrónico", url: "https://www.livroreclamacoes.pt" },
} as const;

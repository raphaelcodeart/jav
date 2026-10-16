import type { Metadata } from "next";
import Link from "next/link";
import { Controller, LegalPage } from "@/components/legal/legal-page";
import { LEGAL } from "@/lib/legal";

export const metadata: Metadata = {
  title: "Política de Privacidade · Judo Arte e Vida",
  description: "Como os clubes da rede JudoArteVida tratam os dados pessoais de atletas, famílias, treinadores e visitantes.",
};

/** La politica di privacy (RGPD, Lei 58/2019): l'analisi dei trattamenti è in
 *  docs/legal.md; qui il testo per chi legge. */
const ROWS: [string, string, string, string][] = [
  ["Conta de utilizador: email, nome de utilizador, palavra-passe (cifrada), idioma, aceitação dos termos", "Criar e gerir a conta, autenticação, segurança", "Execução do contrato (art. 6.º, n.º 1, b)", "Enquanto a conta existir; 5 anos após o fecho"],
  ["Dados do sócio e do encarregado de educação: nome, contactos, morada, NIF, documento de identificação", "Inscrição no clube, seguro desportivo, filiação na Federação Portuguesa de Judo e associação distrital", "Execução do contrato e obrigação legal (art. 6.º, n.º 1, b e c)", "Enquanto for sócio; 5 anos após a saída"],
  ["Atleta (também menor): nome, data de nascimento, sexo, peso, cinturão, escalão, grupo, presenças, provas e resultados, fotografia (se carregada)", "Gestão desportiva: aulas, graduações, inscrição em provas, ranking interno", "Execução do contrato; interesse legítimo na organização desportiva (art. 6.º, n.º 1, b e f)", "Enquanto for sócio; resultados desportivos como registo histórico"],
  ["Atestado médico desportivo (dado de saúde)", "Verificar a aptidão para a prática desportiva, exigida por lei", "Obrigação legal e medicina desportiva (art. 9.º, n.º 2, b e h; Lei 5/2007 e DL 345/99)", "Validade do atestado + 1 ano"],
  ["Judo adaptado (pode revelar informação de saúde)", "Adaptar treino e escalão", "Consentimento explícito do encarregado (art. 9.º, n.º 2, a)", "Enquanto for sócio"],
  ["Quotas, comprovativos de pagamento, recibos, carteira JavCash, encomendas da loja", "Cobrança, contabilidade, faturação", "Execução do contrato e obrigação legal fiscal (art. 6.º, n.º 1, b e c)", "10 anos (obrigações contabilísticas e fiscais)"],
  ["Ficha pública do judoca: «Nome I.», clube, cinturão, escalão, medalhas, resultados, pontos", "Divulgação desportiva no site e nas classificações", "Interesse legítimo (art. 6.º, n.º 1, f), com direito de oposição a qualquer momento", "Até à oposição ou à saída do clube"],
  ["Fotografia e vídeos do atleta no site público", "Divulgação do clube e do atleta", "Consentimento do encarregado de educação (art. 6.º, n.º 1, a; art. 8.º)", "Até à retirada do consentimento"],
  ["Cartas à escola e pedidos de transporte (nome, ano de nascimento, prova)", "Justificar faltas escolares e pedir transporte à câmara ou entidade", "Interesse legítimo do atleta e pedido da família (art. 6.º, n.º 1, f)", "Época desportiva + 1 ano"],
  ["Treinadores e equipa: registo de horas, tarifa, tarefas, mensagens, assinaturas de limpeza", "Gestão do trabalho e pagamentos", "Execução do contrato e obrigação legal (art. 6.º, n.º 1, b e c)", "10 anos (dados com relevância contabilística); mensagens 2 anos"],
  ["Mensagens do site (nome, email, telefone, mensagem, impressão do IP)", "Responder a pedidos e prevenir abusos", "Diligências pré-contratuais e interesse legítimo (art. 6.º, n.º 1, b e f)", "24 meses"],
  ["Conversas com o assistente JAVBOT", "Responder às perguntas na área reservada", "Execução do contrato (art. 6.º, n.º 1, b)", "90 dias de inatividade"],
  ["Registos de segurança: sessões, endereço IP, navegador, registo de auditoria das alterações", "Segurança, prevenção de fraude, prova de quem fez o quê", "Interesse legítimo (art. 6.º, n.º 1, f)", "Sessões 30 dias; auditoria 2 anos"],
  ["Rede de promotores e contratos: dados de identificação, IBAN, documentos KYC, comissões", "Gestão dos contratos e pagamento de comissões", "Execução do contrato e obrigação legal (art. 6.º, n.º 1, b e c)", "10 anos após o fim do contrato"],
  ["Jogos (JAV Games): nome de exibição, clube, pontos", "Jogos educativos e classificação dos jogos", "Execução do contrato (art. 6.º, n.º 1, b)", "Enquanto a conta existir"],
];

const PROCESSORS: [string, string, string][] = [
  ["Hetzner Online GmbH", "Alojamento do servidor, base de dados e ficheiros", "Alemanha (UE)"],
  ["Hostinger International Ltd.", "Envio de emails (servidor SMTP)", "Chipre (UE)"],
  ["Let's Encrypt (ISRG)", "Certificados de segurança HTTPS (sem dados pessoais dos utilizadores)", "EUA"],
  ["Anthropic, PBC (apenas se o assistente JAVBOT com IA for ativado)", "Responder às perguntas feitas ao assistente", "EUA, com cláusulas contratuais-tipo da Comissão Europeia"],
  ["Google LLC / YouTube e Vimeo", "Vídeos incorporados, só depois de aceitar os conteúdos de terceiros", "EUA (EU-US Data Privacy Framework)"],
  ["Federação Portuguesa de Judo, associação distrital, seguradora", "Filiação, licença desportiva e seguro obrigatório (destinatários, não subcontratantes)", "Portugal"],
];

export default function PrivacyPage() {
  const c = LEGAL.controller;
  return (
    <LegalPage
      title="Política de Privacidade"
      intro={<>
        <p>Esta política explica como são tratados os dados pessoais de quem usa o site e a plataforma <strong>JudoArteVida</strong> ({LEGAL.site}): atletas (também menores), encarregados de educação, treinadores, equipa dos clubes, promotores e visitantes. Cumpre o Regulamento (UE) 2016/679 (RGPD) e a Lei n.º 58/2019.</p>
        <p>«JudoArteVida» é o nome da rede de clubes de judo coordenada por {LEGAL.coordinator}; não é uma sociedade. Quem responde pelos dados são os clubes.</p>
      </>}
      sections={[
        { id: "responsavel", title: "Quem é o responsável pelo tratamento", body: <>
          <p>O responsável pelo tratamento da plataforma e do site é:</p>
          <Controller />
          <p>Cada clube da rede é <strong>responsável conjunto</strong> (art. 26.º do RGPD) pelos dados dos seus sócios, atletas e equipa: {LEGAL.jointControllers.map((j) => j.name).join(", ")}. Os clubes acordaram entre si quem faz o quê; o ponto de contacto único para qualquer pedido é o indicado acima, que encaminha para o clube certo.</p>
          <p>Não foi designado um encarregado da proteção de dados (não é obrigatório para estas entidades). Para qualquer questão: <a className="text-brand-700 underline" href={`mailto:${c.email}`}>{c.email}</a>.</p>
        </> },
        { id: "dados", title: "Que dados tratamos, para quê e por quanto tempo", body: <>
          <p>Tratamos apenas os dados necessários a cada finalidade. A tabela resume cada tratamento, a base legal (art. 6.º e 9.º do RGPD) e o prazo de conservação; terminado o prazo, os dados são apagados ou anonimizados.</p>
          <div className="overflow-x-auto rounded-2xl ring-1 ring-ink-900/10">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="bg-ink-50 text-xs uppercase tracking-wide text-ink-500">
                <tr><th className="p-3">Dados</th><th className="p-3">Finalidade</th><th className="p-3">Base legal</th><th className="p-3">Conservação</th></tr>
              </thead>
              <tbody className="divide-y divide-ink-100 bg-white">
                {ROWS.map((r) => <tr key={r[0]}>{r.map((c, i) => <td key={i} className="p-3 align-top">{c}</td>)}</tr>)}
              </tbody>
            </table>
          </div>
        </> },
        { id: "menores", title: "Dados de menores", body: <>
          <p>Os dados dos atletas com menos de 18 anos são fornecidos e geridos pelo <strong>encarregado de educação</strong> (o titular da conta). Um menor pode ter um acesso próprio à sua área (com nome de utilizador ou código QR criado pelo encarregado), mas não paga quotas, não carrega o atestado médico e não altera dados: esses passos são do encarregado.</p>
          <p>Para os serviços da sociedade da informação, a idade do consentimento em Portugal é de 13 anos (art. 16.º da Lei 58/2019); para o tratamento desportivo dos menores é sempre o encarregado quem decide.</p>
        </> },
        { id: "publico", title: "O que aparece no site público", body: <>
          <p>O desporto é público por natureza: classificações e resultados são publicados. Por isso, cada atleta dos clubes da rede aparece no site com a <strong>ficha desportiva</strong>: primeiro nome e inicial do apelido («Tiago M.»), clube, cinturão, escalão, medalhas, resultados e pontos do ranking. A base legal é o interesse legítimo dos clubes e dos atletas na divulgação desportiva.</p>
          <p><strong>Nunca</strong> aparecem: apelido completo, data de nascimento, peso, NIF, contactos, morada, dados da família, quotas, atestados ou qualquer dado de saúde.</p>
          <p><strong>Direito de oposição:</strong> o encarregado de educação (ou o atleta maior) pode opor-se a qualquer momento, na área reservada (ficha do atleta → «Site público JudoArteVida» → «Oponho-me»). A ficha e o nome desaparecem logo do site e das classificações.</p>
          <p>A <strong>fotografia</strong> e os vídeos do atleta só aparecem com o consentimento expresso do encarregado, dado na mesma ficha e retirável a qualquer momento.</p>
          <p>As páginas dos judocas não são indexadas pelos motores de busca.</p>
        </> },
        { id: "destinatarios", title: "Com quem partilhamos os dados", body: <>
          <p>Não vendemos nem cedemos dados para publicidade. Os dados são acessíveis apenas à secretaria e aos treinadores do clube do sócio, e à equipa técnica da plataforma para manutenção. Recorremos aos seguintes subcontratantes e destinatários:</p>
          <div className="overflow-x-auto rounded-2xl ring-1 ring-ink-900/10">
            <table className="w-full min-w-[560px] text-left text-sm">
              <thead className="bg-ink-50 text-xs uppercase tracking-wide text-ink-500"><tr><th className="p-3">Entidade</th><th className="p-3">Para quê</th><th className="p-3">Onde</th></tr></thead>
              <tbody className="divide-y divide-ink-100 bg-white">
                {PROCESSORS.map((r) => <tr key={r[0]}>{r.map((c, i) => <td key={i} className="p-3 align-top">{c}</td>)}</tr>)}
              </tbody>
            </table>
          </div>
          <p>Também recebem dados, quando o pedido parte da família ou é necessário: a escola do atleta (carta de justificação), a câmara municipal ou entidade que assegura o transporte para uma prova (nome e ano de nascimento dos atletas), os organizadores das provas em que o atleta é inscrito.</p>
          <p>As transferências para fora do Espaço Económico Europeu só acontecem com as garantias do capítulo V do RGPD (decisão de adequação ou cláusulas contratuais-tipo).</p>
        </> },
        { id: "direitos", title: "Os seus direitos", body: <>
          <p>Pode, a qualquer momento e sem custos: aceder aos seus dados; corrigi-los; pedir o apagamento; limitar o tratamento; opor-se ao tratamento baseado no interesse legítimo (incluindo a ficha pública); receber os dados num formato estruturado (portabilidade); retirar um consentimento dado (por exemplo, o da fotografia), sem afetar o tratamento feito antes.</p>
          <p>Muitas destas ações faz-se diretamente na área reservada (dados do perfil, ficha pública, fotografia). Para as outras, escreva para <a className="text-brand-700 underline" href={`mailto:${c.email}`}>{c.email}</a>: respondemos no prazo de um mês. Podemos pedir uma prova de identidade.</p>
          <p>Alguns dados não podem ser apagados enquanto a lei obrigar a guardá-los (por exemplo, os documentos contabilísticos, 10 anos).</p>
          <p>Tem também o direito de apresentar reclamação à <a className="text-brand-700 underline" href={LEGAL.authority.url} target="_blank" rel="noopener noreferrer">{LEGAL.authority.name}</a>.</p>
        </> },
        { id: "seguranca", title: "Segurança", body: <>
          <p>Ligação sempre cifrada (HTTPS); palavras-passe guardadas com hash; documentos privados (atestados, comprovativos, cartas) num armazenamento privado, abertos só com ligações temporárias de poucos minutos; acesso por perfis (família, atleta, treinador, secretaria); registo de auditoria de quem altera o quê; cópias de segurança diárias da base de dados, com rotação (até 6 meses).</p>
          <p>Em caso de violação de dados que represente um risco, notificamos a CNPD em 72 horas e, se o risco for elevado, as pessoas afetadas.</p>
        </> },
        { id: "cookies", title: "Cookies", body: <p>O site usa apenas cookies técnicos necessários e, só se aceitar, conteúdos de terceiros (vídeos). Os detalhes estão na <Link href="/cookies" className="text-brand-700 underline">Política de Cookies</Link>.</p> },
        { id: "decisoes", title: "Decisões automatizadas", body: <p>Não tomamos decisões com efeitos jurídicos baseadas apenas em tratamento automatizado. Cálculos automáticos (escalão pela idade federal, quotas, multa por atraso quando o clube a ativa, pontos do ranking) seguem regras fixas e conhecidas, e qualquer correção pode ser pedida à secretaria do clube.</p> },
        { id: "alteracoes", title: "Alterações a esta política", body: <p>Podemos atualizar esta política; a data da versão está no topo. Alterações importantes são comunicadas na área reservada ou por email.</p> },
      ]}
    />
  );
}

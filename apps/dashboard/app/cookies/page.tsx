import type { Metadata } from "next";
import { CookieSettingsButton } from "@/components/legal/cookie-settings-button";
import { LegalPage } from "@/components/legal/legal-page";

export const metadata: Metadata = {
  title: "Política de Cookies · Judo Arte e Vida",
  description: "Que cookies e armazenamento local usa o site JudoArteVida e como gerir a sua escolha.",
};

const ESSENTIAL: [string, string, string][] = [
  ["jav_session", "Mantém a sessão iniciada na área reservada (cifrado, só servidor)", "30 dias"],
  ["jav_refresh_token", "Renova a sessão de forma segura", "Sessão do navegador"],
  ["jav_lang", "Lembra o idioma escolhido", "1 ano"],
  ["jav_club", "Para a equipa da plataforma: o clube em que está a trabalhar", "Sessão do navegador"],
  ["jav_referral", "Liga uma inscrição ao promotor que a recomendou (o link que usou)", "30 dias"],
  ["jav_cookies", "Lembra a sua escolha sobre os cookies", "6 meses"],
];
const LOCAL: [string, string][] = [
  ["jav_course_pref", "O curso escolhido no site, para não o pedir outra vez"],
  ["jav-sidebar-collapsed", "Se o menu lateral está fechado"],
  ["jav.board.seen", "Que publicações do mural já viu"],
  ["javbot-public (sessão)", "A conversa com o assistente do site, até fechar o separador"],
];

function Table({ head, rows }: { head: string[]; rows: string[][] }) {
  return (
    <div className="overflow-x-auto rounded-2xl ring-1 ring-ink-900/10">
      <table className="w-full min-w-[520px] text-left text-sm">
        <thead className="bg-ink-50 text-xs uppercase tracking-wide text-ink-500"><tr>{head.map((h) => <th key={h} className="p-3">{h}</th>)}</tr></thead>
        <tbody className="divide-y divide-ink-100 bg-white">{rows.map((r) => <tr key={r[0]}>{r.map((c, i) => <td key={i} className="p-3 align-top">{i === 0 ? <code>{c}</code> : c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

export default function CookiesPage() {
  return (
    <LegalPage
      title="Política de Cookies"
      intro={<p>Os cookies são pequenos ficheiros guardados no navegador. O site JudoArteVida <strong>não usa cookies de publicidade nem de análise estatística</strong>. Usa só os cookies técnicos sem os quais o site não funciona e, se aceitar, conteúdos de outros sites (vídeos). A lei portuguesa (Lei n.º 41/2004, art. 5.º) dispensa o consentimento para os cookies estritamente necessários; para os outros pedimo-lo no primeiro acesso.</p>}
      sections={[
        { id: "necessarios", title: "Cookies estritamente necessários (sempre ativos)", body: <Table head={["Nome", "Para quê", "Duração"]} rows={ESSENTIAL} /> },
        { id: "local", title: "Armazenamento local do navegador", body: <>
          <p>Algumas preferências ficam só no seu navegador (localStorage e sessionStorage) e nunca são enviadas a terceiros:</p>
          <Table head={["Nome", "Para quê"]} rows={LOCAL} />
        </> },
        { id: "terceiros", title: "Conteúdos de terceiros (só com a sua aceitação)", body: <>
          <p>Os vídeos dos clubes e dos judocas estão no <strong>YouTube</strong> (em modo de privacidade reforçada, youtube-nocookie.com) e alguns no <strong>Vimeo</strong>. Ao carregar um vídeo ou a sua miniatura, o navegador liga-se a esses serviços, que recebem o seu endereço IP e podem guardar cookies próprios, segundo as suas políticas (Google e Vimeo). Também o vídeo de fundo da página inicial vem do YouTube.</p>
          <p>Enquanto não aceitar, no lugar dos vídeos aparece um quadro com o botão «Aceitar e ver»: nada é carregado desses sites. O mapa do clube (Google Maps) só abre se clicar nele.</p>
        </> },
        { id: "gerir", title: "Como gerir a sua escolha", body: <>
          <p>Pode mudar de ideias a qualquer momento: o botão abaixo (e a ligação «Gerir cookies» no fundo de cada página) volta a mostrar a escolha. Pode também apagar os cookies nas definições do navegador; nesse caso terá de iniciar sessão outra vez.</p>
          <CookieSettingsButton />
        </> },
      ]}
    />
  );
}

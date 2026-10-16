import type { Metadata } from "next";
import Link from "next/link";
import { Controller, LegalPage } from "@/components/legal/legal-page";
import { LEGAL } from "@/lib/legal";

export const metadata: Metadata = {
  title: "Termos e Condições · Judo Arte e Vida",
  description: "As regras de utilização do site e da plataforma JudoArteVida, da inscrição nos clubes e da loja dos parceiros.",
};

export default function TermsPage() {
  return (
    <LegalPage
      title="Termos e Condições"
      intro={<>
        <p>Estes termos regulam a utilização do site e da plataforma <strong>JudoArteVida</strong> ({LEGAL.site}): o site público, a área reservada de famílias, atletas e equipa, e a loja dos parceiros. Ao criar uma conta ou ao usar a plataforma aceita estes termos e a <Link href="/privacidade" className="text-brand-700 underline">Política de Privacidade</Link>.</p>
      </>}
      sections={[
        { id: "quem", title: "Quem somos", body: <>
          <p>«JudoArteVida» é a rede de clubes de judo {LEGAL.jointControllers.map((j) => j.name).join(", ")}, coordenada por {LEGAL.coordinator}. Não é uma sociedade comercial. A plataforma é disponibilizada por:</p>
          <Controller />
          <p>Cada clube é a entidade com quem o sócio tem a relação de inscrição: as quotas, as regras do clube e o seguro são do clube em que se inscreve.</p>
        </> },
        { id: "conta", title: "Conta e acesso", body: <>
          <p>A conta é pessoal. É responsável por manter a palavra-passe em segredo e pelos acessos que cria para os seus atletas (nome de utilizador, código QR). Os dados devem ser verdadeiros e atualizados. Os menores de 18 anos são inscritos e geridos pelo encarregado de educação.</p>
          <p>Podemos suspender uma conta usada de forma abusiva, para fraude ou contra estes termos, avisando o titular sempre que possível.</p>
        </> },
        { id: "inscricao", title: "Inscrição no clube e quotas", body: <>
          <p>A inscrição anual, as mensalidades, os descontos e as datas de pagamento são os do plano do clube, visíveis na área reservada antes de os aceitar. Os pagamentos fazem-se por transferência bancária ou MB WAY para o clube (com o comprovativo carregado na plataforma) ou em numerário na secretaria.</p>
          <p>Se o clube ativar os avisos de pagamento, as famílias são avisadas nos dias 1, 10 e 15 do mês; uma mensalidade ainda por pagar no dia 16 pode ter uma multa por atraso, com o valor indicado pelo clube. O atestado médico desportivo válido é obrigatório para treinar e competir.</p>
        </> },
        { id: "conduta", title: "Regras de utilização", body: <>
          <p>Não é permitido: usar a plataforma para fins ilícitos; carregar conteúdos ofensivos, falsos ou de terceiros sem autorização; tentar aceder a dados de outras pessoas; perturbar o funcionamento do serviço. Fotografias e vídeos carregados devem respeitar o direito à imagem das pessoas representadas.</p>
        </> },
        { id: "conteudos", title: "Conteúdos e propriedade intelectual", body: <>
          <p>Textos, logótipos, design e software da plataforma pertencem aos clubes da rede ou aos seus autores. Os conteúdos que carrega (fotografias, textos) continuam seus; concede ao clube a autorização para os usar na plataforma e, se o tiver escolhido, no site público, até a retirar.</p>
        </> },
        { id: "loja", title: "Loja dos parceiros e dos clubes", body: <>
          <p>A loja apresenta <strong>produtos dos nossos parceiros e amigos</strong> e produtos dos clubes. Comprar está reservado aos sócios dos clubes da rede, a partir da área reservada. Cada produto indica quem o vende; o preço inclui o IVA quando aplicável; portes e prazos de envio são mostrados antes da confirmação.</p>
          <p><strong>Direito de livre resolução:</strong> nas compras à distância, o consumidor pode desistir no prazo de <strong>14 dias</strong> a contar da receção do produto, sem indicar motivo (Decreto-Lei n.º 24/2014), salvo as exceções da lei (por exemplo, produtos alimentares ou suplementos selados abertos depois da entrega, por razões de saúde e higiene). Para exercer o direito, escreva para <a className="text-brand-700 underline" href={`mailto:${LEGAL.controller.email}`}>{LEGAL.controller.email}</a> indicando a encomenda; o reembolso é feito em até 14 dias após a devolução.</p>
          <p>Os produtos têm a garantia legal de conformidade de 3 anos (Decreto-Lei n.º 84/2021). Os suplementos alimentares não substituem uma alimentação variada; respeite a dose indicada e, no caso de menores, consulte um profissional de saúde.</p>
          <p>O crédito JavCash da carteira só pode ser usado na plataforma e não é convertível em dinheiro.</p>
        </> },
        { id: "responsabilidade", title: "Responsabilidade", body: <>
          <p>Fazemos o possível para manter a plataforma disponível e correta, mas não garantimos que esteja sempre livre de interrupções ou erros. Datas e informações das provas vêm dos organizadores: confirme sempre no regulamento oficial (circular) de cada prova.</p>
          <p>Nada nestes termos limita a responsabilidade que a lei não permite limitar, nem os direitos dos consumidores.</p>
        </> },
        { id: "reclamacoes", title: "Reclamações e litígios", body: <>
          <p>Pode apresentar uma reclamação através do <a className="text-brand-700 underline" href={LEGAL.disputes.url} target="_blank" rel="noopener noreferrer">{LEGAL.disputes.name}</a> ou escrever-nos. Em caso de litígio de consumo pode recorrer a uma entidade de resolução alternativa de litígios, por exemplo o Centro de Informação, Mediação e Arbitragem de Conflitos de Consumo do Algarve (CIMAAL, <a className="text-brand-700 underline" href="https://www.consumoalgarve.pt" target="_blank" rel="noopener noreferrer">www.consumoalgarve.pt</a>); mais informação no Portal do Consumidor (<a className="text-brand-700 underline" href="https://www.consumidor.gov.pt" target="_blank" rel="noopener noreferrer">www.consumidor.gov.pt</a>).</p>
        </> },
        { id: "lei", title: "Lei aplicável e alterações", body: <>
          <p>Estes termos regem-se pela lei portuguesa. Podemos atualizá-los; a data da versão está no topo e as alterações importantes são comunicadas na área reservada. A versão em português prevalece sobre qualquer tradução.</p>
        </> },
      ]}
    />
  );
}

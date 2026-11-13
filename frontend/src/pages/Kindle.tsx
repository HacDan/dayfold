import { get, post, type Settings } from "../api";
import { Loading, SectionTitle, useAction, useLoad } from "../components/ui";

export default function Kindle() {
  const { run } = useAction();
  const { data, reload } = useLoad(() => get<Settings>("/api/settings"));
  if (!data) return <Loading />;
  const token = data.values.distribution.feed_token;
  const origin = window.location.origin;
  const urls = {
    epub: `${origin}/feed/latest.epub?token=${token}`,
    json: `${origin}/feed/latest.json?token=${token}`,
    opds: `${origin}/opds?token=${token}`,
  };
  const pluginCfg = `return {\n    server = "${origin}",\n    token = "${token}",\n}`;
  return (
    <div>
      <SectionTitle kicker="Distribuição" title="Kindle e e-readers">
        <button className="btn danger" onClick={() => confirm("Gerar um novo token? Os aparelhos configurados precisarão do novo valor.") && run(() => post("/api/settings/distribution/rotate-token"), "Novo token gerado").then(reload)}>Trocar token</button>
      </SectionTitle>
      <div className="grid cols-2 col-rule">
        <section>
          <p className="kicker">1. KOReader + plugin Dayfold (recomendado)</p>
          <p className="small">O plugin baixa a edição do dia pelo Wi-Fi, abre o jornal, e no fim da leitura (ou ao tocar em “Jogar no KOReader”) abre os jogos interativos, guardando o progresso.</p>
          <p className="small">Copie a pasta <code>koreader/plugins/dayfold.koplugin</code> do repositório para <code>koreader/plugins/</code> no Kindle e crie <code>dayfold_config.lua</code> dentro dela:</p>
          <pre>{pluginCfg}</pre>
          <p className="small">Ou rode, a partir do repositório, com SSH no Kindle: <code>make kindle-install KINDLE=kindle</code>.</p>
        </section>
        <section>
          <p className="kicker">2. Catálogo OPDS</p>
          <p className="small">No KOReader: Busca › Catálogo OPDS › + e cole o endereço:</p>
          <pre>{urls.opds}</pre>
          <p className="kicker" style={{ marginTop: 18 }}>3. Download direto</p>
          <p className="small">Qualquer leitor de EPUB pode baixar a última edição (o token vai na URL ou como senha HTTP Basic):</p>
          <pre>{urls.epub}</pre>
          <p className="small">Metadados da edição para scripts: <code>{urls.json}</code></p>
        </section>
      </div>
      <hr className="rule thick" />
      <p className="kicker">Bateria e conexão</p>
      <p className="small" style={{ maxWidth: 820 }}>
        Todo o trabalho pesado acontece no servidor: o Kindle só baixa um EPUB pronto (imagens já em tons de cinza, fontes embutidas)
        e lê offline. O plugin liga o Wi-Fi apenas para sincronizar e não roda nada em segundo plano. O leitor nativo do Kindle não abre EPUB;
        por isso o caminho recomendado é o KOReader. A capa também é salva como PNG para uso como tela de descanso quando o jailbreak permitir.
      </p>
    </div>
  );
}

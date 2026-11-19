import { useState } from "react";
import { get, post, put, type KindleCfg, type Reader, type Settings } from "../api";
import { t } from "../i18n";
import { Field, Loading, SectionTitle, useAction, useLoad } from "../components/ui";

const APP_PASSWORDS = "https://myaccount.google.com/apppasswords";
const APPROVED_LIST = "https://www.amazon.com/hz/mycd/myx#/home/settings/pdoc";
const SEND_TO_KINDLE = "https://www.amazon.com/sendtokindle";

function KOReaderSetup({ token, origin }: { token: string; origin: string }) {
  const urls = {
    epub: `${origin}/feed/latest.epub?token=${token}`,
    json: `${origin}/feed/latest.json?token=${token}`,
    opds: `${origin}/opds?token=${token}`,
  };
  const pluginCfg = `return {\n    server = "${origin}",\n    token = "${token}",\n}`;
  return (
    <div className="grid cols-2 col-rule">
      <section>
        <p className="kicker">{t("1. KOReader + plugin Dayfold (recomendado)")}</p>
        <p className="small">{t("O plugin baixa a edição do dia pelo Wi-Fi, abre o jornal, e no fim da leitura (ou ao tocar em “Jogar no KOReader”) abre os jogos interativos, guardando o progresso.")}</p>
        <p className="small">{t("Copie a pasta")}{" "}<code>{t("koreader/plugins/dayfold.koplugin")}</code>{" "}{t("do repositório para")}{" "}<code>{t("koreader/plugins/")}</code>{" "}{t("no Kindle e crie")}{" "}<code>{t("dayfold_config.lua")}</code>{" "}{t("dentro dela:")}</p>
        <pre>{pluginCfg}</pre>
        <p className="small">{t("Ou rode, a partir do repositório, com SSH no Kindle:")}{" "}<code>{t("make kindle-install KINDLE=kindle")}</code>.</p>
      </section>
      <section>
        <p className="kicker">{t("2. Catálogo OPDS")}</p>
        <p className="small">{t("No KOReader: Busca › Catálogo OPDS › + e cole o endereço:")}</p>
        <pre>{urls.opds}</pre>
        <p className="kicker" style={{ marginTop: 18 }}>{t("3. Download direto")}</p>
        <p className="small">{t("Qualquer leitor de EPUB pode baixar a última edição (o token vai na URL ou como senha HTTP Basic):")}</p>
        <pre>{urls.epub}</pre>
        <p className="small">{t("Metadados da edição para scripts:")}{" "}<code>{urls.json}</code></p>
      </section>
    </div>
  );
}

function NativeSetup({ cfg, token, origin, onSaved }: { cfg: KindleCfg; token: string; origin: string; onSaved: () => void }) {
  const { run, busy } = useAction();
  const [form, setForm] = useState({ kindle_email: cfg.kindle_email, gmail_address: cfg.gmail_address, gmail_app_password: "", auto_send: cfg.auto_send });
  const save = () => run(() => put("/api/settings/kindle", form), t("Envio por e-mail salvo")).then((r) => { if (r) { setForm({ ...form, gmail_app_password: "" }); onSaved(); } });
  const setGames = (v: boolean) => run(() => put("/api/settings/kindle", { native_games: v }), v ? t("Jogos incluídos na versão Kindle") : t("Jogos removidos da versão Kindle")).then(onSaved);
  const sendLatest = () => run(() => post<{ message: string }>("/api/kindle/send"), t("Edição enviada ao Kindle")).then(onSaved);
  const test = (send: boolean) => run(() => post<{ download: string }>("/api/kindle/test", { send }), send ? t("Edição de teste enviada ao Kindle") : undefined)
    .then((r) => { if (r && !send) window.location.href = r.download; onSaved(); });
  const configured = Boolean(cfg.kindle_email && cfg.gmail_address && cfg.gmail_app_password_set);
  const phoneUrl = `${origin}/feed/latest.kindle.epub?token=${token}`;
  return (
    <div>
      <div className="clip ruled" style={{ marginBottom: 22 }}>
        <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
          <div style={{ maxWidth: 720 }}>
            <p className="kicker">{t("Passatempos na versão Kindle")}</p>
            {cfg.native_games ? (
              <p className="small" style={{ margin: 0 }}>{t("Incluídos, sem os jogos interativos do KOReader: Sudoku, Caça-palavras e Palavras Cruzadas para resolver de cabeça, Palavra do Dia com palpites de bolso, e soluções só depois da página “Respostas a seguir”.")}</p>
            ) : (
              <p className="small" style={{ margin: 0 }}><strong>{t("Esta versão não possui jogos.")}</strong>{" "}{t("Use esta opção se, no seu aparelho, as soluções aparecerem ao virar as páginas da edição de teste.")}</p>
            )}
          </div>
          <div className="row" role="group" aria-label={t("Passatempos na versão Kindle")}>
            <button className={`btn${!cfg.native_games ? " primary" : ""}`} aria-pressed={!cfg.native_games} onClick={() => setGames(false)}>{t("Sem jogos")}</button>
            <button className={`btn${cfg.native_games ? " primary" : ""}`} aria-pressed={cfg.native_games} onClick={() => setGames(true)}>{t("Com jogos")}</button>
          </div>
        </div>
      </div>

      <div className="grid cols-2 col-rule">
        <section>
          <p className="kicker">{t("1. Enviar pelo Gmail (automático)")}</p>
          <p className="small">{t("O servidor envia o EPUB para o endereço Send to Kindle do seu aparelho, usando a sua conta Gmail. A Amazon converte o arquivo e entrega pelo Wi-Fi, na seção Documentos.")}</p>
          <ol className="small" style={{ paddingLeft: 18 }}>
            <li>{t("Ative a verificação em duas etapas no Google e crie uma senha de app em")}{" "}<a href={APP_PASSWORDS} target="_blank" rel="noreferrer">myaccount.google.com/apppasswords</a>.</li>
            <li>{t("Na Amazon, em Conteúdo e dispositivos › Preferências › Configurações de documentos pessoais, adicione o seu Gmail à lista de e-mails aprovados e copie o endereço @kindle.com do aparelho.")}{" "}<a href={APPROVED_LIST} target="_blank" rel="noreferrer">{t("Abrir na Amazon")}</a></li>
          </ol>
          <div className="grid cols-2" style={{ gap: 12 }}>
            <Field label={t("E-mail do Kindle")}>
              <input type="email" placeholder="nome_123@kindle.com" value={form.kindle_email} onChange={(e) => setForm({ ...form, kindle_email: e.target.value })} />
            </Field>
            <Field label={t("Seu Gmail")}>
              <input type="email" placeholder="voce@gmail.com" value={form.gmail_address} onChange={(e) => setForm({ ...form, gmail_address: e.target.value })} />
            </Field>
          </div>
          <Field label={t("Senha de app do Gmail")} hint={cfg.gmail_app_password_set ? t("Senha salva. Deixe em branco para manter.") : t("16 letras; os espaços são ignorados. Não é a senha normal da conta.")}>
            <input type="password" autoComplete="new-password" placeholder={cfg.gmail_app_password_set ? "••••••••••••••••" : "abcd efgh ijkl mnop"} value={form.gmail_app_password} onChange={(e) => setForm({ ...form, gmail_app_password: e.target.value })} />
          </Field>
          <label className="check"><input type="checkbox" checked={form.auto_send} onChange={(e) => setForm({ ...form, auto_send: e.target.checked })} />{" "}{t("Enviar automaticamente cada edição nova")}</label>
          <div className="row">
            <button className="btn primary" disabled={busy} onClick={save}>{t("Salvar")}</button>
            <button className="btn" disabled={busy || !configured} onClick={sendLatest}>{t("Enviar a última edição agora")}</button>
          </div>
          {cfg.last_send_at && (
            <p className="small" style={{ marginTop: 12 }}>
              <strong>{cfg.last_send_ok ? t("Último envio:") : t("Último envio falhou:")}</strong>{" "}{cfg.last_send_at} · {cfg.last_send_message}
            </p>
          )}
        </section>
        <section>
          <p className="kicker">{t("2. Edição de teste")}</p>
          <p className="small">{t("A última edição com todos os jogos cadastrados e uma página com o que conferir no aparelho: se as soluções ficam escondidas ao virar as páginas, se os links das dicas e soluções funcionam e se as grades aparecem inteiras.")}</p>
          <div className="row">
            <button className="btn" disabled={busy || !configured} onClick={() => test(true)}>{t("Enviar teste ao Kindle")}</button>
            <button className="btn" disabled={busy} onClick={() => test(false)}>{t("Baixar teste")}</button>
          </div>
          <p className="kicker" style={{ marginTop: 22 }}>{t("3. Envio manual")}</p>
          <p className="small">{t("Baixe o EPUB e envie pelo site Send to Kindle, pelo app Send to Kindle (Windows e macOS) ou pelo app Kindle no celular (Compartilhar › Kindle). Copiar o EPUB por USB não funciona: o leitor do Kindle não abre EPUB.")}</p>
          <div className="row">
            <a className="btn" href="/api/kindle/latest.epub">{t("Baixar EPUB para Kindle")}</a>
            <a className="btn" href={SEND_TO_KINDLE} target="_blank" rel="noreferrer">{t("Abrir Send to Kindle")}</a>
          </div>
          <p className="small" style={{ marginTop: 12 }}>{t("Endereço para abrir no celular e compartilhar com o app Kindle:")}</p>
          <pre>{phoneUrl}</pre>
        </section>
      </div>
    </div>
  );
}

export default function Kindle() {
  const { run } = useAction();
  const { data, reload } = useLoad(() => get<Settings>("/api/settings"));
  const { data: readers, reload: reloadReaders } = useLoad(() => get<Reader[]>("/api/readers"));
  const [readerId, setReaderId] = useState<number | null>(null);
  if (!data || !readers?.length) return <Loading />;
  const reader = readers.find((r) => r.id === readerId) ?? readers[0];
  const token = reader.token;
  const cfg = data.values.kindle;
  const origin = window.location.origin;
  const setMode = (mode: KindleCfg["mode"]) => run(() => put("/api/settings/kindle", { mode })).then(reload);
  const rotate = () => confirm(t("Gerar um novo token? Os aparelhos configurados precisarão do novo valor."))
    && run(() => post(`/api/readers/${reader.id}/rotate-token`), t("Novo token gerado")).then(reloadReaders);
  return (
    <div>
      <SectionTitle kicker={t("Distribuição")} title={t("Kindle e e-readers")}>
        <button className="btn danger" onClick={rotate}>{t("Trocar token")}</button>
      </SectionTitle>
      <div className="clip ruled" style={{ marginBottom: 22 }}>
        <div className="grid cols-2" style={{ gap: 14 }}>
          <Field label={t("Leitor")} hint={t("Cada leitor tem o próprio endereço e a própria agenda na capa.")}>
            <select value={reader.id} onChange={(e) => setReaderId(Number(e.target.value))}>
              {readers.map((r) => <option key={r.id} value={r.id}>{r.name || t("Sem nome")}</option>)}
            </select>
          </Field>
        </div>
        {readers.length > 1 && cfg.mode === "native" && (
          <p className="small muted" style={{ margin: 0 }}>{t("O envio automático manda o jornal do primeiro leitor para o endereço configurado; os demais baixam pelo próprio endereço acima.")}</p>
        )}
      </div>
      <div className="clip ruled" style={{ marginBottom: 22 }}>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div>
            <p className="kicker">{t("Seu Kindle")}</p>
            <p className="small muted" style={{ margin: 0 }}>
              {cfg.mode === "koreader"
                ? t("Com jailbreak: KOReader e o plugin Dayfold, com jogos interativos.")
                : t("Sem jailbreak: o EPUB vai pelo Send to Kindle da Amazon e abre no leitor nativo, sem jogos interativos.")}
            </p>
          </div>
          <div className="row" role="group" aria-label={t("Seu Kindle")}>
            <button className={`btn${cfg.mode === "koreader" ? " primary" : ""}`} aria-pressed={cfg.mode === "koreader"} onClick={() => setMode("koreader")}>{t("Com jailbreak")}</button>
            <button className={`btn${cfg.mode === "native" ? " primary" : ""}`} aria-pressed={cfg.mode === "native"} onClick={() => setMode("native")}>{t("Sem jailbreak")}</button>
          </div>
        </div>
      </div>
      {cfg.mode === "koreader"
        ? <KOReaderSetup token={token} origin={origin} />
        : <NativeSetup cfg={cfg} token={token} origin={origin} onSaved={reload} />}
      <hr className="rule thick" />
      <p className="kicker">{t("Bateria e conexão")}</p>
      <p className="small" style={{ maxWidth: 820 }}>
        {cfg.mode === "koreader"
          ? t("Todo o trabalho pesado acontece no servidor: o Kindle só baixa um EPUB pronto (imagens já em tons de cinza, fontes embutidas) e lê offline. O plugin liga o Wi-Fi apenas para sincronizar e não roda nada em segundo plano. O leitor nativo do Kindle não abre EPUB; por isso o caminho recomendado é o KOReader. A capa também é salva como PNG para uso como tela de descanso quando o jailbreak permitir.")
          : t("Todo o trabalho pesado acontece no servidor. A Amazon converte o EPUB e o entrega quando o Kindle estiver no Wi-Fi; a edição fica também na nuvem, em Documentos, e sincroniza com os apps Kindle.")}
      </p>
    </div>
  );
}

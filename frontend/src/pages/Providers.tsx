import { useState } from "react";
import { t } from "../i18n";
import { Link, useNavigate } from "react-router-dom";
import { get, getFresh, post, put, fmtDateTime, topicLabel, USAGE_LABEL, type Provider, type Topic } from "../api";
import { Empty, Field, Loading, Modal, OptionalNumber, SectionTitle, Stamp, useAction, useLoad } from "../components/ui";

 /** Toggle chips for the provider's sections; the first selected one is the primary. */
function SectionPicker({ value, onChange, topics }: { value: string[]; onChange: (v: string[]) => void; topics: Topic[] | null }) {
  if (!topics) return null;
  const known = new Set(topics.map((tp) => tp.slug));
  const extra = value.filter((v) => !known.has(v)); // sections deleted since: keep them visible, readable
  const toggle = (slug: string) =>
    onChange(value.includes(slug) ? value.filter((v) => v !== slug) : [...value, slug]);
  return (
    <div className="chips" role="group">
      {[...topics.map((tp) => ({ slug: tp.slug, name: tp.name, off: !tp.enabled })), ...extra.map((x) => ({ slug: x, name: topicLabel(topics, x), off: true }))].map((c) => (
        <button key={c.slug} type="button" className={`chip${value.includes(c.slug) ? " on" : ""}${c.off ? " off" : ""}`}
          aria-pressed={value.includes(c.slug)} onClick={() => toggle(c.slug)}>
          {c.name}{value[0] === c.slug && value.length > 1 ? " ★" : ""}
        </button>
      ))}
    </div>
  );
}

export function ProviderForm({ initial, onSubmit, creating }: {
  initial?: Partial<Provider>; creating?: boolean;
  onSubmit: (body: Record<string, unknown>) => void;
}) {
  const [f, setF] = useState({
    name: initial?.name ?? "", base_url: initial?.base_url ?? "",
    categories: initial?.categories?.length ? initial.categories : initial?.category ? [initial.category] : [],
    language: initial?.language ?? "pt", usage_mode: initial?.usage_mode ?? "excerpt_and_link",
    license_name: initial?.license_name ?? "Verificar termos", license_url: initial?.license_url ?? "",
    license_note: initial?.license_note ?? "", enabled: initial?.enabled ?? true, max_items: initial?.max_items ?? 15,
    max_words: initial?.max_words ?? null, max_paragraphs: initial?.max_paragraphs ?? null,
  });
  const [mode, setMode] = useState<"assisted" | "manual">("assisted");
  const [strategy, setStrategy] = useState("rss");
  const [feedUrl, setFeedUrl] = useState("");
  const [specJson, setSpecJson] = useState('{\n  "list_url": "",\n  "item_selector": "article",\n  "link_selector": "a"\n}');
  const [useAi, setUseAi] = useState(true);
  const [prompt, setPrompt] = useState("");
  // Fetched once per form, uncached: a section renamed or added since the page loaded shows here.
  const { data: topics } = useLoad(() => getFresh<Topic[]>("/api/topics"));
  const set = (k: string, v: unknown) => setF((p) => ({ ...p, [k]: v }));

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!f.categories.length) { alert(t("Escolha ao menos uma seção.")); return; }
    const body: Record<string, unknown> = { ...f, license_url: f.license_url || null };
    if (creating) {
      body.mode = mode;
      if (mode === "manual") {
        body.strategy = strategy;
        if (strategy === "rss") body.spec = { feed_url: feedUrl };
        else if (strategy === "generic") body.spec = { list_url: feedUrl || f.base_url };
        else {
          try { body.spec = JSON.parse(specJson); } catch { alert(t("Spec JSON inválida")); return; }
        }
      } else {
        body.use_ai = useAi;
        body.extra_prompt = prompt || null;
      }
    }
    onSubmit(body);
  };

  return (
    <form onSubmit={submit}>
      <div className="grid cols-2" style={{ gap: 16 }}>
        <Field label={t("Nome")}><input type="text" required value={f.name} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label={t("URL base")}><input type="url" required value={f.base_url} onChange={(e) => set("base_url", e.target.value)} placeholder={t("https://...")} /></Field>
        <Field label={t("Seções")} hint={t("Uma ou mais. Cada matéria vai para a seção que mais combina com ela; ★ marca a principal.")}>
          <SectionPicker value={f.categories} onChange={(v) => set("categories", v)} topics={topics} />
        </Field>
        <Field label={t("Idioma")}>
          <select value={f.language} onChange={(e) => set("language", e.target.value)}>
            <option value="pt">{t("Português")}</option><option value="en">{t("Inglês")}</option><option value="es">{t("Espanhol")}</option>
          </select>
        </Field>
        <Field label={t("Modo de uso do conteúdo")} hint={t("Na dúvida, use excerto + link. Texto integral só com licença clara.")}>
          <select value={f.usage_mode} onChange={(e) => set("usage_mode", e.target.value)}>
            {Object.entries(USAGE_LABEL).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}
          </select>
        </Field>
        <Field label={t("Máximo de itens por coleta")}><input type="number" min={1} max={50} value={f.max_items} onChange={(e) => set("max_items", Number(e.target.value))} /></Field>
        {f.usage_mode === "full_content_allowed" && (
          <Field label={t("Tamanho máximo das matérias")} hint={t("Vazio usa o limite da seção ou do jornal. Cortadas terminam com o link para a fonte.")}>
            <div className="row" style={{ flexWrap: "nowrap" }}>
              <OptionalNumber value={f.max_words} min={50} max={5000} placeholder={t("palavras")} label={t("Máximo de palavras por matéria")} onChange={(v) => set("max_words", v)} />
              <OptionalNumber value={f.max_paragraphs} min={1} max={100} placeholder={t("parágrafos")} label={t("Máximo de parágrafos por matéria")} onChange={(v) => set("max_paragraphs", v)} />
            </div>
          </Field>
        )}
        <Field label={t("Licença / política observada")}><input type="text" value={f.license_name} onChange={(e) => set("license_name", e.target.value)} /></Field>
        <Field label={t("URL da licença ou termos")}><input type="url" value={f.license_url ?? ""} onChange={(e) => set("license_url", e.target.value)} /></Field>
      </div>
      <Field label={t("Notas sobre a licença")}><textarea value={f.license_note} onChange={(e) => set("license_note", e.target.value)} /></Field>
      <label className="check"><input type="checkbox" checked={f.enabled} onChange={(e) => set("enabled", e.target.checked)} />{" "}{t("Provedor ativo")}</label>

      {creating && (
        <fieldset>
          <legend>{t("Scraper")}</legend>
          <div className="tabs">
            <button type="button" className={mode === "assisted" ? "active" : ""} onClick={() => setMode("assisted")}>{t("Assistido")}</button>
            <button type="button" className={mode === "manual" ? "active" : ""} onClick={() => setMode("manual")}>{t("Manual")}</button>
          </div>
          {mode === "assisted" ? (
            <>
              <p className="small">{t("O Dayfold procura um feed RSS/Atom, depois tenta a extração genérica e, se nada passar no teste, pede à IA um scraper declarativo (seletores CSS).")}</p>
              <label className="check"><input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} />{" "}{t("Usar IA se o automático falhar")}</label>
              <Field label={t("Instruções extras para a IA (opcional)")} hint={t("Com instruções, o Dayfold vai direto para a IA.")}>
                <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder={t("Ex.: use só a seção de economia")} />
              </Field>
            </>
          ) : (
            <>
              <Field label={t("Estratégia")}>
                <select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
                  <option value="rss">{t("RSS / Atom")}</option>
                  <option value="generic">{t("Extração genérica (links + Trafilatura)")}</option>
                  <option value="selectors">{t("Seletores CSS")}</option>
                </select>
              </Field>
              {strategy !== "selectors" ? (
                <Field label={strategy === "rss" ? t("URL do feed") : t("URL da listagem (vazio = URL base)")}>
                  <input type="url" value={feedUrl} onChange={(e) => setFeedUrl(e.target.value)} required={strategy === "rss"} />
                </Field>
              ) : (
                <Field label={t("Spec (JSON)")} hint={t("Campos: list_url, item_selector, link_selector, article {title, subtitle, author, date, body, image}")}>
                  <textarea style={{ fontFamily: "monospace", minHeight: 140 }} value={specJson} onChange={(e) => setSpecJson(e.target.value)} />
                </Field>
              )}
            </>
          )}
        </fieldset>
      )}
      <button className="btn primary" type="submit">{creating ? t("Adicionar provedor") : t("Salvar")}</button>
    </form>
  );
}

export default function Providers() {
  const nav = useNavigate();
  const { run } = useAction();
  const { data, reload } = useLoad(() => get<Provider[]>("/api/providers"), [], (d) =>
    d?.some((p) => ["GENERATING", "TESTING", "PENDING"].includes(p.latest_status ?? "")) ? 3000 : 20000);
  const { data: topics } = useLoad(() => getFresh<Topic[]>("/api/topics"));
  const [adding, setAdding] = useState(false);
  if (!data) return <Loading />;

  const toggle = (p: Provider) => run(() => put(`/api/providers/${p.id}`, { ...p, enabled: !p.enabled }), p.enabled ? t("Provedor desativado") : t("Provedor ativado")).then(reload);

  return (
    <div>
      <SectionTitle kicker={t("Fontes")} title={t("Provedores")}>
        <button className="btn primary" onClick={() => setAdding(true)}>{t("Adicionar provedor")}</button>
      </SectionTitle>
      <p className="small muted" style={{ maxWidth: 760 }}>
        {t("O Dayfold só publica o que o modo de uso permite:")}{" "}<strong>{t("texto integral")}</strong>{" "}{t("para fontes com licença aberta clara,")}
        {" "}<strong>{t("excerto + link")}</strong>{" "}{t("quando a licença é incerta, e")}{" "}<strong>{t("só metadados")}</strong>{" "}{t("quando nem o excerto é seguro. Confira os termos de cada fonte que você habilitar.")}
      </p>
      {data.length === 0 && <Empty>{t("Nenhum provedor.")}</Empty>}
      <div className="table-wrap">
        <table className="ledger">
          <thead><tr><th>{t("Provedor")}</th><th>{t("Seções")}</th><th>{t("Uso")}</th><th>{t("Scraper")}</th><th>{t("Última coleta")}</th><th></th></tr></thead>
          <tbody>
            {data.map((p) => (
              <tr key={p.id} style={{ opacity: p.enabled ? 1 : 0.55 }}>
                <td>
                  <Link to={`/provedores/${p.id}`} className="name" style={{ textDecoration: "none" }}>{p.name}</Link>
                  <div className="small muted">{p.license_name} · {p.language.toUpperCase()}</div>
                </td>
                <td className="small">{(p.categories?.length ? p.categories : [p.category]).map((s) => topicLabel(topics, s)).join(", ")}</td>
                <td className="small">{t(USAGE_LABEL[p.usage_mode] ?? p.usage_mode)}</td>
                <td>
                  {p.active_version ? <><Stamp status={p.active_version.status} /> <span className="small muted">v{p.active_version.version} · {p.active_version.strategy}</span></> : <Stamp status="off" label={t("sem scraper")} />}
                  {p.latest_status && p.latest_version !== p.active_version?.version && (
                    <div className="small" style={{ marginTop: 4 }}>v{p.latest_version}: <Stamp status={p.latest_status} /></div>
                  )}
                </td>
                <td className="small">
                  {p.last_run_at ? <>{p.last_run_ok ? <Stamp status="ok" label={t("{n} itens", { n: p.last_run_count ?? 0 })} /> : <Stamp status="bad" label={t("falhou")} />} <span className="muted">{fmtDateTime(p.last_run_at)}</span></> : <span className="muted">{t("nunca")}</span>}
                </td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <button className="btn small" onClick={() => toggle(p)}>{p.enabled ? t("Desativar") : t("Ativar")}</button>{" "}
                  <Link className="btn small" to={`/provedores/${p.id}`}>{t("Abrir")}</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {adding && (
        <Modal title={t("Novo provedor")} onClose={() => setAdding(false)}>
          <ProviderForm creating onSubmit={(body) => run(() => post<Provider>("/api/providers", body), t("Provedor criado. O scraper está sendo preparado.")).then((p) => {
            if (p) { setAdding(false); nav(`/provedores/${p.id}`); }
          })} />
        </Modal>
      )}
    </div>
  );
}

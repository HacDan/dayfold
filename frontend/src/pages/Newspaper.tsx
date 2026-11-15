import { useEffect, useMemo, useState } from "react";
import { t } from "../i18n";
import { get, put, type Newspaper as NewspaperT, type Settings, type Typography } from "../api";
import { Field, Loading, OptionalNumber, SectionTitle, useAction, useLoad } from "../components/ui";

const TYPE_LABEL: Record<keyof Typography, string> = {
  masthead: "Nome do jornal (masthead)", headline: "Manchete principal", title: "Título das matérias",
  subtitle: "Subtítulo", body: "Corpo do texto", line_height: "Entrelinha",
};
const MAST_WEIGHT: Record<string, number> = { "old-standard": 700, playfair: 900 };
const ORDER_LABEL = { news: "Notícias", charge: "Charge", games: "Jogos" };
const TIMEZONES = ["America/Sao_Paulo", "America/Manaus", "America/Recife", "America/Fortaleza", "America/Belem",
  "America/Cuiaba", "America/Rio_Branco", "America/Noronha", "Europe/Lisbon", "America/New_York", "UTC"];

function TypePreview({ news, family }: { news: NewspaperT; family: string }) {
  const ty = news.typography;
  const base = 15;
  return (
    <div className="type-preview" style={{ fontSize: base, lineHeight: ty.line_height }}>
      <div className="tp-mast" style={{ fontFamily: `"${family}", serif`, fontSize: `${ty.masthead}em`, fontWeight: MAST_WEIGHT[news.masthead_font] ?? 400 }}>{news.title || "Dayfold"}</div>
      <div style={{ textAlign: "center", fontStyle: "italic", fontSize: ".85em" }}>{news.tagline}</div>
      <div style={{ borderTop: "3px solid #111", borderBottom: "1px solid #111", textAlign: "center", fontFamily: "var(--caps)", fontWeight: 700, fontSize: ".7em", letterSpacing: ".08em", padding: "4px 0", margin: "6px 0 10px", textTransform: "uppercase" }}>
        {new Date().toLocaleDateString(news.language === "pt" ? "pt-BR" : "en-US", { dateStyle: "full" })}
      </div>
      <div className="tp-head" style={{ fontSize: `${ty.headline}em` }}>{t("Missão leva telescópio a observar a borda do sistema solar")}</div>
      <div className="tp-deck" style={{ fontSize: `${ty.subtitle}em` }}>{t("Instrumento vai medir poeira e gelo em órbitas distantes durante cinco anos")}</div>
      <div className="byline" style={{ margin: "6px 0", color: "#555" }}>{t("Por Ana Lima · Fonte: Agência Exemplo")}</div>
      <div className="tp-body" style={{ fontSize: `${ty.body}em` }}>
        <p>{t("A nova missão partiu nesta manhã depois de dois adiamentos causados pelo tempo. Segundo a equipe, os primeiros dados devem chegar em seis semanas, quando o telescópio terminar a calibração.")}</p>
      </div>
      <div className="tp-title" style={{ fontSize: `${ty.title}em` }}>{t("Bibliotecas públicas ampliam horário aos sábados")}</div>
      <div className="tp-body" style={{ fontSize: `${ty.body}em` }}><p>{t("A medida vale a partir do próximo mês e inclui oficinas de leitura para crianças.")}</p></div>
    </div>
  );
}

export default function Newspaper({ onTitle }: { onTitle: (t: string) => void }) {
  const { run, busy } = useAction();
  const { data, reload } = useLoad(() => get<Settings>("/api/settings"));
  const [v, setV] = useState<Settings["values"] | null>(null);
  const [coverUrl, setCoverUrl] = useState<string | null>(null);
  const [coverBusy, setCoverBusy] = useState(false);
  useEffect(() => { if (data) setV(structuredClone(data.values)); }, [data]);
  useEffect(() => {
    window.addEventListener("dayfold:settings", reload);
    return () => window.removeEventListener("dayfold:settings", reload);
  }, [reload]);
  const family = useMemo(() => data?.meta.masthead_fonts.find((f) => f.key === v?.newspaper.masthead_font)?.family ?? "Chomsky", [data, v?.newspaper.masthead_font]);
  if (!data || !v) return <Loading />;
  const meta = data.meta;
  const news = v.newspaper;
  const setNews = (patch: Partial<NewspaperT>) => setV({ ...v, newspaper: { ...news, ...patch } });
  const setType = (k: keyof Typography, val: number) => setNews({ typography: { ...news.typography, [k]: val } });

  const save = async (section: keyof Settings["values"]) => {
    const r = await run(() => put(`/api/settings/${section}`, v[section]), t("Configurações salvas"));
    if (r) {
      if (section === "newspaper") onTitle(news.title);
      reload();
    }
  };

  const previewCover = async () => {
    setCoverBusy(true);
    try {
      const res = await fetch("/api/preview/cover", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(news) });
      if (!res.ok) throw new Error((await res.json()).detail ?? "erro");
      const blob = await res.blob();
      setCoverUrl((old) => { if (old) URL.revokeObjectURL(old); return URL.createObjectURL(blob); });
    } catch (e) { alert((e as Error).message); } finally { setCoverBusy(false); }
  };

  const moveOrder = (i: number, d: -1 | 1) => {
    const o = [...news.closing_order];
    [o[i], o[i + d]] = [o[i + d], o[i]];
    setNews({ closing_order: o });
  };

  return (
    <div>
      <SectionTitle kicker={t("Expediente")} title={t("Configuração do jornal")}>
        <button className="btn primary" disabled={busy} onClick={() => save("newspaper")}>{t("Salvar jornal")}</button>
      </SectionTitle>

      <div className="lead-grid">
        <div>
          <fieldset>
            <legend>{t("Identidade")}</legend>
            <Field label={t("Nome do jornal")} hint={t("Também é o título do EPUB e o nome na capa do Kindle.")}>
              <input type="text" maxLength={40} value={news.title} onChange={(e) => setNews({ title: e.target.value })} />
            </Field>
            <Field label={t("Lema (abaixo do nome)")}><input type="text" maxLength={120} value={news.tagline} onChange={(e) => setNews({ tagline: e.target.value })} /></Field>
            <Field label={t("Fonte do masthead")} hint={t("Todas sob licença SIL OFL, embutidas no EPUB.")}>
              <select value={news.masthead_font} onChange={(e) => setNews({ masthead_font: e.target.value })}>
                {meta.masthead_fonts.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
              </select>
            </Field>
            <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 10, marginBottom: 14 }}>
              {meta.masthead_fonts.map((f) => (
                <button key={f.key} type="button" onClick={() => setNews({ masthead_font: f.key })} className="clip"
                  style={{ cursor: "pointer", textAlign: "center", fontFamily: `"${f.family}", serif`, fontSize: 30, fontWeight: MAST_WEIGHT[f.key] ?? 400, lineHeight: 1.1, padding: "10px 6px",
                    outline: f.key === news.masthead_font ? "2px solid var(--ink)" : "none", color: "var(--ink)" }}>
                  {news.title || "Dayfold"}
                </button>
              ))}
            </div>
            <Field label={t("Idioma da edição")} hint={t("Rótulos, datas, nomes padrão das seções e os jogos com idioma “Igual à edição”. Independe do idioma da dashboard.")}>
              <select value={news.language} onChange={(e) => setNews({ language: e.target.value as "pt" | "en" })}>
                <option value="pt">{t("Português")}</option><option value="en">{t("English")}</option>
              </select>
            </Field>
          </fieldset>

          <fieldset>
            <legend>{t("Tipografia")}</legend>
            <p className="small muted">{t("Tamanhos relativos ao corpo de letra do leitor, limitados a faixas que não quebram o layout no Kindle.")}</p>
            {(Object.keys(TYPE_LABEL) as (keyof Typography)[]).map((k) => {
              const r = meta.type_ranges[k];
              return (
                <label className="field" key={k}>
                  <span>{t(TYPE_LABEL[k])}: {news.typography[k].toFixed(2)}{k === "line_height" ? "" : " em"} <span className="muted">({r.min} a {r.max})</span></span>
                  <div className="row">
                    <input className="grow" type="range" min={r.min} max={r.max} step={0.05} value={news.typography[k]} onChange={(e) => setType(k, Number(e.target.value))} />
                    <button type="button" className="btn small" onClick={() => setType(k, r.default)}>{t("padrão")}</button>
                  </div>
                </label>
              );
            })}
          </fieldset>

          <fieldset>
            <legend>{t("Conteúdo da edição")}</legend>
            <div className="grid cols-2" style={{ gap: 14 }}>
              <Field label={t("Máximo de matérias")}><input type="number" min={3} max={60} value={news.max_articles} onChange={(e) => setNews({ max_articles: Number(e.target.value) })} /></Field>
              <Field label={t("Palavras no excerto")}><input type="number" min={20} max={200} value={news.excerpt_words} onChange={(e) => setNews({ excerpt_words: Number(e.target.value) })} /></Field>
              <Field label={t("Máximo de palavras por matéria")} hint={t("Só para texto integral. Vazio: matéria inteira.")}>
                <OptionalNumber value={news.article_max_words} min={50} max={5000} placeholder={t("sem limite")} onChange={(v) => setNews({ article_max_words: v })} />
              </Field>
              <Field label={t("Máximo de parágrafos por matéria")} hint={t("Seções e provedores podem ter limites próprios.")}>
                <OptionalNumber value={news.article_max_paragraphs} min={1} max={100} placeholder={t("sem limite")} onChange={(v) => setNews({ article_max_paragraphs: v })} />
              </Field>
            </div>
            <p className="small muted">{t("Uma matéria cortada termina na última frase que cabe e ganha a nota “A matéria continua na fonte” com o link.")}</p>
            <label className="check"><input type="checkbox" checked={news.include_images} onChange={(e) => setNews({ include_images: e.target.checked })} />{" "}{t("Incluir fotos (só de fontes com texto integral liberado)")}</label>
            <label className="check" title={meta.ai_available ? "" : "Configure uma IA para habilitar"}>
              <input type="checkbox" disabled={!meta.ai_available} checked={news.include_charge} onChange={(e) => setNews({ include_charge: e.target.checked })} />
              {t("Incluir charge")}{" "}{meta.ai_available ? "" : <em className="muted">{t("(indisponível: exige IA configurada)")}</em>}
            </label>
            <label className="check"><input type="checkbox" checked={news.include_games} onChange={(e) => setNews({ include_games: e.target.checked })} />{" "}{t("Incluir jogos")}</label>
            {news.include_games && (
              <Field label={t("Jogos por edição")} hint={t("Escolhidos entre os jogos ativos, em rodízio: cada dia traz uma combinação diferente.")}>
                <select value={news.games_per_edition} onChange={(e) => setNews({ games_per_edition: Number(e.target.value) })}>
                  {[1, 2, 3].map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              </Field>
            )}
            <p className="kicker" style={{ marginTop: 10 }}>{t("Ordem de fechamento")}</p>
            <ol style={{ paddingLeft: 20, margin: "0 0 10px" }}>
              {news.closing_order.map((o, i) => (
                <li key={o} style={{ marginBottom: 4 }}>
                  <span style={{ display: "inline-block", minWidth: 100 }}>{t(ORDER_LABEL[o])}</span>
                  <button type="button" className="btn small" disabled={i === 0} onClick={() => moveOrder(i, -1)}>↑</button>{" "}
                  <button type="button" className="btn small" disabled={i === news.closing_order.length - 1} onClick={() => moveOrder(i, 1)}>↓</button>
                </li>
              ))}
            </ol>
          </fieldset>
          <button className="btn primary" disabled={busy} onClick={() => save("newspaper")}>{t("Salvar jornal")}</button>

          <hr className="rule thick" />
          <fieldset>
            <legend>{t("Agendamento")}</legend>
            <label className="check"><input type="checkbox" checked={v.schedule.enabled} onChange={(e) => setV({ ...v, schedule: { ...v.schedule, enabled: e.target.checked } })} />{" "}{t("Gerar automaticamente todos os dias")}</label>
            <div className="grid cols-2" style={{ gap: 14 }}>
              <Field label={t("Horário")}><input type="time" value={v.schedule.time} onChange={(e) => setV({ ...v, schedule: { ...v.schedule, time: e.target.value } })} /></Field>
              <Field label={t("Fuso horário")}>
                <select value={v.schedule.timezone} onChange={(e) => setV({ ...v, schedule: { ...v.schedule, timezone: e.target.value } })}>
                  {[...new Set([v.schedule.timezone, ...TIMEZONES])].map((tz) => <option key={tz}>{tz}</option>)}
                </select>
              </Field>
            </div>
            <button className="btn" onClick={() => save("schedule")}>{t("Salvar agendamento")}</button>
          </fieldset>

          <fieldset>
            <legend>{t("Curadoria e filtros")}</legend>
            <label className="check" title={meta.ai_available ? "" : "Configure uma IA para habilitar"}>
              <input type="checkbox" disabled={!meta.ai_available} checked={v.curation.use_ai} onChange={(e) => setV({ ...v, curation: { ...v.curation, use_ai: e.target.checked } })} />
              {t("Curadoria com IA")}{" "}{meta.ai_available ? "(recebe só as candidatas pré-filtradas)" : <em className="muted">{t("(exige IA)")}</em>}
            </label>
            <div className="grid cols-2" style={{ gap: 14 }}>
              <Field label={t("Idade máxima (horas)")}><input type="number" min={6} max={168} value={v.curation.max_age_hours} onChange={(e) => setV({ ...v, curation: { ...v.curation, max_age_hours: Number(e.target.value) } })} /></Field>
              <Field label={t("Máx. por provedor")}><input type="number" min={1} max={20} value={v.curation.per_provider_limit} onChange={(e) => setV({ ...v, curation: { ...v.curation, per_provider_limit: Number(e.target.value) } })} /></Field>
              <Field label={t("Idiomas aceitos")} hint={t("códigos separados por vírgula")}>
                <input type="text" value={v.curation.languages.join(", ")} onChange={(e) => setV({ ...v, curation: { ...v.curation, languages: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) } })} />
              </Field>
              <Field label={t("Candidatas enviadas à IA")}><input type="number" min={10} max={120} value={v.curation.ai_candidates} onChange={(e) => setV({ ...v, curation: { ...v.curation, ai_candidates: Number(e.target.value) } })} /></Field>
            </div>
            <Field label={t("Palavras bloqueadas")} hint={t("matérias com estes termos são descartadas")}>
              <input type="text" value={v.curation.blocked_keywords.join(", ")} onChange={(e) => setV({ ...v, curation: { ...v.curation, blocked_keywords: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) } })} />
            </Field>
            <button className="btn" onClick={() => save("curation")}>{t("Salvar curadoria")}</button>
          </fieldset>

          <fieldset>
            <legend>{t("Charge")}</legend>
            <Field label={t("Modo")}>
              <select value={v.charge.mode} onChange={(e) => setV({ ...v, charge: { ...v.charge, mode: e.target.value as "structured" | "illustrated" } })}>
                <option value="illustrated">{t("Ilustrada: gerador de imagem (Codex/ChatGPT ou API de imagem)")}</option>
                <option value="structured">{t("Roteirizada: traço simples desenhado pelo servidor (sem gerador de imagem)")}</option>
              </select>
            </Field>
            <Field label={t("Estilo / linha editorial")}><textarea value={v.charge.style} onChange={(e) => setV({ ...v, charge: { ...v.charge, style: e.target.value } })} /></Field>
            <button className="btn" onClick={() => save("charge")}>{t("Salvar charge")}</button>
          </fieldset>

          <fieldset>
            <legend>{t("Aparelho")}</legend>
            <div className="grid cols-3" style={{ gap: 14 }}>
              <Field label={t("Largura da capa")}><input type="number" value={v.device.cover_width} onChange={(e) => setV({ ...v, device: { ...v.device, cover_width: Number(e.target.value) } })} /></Field>
              <Field label={t("Altura da capa")}><input type="number" value={v.device.cover_height} onChange={(e) => setV({ ...v, device: { ...v.device, cover_height: Number(e.target.value) } })} /></Field>
              <Field label={t("Largura das fotos")}><input type="number" value={v.device.image_max_width} onChange={(e) => setV({ ...v, device: { ...v.device, image_max_width: Number(e.target.value) } })} /></Field>
            </div>
            <p className="hint">{t("Padrão: Kindle Paperwhite 5 (1236 × 1648). Paperwhite 3/4: 1072 × 1448. Basic: 600 × 800.")}</p>
            <label className="check">
              <input type="checkbox" checked={v.device.screensaver_cover} onChange={(e) => setV({ ...v, device: { ...v.device, screensaver_cover: e.target.checked } })} />
              {t("Usar a capa do último jornal como tela de descanso do Kindle")}
            </label>
            <p className="hint">{t("Aplicado pelo plugin na próxima sincronização. Na tela de descanso nativa do Kindle exige o vigia instalado com make kindle-screensaver.")}</p>
            <button className="btn" onClick={() => save("device")}>{t("Salvar aparelho")}</button>
          </fieldset>
        </div>

        <aside style={{ position: "sticky", top: 12, alignSelf: "start" }}>
          <p className="kicker">{t("Prévia tipográfica")}</p>
          <TypePreview news={news} family={family} />
          <div className="row" style={{ margin: "16px 0 8px", justifyContent: "space-between" }}>
            <p className="kicker" style={{ margin: 0 }}>{t("Prévia da capa")}</p>
            <button className="btn small" disabled={coverBusy} onClick={previewCover}>{coverBusy ? t("Compondo…") : t("Atualizar prévia")}</button>
          </div>
          {coverUrl ? <div className="cover-frame"><img src={coverUrl} alt={t("Prévia da capa")} /></div>
            : <div className="empty">{t("Clique em “Atualizar prévia” para compor a capa com as configurações acima (sem salvar).")}</div>}
        </aside>
      </div>
    </div>
  );
}


import { useState } from "react";
import { t } from "../i18n";
import { del, get, post, put, type Topic } from "../api";
import { Field, Loading, OptionalNumber, SectionTitle, useAction, useLoad } from "../components/ui";

function TopicRow({ topic: tp, onSaved, onMove, first, last }: { topic: Topic; onSaved: () => void; onMove: (d: -1 | 1) => void; first: boolean; last: boolean }) {
  const { run } = useAction();
  const [f, setF] = useState({ ...tp, kw: tp.keywords.join(", ") });
  const dirty = f.name !== tp.name || f.kw !== tp.keywords.join(", ") || f.weight !== tp.weight || f.max_articles !== tp.max_articles || f.enabled !== tp.enabled || f.max_words !== tp.max_words || f.max_paragraphs !== tp.max_paragraphs;
  const save = () => run(() => put(`/api/topics/${tp.id}`, {
    slug: tp.slug, name: f.name, keywords: f.kw.split(",").map((k) => k.trim()).filter(Boolean),
    weight: f.weight, max_articles: f.max_articles, enabled: f.enabled, max_words: f.max_words, max_paragraphs: f.max_paragraphs,
  }), t("Seção salva")).then(onSaved);
  return (
    <tr style={{ opacity: f.enabled ? 1 : 0.55 }}>
      <td style={{ whiteSpace: "nowrap" }}>
        <button className="btn small" disabled={first} onClick={() => onMove(-1)} aria-label={t("Subir")}>↑</button>{" "}
        <button className="btn small" disabled={last} onClick={() => onMove(1)} aria-label={t("Descer")}>↓</button>
      </td>
      <td style={{ minWidth: 150 }}><input type="text" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /><div className="small muted">{tp.slug}</div></td>
      <td style={{ minWidth: 280 }}><textarea style={{ minHeight: 60 }} value={f.kw} onChange={(e) => setF({ ...f, kw: e.target.value })} /></td>
      <td style={{ width: 90 }}><input type="number" step={0.1} min={0.1} max={3} value={f.weight} onChange={(e) => setF({ ...f, weight: Number(e.target.value) })} /></td>
      <td style={{ width: 80 }}><input type="number" min={1} max={20} value={f.max_articles} onChange={(e) => setF({ ...f, max_articles: Number(e.target.value) })} /></td>
      <td style={{ minWidth: 140 }}>
        <div className="stack-inputs">
          <OptionalNumber value={f.max_words} min={50} max={5000} placeholder={t("palavras")} label={t("Máximo de palavras por matéria")} onChange={(v) => setF({ ...f, max_words: v })} />
          <OptionalNumber value={f.max_paragraphs} min={1} max={100} placeholder={t("parágrafos")} label={t("Máximo de parágrafos por matéria")} onChange={(v) => setF({ ...f, max_paragraphs: v })} />
        </div>
      </td>
      <td><input type="checkbox" checked={f.enabled} onChange={(e) => setF({ ...f, enabled: e.target.checked })} aria-label={t("Ativa")} /></td>
      <td style={{ whiteSpace: "nowrap" }}>
        <button className="btn small primary" disabled={!dirty} onClick={save}>{t("Salvar")}</button>{" "}
        <button className="btn small danger" onClick={() => confirm(t("Excluir a seção {name}?", { name: tp.name })) && run(() => del(`/api/topics/${tp.id}`), t("Seção excluída")).then(onSaved)}>×</button>
      </td>
    </tr>
  );
}

export default function Sections() {
  const { run } = useAction();
  const { data, reload } = useLoad(() => get<Topic[]>("/api/topics"));
  const [n, setN] = useState({ slug: "", name: "", keywords: "" });
  if (!data) return <Loading />;
  const move = (i: number, d: -1 | 1) => {
    const ids = data.map((x) => x.id);
    [ids[i], ids[i + d]] = [ids[i + d], ids[i]];
    run(() => put("/api/topics-order", ids)).then(reload);
  };
  return (
    <div>
      <SectionTitle kicker={t("Pauta")} title={t("Seções e temas")} />
      <p className="small muted" style={{ maxWidth: 760 }}>
        {t("As palavras-chave definem os temas da curadoria: sem IA, elas pontuam e classificam as matérias; com IA, guiam a seleção. A ordem aqui é a ordem das seções no jornal. Peso maior dá mais destaque; o limite controla quantas matérias cada seção recebe.")}{" "}
        {t("Tamanho limita palavras e parágrafos de cada matéria com texto integral; vazio usa o padrão do jornal.")}
      </p>
      <div className="table-wrap">
        <table className="ledger">
          <thead><tr><th>{t("Ordem")}</th><th>{t("Seção")}</th><th>{t("Palavras-chave")}</th><th>{t("Peso")}</th><th>{t("Máx.")}</th><th title={t("Limite de tamanho das matérias da seção (vazio: padrão do jornal)")}>{t("Tamanho")}</th><th>{t("Ativa")}</th><th></th></tr></thead>
          <tbody>{data.map((x, i) => <TopicRow key={`${x.id}-${x.position}`} topic={x} onSaved={reload} onMove={(d) => move(i, d)} first={i === 0} last={i === data.length - 1} />)}</tbody>
        </table>
      </div>
      <hr className="rule double" />
      <p className="kicker">{t("Nova seção")}</p>
      <form className="grid cols-3" style={{ gap: 14 }} onSubmit={(e) => {
        e.preventDefault();
        run(() => post("/api/topics", { slug: n.slug, name: n.name, keywords: n.keywords.split(",").map((k) => k.trim()).filter(Boolean) }), t("Seção criada")).then((r) => { if (r) { setN({ slug: "", name: "", keywords: "" }); reload(); } });
      }}>
        <Field label={t("Nome")}><input type="text" required value={n.name} onChange={(e) => setN({ ...n, name: e.target.value, slug: n.slug || "" })} /></Field>
        <Field label={t("Slug")} hint={t("minúsculas e hífens, ex.: economia")}><input type="text" required pattern="[a-z0-9-]{2,40}" value={n.slug} onChange={(e) => setN({ ...n, slug: e.target.value })} /></Field>
        <Field label={t("Palavras-chave (vírgulas)")}><input type="text" value={n.keywords} onChange={(e) => setN({ ...n, keywords: e.target.value })} /></Field>
        <div><button className="btn primary" type="submit">{t("Criar seção")}</button></div>
      </form>
    </div>
  );
}

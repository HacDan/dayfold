import { useState } from "react";
import { del, get, post, put, type Topic } from "../api";
import { Field, Loading, SectionTitle, useAction, useLoad } from "../components/ui";

function TopicRow({ t, onSaved, onMove, first, last }: { t: Topic; onSaved: () => void; onMove: (d: -1 | 1) => void; first: boolean; last: boolean }) {
  const { run } = useAction();
  const [f, setF] = useState({ ...t, kw: t.keywords.join(", ") });
  const dirty = f.name !== t.name || f.kw !== t.keywords.join(", ") || f.weight !== t.weight || f.max_articles !== t.max_articles || f.enabled !== t.enabled;
  const save = () => run(() => put(`/api/topics/${t.id}`, {
    slug: t.slug, name: f.name, keywords: f.kw.split(",").map((k) => k.trim()).filter(Boolean),
    weight: f.weight, max_articles: f.max_articles, enabled: f.enabled,
  }), "Seção salva").then(onSaved);
  return (
    <tr style={{ opacity: f.enabled ? 1 : 0.55 }}>
      <td style={{ whiteSpace: "nowrap" }}>
        <button className="btn small" disabled={first} onClick={() => onMove(-1)} aria-label="Subir">↑</button>{" "}
        <button className="btn small" disabled={last} onClick={() => onMove(1)} aria-label="Descer">↓</button>
      </td>
      <td style={{ minWidth: 150 }}><input type="text" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /><div className="small muted">{t.slug}</div></td>
      <td style={{ minWidth: 280 }}><textarea style={{ minHeight: 60 }} value={f.kw} onChange={(e) => setF({ ...f, kw: e.target.value })} /></td>
      <td style={{ width: 90 }}><input type="number" step={0.1} min={0.1} max={3} value={f.weight} onChange={(e) => setF({ ...f, weight: Number(e.target.value) })} /></td>
      <td style={{ width: 80 }}><input type="number" min={1} max={20} value={f.max_articles} onChange={(e) => setF({ ...f, max_articles: Number(e.target.value) })} /></td>
      <td><input type="checkbox" checked={f.enabled} onChange={(e) => setF({ ...f, enabled: e.target.checked })} aria-label="Ativa" /></td>
      <td style={{ whiteSpace: "nowrap" }}>
        <button className="btn small primary" disabled={!dirty} onClick={save}>Salvar</button>{" "}
        <button className="btn small danger" onClick={() => confirm(`Excluir a seção ${t.name}?`) && run(() => del(`/api/topics/${t.id}`), "Seção excluída").then(onSaved)}>×</button>
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
    const ids = data.map((t) => t.id);
    [ids[i], ids[i + d]] = [ids[i + d], ids[i]];
    run(() => put("/api/topics-order", ids)).then(reload);
  };
  return (
    <div>
      <SectionTitle kicker="Pauta" title="Seções e temas" />
      <p className="small muted" style={{ maxWidth: 760 }}>
        As palavras-chave definem os temas da curadoria: sem IA, elas pontuam e classificam as matérias; com IA, guiam a seleção.
        A ordem aqui é a ordem das seções no jornal. Peso maior dá mais destaque; o limite controla quantas matérias cada seção recebe.
      </p>
      <div className="table-wrap">
        <table className="ledger">
          <thead><tr><th>Ordem</th><th>Seção</th><th>Palavras-chave</th><th>Peso</th><th>Máx.</th><th>Ativa</th><th></th></tr></thead>
          <tbody>{data.map((t, i) => <TopicRow key={`${t.id}-${t.position}`} t={t} onSaved={reload} onMove={(d) => move(i, d)} first={i === 0} last={i === data.length - 1} />)}</tbody>
        </table>
      </div>
      <hr className="rule double" />
      <p className="kicker">Nova seção</p>
      <form className="grid cols-3" style={{ gap: 14 }} onSubmit={(e) => {
        e.preventDefault();
        run(() => post("/api/topics", { slug: n.slug, name: n.name, keywords: n.keywords.split(",").map((k) => k.trim()).filter(Boolean) }), "Seção criada").then((r) => { if (r) { setN({ slug: "", name: "", keywords: "" }); reload(); } });
      }}>
        <Field label="Nome"><input type="text" required value={n.name} onChange={(e) => setN({ ...n, name: e.target.value, slug: n.slug || "" })} /></Field>
        <Field label="Slug" hint="minúsculas e hífens, ex.: economia"><input type="text" required pattern="[a-z0-9-]{2,40}" value={n.slug} onChange={(e) => setN({ ...n, slug: e.target.value })} /></Field>
        <Field label="Palavras-chave (vírgulas)"><input type="text" value={n.keywords} onChange={(e) => setN({ ...n, keywords: e.target.value })} /></Field>
        <div><button className="btn primary" type="submit">Criar seção</button></div>
      </form>
    </div>
  );
}

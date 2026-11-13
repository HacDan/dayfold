import { Link } from "react-router-dom";
import { get, type EditionSummary } from "../api";
import { Empty, Loading, SectionTitle, Stamp, useLoad } from "../components/ui";

export default function Editions() {
  const { data } = useLoad(() => get<EditionSummary[]>("/api/editions"), [], 20000);
  if (!data) return <Loading />;
  return (
    <div>
      <SectionTitle kicker="Arquivo" title="Histórico de edições" />
      {data.length === 0 && <Empty>Nenhuma edição ainda. Use “Gerar jornal agora” na capa.</Empty>}
      <div className="editions-grid">
        {data.map((e) => (
          <Link key={e.id} to={`/edicoes/${e.id}`}>
            {e.cover_url ? <div className="cover-frame"><img src={e.cover_url} alt={`Capa nº ${e.number}`} loading="lazy" /></div>
              : <div className="empty" style={{ aspectRatio: "3 / 4" }}>{e.status === "FAILED" ? "falhou" : "sem capa"}</div>}
            <div className="cap">Nº {e.number} · {new Date(e.date + "T12:00").toLocaleDateString("pt-BR")}</div>
            <div className="small" style={{ fontFamily: "var(--display)", fontWeight: 700, lineHeight: 1.2 }}>{e.headline}</div>
            <div style={{ marginTop: 4 }}><Stamp status={e.status} /></div>
          </Link>
        ))}
      </div>
    </div>
  );
}

import { useState } from "react";
import { Link } from "react-router-dom";
import { locale, t } from "../i18n";
import { get, type SearchResults } from "../api";
import { Empty, SectionTitle, useToast } from "../components/ui";

export default function Search() {
  const [q, setQ] = useState("");
  const [found, setFound] = useState<SearchResults | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const term = q.trim();

  const run = async (event: React.FormEvent) => {
    event.preventDefault();
    if (term.length < 2) return;
    setBusy(true);
    try {
      setFound(await get<SearchResults>(`/api/search?q=${encodeURIComponent(term)}`));
    } catch (e) {
      toast((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <SectionTitle kicker={t("Arquivo")} title={t("Buscar no arquivo")} />
      <form className="row" onSubmit={run} style={{ marginBottom: 18 }}>
        <input className="grow" type="search" value={q} onChange={(e) => setQ(e.target.value)}
          placeholder={t("Título ou texto de uma matéria já publicada")} />
        <button className="btn primary" disabled={busy || term.length < 2}>
          {busy ? "…" : t("Buscar")}
        </button>
      </form>
      {found === null ? null : found.hits.length === 0 ? (
        <Empty>{t("Nenhuma matéria encontrada para “{q}”.", { q: term })}</Empty>
      ) : (
        <div className="hits">
          {found.hits.map((h, i) => (
            <Link key={`${h.edition_id}-${i}`} className="hit" to={`/edicoes/${h.edition_id}`}>
              <span className="cap">
                Nº {h.number} · {new Date(h.date + "T12:00").toLocaleDateString(locale())} · {h.section}
              </span>
              <strong>{h.title}</strong>
              <span className="small muted">{h.snippet}</span>
            </Link>
          ))}
        </div>
      )}
      {found?.more && (
        <p className="small muted" style={{ textAlign: "center", marginTop: 12 }}>
          {t("Mostrando as {n} matérias mais recentes; refine a busca para ver as restantes.", { n: found.hits.length })}
        </p>
      )}
    </div>
  );
}

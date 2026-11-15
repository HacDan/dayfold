import { Link, useNavigate, useParams } from "react-router-dom";
import { locale, t } from "../i18n";
import { del, get, post, fmtDateTime, USAGE_LABEL, type EditionSummary, type Job } from "../api";
import { GamePreview } from "../components/games";
import { Loading, SectionTitle, Stamp, useAction, useLoad } from "../components/ui";
import { PressImage } from "../components/ui";

type Detail = EditionSummary & {
  articles: {
    id: number; position: number; section: string; section_name: string; priority: number; is_headline: boolean;
    score: number; title: string; subtitle: string | null; author: string | null; published_at: string | null;
    provider: string; url: string; usage_mode: string; has_body: boolean;
  }[];
  games: { kind: string; title: string; puzzle: Record<string, unknown>; solution: Record<string, unknown> }[];
  charge: { mode: string; caption: string | null; image_url: string; script: Record<string, unknown> | null } | null;
  job: Job | null;
};

export default function EditionDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { run, busy } = useAction();
  const { data, reload } = useLoad(() => get<Detail>(`/api/editions/${id}`), [id]);
  if (!data) return <Loading />;
  const sections = new Map<string, Detail["articles"]>();
  for (const a of data.articles) {
    const key = a.is_headline ? t("Manchete") : a.section_name;
    sections.set(key, [...(sections.get(key) ?? []), a]);
  }

  return (
    <div>
      <SectionTitle kicker={`${t("Edição nº {n}", { n: data.number })} · ${new Date(data.date + "T12:00").toLocaleDateString(locale(), { dateStyle: "full" })}`} title={data.headline ?? data.title}>
        {data.epub_url && <a className="btn primary" href={data.epub_url}>{t("Baixar EPUB")}</a>}
        {data.status === "READY" && <Link className="btn" to={`/edicoes/${data.id}/avaliar`}>{t("Avaliar edição")}</Link>}
        <button className="btn" disabled={busy} onClick={() => run(() => post(`/api/editions/${data.id}/charge`), t("Nova charge desenhada")).then((r) => r && reload())}>{busy ? t("Desenhando…") : t("Refazer charge")}</button>
        <button className="btn" onClick={() => run(() => post(`/api/editions/${data.id}/retypeset`), t("Edição recomposta com as configurações atuais")).then((r) => r && reload())}>{t("Recompor")}</button>
        <button className="btn danger" onClick={() => {
          if (confirm(t("Excluir esta edição e seus arquivos?"))) run(() => del(`/api/editions/${data.id}`), t("Edição excluída")).then((r) => r && nav("/edicoes"));
        }}>{t("Excluir")}</button>
      </SectionTitle>

      <div className="lead-grid">
        <div>
          <p className="byline">
            <Stamp status={data.status} /> · {String(data.stats.articles ?? 0)}{" "}{t("matérias ·")}{" "}{String(data.stats.images ?? 0)}{" "}{t("imagens · EPUB")}{" "}{String(data.stats.epub_kb ?? "?")}{" "}{t("KB · curadoria por")}{" "}{data.curated_by === "ai" ? t("IA") : t("regras")}{" "}{t("· gerada em")}{" "}{fmtDateTime(data.created_at)}
          </p>
          {[...sections.entries()].map(([name, items]) => (
            <section key={name} style={{ marginBottom: 22 }}>
              <h3 style={{ borderBottom: "1px solid var(--rule)", paddingBottom: 4 }}>{name}</h3>
              {items.map((a) => (
                <article key={a.id} style={{ padding: "8px 0", borderBottom: "1px solid var(--rule-soft)" }}>
                  <div style={{ fontFamily: "var(--display)", fontWeight: 700, fontSize: a.is_headline ? "1.4rem" : "1.05rem", lineHeight: 1.2 }}>
                    <a href={a.url} target="_blank" rel="noreferrer" style={{ textDecoration: "none" }}>{a.title}</a>
                  </div>
                  {a.subtitle && <div className="deck small">{a.subtitle}</div>}
                  <div className="byline">
                    {a.author ? `${t("Por")} ${a.author} · ` : ""}{a.provider} · {fmtDateTime(a.published_at)} · {USAGE_LABEL[a.usage_mode] ? t(USAGE_LABEL[a.usage_mode]) : a.usage_mode}
                    {" "}{t("· prioridade")}{" "}{a.priority}{" "}{t("· nota")}{" "}{a.score.toFixed(2)}
                  </div>
                </article>
              ))}
            </section>
          ))}
        </div>
        <aside>
          {data.cover_url && <div className="cover-frame" style={{ marginBottom: 24 }}><PressImage src={data.cover_url} alt={t("Capa")} /></div>}
          {data.charge && (
            <section style={{ marginBottom: 24 }}>
              <p className="kicker">{t("Charge (")}{data.charge.mode === "structured" ? t("roteirizada") : t("ilustrada")})</p>
              <div className="cover-frame"><PressImage src={data.charge.image_url} alt={data.charge.caption ?? t("Charge")} /></div>
              {data.charge.caption && <p className="deck small" style={{ marginTop: 6 }}>{data.charge.caption}</p>}
            </section>
          )}
          {data.games.map((g) => (
            <section key={g.title} style={{ marginBottom: 20 }}>
              <p className="kicker">{g.title}</p>
              <GamePreview kind={g.kind} puzzle={g.puzzle} solution={g.solution} />
            </section>
          ))}
        </aside>
      </div>
      {data.job && (
        <>
          <hr className="rule thick" />
          <p className="kicker">{t("Registro da geração #")}{data.job.id}</p>
          <div className="log">{data.job.log.join("\n")}</div>
        </>
      )}
    </div>
  );
}

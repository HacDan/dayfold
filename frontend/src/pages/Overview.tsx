import { Link } from "react-router-dom";
import { locale, t, triggerLabel } from "../i18n";
import { get, post, fmtDateTime, type Job, type Overview as OverviewT } from "../api";
import { Loading, Press, Stamp, useAction, useLoad } from "../components/ui";
import { PressImage } from "../components/ui";

const STEP: Record<string, string> = {
  collect: "Coletando matérias", curate: "Curadoria", images: "Preparando imagens", games: "Gerando jogos",
  charge: "Desenhando a charge", cover: "Compondo a capa", epub: "Montando o EPUB", done: "Pronto",
};

export function GenerateButton({ job, onStarted }: { job: Job | null; onStarted: () => void }) {
  const { run, busy } = useAction();
  const running = job && (job.status === "RUNNING" || job.status === "QUEUED");
  return (
    <div>
      <button className="btn primary big" disabled={busy || !!running}
        onClick={() => run(() => post("/api/generate"), t("Geração iniciada. Acompanhe abaixo.")).then(onStarted)}>
        {running ? t("Imprimindo…") : t("Gerar jornal agora")}
      </button>
      {running && job && (
        <div style={{ marginTop: 14 }}>
          <p className="byline">{t(STEP[job.step ?? ""] ?? "Na fila")} · {Math.round(job.progress * 100)}%</p>
          <Press value={job.progress} />
          <div className="log" style={{ marginTop: 10, maxHeight: 160 }}>{job.log.slice(-6).join("\n")}</div>
        </div>
      )}
    </div>
  );
}

export default function Overview() {
  const { data, reload } = useLoad(() => get<OverviewT>("/api/overview"), [], (d) =>
    d?.last_job && ["RUNNING", "QUEUED"].includes(d.last_job.status) ? 2000 : 30000);
  if (!data) return <Loading />;
  const ed = data.latest_edition;
  const job = data.last_job;

  return (
    <div>
      <div className="lead-grid">
        <article>
          <p className="kicker">{ed && !data.edition_is_today ? t("Última edição") : t("Edição de hoje")}</p>
          {ed ? (
            <>
              <h2 style={{ fontSize: "2.4rem" }}><Link to={`/edicoes/${ed.id}`} style={{ textDecoration: "none" }}>{ed.headline ?? ed.title}</Link></h2>
              <p className="deck">
                {t("Edição nº {n}, de {date}: {articles} matérias em {sections} seções, {games} jogos{charge}. Curadoria por {by}.", {
                  n: ed.number,
                  date: new Date(ed.date + "T12:00").toLocaleDateString(locale(), { dateStyle: "long" }),
                  articles: String(ed.stats.articles ?? 0), sections: String(ed.stats.sections ?? 0),
                  games: String(ed.stats.games ?? 0), charge: ed.stats.charge ? t(" e charge") : "",
                  by: ed.curated_by === "ai" ? t("IA") : t("regras"),
                })}
              </p>
              <p className="byline">{t("Gerada em")}{" "}{fmtDateTime(ed.created_at)}{" "}{t("· EPUB")}{" "}{String(ed.stats.epub_kb ?? "?")} KB</p>
              <div className="row" style={{ margin: "14px 0 22px" }}>
                <Link className="btn primary" to={`/edicoes/${ed.id}/avaliar`}>
                  {data.latest_ratings && data.latest_ratings.rated > 0
                    ? t("Avaliar edição ({rated}/{total})", { rated: data.latest_ratings.rated, total: data.latest_ratings.total })
                    : t("Avaliar edição")}
                </Link>
                {ed.epub_url && <a className="btn" href={ed.epub_url}>{t("Baixar EPUB")}</a>}
                <Link className="btn" to={`/edicoes/${ed.id}`}>{t("Ver detalhes")}</Link>
                <Link className="btn" to="/kindle">{t("Enviar ao Kindle")}</Link>
              </div>
            </>
          ) : (
            <>
              <h2 style={{ fontSize: "2.4rem" }}>{t("Nenhuma edição impressa ainda")}</h2>
              <p className="deck">{t("Gere a primeira edição para ver a capa, as matérias e os jogos do dia.")}</p>
            </>
          )}
          <hr className="rule double" />
          <GenerateButton job={job} onStarted={reload} />
          {job && !["RUNNING", "QUEUED"].includes(job.status) && (
            <p className="small muted" style={{ marginTop: 10 }}>
              {t("Última geração:")}{" "}<Stamp status={job.status} /> {fmtDateTime(job.finished_at)} ({triggerLabel(job.trigger)})
              {job.error && <> · <span style={{ color: "var(--bad)" }}>{job.error}</span></>}
              {" "}· <Link to="/registros">{t("registros")}</Link>
            </p>
          )}
        </article>
        <aside>
          {ed?.cover_url ? (
            <Link to={`/edicoes/${ed.id}`} className="cover-frame" style={{ display: "block", maxWidth: 380, marginLeft: "auto" }}>
              <PressImage src={`${ed.cover_url}?v=${ed.id}`} alt={t("Capa da edição {n}", { n: ed.number })} />
            </Link>
          ) : (
            <div className="empty" style={{ aspectRatio: "3 / 4" }}>{t("A capa da edição aparecerá aqui.")}</div>
          )}
        </aside>
      </div>

      <hr className="rule thick" style={{ marginTop: 34 }} />
      <div className="grid cols-3 col-rule">
        <section>
          <p className="kicker">{t("Próxima geração")}</p>
          <div className="stat">{data.schedule.enabled ? data.schedule.time : t("desligado")}</div>
          <p className="small muted">
            {data.schedule.enabled && data.next_run ? t("Próxima: {when} ({tz})", { when: fmtDateTime(data.next_run), tz: data.schedule.timezone }) : t("Agendamento desativado")}
          </p>
          <Link className="btn small" to="/jornal">{t("Ajustar horário")}</Link>
        </section>
        <section>
          <p className="kicker">{t("Provedores ativos")}</p>
          <div className="stat">{data.providers.active}<small>{t("de")}{" "}{data.providers.total}</small></div>
          <p className="small muted">{data.providers.failing ? t("{n} com falha na última coleta", { n: data.providers.failing }) : t("Todos responderam na última coleta")}</p>
          <Link className="btn small" to="/provedores">{t("Gerenciar")}</Link>
        </section>
        <section>
          <p className="kicker">{t("Scrapers pendentes")}</p>
          <div className="stat">{data.scrapers.pending}</div>
          <p className="small muted">{data.scrapers.failed_jobs}{" "}{t("gerações com falha no histórico")}</p>
          <Link className="btn small" to="/scrapers">{t("Ver scrapers")}</Link>
        </section>
      </div>
      <hr className="rule" />
      <div className="grid cols-3 col-rule">
        <section>
          <p className="kicker">{t("Inteligência artificial")}</p>
          <h3>{data.ai.active ? data.ai.name : t("Desligada")}</h3>
          <p className="small muted">
            {data.ai.active
              ? t("Usada em curadoria, charge e scrapers. Nesta sessão: {calls} chamadas, ~{tokens} tokens.", { calls: data.ai.session_usage.calls, tokens: Math.round((data.ai.session_usage.prompt_chars + data.ai.session_usage.completion_chars) / 4) })
              : t("O jornal funciona sem IA, com curadoria por regras e palavras-chave.")}
          </p>
          <Link className="btn small" to="/ia">{t("Configurar")}</Link>
        </section>
        <section>
          <p className="kicker">{t("Charge")}</p>
          <h3>{data.charge.enabled ? t("Na edição") : data.charge.available ? t("Desligada") : t("Indisponível")}</h3>
          <p className="small muted">{data.charge.available ? t("Gerada a partir das manchetes mais relevantes do dia.") : t("Exige uma IA configurada.")}</p>
          <Link className="btn small" to="/jornal">{t("Jornal")}</Link>
        </section>
        <section>
          <p className="kicker">{t("Jogos")}</p>
          <h3>{data.games.filter((g) => g.enabled).map((g) => t(g.name)).join(", ") || t("Nenhum")}</h3>
          <p className="small muted">{t("Preparados no servidor e entregues dentro da edição.")}</p>
          <Link className="btn small" to="/jogos">{t("Jogos")}</Link>
        </section>
      </div>

      {data.recent_editions.length > 1 && (
        <>
          <hr className="rule thick" style={{ marginTop: 30 }} />
          <p className="kicker">{t("Edições anteriores")}</p>
          <div className="editions-grid">
            {data.recent_editions.slice(1).map((e) => (
              <Link key={e.id} to={`/edicoes/${e.id}`}>
                {e.cover_url ? <div className="cover-frame"><PressImage src={e.cover_url} alt="" loading="lazy" /></div> : <div className="empty">{t("sem capa")}</div>}
                <div className="cap">{t("Nº")} {e.number} · {e.date} <Stamp status={e.status} /></div>
              </Link>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

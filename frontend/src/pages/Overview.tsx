import { Link } from "react-router-dom";
import { get, post, fmtDateTime, type Job, type Overview as OverviewT } from "../api";
import { Loading, Press, Stamp, useAction, useLoad } from "../components/ui";

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
        onClick={() => run(() => post("/api/generate"), "Geração iniciada. Acompanhe abaixo.").then(onStarted)}>
        {running ? "Imprimindo…" : "Gerar jornal agora"}
      </button>
      {running && job && (
        <div style={{ marginTop: 14 }}>
          <p className="byline">{STEP[job.step ?? ""] ?? "Na fila"} · {Math.round(job.progress * 100)}%</p>
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
          <p className="kicker">Edição de hoje</p>
          {ed ? (
            <>
              <h2 style={{ fontSize: "2.4rem" }}><Link to={`/edicoes/${ed.id}`} style={{ textDecoration: "none" }}>{ed.headline ?? ed.title}</Link></h2>
              <p className="deck">
                Edição nº {ed.number}, de {new Date(ed.date + "T12:00").toLocaleDateString("pt-BR", { dateStyle: "long" })}:
                {" "}{String(ed.stats.articles ?? 0)} matérias em {String(ed.stats.sections ?? 0)} seções,
                {" "}{String(ed.stats.games ?? 0)} jogos{ed.stats.charge ? " e charge" : ""}. Curadoria por {ed.curated_by === "ai" ? "IA" : "regras"}.
              </p>
              <p className="byline">Gerada em {fmtDateTime(ed.created_at)} · EPUB {String(ed.stats.epub_kb ?? "?")} KB</p>
              <div className="row" style={{ margin: "14px 0 22px" }}>
                {ed.epub_url && <a className="btn" href={ed.epub_url}>Baixar EPUB</a>}
                <Link className="btn" to={`/edicoes/${ed.id}`}>Ver detalhes</Link>
                <Link className="btn" to="/kindle">Enviar ao Kindle</Link>
              </div>
            </>
          ) : (
            <>
              <h2 style={{ fontSize: "2.4rem" }}>Nenhuma edição impressa ainda</h2>
              <p className="deck">Gere a primeira edição para ver a capa, as matérias e os jogos do dia.</p>
            </>
          )}
          <hr className="rule double" />
          <GenerateButton job={job} onStarted={reload} />
          {job && !["RUNNING", "QUEUED"].includes(job.status) && (
            <p className="small muted" style={{ marginTop: 10 }}>
              Última geração: <Stamp status={job.status} /> {fmtDateTime(job.finished_at)} ({job.trigger === "schedule" ? "agendada" : "manual"})
              {job.error && <> · <span style={{ color: "var(--bad)" }}>{job.error}</span></>}
              {" "}· <Link to="/registros">registros</Link>
            </p>
          )}
        </article>
        <aside>
          {ed?.cover_url ? (
            <Link to={`/edicoes/${ed.id}`} className="cover-frame" style={{ display: "block", maxWidth: 380, marginLeft: "auto" }}>
              <img src={`${ed.cover_url}?v=${ed.id}`} alt={`Capa da edição ${ed.number}`} />
            </Link>
          ) : (
            <div className="empty" style={{ aspectRatio: "3 / 4" }}>A capa da edição aparecerá aqui.</div>
          )}
        </aside>
      </div>

      <hr className="rule thick" style={{ marginTop: 34 }} />
      <div className="grid cols-3 col-rule">
        <section>
          <p className="kicker">Próxima geração</p>
          <div className="stat">{data.schedule.enabled ? data.schedule.time : "off"}</div>
          <p className="small muted">
            {data.schedule.enabled && data.next_run ? `Próxima: ${fmtDateTime(data.next_run)} (${data.schedule.timezone})` : "Agendamento desativado"}
          </p>
          <Link className="btn small" to="/jornal">Ajustar horário</Link>
        </section>
        <section>
          <p className="kicker">Provedores ativos</p>
          <div className="stat">{data.providers.active}<small>de {data.providers.total}</small></div>
          <p className="small muted">{data.providers.failing ? `${data.providers.failing} com falha na última coleta` : "Todos responderam na última coleta"}</p>
          <Link className="btn small" to="/provedores">Gerenciar</Link>
        </section>
        <section>
          <p className="kicker">Scrapers pendentes</p>
          <div className="stat">{data.scrapers.pending}</div>
          <p className="small muted">{data.scrapers.failed_jobs} gerações com falha no histórico</p>
          <Link className="btn small" to="/scrapers">Ver scrapers</Link>
        </section>
      </div>
      <hr className="rule" />
      <div className="grid cols-3 col-rule">
        <section>
          <p className="kicker">Inteligência artificial</p>
          <h3>{data.ai.active ? data.ai.name : "Desligada"}</h3>
          <p className="small muted">
            {data.ai.active
              ? `Usada em curadoria, charge e scrapers. Nesta sessão: ${data.ai.session_usage.calls} chamadas, ~${Math.round((data.ai.session_usage.prompt_chars + data.ai.session_usage.completion_chars) / 4)} tokens.`
              : "O jornal funciona sem IA, com curadoria por regras e palavras-chave."}
          </p>
          <Link className="btn small" to="/ia">Configurar</Link>
        </section>
        <section>
          <p className="kicker">Charge</p>
          <h3>{data.charge.enabled ? "Na edição" : data.charge.available ? "Desligada" : "Indisponível"}</h3>
          <p className="small muted">{data.charge.available ? "Gerada a partir das manchetes mais relevantes do dia." : "Exige uma IA configurada."}</p>
          <Link className="btn small" to="/jornal">Jornal</Link>
        </section>
        <section>
          <p className="kicker">Jogos</p>
          <h3>{data.games.filter((g) => g.enabled).map((g) => g.name).join(", ") || "Nenhum"}</h3>
          <p className="small muted">Preparados no servidor e entregues dentro da edição.</p>
          <Link className="btn small" to="/jogos">Jogos</Link>
        </section>
      </div>

      {data.recent_editions.length > 1 && (
        <>
          <hr className="rule thick" style={{ marginTop: 30 }} />
          <p className="kicker">Edições anteriores</p>
          <div className="editions-grid">
            {data.recent_editions.slice(1).map((e) => (
              <Link key={e.id} to={`/edicoes/${e.id}`}>
                {e.cover_url ? <div className="cover-frame"><img src={e.cover_url} alt="" loading="lazy" /></div> : <div className="empty">sem capa</div>}
                <div className="cap">Nº {e.number} · {e.date} <Stamp status={e.status} /></div>
              </Link>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

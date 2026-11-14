import { Link } from "react-router-dom";
import { t } from "../i18n";
import { get, fmtDateTime, type ScraperJob, type Version } from "../api";
import { Loading, SectionTitle, Stamp, useLoad } from "../components/ui";

export default function Scrapers() {
  const versions = useLoad(() => get<Version[]>("/api/scrapers"), [], 8000);
  const jobs = useLoad(() => get<ScraperJob[]>("/api/scraper-jobs"), [], (d) =>
    d?.some((j) => ["QUEUED", "RUNNING"].includes(j.status)) ? 2000 : 10000);
  if (!versions.data || !jobs.data) return <Loading />;
  const names = new Map(versions.data.map((v) => [v.provider_id, v.provider_name]));
  const counts = versions.data.reduce<Record<string, number>>((acc, v) => ({ ...acc, [v.status]: (acc[v.status] ?? 0) + 1 }), {});

  return (
    <div>
      <SectionTitle kicker={t("Oficina")} title={t("Scrapers")} />
      <p className="small muted" style={{ maxWidth: 780 }}>
        {t("Scrapers são especificações declarativas (feed, extração genérica ou seletores CSS), nunca código gerado. Cada versão roda em um processo isolado com limite de tempo e memória, e só é ativada depois de passar no teste. Para criar ou regenerar, abra um provedor.")}
      </p>
      <div className="row" style={{ margin: "10px 0 20px" }}>
        {Object.entries(counts).map(([s, n]) => <span key={s}><Stamp status={s} /> {n}</span>)}
      </div>

      <div className="lead-grid">
        <section>
          <p className="kicker">{t("Todas as versões")}</p>
          <div className="table-wrap">
            <table className="ledger">
              <thead><tr><th>{t("Provedor")}</th><th>{t("Versão")}</th><th>{t("Estratégia")}</th><th>{t("Estado")}</th><th>{t("Atualizada")}</th></tr></thead>
              <tbody>
                {versions.data.map((v) => (
                  <tr key={v.id}>
                    <td><Link className="name" to={`/provedores/${v.provider_id}`} style={{ textDecoration: "none" }}>{v.provider_name}</Link></td>
                    <td>v{v.version} {v.is_active && <Stamp status="ok" label={t("ativa")} />}</td>
                    <td className="small">{v.strategy} · {v.origin === "ai" ? t("IA") : t(v.origin)}</td>
                    <td><Stamp status={v.status} /></td>
                    <td className="small muted">{fmtDateTime(v.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <aside>
          <p className="kicker">{t("Fila de geração e testes")}</p>
          {jobs.data.length === 0 && <p className="small muted">{t("Nenhum job ainda.")}</p>}
          {jobs.data.map((j) => (
            <div key={j.id} className="clip ruled" style={{ marginBottom: 14 }}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <strong><Link to={`/provedores/${j.provider_id}`}>{names.get(j.provider_id) ?? `#${j.provider_id}`}</Link></strong>
                <Stamp status={j.status} />
              </div>
              <div className="byline">{j.kind === "test" ? t("teste") : j.use_ai ? t("geração com IA") : t("geração automática")} · {fmtDateTime(j.created_at)}</div>
              {j.extra_prompt && <p className="small muted">“{j.extra_prompt}”</p>}
              {j.log.length > 0 && <div className="log" style={{ maxHeight: 120 }}>{j.log.slice(-4).join("\n")}</div>}
            </div>
          ))}
        </aside>
      </div>
    </div>
  );
}

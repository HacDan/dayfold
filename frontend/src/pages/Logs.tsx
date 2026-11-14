import { Fragment, useState } from "react";
import { t } from "../i18n";
import { Link } from "react-router-dom";
import { get, fmtDateTime, type Job } from "../api";
import { Empty, Loading, Press, SectionTitle, Stamp, useLoad } from "../components/ui";
import { GenerateButton } from "./Overview";

export default function Logs() {
  const { data, reload } = useLoad(() => get<Job[]>("/api/jobs"), [], (d) => d?.some((j) => ["RUNNING", "QUEUED"].includes(j.status)) ? 2000 : 15000);
  const [open, setOpen] = useState<number | null>(null);
  if (!data) return <Loading />;
  const current = data[0] ?? null;
  return (
    <div>
      <SectionTitle kicker={t("Gráfica")} title={t("Registros e status das gerações")} />
      <GenerateButton job={current} onStarted={reload} />
      <hr className="rule double" />
      {data.length === 0 && <Empty>{t("Nenhuma geração registrada.")}</Empty>}
      <div className="table-wrap">
        <table className="ledger">
          <thead><tr><th>#</th><th>{t("Origem")}</th><th>{t("Estado")}</th><th>{t("Etapa")}</th><th>{t("Início")}</th><th>{t("Fim")}</th><th>{t("Edição")}</th><th></th></tr></thead>
          <tbody>
            {data.map((j) => (
              <Fragment key={j.id}>
                <tr>
                  <td>{j.id}</td>
                  <td className="small">{j.trigger === "schedule" ? t("agendada") : t(j.trigger)}</td>
                  <td><Stamp status={j.status} /></td>
                  <td style={{ minWidth: 140 }}>{j.status === "RUNNING" ? <Press value={j.progress} /> : <span className="small muted">{j.step ?? "-"}</span>}</td>
                  <td className="small">{fmtDateTime(j.started_at)}</td>
                  <td className="small">{fmtDateTime(j.finished_at)}</td>
                  <td className="small">{j.edition_id ? <Link to={`/edicoes/${j.edition_id}`}>{t("abrir")}</Link> : "-"}</td>
                  <td><button className="btn small" onClick={() => setOpen(open === j.id ? null : j.id)}>{open === j.id ? t("Ocultar") : t("Registro")}</button></td>
                </tr>
                {open === j.id && (
                  <tr><td colSpan={8}>
                    {j.error && <p style={{ color: "var(--bad)" }}>{j.error}</p>}
                    <div className="log">{j.log.join("\n") || t("sem registro")}</div>
                  </td></tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

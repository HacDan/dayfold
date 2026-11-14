import { useState } from "react";
import { t } from "../i18n";
import { useNavigate, useParams } from "react-router-dom";
import { del, get, post, put, fmtDateTime, USAGE_LABEL, type Provider, type Version } from "../api";
import { Field, Loading, Modal, SectionTitle, Stamp, useAction, useLoad } from "../components/ui";
import { ProviderForm } from "./Providers";

function Report({ v }: { v: Version }) {
  const r = v.test_report;
  if (!r) return null;
  return (
    <div className="small" style={{ marginTop: 6 }}>
      <strong>{r.ok ? t("Teste aprovado") : t("Teste reprovado")}</strong>: {r.count}{" "}{t("matérias,")}{" "}{r.with_body}{" "}{t("com corpo,")}{" "}{r.with_date}{" "}{t("com data,")}
      {" "}{r.with_author}{" "}{t("com autor,")}{" "}{r.with_image}{" "}{t("com imagem.")}
      {r.reasons.length > 0 && <div style={{ color: "var(--bad)" }}>{r.reasons.join("; ")}</div>}
      {r.sample.length > 0 && (
        <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
          {r.sample.map((s) => <li key={s.url}><a href={s.url} target="_blank" rel="noreferrer">{s.title}</a></li>)}
        </ul>
      )}
    </div>
  );
}

export default function ProviderDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { run, busy } = useAction();
  const { data, reload } = useLoad(() => get<Provider>(`/api/providers/${id}`), [id], (d) =>
    d?.jobs?.some((j) => ["QUEUED", "RUNNING"].includes(j.status)) ? 2000 : 15000);
  const [editing, setEditing] = useState(false);
  const [regen, setRegen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [useAi, setUseAi] = useState(true);
  if (!data) return <Loading />;
  const runningJob = data.jobs?.find((j) => ["QUEUED", "RUNNING"].includes(j.status));

  return (
    <div>
      <SectionTitle kicker={`Provedor · ${data.category}`} title={data.name}>
        <button className="btn" disabled={busy || !data.active_version_id} onClick={() => run(() => post(`/api/providers/${data.id}/test`), t("Teste enfileirado")).then(reload)}>{t("Testar")}</button>
        <button className="btn" disabled={!!runningJob} onClick={() => setRegen(true)}>{t("Regenerar scraper")}</button>
        <button className="btn" onClick={() => setEditing(true)}>{t("Editar")}</button>
        <button className="btn danger" onClick={() => {
          if (confirm(t("Excluir {name} e suas matérias coletadas?", { name: data.name }))) run(() => del(`/api/providers/${data.id}`), t("Provedor excluído")).then((r) => r && nav("/provedores"));
        }}>{t("Excluir")}</button>
      </SectionTitle>

      <div className="grid cols-3 col-rule">
        <section>
          <p className="kicker">{t("Fonte")}</p>
          <p><a href={data.base_url} target="_blank" rel="noreferrer">{data.base_url}</a></p>
          <p className="small">{t("Idioma")}{" "}{data.language.toUpperCase()}{" "}{t("· tipo")}{" "}{data.source_type.toUpperCase()}{" "}{t("· até")}{" "}{data.max_items}{" "}{t("itens")}</p>
          <label className="check"><input type="checkbox" checked={data.enabled} onChange={() => run(() => put(`/api/providers/${data.id}`, { ...data, enabled: !data.enabled })).then(reload)} />{" "}{t("Ativo nas edições")}</label>
        </section>
        <section>
          <p className="kicker">{t("Licença e uso")}</p>
          <h3>{t(USAGE_LABEL[data.usage_mode] ?? data.usage_mode)}</h3>
          <p className="small">{data.license_name}{data.license_url && <> · <a href={data.license_url} target="_blank" rel="noreferrer">{t("termos")}</a></>}</p>
          {data.license_note && <p className="small muted">{data.license_note}</p>}
        </section>
        <section>
          <p className="kicker">{t("Última coleta")}</p>
          <h3>{data.last_run_at ? (data.last_run_ok ? t("{n} itens", { n: data.last_run_count ?? 0 }) : t("Falhou")) : t("Nunca")}</h3>
          <p className="small muted">{fmtDateTime(data.last_run_at)}{data.last_run_message ? ` · ${data.last_run_message}` : ""}</p>
        </section>
      </div>

      {runningJob && (
        <>
          <hr className="rule" />
          <p className="kicker">{t("Preparando scraper")}{" "}<Stamp status={runningJob.status} /></p>
          <div className="log">{runningJob.log.join("\n") || "Na fila…"}</div>
          <p className="small muted">{t("A versão ativa continua coletando até a nova passar na validação.")}</p>
        </>
      )}

      <hr className="rule thick" />
      <p className="kicker">{t("Versões do scraper")}</p>
      <div className="table-wrap">
        <table className="ledger">
          <thead><tr><th>{t("Versão")}</th><th>{t("Estado")}</th><th>{t("Estratégia")}</th><th>{t("Teste")}</th><th></th></tr></thead>
          <tbody>
            {data.versions?.map((v) => (
              <tr key={v.id}>
                <td>
                  <span className="name">v{v.version}</span> {v.is_active && <Stamp status="ok" label={t("ativa")} />}
                  <div className="small muted">{v.origin === "ai" ? "IA" : v.origin === "default" ? "padrão" : v.origin} · {fmtDateTime(v.created_at)}</div>
                  {v.prompt && <div className="small muted">“{v.prompt}”</div>}
                </td>
                <td><Stamp status={v.status} /></td>
                <td className="small"><code>{v.strategy}</code><pre style={{ maxWidth: 380, margin: "6px 0 0" }}>{JSON.stringify(v.spec, null, 1)}</pre></td>
                <td style={{ maxWidth: 360 }}><Report v={v} />
                  {v.log.length > 0 && <details><summary className="small">{t("registro")}</summary><div className="log">{v.log.join("\n")}</div></details>}
                </td>
                <td style={{ whiteSpace: "nowrap" }}>
                  {!v.is_active && v.status === "READY" && <button className="btn small" onClick={() => run(() => post(`/api/scrapers/${v.id}/activate`), t("Versão ativada")).then(reload)}>{t("Ativar")}</button>}
                  {v.status === "DISABLED" && <button className="btn small" onClick={() => run(() => post(`/api/scrapers/${v.id}/enable`), t("Revalidando versão")).then(reload)}>{t("Reativar")}</button>}
                  {v.status !== "DISABLED" && !["GENERATING", "TESTING"].includes(v.status) && <> <button className="btn small" onClick={() => run(() => post(`/api/scrapers/${v.id}/disable`), t("Versão desativada")).then(reload)}>{t("Desativar")}</button></>}
                  {!v.is_active && <> <button className="btn small danger" onClick={() => confirm(t("Excluir esta versão?")) && run(() => del(`/api/scrapers/${v.id}`), t("Versão excluída")).then(reload)}>{t("Excluir")}</button></>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && (
        <Modal title={t("Editar {name}", { name: data.name })} onClose={() => setEditing(false)}>
          <ProviderForm initial={data} onSubmit={(body) => run(() => put(`/api/providers/${data.id}`, body), t("Provedor salvo")).then((r) => { if (r) { setEditing(false); reload(); } })} />
        </Modal>
      )}
      {regen && (
        <Modal title={t("Regenerar scraper")} onClose={() => setRegen(false)}>
          <p className="small">{t("Uma nova versão será criada e testada. A versão ativa só é trocada se a nova passar na validação; você pode voltar a qualquer versão aprovada.")}</p>
          <label className="check"><input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} />{" "}{t("Usar IA")}</label>
          <Field label={t("Prompt adicional")} hint={t("Com prompt, a geração vai direto para a IA. Sem prompt, tenta feed e extração genérica primeiro.")}>
            <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder={t("Ex.: os títulos ficam em h3.card-title; ignore a coluna de opinião")} />
          </Field>
          <button className="btn primary" onClick={() => run(() => post(`/api/providers/${data.id}/regenerate`, { use_ai: useAi, extra_prompt: prompt || null }), t("Regeneração iniciada")).then((r) => { if (r) { setRegen(false); reload(); } })}>{t("Regenerar")}</button>
        </Modal>
      )}
    </div>
  );
}

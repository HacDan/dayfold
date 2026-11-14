import { useState } from "react";
import { t } from "../i18n";
import { del, get, post, put, type AIProvider } from "../api";
import { Empty, Field, Loading, Modal, SectionTitle, Stamp, useAction, useLoad } from "../components/ui";

const PRESETS: Record<string, Partial<AIProvider> & { label: string }> = {
  claude_cli: { label: "Claude Code (CLI)", name: "Claude CLI", kind: "cli", command: "claude -p --model claude-haiku-5-5 --output-format text" },
  codex_cli: { label: "Codex (CLI)", name: "Codex CLI", kind: "cli", command: "codex exec --skip-git-repo-check -s read-only --ephemeral -C /tmp -", image_command: "codex exec --skip-git-repo-check -s workspace-write --ephemeral -" },
  anthropic: { label: "Anthropic API", name: "Anthropic", kind: "anthropic", model: "claude-haiku-5-5" },
  openai: { label: "OpenAI API", name: "OpenAI", kind: "openai", base_url: "https://api.openai.com/v1", model: "gpt-5-mini", image_model: "gpt-image-1" },
  ollama: { label: "Ollama (local)", name: "Ollama", kind: "openai", base_url: "http://localhost:11434/v1", model: "llama3.2" },
  openrouter: { label: "OpenRouter", name: "OpenRouter", kind: "openai", base_url: "https://openrouter.ai/api/v1", model: "" },
};

function AIForm({ initial, onSubmit }: { initial?: Partial<AIProvider>; onSubmit: (b: Record<string, unknown>) => void }) {
  const [f, setF] = useState({
    name: initial?.name ?? "", kind: initial?.kind ?? "cli", base_url: initial?.base_url ?? "", model: initial?.model ?? "",
    api_key: "", command: initial?.command ?? "", image_model: initial?.image_model ?? "", image_command: initial?.image_command ?? "",
    max_tokens: initial?.max_tokens ?? 1500, timeout_s: initial?.timeout_s ?? 120,
  });
  const set = (k: string, v: unknown) => setF((p) => ({ ...p, [k]: v }));
  return (
    <form onSubmit={(e) => {
      e.preventDefault();
      onSubmit({ ...f, base_url: f.base_url || null, model: f.model || null, api_key: f.api_key || null, command: f.command || null, image_model: f.image_model || null, image_command: f.image_command || null });
    }}>
      {!initial?.id && (
        <div className="row" style={{ marginBottom: 14 }}>
          {Object.entries(PRESETS).map(([k, p]) => (
            <button type="button" key={k} className="btn small" onClick={() => setF((old) => ({ ...old, ...Object.fromEntries(Object.entries(p).filter(([kk]) => kk !== "label")) }))}>{p.label}</button>
          ))}
        </div>
      )}
      <div className="grid cols-2" style={{ gap: 14 }}>
        <Field label={t("Nome")}><input type="text" required value={f.name} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label={t("Tipo")}>
          <select value={f.kind} onChange={(e) => set("kind", e.target.value)}>
            <option value="cli">{t("CLI local (stdin → stdout)")}</option>
            <option value="openai">{t("API compatível com OpenAI")}</option>
            <option value="anthropic">{t("API Anthropic")}</option>
          </select>
        </Field>
      </div>
      {f.kind === "cli" ? (
        <Field label={t("Comando")} hint={t("O prompt é enviado pela entrada padrão; a resposta é lida da saída. O comando roda como o usuário do servidor.")}>
          <input type="text" required value={f.command} onChange={(e) => set("command", e.target.value)} />
        </Field>
      ) : (
        <div className="grid cols-2" style={{ gap: 14 }}>
          <Field label={t("URL base")}><input type="text" value={f.base_url} onChange={(e) => set("base_url", e.target.value)} placeholder={f.kind === "anthropic" ? "https://api.anthropic.com" : "https://api.openai.com/v1"} /></Field>
          <Field label={t("Modelo")}><input type="text" value={f.model} onChange={(e) => set("model", e.target.value)} /></Field>
          <Field label={t("Chave de API")} hint={initial?.api_key_set ? t("Salva ({hint}). Deixe vazio para manter.", { hint: initial.api_key_hint ?? t("oculta") }) : t("Fica só no banco local do servidor.")}>
            <input type="password" autoComplete="off" value={f.api_key} onChange={(e) => set("api_key", e.target.value)} />
          </Field>
          {f.kind === "openai" && <Field label={t("Modelo de imagem (charge ilustrada)")} hint={t("opcional")}><input type="text" value={f.image_model} onChange={(e) => set("image_model", e.target.value)} /></Field>}
        </div>
      )}
      <Field label={t("Comando de imagem (charge ilustrada, opcional)")} hint={t("CLI capaz de gerar imagens (ex.: Codex com sua conta ChatGPT). Roda numa pasta temporária e deve salvar um PNG nela.")}>
        <input type="text" value={f.image_command} onChange={(e) => set("image_command", e.target.value)} />
      </Field>
      <div className="grid cols-2" style={{ gap: 14 }}>
        <Field label={t("Máx. tokens por resposta")}><input type="number" min={100} max={16000} value={f.max_tokens} onChange={(e) => set("max_tokens", Number(e.target.value))} /></Field>
        <Field label={t("Tempo limite (s)")}><input type="number" min={10} max={900} value={f.timeout_s} onChange={(e) => set("timeout_s", Number(e.target.value))} /></Field>
      </div>
      <button className="btn primary" type="submit">{t("Salvar")}</button>
    </form>
  );
}

export default function AI() {
  const { run, busy } = useAction();
  const { data, reload } = useLoad(() => get<AIProvider[]>("/api/ai/providers"));
  const [editing, setEditing] = useState<Partial<AIProvider> | null>(null);
  if (!data) return <Loading />;
  const active = data.find((p) => p.is_active);
  return (
    <div>
      <SectionTitle kicker={t("Opcional")} title={t("Inteligência artificial")}>
        <button className="btn primary" onClick={() => setEditing({})}>{t("Adicionar IA")}</button>
        {active && <button className="btn" onClick={() => run(() => post("/api/ai/deactivate"), t("IA desligada; charge e curadoria por IA foram desativadas")).then(reload)}>{t("Desligar IA")}</button>}
      </SectionTitle>
      <div className="grid cols-3 col-rule" style={{ marginBottom: 22 }}>
        <section><p className="kicker">{t("Curadoria")}</p><p className="small">{t("Recebe só as candidatas já filtradas (título + 30 palavras) e devolve um JSON validado com seleção, seção e prioridade. Sem IA, valem as regras e palavras-chave.")}</p></section>
        <section><p className="kicker">{t("Charge")}</p><p className="small">{t("Só existe com IA. No modo roteirizado, a IA escreve um roteiro curto e o servidor desenha; no ilustrado, chama um gerador de imagem.")}</p></section>
        <section><p className="kicker">{t("Scrapers")}</p><p className="small">{t("Quando feed e extração genérica falham, a IA lê um HTML resumido e propõe seletores CSS, que são testados antes de entrar em uso.")}</p></section>
      </div>
      {data.length === 0 && <Empty>{t("Nenhuma IA configurada. O Dayfold funciona normalmente sem ela.")}</Empty>}
      <div className="table-wrap">
        <table className="ledger">
          <thead><tr><th>{t("Nome")}</th><th>{t("Tipo")}</th><th>{t("Modelo / comando")}</th><th>{t("Teste")}</th><th></th></tr></thead>
          <tbody>
            {data.map((p) => (
              <tr key={p.id}>
                <td><span className="name">{p.name}</span> {p.is_active && <Stamp status="ok" label={t("ativa")} />}</td>
                <td className="small">{p.kind}</td>
                <td className="small"><code>{p.kind === "cli" ? p.command : `${p.model ?? ""} ${p.base_url ? "@ " + p.base_url : ""}`}</code>{p.can_generate_images && <div className="muted">{t("imagens:")}{" "}{p.image_command ? "via CLI" : p.image_model}</div>}</td>
                <td className="small">{p.last_test_ok === null ? <span className="muted">{t("não testada")}</span> : <><Stamp status={p.last_test_ok ? "ok" : "bad"} label={p.last_test_ok ? "ok" : "falhou"} /> <span className="muted">{p.last_test_message}</span></>}</td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <button className="btn small" disabled={busy} onClick={() => run(() => post(`/api/ai/providers/${p.id}/test`)).then(reload)}>{busy ? t("Testando…") : t("Testar")}</button>{" "}
                  {!p.is_active && <button className="btn small" onClick={() => run(() => post(`/api/ai/providers/${p.id}/activate`), t("IA ativada")).then(reload)}>{t("Ativar")}</button>}{" "}
                  <button className="btn small" onClick={() => setEditing(p)}>{t("Editar")}</button>{" "}
                  <button className="btn small danger" onClick={() => confirm(t("Excluir {name}?", { name: p.name })) && run(() => del(`/api/ai/providers/${p.id}`), t("IA excluída")).then(reload)}>×</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint" style={{ marginTop: 14 }}>{t("Economia de tokens: a IA nunca recebe o texto completo das matérias e não reescreve notícias; ela só seleciona e organiza.")}</p>
      {editing && (
        <Modal title={editing.id ? t("Editar {name}", { name: editing.name ?? "" }) : t("Nova IA")} onClose={() => setEditing(null)}>
          <AIForm initial={editing} onSubmit={(b) => run(() => (editing.id ? put(`/api/ai/providers/${editing.id}`, b) : post("/api/ai/providers", b)), t("IA salva")).then((r) => { if (r) { setEditing(null); reload(); } })} />
        </Modal>
      )}
    </div>
  );
}

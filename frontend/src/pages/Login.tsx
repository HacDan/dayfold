import { useState } from "react";
import { t } from "../i18n";
import { post } from "../api";

export default function Login({ onDone }: { onDone: () => void }) {
  const [pw, setPw] = useState("");
  const [err, setErr] = useState<string | null>(null);
  return (
    <div className="page" style={{ maxWidth: 460, paddingTop: 80 }}>
      <div className="mast">
        <h1 className="name">{t("Dayfold")}</h1>
        <p className="tag">{t("Sala de redação. Entrada restrita.")}</p>
      </div>
      <hr className="rule thick" />
      <form onSubmit={async (e) => {
        e.preventDefault();
        try { await post("/api/auth/login", { password: pw }); onDone(); } catch (x) { setErr((x as Error).message); }
      }}>
        <label className="field"><span>{t("Senha")}</span><input type="password" autoFocus value={pw} onChange={(e) => setPw(e.target.value)} /></label>
        {err && <p style={{ color: "var(--bad)" }}>{err}</p>}
        <button className="btn primary" type="submit">{t("Entrar")}</button>
      </form>
    </div>
  );
}

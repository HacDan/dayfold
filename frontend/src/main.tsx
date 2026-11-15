import { StrictMode, useEffect, useState } from "react";
import { getLang, setLang, t, type Lang } from "./i18n";
import { applyTheme, effectiveTheme, type Theme } from "./theme";
import { createRoot } from "react-dom/client";
import { BrowserRouter, NavLink, Route, Routes, Link, useLocation } from "react-router-dom";
import "./styles.css";
import { get, post, put, fmtLongDate } from "./api";
import { ToastProvider, Loading } from "./components/ui";
import Overview from "./pages/Overview";
import Editions from "./pages/Editions";
import EditionDetail from "./pages/EditionDetail";
import Providers from "./pages/Providers";
import ProviderDetail from "./pages/ProviderDetail";
import Scrapers from "./pages/Scrapers";
import Newspaper from "./pages/Newspaper";
import Sections from "./pages/Sections";
import Games from "./pages/Games";
import AI from "./pages/AI";
import Logs from "./pages/Logs";
import Kindle from "./pages/Kindle";
import Login from "./pages/Login";

const NAV = [
  ["/", "Capa"],
  ["/edicoes", "Edições"],
  ["/provedores", "Provedores"],
  ["/scrapers", "Scrapers"],
  ["/secoes", "Seções"],
  ["/jornal", "Jornal"],
  ["/jogos", "Jogos"],
  ["/ia", "IA"],
  ["/registros", "Registros"],
  ["/kindle", "Kindle"],
] as const;

/* Inline SVG flags: emoji flags do not render on Windows. */
function Flag({ lang }: { lang: Lang }) {
  if (lang === "pt") {
    return (
      <svg className="flag" viewBox="0 0 20 14" width="18" height="13" aria-hidden="true">
        <rect width="20" height="14" fill="#009739"/>
        <path d="M10 1.6 18.2 7 10 12.4 1.8 7Z" fill="#FEDD00"/>
        <circle cx="10" cy="7" r="3.3" fill="#012169"/>
        <path d="M6.9 6.3q3.2-.9 6.2.9" stroke="#fff" strokeWidth=".6" fill="none"/>
      </svg>
    );
  }
  return (
    <svg className="flag" viewBox="0 0 19 13" width="18" height="13" aria-hidden="true">
      <rect width="19" height="13" fill="#fff"/>
      {[0, 2, 4, 6, 8, 10, 12].map((y) => <rect key={y} y={y} width="19" height="1" fill="#B22234"/>)}
      <rect width="7.6" height="7" fill="#3C3B6E"/>
    </svg>
  );
}

function HeaderControls({ onLang }: { onLang: (l: Lang) => void }) {
  const [theme, setTheme] = useState<Theme>(effectiveTheme());
  const next: Theme = theme === "dark" ? "light" : "dark";
  const lang = getLang();
  return (
    <span className="header-controls">
      <button type="button" className="ctl" onClick={() => { applyTheme(next); setTheme(next); }}
        aria-label={t(next === "dark" ? "Mudar para o tema escuro" : "Mudar para o tema claro")}
        title={t(next === "dark" ? "Mudar para o tema escuro" : "Mudar para o tema claro")}>
        {theme === "dark" ? (
          <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><circle cx="12" cy="12" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.8"/><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>
        ) : (
          <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round"/></svg>
        )}
        <span>{theme === "dark" ? t("Tema claro") : t("Tema escuro")}</span>
      </button>
      <span className="lang-switch" role="group" aria-label={t("Idioma da dashboard")}>
        {(["en", "pt"] as Lang[]).map((l) => (
          <button key={l} type="button" className={l === lang ? "on" : ""} aria-pressed={l === lang}
            onClick={() => l !== lang && onLang(l)} title={l === "pt" ? "Português" : "English"}>
            <Flag lang={l} /><span>{l.toUpperCase()}</span>
          </button>
        ))}
      </span>
    </span>
  );
}

const HINT_KEY = "dayfold.editionLangHint";

/* The dashboard switch only changes the dashboard. When the editions are printed in the other
   language, say so right under it and offer to switch them too (dismissable per language). */
function EditionLangHint() {
  const lang = getLang();
  const [edition, setEdition] = useState<Lang | null>(null);
  const [switched, setSwitched] = useState(false);
  const [hidden, setHidden] = useState(() => {
    try { return localStorage.getItem(HINT_KEY) === lang; } catch { return false; }
  });
  useEffect(() => {
    get<{ values: { newspaper: { language: Lang } } }>("/api/settings").then((s) => setEdition(s.values.newspaper.language)).catch(() => {});
  }, []);
  if (hidden || !edition || (edition === lang && !switched)) return null;
  const dismiss = () => {
    try { localStorage.setItem(HINT_KEY, lang); } catch { /* ignore */ }
    setHidden(true);
  };
  const apply = async () => {
    await put("/api/settings/newspaper", { language: lang });
    setEdition(lang);
    setSwitched(true);
    window.dispatchEvent(new Event("dayfold:settings"));
  };
  const name = (l: Lang) => (l === "pt" ? t("português") : t("inglês"));
  return (
    <p className="lang-hint" role="status">
      {switched ? (
        <span>{t("Pronto: as próximas edições saem em {lang}. Para refazer uma edição existente, use Recompor.", { lang: name(lang) })}</span>
      ) : (
        <>
          <span>{t("As edições são impressas em {lang}.", { lang: name(edition) })}</span>
          <button type="button" className="btn small" onClick={apply}>{t("Imprimir em {lang}", { lang: name(lang) })}</button>
        </>
      )}
      <button type="button" className="ctl" onClick={dismiss} aria-label={t("Dispensar")} title={t("Dispensar")}>×</button>
    </p>
  );
}

function Masthead({ title, onLang }: { title: string; onLang: (l: Lang) => void }) {
  const today = fmtLongDate(new Date());
  return (
    <header>
      <div className="mast">
        <div className="ears"><span>{t("Sala de redação")}</span><HeaderControls onLang={onLang} /></div>
        <EditionLangHint />
        <h1 className="name"><Link to="/">{title}</Link></h1>
        <p className="tag">{t("Painel editorial do seu jornal diário para e-readers")}</p>
      </div>
      <div className="dateline">
        <span>{t("Edição do operador")}</span>
        <span className="center">{today}</span>
        <span>{t("Dayfold 0.1")}</span>
      </div>
      <nav className="sections-nav" aria-label={t("Seções")}>
        {NAV.map(([to, label]) => <NavLink key={to} to={to} end={to === "/"}>{t(label)}</NavLink>)}
      </nav>
    </header>
  );
}

function App() {
  const [auth, setAuth] = useState<{ required: boolean; authenticated: boolean } | null>(null);
  const [title, setTitle] = useState("Dayfold");
  const [lang, setLangState] = useState<Lang>(getLang());
  const changeLang = (l: Lang) => { setLang(l); setLangState(l); };
  const loc = useLocation();

  useEffect(() => {
    get<{ required: boolean; authenticated: boolean }>("/api/auth/status").then(setAuth).catch(() => setAuth({ required: false, authenticated: true }));
    const onUnauth = () => setAuth((a) => (a ? { ...a, authenticated: false } : a));
    window.addEventListener("dayfold:unauthorized", onUnauth);
    return () => window.removeEventListener("dayfold:unauthorized", onUnauth);
  }, []);

  useEffect(() => {
    if (auth?.authenticated) {
      get<{ values: { newspaper: { title: string } } }>("/api/settings").then((s) => {
        setTitle(s.values.newspaper.title);
        document.title = `${s.values.newspaper.title}`;
      }).catch(() => {});
    }
  }, [auth?.authenticated]);

  if (!auth) return <Loading />;
  if (!auth.authenticated) return <Login onDone={() => setAuth({ ...auth, authenticated: true })} />;

  return (
    <div className="page" key={lang}>
      <Masthead title={title} onLang={changeLang} />
      <main key={loc.pathname} className="page-enter">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/edicoes" element={<Editions />} />
          <Route path="/edicoes/:id" element={<EditionDetail />} />
          <Route path="/provedores" element={<Providers />} />
          <Route path="/provedores/:id" element={<ProviderDetail />} />
          <Route path="/scrapers" element={<Scrapers />} />
          <Route path="/secoes" element={<Sections />} />
          <Route path="/jornal" element={<Newspaper onTitle={setTitle} />} />
          <Route path="/jogos" element={<Games />} />
          <Route path="/ia" element={<AI />} />
          <Route path="/registros" element={<Logs />} />
          <Route path="/kindle" element={<Kindle />} />
          <Route path="*" element={<p className="empty">{t("Página não encontrada.")}</p>} />
        </Routes>
      </main>
      <footer className="footer">
        {t("Dayfold · software livre (MIT) · fontes OFL ·")}{" "}
        {auth.required && <button className="btn link" onClick={() => post("/api/auth/logout").then(() => location.reload())}>{t("sair")}</button>}
      </footer>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <ToastProvider>
        <App />
      </ToastProvider>
    </BrowserRouter>
  </StrictMode>,
);

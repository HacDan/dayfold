import { StrictMode, useEffect, useState } from "react";
import { getLang, setLang, t, type Lang } from "./i18n";
import { applyTheme, effectiveTheme, type Theme } from "./theme";
import { createRoot } from "react-dom/client";
import { BrowserRouter, NavLink, Route, Routes, Link, useLocation } from "react-router-dom";
import "./styles.css";
import { get, post, fmtLongDate } from "./api";
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
        {(["pt", "en"] as Lang[]).map((l) => (
          <button key={l} type="button" className={l === lang ? "on" : ""} aria-pressed={l === lang}
            onClick={() => l !== lang && onLang(l)}>{l.toUpperCase()}</button>
        ))}
      </span>
    </span>
  );
}

function Masthead({ title, onLang }: { title: string; onLang: (l: Lang) => void }) {
  const today = fmtLongDate(new Date());
  return (
    <header>
      <div className="mast">
        <div className="ears"><span>{t("Sala de redação")}</span><HeaderControls onLang={onLang} /></div>
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

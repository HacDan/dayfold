import { StrictMode, useEffect, useState } from "react";
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

function Masthead({ title }: { title: string }) {
  const today = fmtLongDate(new Date());
  return (
    <header>
      <div className="mast">
        <div className="ears"><span>Sala de redação</span><span>Self-hosted</span></div>
        <h1 className="name"><Link to="/">{title}</Link></h1>
        <p className="tag">Painel editorial do seu jornal diário para e-readers</p>
      </div>
      <div className="dateline">
        <span>Edição do operador</span>
        <span className="center">{today}</span>
        <span>Dayfold 0.1</span>
      </div>
      <nav className="sections-nav" aria-label="Seções">
        {NAV.map(([to, label]) => <NavLink key={to} to={to} end={to === "/"}>{label}</NavLink>)}
      </nav>
    </header>
  );
}

function App() {
  const [auth, setAuth] = useState<{ required: boolean; authenticated: boolean } | null>(null);
  const [title, setTitle] = useState("Dayfold");
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
        document.title = `${s.values.newspaper.title} | Redação`;
      }).catch(() => {});
    }
  }, [auth?.authenticated]);

  if (!auth) return <Loading />;
  if (!auth.authenticated) return <Login onDone={() => setAuth({ ...auth, authenticated: true })} />;

  return (
    <div className="page">
      <Masthead title={title} />
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
          <Route path="*" element={<p className="empty">Página não encontrada.</p>} />
        </Routes>
      </main>
      <footer className="footer">
        Dayfold · software livre (MIT) · fontes OFL ·{" "}
        {auth.required && <button className="btn link" onClick={() => post("/api/auth/logout").then(() => location.reload())}>sair</button>}
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

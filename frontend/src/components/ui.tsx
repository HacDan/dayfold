import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState, type ImgHTMLAttributes, type ReactNode } from "react";
import { t } from "../i18n";
import { STATUS_LABEL } from "../api";

// ---------------------------------------------------------------- data hooks

export function useLoad<T>(load: () => Promise<T>, deps: unknown[] = [], pollMs?: number | ((data: T | null) => number | undefined)) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const loadRef = useRef(load);
  loadRef.current = load;
  const reload = useCallback(async () => {
    try {
      const d = await loadRef.current();
      setData(d);
      setError(null);
      return d;
    } catch (e) {
      setError((e as Error).message);
      return null;
    }
  }, []);
  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    const tick = async () => {
      const d = await reload();
      if (!alive) return;
      const ms = typeof pollMs === "function" ? pollMs(d) : pollMs;
      if (ms) timer = window.setTimeout(tick, ms);
    };
    tick();
    return () => {
      alive = false;
      if (timer) window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error, reload, setData };
}

// ---------------------------------------------------------------- toast

type ToastFn = (msg: string, bad?: boolean) => void;
const ToastCtx = createContext<ToastFn>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<{ msg: string; bad: boolean } | null>(null);
  const show = useCallback<ToastFn>((msg, bad = false) => {
    setToast({ msg, bad });
    window.setTimeout(() => setToast(null), 4200);
  }, []);
  return (
    <ToastCtx.Provider value={show}>
      {children}
      {toast && <div className={`toast${toast.bad ? " bad" : ""}`} role="status">{toast.msg}</div>}
    </ToastCtx.Provider>
  );
}

/** Wrap an async action: shows errors as toast, returns result or null. */
export function useAction() {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const run = useCallback(async <T,>(fn: () => Promise<T>, ok?: string): Promise<T | null> => {
    setBusy(true);
    try {
      const r = await fn();
      if (ok) toast(ok);
      return r;
    } catch (e) {
      toast((e as Error).message, true);
      return null;
    } finally {
      setBusy(false);
    }
  }, [toast]);
  return { run, busy };
}

// ---------------------------------------------------------------- bits

const RUNNING = new Set(["GENERATING", "TESTING", "RUNNING", "QUEUED", "PENDING", "BUILDING"]);

export function Stamp({ status, label }: { status: string; label?: string }) {
  // Animate only when the status changes while the stamp is on screen, never on first render.
  const prev = useRef(status);
  const [changed, setChanged] = useState(false);
  useEffect(() => {
    if (prev.current !== status) {
      prev.current = status;
      setChanged(false);
      requestAnimationFrame(() => setChanged(true));
    }
  }, [status]);
  return (
    <span className={`stamp ${status}${RUNNING.has(status) ? " spin" : ""}`} data-changed={changed}>
      {label ?? (STATUS_LABEL[status] ? t(STATUS_LABEL[status]) : status)}
    </span>
  );
}

/** Image that "comes off the press" once loaded. */
export function PressImage(props: ImgHTMLAttributes<HTMLImageElement>) {
  const ref = useRef<HTMLImageElement>(null);
  const [state, setState] = useState<"pending" | "fresh" | "cached">("pending");
  useLayoutEffect(() => {
    if (ref.current?.complete && ref.current.naturalWidth) setState("cached"); // seen before: no reveal
  }, []);
  return <img ref={ref} {...props} data-loaded={state}
    onLoad={(e) => { setState((s) => (s === "pending" ? "fresh" : s)); props.onLoad?.(e); }} />;
}

export function SectionTitle({ kicker, title, children }: { kicker?: string; title: string; children?: ReactNode }) {
  return (
    <div className="section-title">
      <div>
        {kicker && <p className="kicker">{kicker}</p>}
        <h2>{title}</h2>
      </div>
      {children && <div className="actions">{children}</div>}
    </div>
  );
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-bg" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
          <h2 style={{ margin: 0 }}>{title}</h2>
          <button className="btn small" onClick={onClose}>{t("Fechar")}</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Press({ value }: { value: number }) {
  return <div className="press" aria-label={`${Math.round(value * 100)}%`}><div style={{ transform: `scaleX(${Math.max(0.02, value)})` }} /></div>;
}

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <div className="hint">{hint}</div>}
    </label>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Loading() {
  return <p className="muted center" style={{ padding: 40 }}><em>{t("Compondo a página…")}</em></p>;
}

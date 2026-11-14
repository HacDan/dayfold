import { locale, t } from "./i18n";
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function detail(body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return d.map((e) => (e as { msg?: string }).msg ?? JSON.stringify(e)).join("; ");
  }
  return "erro inesperado / unexpected error";
}

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, ...rest } = init;
  const res = await fetch(path, {
    credentials: "same-origin",
    ...rest,
    headers: { ...(json !== undefined ? { "content-type": "application/json" } : {}), ...(rest.headers ?? {}) },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  const ct = res.headers.get("content-type") ?? "";
  const body = ct.includes("json") ? await res.json() : await res.text();
  if (res.status === 401 && !path.startsWith("/api/auth")) window.dispatchEvent(new Event("dayfold:unauthorized"));
  if (!res.ok) throw new ApiError(res.status, detail(body));
  return body as T;
}

export const get = <T,>(p: string) => api<T>(p);
export const post = <T,>(p: string, json?: unknown) => api<T>(p, { method: "POST", json: json ?? {} });
export const put = <T,>(p: string, json: unknown) => api<T>(p, { method: "PUT", json });
export const del = <T,>(p: string) => api<T>(p, { method: "DELETE" });

// ---- types -------------------------------------------------------------

export type Job = {
  id: number; trigger: string; status: string; step: string | null; progress: number; log: string[];
  error: string | null; edition_id: number | null; created_at: string; started_at: string | null; finished_at: string | null;
};

export type EditionSummary = {
  id: number; number: number; date: string; title: string; status: string; headline: string | null;
  stats: Record<string, number | boolean>; curated_by: string; created_at: string; has_epub: boolean;
  cover_url: string | null; epub_url: string | null;
};

export type Typography = { masthead: number; headline: number; title: number; subtitle: number; body: number; line_height: number };

export type Newspaper = {
  title: string; tagline: string; masthead_font: string; language: "pt" | "en"; max_articles: number;
  excerpt_words: number; include_images: boolean; include_charge: boolean; include_games: boolean; games_per_edition: number;
  closing_order: ("news" | "charge" | "games")[]; typography: Typography;
};

export type Settings = {
  values: {
    newspaper: Newspaper;
    schedule: { enabled: boolean; time: string; timezone: string };
    curation: { use_ai: boolean; max_age_hours: number; languages: string[]; blocked_keywords: string[]; ai_candidates: number; per_provider_limit: number };
    charge: { mode: "structured" | "illustrated"; style: string };
    device: { cover_width: number; cover_height: number; image_max_width: number; screensaver_cover: boolean };
    distribution: { feed_token: string; keep_editions: number };
  };
  meta: {
    masthead_fonts: { key: string; label: string; family: string; file: string; license: string }[];
    type_ranges: Record<keyof Typography, { min: number; default: number; max: number }>;
    ai_available: boolean;
  };
};

export type Version = {
  id: number; provider_id: number; version: number; strategy: string; spec: Record<string, unknown>; status: string;
  origin: string; prompt: string | null; test_report: TestReport | null; log: string[]; is_active: boolean;
  created_at: string; updated_at: string; provider_name?: string;
};

export type TestReport = {
  ok: boolean; count: number; with_body: number; with_date: number; with_author: number; with_image: number;
  sample: { title: string; url: string; published_at: string | null; author: string | null }[]; reasons: string[]; error: string | null;
};

export type ScraperJob = {
  id: number; provider_id: number; version_id: number | null; kind: string; use_ai: boolean; extra_prompt: string | null;
  status: string; log: string[]; error: string | null; created_at: string; finished_at: string | null;
};

export type Provider = {
  id: number; slug: string; name: string; base_url: string; source_type: string; category: string; categories: string[]; language: string;
  enabled: boolean; usage_mode: string; license_name: string; license_url: string | null; license_note: string;
  is_default: boolean; max_items: number; active_version_id: number | null; active_version: Version | null;
  latest_status: string | null; latest_version: number | null; last_run_at: string | null; last_run_ok: boolean | null;
  last_run_message: string | null; last_run_count: number | null; versions?: Version[]; jobs?: ScraperJob[];
};

export type Topic = { id: number; slug: string; name: string; keywords: string[]; weight: number; enabled: boolean; max_articles: number; position: number };

export type AIProvider = {
  id: number; name: string; kind: "openai" | "anthropic" | "cli"; base_url: string | null; model: string | null;
  api_key_set: boolean; api_key_hint: string | null; command: string | null; image_model: string | null; image_command: string | null;
  max_tokens: number; timeout_s: number; is_active: boolean; last_test_ok: boolean | null; last_test_message: string | null;
  can_generate_images: boolean;
};

export type Game = { id: number; kind: "sudoku" | "wordle" | "wordsearch" | "crossword"; name: string; enabled: boolean; position: number; config: Record<string, string | number> };

export type Overview = {
  today: string; newspaper: Newspaper; latest_edition: EditionSummary | null; last_job: Job | null; next_run: string | null;
  schedule: { enabled: boolean; time: string; timezone: string };
  providers: { total: number; active: number; failing: number }; scrapers: { pending: number; failed_jobs: number };
  ai: { active: boolean; name: string | null; kind: string | null; session_usage: { calls: number; prompt_chars: number; completion_chars: number } };
  games: { kind: string; name: string; enabled: boolean }[]; charge: { enabled: boolean; available: boolean };
  recent_editions: EditionSummary[];
};

export const USAGE_LABEL: Record<string, string> = {
  metadata_only: "Só metadados",
  excerpt_and_link: "Excerto + link",
  full_content_allowed: "Texto integral",
};

export const STATUS_LABEL: Record<string, string> = {
  PENDING: "Pendente", GENERATING: "Gerando", TESTING: "Testando", READY: "Pronto", FAILED: "Falhou",
  DISABLED: "Desativado", QUEUED: "Na fila", RUNNING: "Rodando", SUCCEEDED: "Concluído", BUILDING: "Montando",
  ARCHIVED: "Arquivado",
};

export const fmtDateTime = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString(locale(), { dateStyle: "short", timeStyle: "short" }) : t("nunca");

export const fmtLongDate = (d: Date) =>
  d.toLocaleDateString(locale(), { weekday: "long", day: "numeric", month: "long", year: "numeric" });

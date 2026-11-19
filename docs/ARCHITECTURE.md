# Dayfold architecture

Dayfold is a self-hosted daily newspaper for e-readers. The server does all the heavy
work (collection, extraction, curation, typesetting, cover, cartoon and games) and the
e-reader only reads an offline file.

```
                   ┌──────────────────────── home server ─────────────────────────┐
                   │                                                              │
  RSS / Atom ────▶ │  sources/      collect ─▶ extract ─▶ dedupe ─▶ filter         │
  HTML pages ────▶ │  (rss, generic,         (trafilatura)          (date, lang,   │
                   │   selectors)                                    keywords)     │
                   │                                  │                           │
                   │                                  ▼                           │
                   │  curation/   deterministic score ─▶ optional AI selection     │
                   │                                  │   (JSON, validated)        │
                   │                                  ▼                           │
                   │  edition/    cover (Pillow) + EPUB (EbookLib + Jinja2 + CSS)  │
                   │  games/      sudoku, wordle, word search, crossword (per day) │
                   │  charge/     structured cartoon (AI script ─▶ Pillow) or      │
                   │              illustrated (image API)                          │
                   │                                  │                           │
                   │  api/ (FastAPI) ── dashboard (React, served by the same app)  │
                   │                 ── /feed: latest.epub, games.json, OPDS       │
                   └──────────────────────────────────┼───────────────────────────┘
                                                      │ Wi-Fi, once a day
                                                      ▼
                         Kindle + KOReader + dayfold.koplugin (offline reading)
```

## Technical decisions

| Area | Decision | Why |
| --- | --- | --- |
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2, SQLite (WAL) | Best ecosystem for feeds and extraction; one file database fits a home server. |
| Jobs | Jobs table in SQLite + one worker thread | Survives restarts, no Redis. Jobs left `RUNNING` on boot are marked `FAILED`, and the edition an interrupted generation was building is discarded. A failed generation is tried once more; scrapers are not. |
| Scheduling | APScheduler `CronTrigger` rebuilt whenever settings change | Configurable weekdays, time and timezone from the dashboard. A run missed while the machine was off is made up at startup (`catch_up()`), unless today is not a print day or today's paper is already printed. |
| Extraction | feedparser + Trafilatura; Playwright only if installed and requested | Most institutional sources publish feeds; a browser is heavy and optional. |
| Custom scrapers | **Declarative selector specs (JSON)**, not generated code | AI output is data that the engine validates and runs in a subprocess with a timeout. No arbitrary code execution. |
| AI | Adapters: OpenAI compatible (OpenAI, Ollama, OpenRouter, LM Studio), Anthropic, CLI (`claude -p`, `codex exec`, any command reading stdin) | AI is optional; every AI call returns JSON validated by Pydantic. |
| EPUB | EbookLib, Jinja2 templates, embedded OFL fonts, CSS sized in `em` | EPUB is the base format. Fonts are embedded so the masthead looks the same on any reader. |
| Images | Pillow, 8 bit grayscale, 16 level palette, dithering for photos | Ready for e-ink, nothing left to process on the device. |
| Dashboard | React + TypeScript + Vite, hand written editorial CSS | No UI kit: the product must look like a newspaper, not a SaaS. |
| Kindle | KOReader + `dayfold.koplugin` | The stock Kindle reader does not open EPUB. KOReader does, and the plugin adds sync and interactive games. |
| Kindle without jailbreak | Send to Kindle by e-mail (`delivery/kindle_mail.py`, Gmail SMTP) | Amazon converts the EPUB. A native variant (`*.kindle.epub`, `*.kindle-games.epub`) drops the KOReader links and keeps answers after an "Answers ahead" page. |
| Auth | Optional dashboard password (signed cookie) + feed token for devices | Simple for a LAN, safe enough behind Tailscale. |

## Data model

| Table | Purpose |
| --- | --- |
| `settings` | Key/value JSON: newspaper, typography, schedule, curation, charge, distribution. |
| `ai_providers` | Configured AI backends (kind, base URL, model, API key, command). One is marked active. |
| `topics` | Sections with keywords and weight (Brasil, Mundo, Ciência...). |
| `providers` | Sources: name, base URL, source type, category, language, usage mode, license note, active version. |
| `scraper_versions` | Versioned scraper specs per provider with status `PENDING / GENERATING / TESTING / READY / FAILED / DISABLED`, test report and logs. |
| `scraper_jobs` | Creation or regeneration requests (with the extra prompt) and their state. |
| `articles` | Collected items: title, subtitle, author, date, provider, URL, image, body, excerpt, hash, language. |
| `editions` | One generated issue: number, date, title, status, files, stats. |
| `edition_articles` | Which articles went into an edition, their section, order and priority. |
| `article_ratings` | Reader ratings from "Rate edition" (-1, 0, 1), with provider, section and title copied so they outlive the edition. |
| `games` | Game catalog (`sudoku`, `wordle`, `wordsearch`, `crossword`), enabled flag, order and per game config. |
| `game_instances` | Puzzles generated for an edition (puzzle and solution JSON). |
| `generation_jobs` | Edition generations with step, progress and log lines. |
| `charge_assets` | Cartoon for an edition: mode, script JSON, image path, status. |

## Generation flow

1. `generation_jobs` row created (cron, startup catch-up or "Gerar jornal agora").
2. **Collect**: every active provider runs its `READY` scraper version in an isolated
   subprocess (timeout, size limits). Results are normalized into `articles`.
3. **Respect usage mode**: `metadata_only` stores title and metadata, `excerpt_and_link`
   keeps a short excerpt (default 60 words), `full_content_allowed` keeps the body.
4. **Dedupe** by normalized URL, then by title similarity (token Jaccard).
5. **Filter** by maximum age, language, active sections and blocked keywords.
6. **Curate**: deterministic score (section keywords, recency, has body, has image), plus a
   bonus learned from the reader ratings (`pipeline/feedback.py`: provider, section and title
   words, smoothed and decayed with a 60 day half life).
   With AI on, only the top N candidates go to the model as compact lines
   (`id | section guess | title | 30 word excerpt`), and the model returns
   `{"selected": [{"id", "section", "priority"}], "headline_id"}`. Invalid answers fall
   back to the deterministic ranking.
7. **Games** are generated with a seed derived from the edition date.
8. **Charge** (only when AI is configured): the model writes a cartoon script from the
   top headlines, the renderer draws it; image mode calls an image API instead.
9. **Typeset**: cover PNG, EPUB with cover, sections, articles, charge, games and
   solutions, plus `games.json` for the KOReader plugin.
10. Edition becomes `READY` and is exposed at `/feed/latest.epub` and in OPDS.

One paper per day: a rerun (manual, cron or catch-up) first discards what an earlier failed or
interrupted attempt left in `BUILDING` or `FAILED`, and a failure after the paper is typeset is
not retried, so a day never ends up with a phantom edition next to its paper.

## Scraper lifecycle

```
new provider ─▶ PENDING ─▶ GENERATING ─▶ TESTING ─▶ READY ──▶ (activated)
                                  │            │
                                  └────────────┴──▶ FAILED (previous version stays active)
```

Assisted creation tries, in order: feed autodiscovery (`<link rel=alternate>`, common
paths, sitemap), generic extraction (heuristic links + Trafilatura) and only then asks the
AI for a selector spec built from a trimmed HTML sample. Each attempt is tested; the
version is activated only if it returns enough valid articles. Rollback is selecting an
older `READY` version.

## Reading flow on the Kindle

* **EPUB only**: cover (which is the front page), sections, charge, games (printable Sudoku and word
  search, "pocket Wordle" with tappable guesses) and solutions behind links. Works in
  any reader.
* **KOReader plugin**: downloads the latest edition and `games.json` over Wi-Fi, opens it,
  and when the reader reaches the end of the edition (or taps a game link) opens the
  interactive game in place, keeps progress per edition and returns to the page you came
  from.

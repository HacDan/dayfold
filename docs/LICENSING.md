# Content licensing and copyright

Dayfold is software. It does not grant you any right over the news you collect with it.
**The person who runs a Dayfold server is responsible for checking the terms of use of every
source they enable.** This page explains how Dayfold helps with that and what it cannot do.

## Usage modes

Every provider has a usage mode, enforced when an article is stored (not only when it is shown):

| Mode | Stored and printed | When to use |
| --- | --- | --- |
| `full_content_allowed` | Title, subtitle, author, date, full text, main photo | The source publishes under an open license (Creative Commons, public domain) or explicitly allows reproduction with credit. |
| `excerpt_and_link` (default) | Title, metadata, an excerpt of up to N words (default 70) and the link | The license is unclear or does not allow republication. |
| `metadata_only` | Title, author, date, source and link | Even an excerpt is not clearly allowed. |

Photos are kept only for `full_content_allowed` providers, because images often carry rights
that differ from the text (agency photographers, stock images). Every article in the edition
shows its author, date and source, and the colophon lists every source with its license note.

## Default providers

The defaults favor official, institutional and open sources. The license column is what the
project found when the defaults were chosen; **terms change, so verify before relying on it.**

| Provider | Section | Mode | Basis |
| --- | --- | --- | --- |
| Agência Brasil (EBC) | Brasil | full text | Creative Commons Attribution, per the EBC terms |
| Agência Senado | Brasil | full text | Reproduction allowed with credit to the agency |
| Agência Câmara de Notícias | Brasil | full text | Reproduction allowed with the agency signature |
| Portal gov.br | Brasil | full text | CC BY-ND 3.0 (text shown unchanged) |
| Ministério da Cultura (gov.br) | Cultura | full text | CC BY-ND 3.0 |
| ONU News (Portuguese) | Mundo | excerpt | UN terms do not clearly grant republication |
| European Commission Press Corner | Mundo | full text | Reuse allowed with acknowledgement (Decision 2011/833/EU) |
| World Health Organization | Saúde | excerpt | News pages are copyrighted by WHO |
| Agência Fiocruz de Notícias | Saúde | excerpt | Terms not verified |
| NASA | Espaço | full text | U.S. government work, generally not copyrighted |
| NOAA | Ciência | full text | U.S. government work |
| U.S. National Science Foundation | Ciência | full text | U.S. government work |
| Kubernetes Blog | Tecnologia | full text | CC BY 4.0 |
| Python Insider, Python Software Foundation, Mozilla, Linux Foundation | Tecnologia | excerpt | No explicit open license on the blogs |

Large private outlets are intentionally not included. You can add any source, but Dayfold will
not guess its license: new providers start as `excerpt_and_link` unless you change it.

## Scraping etiquette

* Feeds are preferred over scraping; HTML scrapers respect `robots.txt`.
* Requests are throttled per host (one per second) and identify themselves with a Dayfold user agent.
* Scraping runs once a day, at the time you configure.

## Private use

Dayfold is designed for a personal edition on your own devices. Do not publish the generated
EPUB files or expose the feed endpoints to the internet unless every source you use allows it.

## Fonts and code

* Code: MIT (see `LICENSE`).
* Fonts bundled in `backend/dayfold/assets/fonts` and embedded in every EPUB: Chomsky,
  UnifrakturMaguntia, UnifrakturCook, Playfair Display, Literata and Old Standard TT, all under
  the SIL Open Font License 1.1 (license files in `assets/fonts/licenses`).

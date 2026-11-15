"""Default providers, sections and games installed on first run.

License notes are a starting point, not legal advice: the server operator must check
the terms of every enabled source (see docs/LICENSING.md). When the license is unclear
the provider defaults to ``excerpt_and_link``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Game, Provider, ScraperStatus, ScraperVersion, Setting, Topic, UsageMode

FULL = UsageMode.FULL_CONTENT_ALLOWED
EXCERPT = UsageMode.EXCERPT_AND_LINK

DEFAULT_PROVIDERS: list[dict] = [
    # Brasil
    dict(
        slug="agencia-brasil", name="Agência Brasil", category="brasil", language="pt",
        base_url="https://agenciabrasil.ebc.com.br",
        feed="https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml",
        usage_mode=FULL, license_name="CC BY 4.0 (com crédito)",
        license_url="https://agenciabrasil.ebc.com.br/termos-de-uso",
        license_note="Conteúdo da EBC liberado com atribuição. Fotos podem ter outra licença.",
    ),
    dict(
        slug="agencia-senado", name="Agência Senado", category="brasil", language="pt",
        base_url="https://www12.senado.leg.br/noticias",
        feed="https://www12.senado.leg.br/noticias/feed/todasnoticias/RSS",
        usage_mode=FULL, license_name="Reprodução permitida com citação da fonte",
        license_url="https://www12.senado.leg.br/noticias/institucional/termos",
        license_note="Reprodução permitida desde que citada a Agência Senado.",
    ),
    dict(
        slug="agencia-camara", name="Agência Câmara de Notícias", category="brasil",
        language="pt", base_url="https://www.camara.leg.br/noticias",
        feed="https://www.camara.leg.br/noticias/rss/ultimas-noticias",
        usage_mode=FULL, license_name="Reprodução autorizada com assinatura",
        license_url="https://www.camara.leg.br/noticias",
        license_note="Reprodução autorizada desde que contenha a assinatura 'Agência Câmara Notícias'.",
    ),
    dict(
        slug="gov-br", name="Portal gov.br", category="brasil", language="pt",
        base_url="https://www.gov.br", feed="https://www.gov.br/pt-br/noticias/RSS",
        usage_mode=FULL, license_name="CC BY-ND 3.0",
        license_url="https://creativecommons.org/licenses/by-nd/3.0/deed.pt",
        license_note="Sem obras derivadas: o texto é exibido sem alterações.",
    ),
    # Mundo
    dict(
        slug="onu-news-pt", name="ONU News", category="mundo", language="pt",
        base_url="https://news.un.org/pt",
        feed="https://news.un.org/feed/subscribe/pt/news/all/rss.xml",
        usage_mode=EXCERPT, license_name="Termos da ONU (verificar)",
        license_url="https://www.un.org/en/about-us/terms-of-use",
        license_note="Licença de republicação não é explícita: usar excerto e link.",
    ),
    dict(
        slug="european-commission", name="European Commission Press Corner", category="mundo",
        language="en", base_url="https://ec.europa.eu/commission/presscorner",
        feed="https://ec.europa.eu/commission/presscorner/api/rss?language=en",
        usage_mode=FULL, license_name="CC BY 4.0 (Decisão 2011/833/UE)",
        license_url="https://commission.europa.eu/legal-notice_en",
        license_note="Reutilização permitida com reconhecimento da fonte.",
    ),
    # Saúde
    dict(
        slug="who-news", name="World Health Organization", category="saude", language="en",
        base_url="https://www.who.int", feed="https://www.who.int/rss-feeds/news-english.xml",
        usage_mode=EXCERPT, license_name="Copyright WHO (verificar)",
        license_url="https://www.who.int/about/policies/publishing/copyright",
        license_note="Notícias não têm licença aberta explícita: usar excerto e link.",
    ),
    dict(
        slug="fiocruz", name="Agência Fiocruz de Notícias", category="saude", language="pt",
        base_url="https://agencia.fiocruz.br", feed="https://agencia.fiocruz.br/rss.xml",
        usage_mode=EXCERPT, license_name="Verificar termos",
        license_url="https://agencia.fiocruz.br",
        license_note="Termos de republicação não verificados: usar excerto e link.",
    ),
    # Ciência e espaço
    dict(
        slug="nasa", name="NASA", category="espaco", language="en",
        base_url="https://www.nasa.gov", feed="https://www.nasa.gov/news-release/feed/",
        usage_mode=FULL, license_name="Domínio público (governo dos EUA)",
        license_url="https://www.nasa.gov/nasa-brand-center/images-and-media/",
        license_note="Material da NASA em geral não tem copyright; logos e terceiros têm regras próprias.",
    ),
    dict(
        slug="noaa", name="NOAA", category="ciencia", language="en",
        base_url="https://www.noaa.gov", feed="https://www.noaa.gov/rss.xml",
        usage_mode=FULL, license_name="Domínio público (governo dos EUA)",
        license_url="https://www.noaa.gov/disclaimer",
        license_note="Obras de servidores federais dos EUA são domínio público.",
    ),
    dict(
        slug="nsf", name="U.S. National Science Foundation", category="ciencia", language="en",
        base_url="https://www.nsf.gov/news", feed="https://www.nsf.gov/rss/rss_www_news.xml",
        usage_mode=FULL, license_name="Domínio público (governo dos EUA)",
        license_url="https://www.nsf.gov/policies/site-policies",
        license_note="Textos de servidores federais dos EUA; imagens podem ter créditos de terceiros.",
    ),
    # Tecnologia
    dict(
        slug="kubernetes-blog", name="Kubernetes Blog", category="tecnologia", language="en",
        base_url="https://kubernetes.io/blog/", feed="https://kubernetes.io/feed.xml",
        usage_mode=FULL, license_name="CC BY 4.0",
        license_url="https://github.com/kubernetes/website/blob/main/LICENSE",
        license_note="Documentação e blog sob CC BY 4.0.",
    ),
    dict(
        slug="python-insider", name="Python Insider", category="tecnologia", language="en",
        base_url="https://blog.python.org", feed="https://blog.python.org/feeds/posts/default",
        usage_mode=EXCERPT, license_name="Verificar termos", license_url="https://blog.python.org",
        license_note="Sem licença explícita no blog: usar excerto e link.",
    ),
    dict(
        slug="psf-blog", name="Python Software Foundation", category="tecnologia",
        language="en", base_url="https://pyfound.blogspot.com",
        feed="https://pyfound.blogspot.com/feeds/posts/default",
        usage_mode=EXCERPT, license_name="Verificar termos", license_url="https://pyfound.blogspot.com",
        license_note="Sem licença explícita no blog: usar excerto e link.",
    ),
    dict(
        slug="mozilla-blog", name="Mozilla Blog", category="tecnologia", language="en",
        base_url="https://blog.mozilla.org", feed="https://blog.mozilla.org/en/feed/",
        usage_mode=EXCERPT, license_name="Verificar termos",
        license_url="https://www.mozilla.org/en-US/about/legal/terms/mozilla/",
        license_note="Termos do site da Mozilla: usar excerto e link.",
    ),
    dict(
        slug="linux-foundation", name="Linux Foundation", category="tecnologia", language="en",
        base_url="https://www.linuxfoundation.org/blog",
        feed="https://www.linuxfoundation.org/blog/rss.xml",
        usage_mode=EXCERPT, license_name="Verificar termos",
        license_url="https://www.linuxfoundation.org/legal/terms",
        license_note="Termos do site: usar excerto e link.",
    ),
    # Cultura institucional
    dict(
        slug="agencia-gov-cultura", name="Ministério da Cultura (gov.br)", category="cultura",
        language="pt", base_url="https://www.gov.br/cultura",
        feed="https://www.gov.br/cultura/RSS",
        usage_mode=FULL, license_name="CC BY-ND 3.0",
        license_url="https://creativecommons.org/licenses/by-nd/3.0/deed.pt",
        license_note="Sem obras derivadas: o texto é exibido sem alterações.",
    ),
]

DEFAULT_TOPICS: list[dict] = [
    dict(slug="brasil", name="Brasil", keywords=["brasil", "governo", "senado", "câmara",
         "ministério", "lula", "stf", "economia", "estado"], weight=1.2, max_articles=5),
    dict(slug="mundo", name="Mundo", keywords=["onu", "world", "europe", "guerra", "paz",
         "international", "global", "refugiados"], weight=1.1, max_articles=4),
    dict(slug="ciencia", name="Ciência", keywords=["ciência", "science", "pesquisa",
         "research", "climate", "clima", "study", "data"], weight=1.0, max_articles=3),
    dict(slug="espaco", name="Espaço", keywords=["nasa", "space", "moon", "mars", "artemis",
         "telescope", "orbit", "espaço"], weight=1.0, max_articles=3),
    dict(slug="saude", name="Saúde", keywords=["saúde", "health", "vacina", "vaccine",
         "doença", "disease", "sus", "who"], weight=1.0, max_articles=3),
    dict(slug="tecnologia", name="Tecnologia", keywords=["python", "kubernetes", "linux",
         "open source", "software", "ai", "inteligência artificial", "firefox"], weight=0.9,
         max_articles=3),
    dict(slug="cultura", name="Cultura", keywords=["cultura", "museu", "arte", "livro",
         "cinema", "música", "patrimônio", "festival"], weight=0.8, max_articles=2),
]

DEFAULT_GAMES: list[dict] = [
    dict(kind="sudoku", name="Sudoku", position=0,
         config={"difficulty": "medium", "count": 1}),
    dict(kind="wordle", name="Palavra do Dia", position=1,
         config={"language": "pt", "length": 5, "attempts": 6}),
    dict(kind="wordsearch", name="Caça-palavras", position=2,
         config={"language": "pt", "size": 12, "theme": "news", "words": 10}),
    dict(kind="crossword", name="Palavras Cruzadas", position=3,
         config={"language": "pt", "words": 10, "size": 13}),
]


# Install-wide record of what has already been seeded, kept in the settings table so no schema
# change is needed. Once a default list has been installed, an empty one stays empty: deleting
# every section (or every provider) must not bring the Portuguese defaults back on restart.
SEED_KEY = "seed"


def _seed_state(session: Session) -> dict:
    row = session.get(Setting, SEED_KEY)
    return dict(row.value or {}) if row is not None else {}


def _mark_seeded(session: Session, name: str) -> None:
    row = session.get(Setting, SEED_KEY)
    state = dict(row.value or {}) if row is not None else {}
    state[name] = True
    if row is None:
        session.add(Setting(key=SEED_KEY, value=state))
    else:
        row.value = state
    session.flush()


def seed(session: Session) -> None:
    state = _seed_state(session)
    if not state.get("topics"):
        if session.scalar(select(Topic.id).limit(1)) is None:
            for i, t in enumerate(DEFAULT_TOPICS):
                session.add(Topic(position=i, **t))
        _mark_seeded(session, "topics")

    # Games added in later versions are appended to the end of existing installs.
    existing = {k: p for k, p in session.execute(select(Game.kind, Game.position))}
    last = max(existing.values(), default=-1)
    for g in DEFAULT_GAMES:
        if g["kind"] not in existing:
            if existing:
                last += 1
                g = {**g, "position": last}
            session.add(Game(**g))

    if session.scalar(select(Provider.id).limit(1)) is None:
        for p in DEFAULT_PROVIDERS:
            data = dict(p)
            feed = data.pop("feed")
            provider = Provider(source_type="rss", is_default=True, **data)
            session.add(provider)
            session.flush()
            version = ScraperVersion(
                provider_id=provider.id, version=1, strategy="rss", spec={"feed_url": feed},
                status=ScraperStatus.READY, origin="default",
                log=["Versão padrão: feed RSS/Atom oficial."],
            )
            session.add(version)
            session.flush()
            provider.active_version_id = version.id
    session.flush()

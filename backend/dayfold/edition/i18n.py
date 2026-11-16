from __future__ import annotations

from datetime import date, datetime

WEEKDAYS = {
    "pt": ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira",
           "Sábado", "Domingo"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
}
MONTHS = {
    "pt": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
           "setembro", "outubro", "novembro", "dezembro"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
}

LABELS = {
    "pt": {
        "edition": "Edição", "number": "Nº", "year": "Ano", "by": "Por", "source": "Fonte",
        "in_this_edition": "Nesta edição", "front_page": "Primeira página",
        "read_more": "Leia a íntegra na fonte", "continues": "A matéria continua na fonte",
        "excerpt_note": "Excerto. Texto integral em",
        "metadata_note": "Somente título e dados. Matéria completa em",
        "charge": "A Charge", "charge_kicker": "Humor", "games": "Passatempos",
        "solutions": "Soluções", "see_solution": "Ver solução", "back": "Voltar",
        "play_koreader": "Jogar no KOReader", "colophon": "Expediente",
        "clues": "pistas",
        "sudoku_help": "Preencha a grade para que cada linha, coluna e bloco 3×3 tenha os números de 1 a 9.",
        "wordle": "Palavra do Dia",
        "wordle_help": "Descubra a palavra de {n} letras. No KOReader, jogue com até {a} tentativas. "
                        "Aqui, toque em uma das palavras abaixo para ver as dicas.",
        "wordle_help_native": "Descubra a palavra de {n} letras. Toque em uma das palavras abaixo "
                               "para ver as dicas e use Voltar para tentar outra.",
        "answers_ahead": "Respostas a seguir",
        "answers_ahead_note": "Fim da edição. Depois desta página vêm as soluções e as dicas dos "
                              "passatempos. Pare aqui se ainda estiver jogando.",
        "test_title": "Teste do Kindle",
        "test_intro": "Edição de teste com todos os passatempos, para validar o Kindle sem jailbreak. "
                      "Confira cada item abaixo no aparelho:",
        "test_checks": [
            "Vire as páginas do começo ao fim, sem tocar em links. Nenhuma solução e nenhuma dica do {wordle} deve aparecer antes da página “Respostas a seguir”.",
            "Depois de “Respostas a seguir”, continue virando. Se aparecerem soluções ou dicas, o Kindle ignorou as páginas ocultas: mantenha os jogos desligados na versão Kindle nativo.",
            "No {wordle}, toque em uma palavra: a página de dicas deve abrir, e “Voltar” deve retornar ao jogo.",
            "Em cada jogo, “Ver solução” deve levar à solução certa, e “Voltar” deve retornar ao jogo.",
            "As grades (Sudoku, Caça-palavras e Palavras Cruzadas) devem aparecer inteiras e legíveis.",
        ],
        "test_games": "Jogos nesta edição de teste",
        "wordle_legend": "■ letra certa no lugar certo · ▣ letra existe em outra posição · □ não existe",
        "wordle_pocket": "Palpites de bolso",
        "wordsearch_help": "Encontre as palavras escondidas na grade. Tema: {theme}.",
        "crossword_help": "Use as dicas para preencher a grade. As respostas não levam acento.",
        "across": "Horizontais", "down": "Verticais",
        "difficulty": {"easy": "fácil", "medium": "médio", "hard": "difícil"},
        "sources": "Fontes desta edição", "license": "Licença/política",
        "generated": "Edição gerada em", "curated_ai": "Seleção editorial assistida por IA.",
        "curated_rules": "Seleção editorial por regras e palavras-chave.",
        "charge_credit": "Charge gerada por IA a partir das manchetes do dia.",
        "also": "Também nesta edição", "end": "Fim da edição",
        "end_note": "Obrigado pela leitura. Até amanhã.",
        "daily": "Edição diária",
        "high": "Máx.", "low": "Mín.", "sunrise": "Nascer do sol", "sunset": "Pôr do sol",
        "weather_credit": "Dados meteorológicos: Open-Meteo (CC BY 4.0).",
        "free_software": "Dayfold é software livre (licença MIT). Tipografia sob SIL Open Font "
                         "License 1.1: Chomsky, UnifrakturMaguntia, UnifrakturCook, Playfair "
                         "Display, Literata e Old Standard TT.",
    },
    "en": {
        "edition": "Edition", "number": "No.", "year": "Vol.", "by": "By", "source": "Source",
        "in_this_edition": "In this edition", "front_page": "Front page",
        "read_more": "Read the full story at the source", "continues": "The story continues online",
        "excerpt_note": "Excerpt. Full text at",
        "metadata_note": "Headline and metadata only. Full story at",
        "charge": "The Cartoon", "charge_kicker": "Humor", "games": "Puzzles",
        "solutions": "Solutions", "see_solution": "See solution", "back": "Back",
        "play_koreader": "Play in KOReader", "colophon": "Masthead",
        "clues": "clues",
        "sudoku_help": "Fill the grid so every row, column and 3×3 box contains 1 to 9.",
        "wordle": "Word of the Day",
        "wordle_help": "Find the {n} letter word. In KOReader you get {a} tries. Here, tap one "
                        "of the words below to see the hints.",
        "wordle_help_native": "Find the {n} letter word. Tap one of the words below to see the "
                               "hints, then use Back to try another.",
        "answers_ahead": "Answers ahead",
        "answers_ahead_note": "End of the edition. The puzzle solutions and hints come after this "
                              "page. Stop here if you are still playing.",
        "test_title": "Kindle test",
        "test_intro": "Test edition with every puzzle, to validate a Kindle without jailbreak. "
                      "Check each item below on the device:",
        "test_checks": [
            "Turn the pages from start to end without tapping links. No solution and no {wordle} hint may show up before the “Answers ahead” page.",
            "After “Answers ahead”, keep turning. If solutions or hints show up, the Kindle ignored the hidden pages: keep games off in the native Kindle version.",
            "In {wordle}, tap a word: its hint page must open, and “Back” must return to the game.",
            "In every game, “See solution” must open the right solution, and “Back” must return to the game.",
            "The grids (Sudoku, Word Search and Crossword) must show complete and readable.",
        ],
        "test_games": "Games in this test edition",
        "wordle_legend": "■ right letter, right spot · ▣ letter elsewhere · □ not in the word",
        "wordle_pocket": "Pocket guesses",
        "wordsearch_help": "Find the hidden words in the grid. Theme: {theme}.",
        "crossword_help": "Use the clues to fill in the grid.",
        "across": "Across", "down": "Down",
        "difficulty": {"easy": "easy", "medium": "medium", "hard": "hard"},
        "sources": "Sources in this edition", "license": "License/policy",
        "generated": "Generated on", "curated_ai": "Editorial selection assisted by AI.",
        "curated_rules": "Editorial selection by rules and keywords.",
        "charge_credit": "Cartoon generated by AI from today's headlines.",
        "also": "Also in this edition", "end": "End of edition",
        "end_note": "Thanks for reading. See you tomorrow.",
        "daily": "Daily edition",
        "high": "High", "low": "Low", "sunrise": "Sunrise", "sunset": "Sunset",
        "weather_credit": "Weather data: Open-Meteo (CC BY 4.0).",
        "free_software": "Dayfold is free software (MIT license). Typefaces under the SIL Open "
                         "Font License 1.1: Chomsky, UnifrakturMaguntia, UnifrakturCook, Playfair "
                         "Display, Literata and Old Standard TT.",
    },
}


# Defaults that ship with Dayfold. While the user keeps them, the edition shows them in its own
# language; anything the user typed is printed as is.
DEFAULT_TAGLINES = {
    "pt": "Notícias do dia, dobradas para ler com calma.",
    "en": "The day's news, folded for an unhurried read.",
}
DEFAULT_SECTION_NAMES = {
    "brasil": {"pt": "Brasil", "en": "Brazil"},
    "mundo": {"pt": "Mundo", "en": "World"},
    "ciencia": {"pt": "Ciência", "en": "Science"},
    "espaco": {"pt": "Espaço", "en": "Space"},
    "saude": {"pt": "Saúde", "en": "Health"},
    "tecnologia": {"pt": "Tecnologia", "en": "Technology"},
    "cultura": {"pt": "Cultura", "en": "Culture"},
    "quadrinhos": {"pt": "Quadrinhos", "en": "Comics"},
}


def localized_tagline(tagline: str, lang: str) -> str:
    return DEFAULT_TAGLINES[lang] if tagline in DEFAULT_TAGLINES.values() else tagline


def section_name(slug: str, name: str, lang: str) -> str:
    names = DEFAULT_SECTION_NAMES.get(slug)
    return names[lang] if names and name in names.values() else name


def generated_stamp(dt: datetime, lang: str) -> str:
    return short_date(dt.date(), lang) + dt.strftime(", %H:%M")


def long_date(d: date, lang: str) -> str:
    wd = WEEKDAYS[lang][d.weekday()]
    m = MONTHS[lang][d.month - 1]
    if lang == "pt":
        return f"{wd}, {d.day} de {m} de {d.year}"
    return f"{wd}, {m} {d.day}, {d.year}"


def short_date(d: date, lang: str) -> str:
    m = MONTHS[lang][d.month - 1]
    return f"{d.day} de {m} de {d.year}" if lang == "pt" else f"{m} {d.day}, {d.year}"


def roman(n: int) -> str:
    vals = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
            (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for v, s in vals:
        while n >= v:
            out += s
            n -= v
    return out


MONTHS_ABBR = {
    "pt": ["jan.", "fev.", "mar.", "abr.", "maio", "jun.", "jul.", "ago.", "set.", "out.", "nov.", "dez."],
    "en": ["Jan.", "Feb.", "Mar.", "Apr.", "May", "June", "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."],
}


def book_title(name: str, d: date, lang: str) -> str:
    """Title shown in e-reader libraries: the newspaper name plus the date, so a week of
    editions does not look like seven copies of the same book."""
    m = MONTHS_ABBR[lang][d.month - 1]
    return f"{name} · {d.day} {m} {d.year}" if lang == "pt" else f"{name} · {m} {d.day}, {d.year}"

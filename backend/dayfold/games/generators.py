"""Puzzle generators. All randomness comes from a seed derived from the edition date, so
the same edition always gets the same puzzles."""

from __future__ import annotations

import hashlib
import random
import re
import string
import unicodedata
from collections.abc import Callable

from .crossword_words import CROSSWORD
from .words import STOPWORDS, WORDLE, WORDSEARCH_THEMES


def seeded(edition_key: str, kind: str, n: int = 0) -> random.Random:
    digest = hashlib.sha256(f"dayfold:{edition_key}:{kind}:{n}".encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def plain(word: str) -> str:
    w = unicodedata.normalize("NFKD", word.lower())
    return "".join(c for c in w if c in string.ascii_lowercase)


# ------------------------------------------------------------------ sudoku

CLUES = {"easy": 40, "medium": 32, "hard": 27}


def _sudoku_solve(grid: list[int], rng: random.Random | None, limit: int = 2) -> int:
    """Count solutions (up to ``limit``); fills ``grid`` with the first one found."""
    try:
        i = grid.index(0)
    except ValueError:
        return 1
    r, c = divmod(i, 9)
    used = set(grid[r * 9 : r * 9 + 9]) | {grid[k * 9 + c] for k in range(9)}
    br, bc = r - r % 3, c - c % 3
    used |= {grid[(br + y) * 9 + bc + x] for y in range(3) for x in range(3)}
    digits = [d for d in range(1, 10) if d not in used]
    if rng:
        rng.shuffle(digits)
    count = 0
    for d in digits:
        grid[i] = d
        found = _sudoku_solve(grid, rng, limit - count)
        if found and rng:
            return found
        count += found
        if count >= limit:
            grid[i] = 0
            return count
    grid[i] = 0
    return count


def sudoku(rng: random.Random, difficulty: str = "medium") -> tuple[dict, dict]:
    full = [0] * 81
    _sudoku_solve(full, rng)
    solution = full[:]
    puzzle = full[:]
    target = CLUES.get(difficulty, 32)
    cells = list(range(81))
    rng.shuffle(cells)
    clues = 81
    for i in cells:
        if clues <= target:
            break
        backup = puzzle[i]
        puzzle[i] = 0
        if _sudoku_solve(puzzle[:], None, 2) != 1:
            puzzle[i] = backup
        else:
            clues -= 1
    return (
        {"grid": puzzle, "difficulty": difficulty, "clues": clues},
        {"grid": solution},
    )


# ------------------------------------------------------------------ wordle


def wordle_feedback(guess: str, answer: str) -> list[str]:
    """Per letter: 'correct', 'present' or 'absent' (handles repeated letters)."""
    result = ["absent"] * len(guess)
    remaining: dict[str, int] = {}
    for i, (g, a) in enumerate(zip(guess, answer, strict=True)):
        if g == a:
            result[i] = "correct"
        else:
            remaining[a] = remaining.get(a, 0) + 1
    for i, g in enumerate(guess):
        if result[i] == "absent" and remaining.get(g, 0) > 0:
            result[i] = "present"
            remaining[g] -= 1
    return result


def wordle(rng: random.Random, language: str = "pt", length: int = 5, attempts: int = 6,
           pocket_guesses: int = 12) -> tuple[dict, dict]:
    words = WORDLE.get(language, WORDLE["pt"]).get(length) or WORDLE[language][5]
    length = len(words[0])
    answer = rng.choice(words)
    others = [w for w in words if w != answer]
    rng.shuffle(others)
    # "Pocket" mode for plain EPUB: a fixed set of tappable guesses with precomputed hints.
    pocket = others[: pocket_guesses - 1] + [answer]
    rng.shuffle(pocket)
    return (
        {
            "language": language,
            "length": length,
            "attempts": attempts,
            "answer_hash": hashlib.sha256(answer.encode()).hexdigest(),
            "pocket": [{"word": w.upper(), "feedback": wordle_feedback(w, answer)} for w in pocket],
        },
        {"answer": answer.upper()},
    )


# ------------------------------------------------------------------ word search

THEME_LABELS = {
    "animais": "Animais", "natureza": "Natureza", "espaco": "Espaço", "cidade": "Cidade",
    "cozinha": "Cozinha", "animals": "Animals", "nature": "Nature", "space": "Space",
    "city": "City", "kitchen": "Kitchen",
}

DIRS_EASY = [(0, 1), (1, 0)]
DIRS_MEDIUM = [(0, 1), (1, 0), (1, 1), (-1, 1)]
DIRS_HARD = DIRS_MEDIUM + [(0, -1), (-1, 0), (-1, -1), (1, -1)]


def news_words(headlines: list[str], language: str, size: int) -> list[str]:
    seen: list[str] = []
    for h in headlines:
        for raw in re.split(r"[^\w]+", h):
            w = plain(raw)
            if 4 <= len(w) <= min(size, 11) and w not in STOPWORDS and w not in seen:
                seen.append(w)
    return seen


def wordsearch(rng: random.Random, language: str = "pt", size: int = 12, theme: str = "news",
               count: int = 10, headlines: list[str] | None = None,
               difficulty: str = "medium") -> tuple[dict, dict]:
    size = max(8, min(size, 16))
    pool: list[str] = []
    theme_label = ""
    if theme == "news" and headlines:
        pool = news_words(headlines, language, size)
        theme_label = "Notícias do dia" if language == "pt" else "Today's news"
    if len(pool) < count:
        themes = WORDSEARCH_THEMES.get(language, WORDSEARCH_THEMES["pt"])
        key = theme if theme in themes else rng.choice(sorted(themes))
        if not pool:  # no headlines to draw from: label the theme itself
            theme_label = THEME_LABELS.get(key, key.capitalize())
        pool += [plain(w) for w in themes[key] if plain(w) not in pool]
    pool = [w for w in pool if 3 <= len(w) <= size]
    rng.shuffle(pool)
    dirs = {"easy": DIRS_EASY, "hard": DIRS_HARD}.get(difficulty, DIRS_MEDIUM)
    grid = [[""] * size for _ in range(size)]
    placed: list[dict] = []
    for word in sorted(pool, key=len, reverse=True):
        if len(placed) >= count:
            break
        for _ in range(200):
            dr, dc = rng.choice(dirs)
            r0, c0 = rng.randrange(size), rng.randrange(size)
            r1, c1 = r0 + dr * (len(word) - 1), c0 + dc * (len(word) - 1)
            if not (0 <= r1 < size and 0 <= c1 < size):
                continue
            cells = [(r0 + dr * k, c0 + dc * k) for k in range(len(word))]
            if all(grid[r][c] in ("", word[k]) for k, (r, c) in enumerate(cells)):
                for k, (r, c) in enumerate(cells):
                    grid[r][c] = word[k]
                placed.append({"word": word.upper(), "start": [r0, c0], "end": [r1, c1]})
                break
    letters = "abcdefghijlmnoprstuv" if language == "pt" else string.ascii_lowercase
    for r in range(size):
        for c in range(size):
            if not grid[r][c]:
                grid[r][c] = rng.choice(letters)
    words = sorted(p["word"] for p in placed)
    return (
        {"size": size, "rows": ["".join(row).upper() for row in grid], "words": words,
         "theme": theme_label},
        {"placements": placed},
    )


# ------------------------------------------------------------------ crossword

ACROSS, DOWN = (0, 1), (1, 0)


def _cw_fits(grid: dict, dirs: dict, word: str, r0: int, c0: int, d: tuple[int, int],
             size: int) -> int:
    """Crossings the word makes at (r0, c0) going ``d``, or -1 when it cannot go there."""
    dr, dc = d
    n = len(word)
    if not (0 <= r0 and 0 <= c0 and r0 + dr * (n - 1) < size and c0 + dc * (n - 1) < size):
        return -1
    if (r0 - dr, c0 - dc) in grid or (r0 + dr * n, c0 + dc * n) in grid:
        return -1  # would touch another word end to end
    crossings = 0
    for k, ch in enumerate(word):
        cell = (r0 + dr * k, c0 + dc * k)
        if cell in grid:
            if grid[cell] != ch or d in dirs[cell]:
                return -1
            crossings += 1
            continue
        # a new letter must not sit beside another word (that would spell junk)
        side1, side2 = (cell[0] + dc, cell[1] + dr), (cell[0] - dc, cell[1] - dr)
        if side1 in grid or side2 in grid:
            return -1
    return crossings


def _cw_build(rng: random.Random, pool: list[tuple[str, str]], count: int, size: int) -> list[dict]:
    grid: dict[tuple[int, int], str] = {}
    dirs: dict[tuple[int, int], set] = {}
    placed: list[dict] = []

    def put(word: str, clue: str, r0: int, c0: int, d: tuple[int, int]) -> None:
        for k, ch in enumerate(word):
            cell = (r0 + d[0] * k, c0 + d[1] * k)
            grid[cell] = ch
            dirs.setdefault(cell, set()).add(d)
        placed.append({"word": word, "clue": clue, "row": r0, "col": c0,
                       "dir": "across" if d == ACROSS else "down"})

    first = max(pool[:6], key=lambda wc: len(wc[0]))
    put(first[0], first[1], size // 2, (size - len(first[0])) // 2, ACROSS)
    for word, clue in pool:
        if len(placed) >= count:
            break
        if word == first[0]:
            continue
        options = []
        for (r, c), ch in list(grid.items()):
            for k, wch in enumerate(word):
                if wch != ch:
                    continue
                for d in (ACROSS, DOWN):
                    r0, c0 = r - d[0] * k, c - d[1] * k
                    x = _cw_fits(grid, dirs, word, r0, c0, d, size)
                    if x > 0:
                        options.append((x, rng.random(), r0, c0, d))
        if options:
            _, _, r0, c0, d = max(options)
            put(word, clue, r0, c0, d)
    return placed


def crossword(rng: random.Random, language: str = "pt", words: int = 10,
              size: int = 13) -> tuple[dict, dict]:
    """Free-form crossword: words cross each other inside a ``size`` square, the best of
    several tries is kept, then the grid is cropped to the words and numbered."""
    bank = CROSSWORD.get(language, CROSSWORD["pt"])
    size = max(9, min(size, 17))
    bank = [(w, c) for w, c in bank if 3 <= len(w) <= size]
    best: list[dict] = []
    best_score = (-1, 0)
    for _ in range(40):
        pool = bank[:]
        rng.shuffle(pool)
        placed = _cw_build(rng, pool, words, size)
        cells = {(p["row"] + (k if p["dir"] == "down" else 0), p["col"] + (k if p["dir"] == "across" else 0))
                 for p in placed for k in range(len(p["word"]))}
        letters = sum(len(p["word"]) for p in placed)
        score = (len(placed), letters - len(cells))  # more words, then more crossings
        if score > best_score:
            best, best_score = placed, score
        if len(placed) >= words and score[1] >= words:
            break
    top = min(p["row"] for p in best)
    left = min(p["col"] for p in best)
    for p in best:
        p["row"] -= top
        p["col"] -= left
    rows = max(p["row"] + (len(p["word"]) if p["dir"] == "down" else 1) for p in best)
    cols = max(p["col"] + (len(p["word"]) if p["dir"] == "across" else 1) for p in best)
    solved = [["#"] * cols for _ in range(rows)]
    for p in best:
        for k, ch in enumerate(p["word"].upper()):
            r = p["row"] + (k if p["dir"] == "down" else 0)
            c = p["col"] + (k if p["dir"] == "across" else 0)
            solved[r][c] = ch
    starts = sorted({(p["row"], p["col"]) for p in best})
    number = {cell: i + 1 for i, cell in enumerate(starts)}
    entries: dict[str, list[dict]] = {"across": [], "down": []}
    for p in best:
        entries[p["dir"]].append({"n": number[(p["row"], p["col"])], "row": p["row"], "col": p["col"],
                                  "len": len(p["word"]), "clue": p["clue"], "answer": p["word"].upper()})
    for v in entries.values():
        v.sort(key=lambda e: e["n"])
    return (
        {
            "language": language, "rows": rows, "cols": cols,
            "grid": ["".join("#" if ch == "#" else "." for ch in row) for row in solved],
            "numbers": [[r, c, n] for (r, c), n in sorted(number.items(), key=lambda kv: kv[1])],
            "across": [{k: e[k] for k in ("n", "row", "col", "len", "clue")} for e in entries["across"]],
            "down": [{k: e[k] for k in ("n", "row", "col", "len", "clue")} for e in entries["down"]],
        },
        {
            "grid": ["".join(row) for row in solved],
            "across": [{"n": e["n"], "answer": e["answer"]} for e in entries["across"]],
            "down": [{"n": e["n"], "answer": e["answer"]} for e in entries["down"]],
        },
    )


GENERATORS: dict[str, Callable] = {"sudoku": sudoku, "wordle": wordle, "wordsearch": wordsearch,
                                   "crossword": crossword}

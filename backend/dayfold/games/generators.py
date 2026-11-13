"""Puzzle generators. All randomness comes from a seed derived from the edition date, so
the same edition always gets the same puzzles."""

from __future__ import annotations

import hashlib
import random
import string
import unicodedata
from collections.abc import Callable

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
        for raw in h.split():
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
        if not pool:
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


GENERATORS: dict[str, Callable] = {"sudoku": sudoku, "wordle": wordle, "wordsearch": wordsearch}

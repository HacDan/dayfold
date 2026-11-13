from dayfold.games.generators import _sudoku_solve, seeded, sudoku, wordle, wordle_feedback, wordsearch


def test_sudoku_has_unique_solution():
    puzzle, solution = sudoku(seeded("2026-01-01", "sudoku"), "hard")
    grid = puzzle["grid"][:]
    assert _sudoku_solve(grid[:], None, 2) == 1
    assert all(p in (0, s) for p, s in zip(puzzle["grid"], solution["grid"], strict=True))
    assert sorted(solution["grid"][:9]) == list(range(1, 10))


def test_same_seed_same_puzzle():
    a, _ = sudoku(seeded("2026-01-01", "sudoku"), "easy")
    b, _ = sudoku(seeded("2026-01-01", "sudoku"), "easy")
    assert a == b


def test_wordle_feedback_repeated_letters():
    assert wordle_feedback("arara", "barco") == ["present", "present", "absent", "absent", "absent"]
    assert wordle_feedback("barco", "barco") == ["correct"] * 5


def test_wordle_pocket_contains_answer():
    puzzle, solution = wordle(seeded("x", "wordle"), "pt", 5, 6)
    words = [p["word"] for p in puzzle["pocket"]]
    assert solution["answer"] in words
    assert all(len(w) == 5 for w in words)


def test_wordsearch_places_words_in_grid():
    puzzle, solution = wordsearch(seeded("x", "ws"), "pt", 12, "animais", 8)
    rows = puzzle["rows"]
    for p in solution["placements"]:
        (r0, c0), (r1, c1) = p["start"], p["end"]
        n = len(p["word"])
        dr, dc = (r1 - r0) // max(1, n - 1), (c1 - c0) // max(1, n - 1)
        assert "".join(rows[r0 + dr * k][c0 + dc * k] for k in range(n)) == p["word"]

type Puzzle = Record<string, unknown>;

export function SudokuGrid({ grid }: { grid: number[] }) {
  return (
    <table className="sudoku">
      <tbody>
        {Array.from({ length: 9 }, (_, r) => (
          <tr key={r}>
            {Array.from({ length: 9 }, (_, c) => {
              const v = grid[r * 9 + c];
              return <td key={c} className={`${c === 2 || c === 5 ? "br " : ""}${r === 2 || r === 5 ? "bb" : ""}`}>{v || ""}</td>;
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function WordleTiles({ word, feedback }: { word: string; feedback?: string[] }) {
  return (
    <div className="tiles">
      {word.split("").map((ch, i) => <span key={i} className={`tile ${feedback?.[i] ?? ""}`}>{ch}</span>)}
    </div>
  );
}

export function WordSearchGrid({ rows }: { rows: string[] }) {
  return (
    <table className="wsgrid">
      <tbody>
        {rows.map((row, r) => <tr key={r}>{row.split("").map((ch, c) => <td key={c}>{ch}</td>)}</tr>)}
      </tbody>
    </table>
  );
}

export function GamePreview({ kind, puzzle, solution }: { kind: string; puzzle: Puzzle; solution: Puzzle }) {
  if (kind === "sudoku") {
    return <div><SudokuGrid grid={puzzle.grid as number[]} /><p className="small muted">{String(puzzle.clues)} pistas</p></div>;
  }
  if (kind === "wordle") {
    const pocket = puzzle.pocket as { word: string; feedback: string[] }[];
    return (
      <div>
        <p className="small muted">Resposta: <strong>{String(solution.answer)}</strong>. Palpites de bolso do EPUB:</p>
        {pocket.slice(0, 4).map((p) => <WordleTiles key={p.word} word={p.word} feedback={p.feedback} />)}
      </div>
    );
  }
  return (
    <div>
      <WordSearchGrid rows={puzzle.rows as string[]} />
      <p className="small muted" style={{ marginTop: 8 }}>Tema: {String(puzzle.theme)} · {(puzzle.words as string[]).join(" · ")}</p>
    </div>
  );
}

import { useState } from "react";
import { get, put, type Game } from "../api";
import { GamePreview } from "../components/games";
import { Field, Loading, SectionTitle, useAction, useLoad } from "../components/ui";

type GamesResp = { games: Game[]; schemas: Record<string, Record<string, (string | number)[]>> };

const PARAM_LABEL: Record<string, string> = {
  difficulty: "Dificuldade", count: "Puzzles por edição", language: "Idioma", length: "Letras", attempts: "Tentativas",
  size: "Tamanho da grade", theme: "Tema", words: "Palavras",
};
const VALUE_LABEL: Record<string, string> = {
  easy: "Fácil", medium: "Médio", hard: "Difícil", pt: "Português", en: "Inglês", news: "Notícias do dia",
};
const DESCR: Record<string, string> = {
  sudoku: "Grade 9×9 com solução única garantida. No EPUB, para resolver de cabeça; no KOReader, toque nas casas para preencher.",
  wordle: "Descubra a palavra do dia. No EPUB, palpites de bolso com dicas por link; no KOReader, jogo completo com teclado.",
  wordsearch: "Palavras escondidas na grade. O tema “Notícias do dia” usa termos das manchetes da edição.",
};

function GameCard({ g, schema, onSaved, onMove, first, last }: {
  g: Game; schema: Record<string, (string | number)[]>; onSaved: () => void; onMove: (d: -1 | 1) => void; first: boolean; last: boolean;
}) {
  const { run } = useAction();
  const [cfg, setCfg] = useState(g.config);
  const [enabled, setEnabled] = useState(g.enabled);
  const [preview, setPreview] = useState<{ kind: string; puzzle: Record<string, unknown>; solution: Record<string, unknown> } | null>(null);
  const save = () => run(() => put(`/api/games/${g.id}`, { enabled, config: cfg }), "Jogo salvo").then(onSaved);
  return (
    <section className="clip" style={{ opacity: enabled ? 1 : 0.6 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <p className="kicker">#{g.position + 1} na edição</p>
          <h3 style={{ fontSize: "1.6rem" }}>{g.name}</h3>
        </div>
        <div className="row">
          <button className="btn small" disabled={first} onClick={() => onMove(-1)} aria-label="Antes">↑</button>
          <button className="btn small" disabled={last} onClick={() => onMove(1)} aria-label="Depois">↓</button>
        </div>
      </div>
      <p className="small muted">{DESCR[g.kind]}</p>
      <label className="check"><input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} /> Ativo</label>
      <div className="grid cols-2" style={{ gap: 12 }}>
        {Object.entries(schema).map(([k, opts]) => (
          <Field key={k} label={PARAM_LABEL[k] ?? k}>
            <select value={String(cfg[k] ?? opts[0])} onChange={(e) => setCfg({ ...cfg, [k]: typeof opts[0] === "number" ? Number(e.target.value) : e.target.value })}>
              {opts.map((o) => <option key={String(o)} value={String(o)}>{VALUE_LABEL[String(o)] ?? String(o)}</option>)}
            </select>
          </Field>
        ))}
      </div>
      <div className="row">
        <button className="btn primary small" onClick={save}>Salvar</button>
        <button className="btn small" onClick={async () => { await save(); setPreview(await get(`/api/games/${g.id}/preview`)); }}>Prévia</button>
      </div>
      {preview && <div style={{ marginTop: 12 }}><GamePreview {...preview} /></div>}
    </section>
  );
}

export default function Games() {
  const { run } = useAction();
  const { data, reload } = useLoad(() => get<GamesResp>("/api/games"));
  if (!data) return <Loading />;
  const move = (i: number, d: -1 | 1) => {
    const ids = data.games.map((g) => g.id);
    [ids[i], ids[i + d]] = [ids[i + d], ids[i]];
    run(() => put("/api/games-order", ids)).then(reload);
  };
  return (
    <div>
      <SectionTitle kicker="Passatempos" title="Jogos" />
      <p className="small muted" style={{ maxWidth: 780 }}>
        Os jogos são gerados no servidor com uma semente do dia e entram no fim da edição, depois da charge. As soluções ficam em páginas
        separadas, só acessíveis por link, para não estragar a surpresa ao virar a página.
      </p>
      <div className="grid cols-3">
        {data.games.map((g, i) => (
          <GameCard key={`${g.id}-${g.position}`} g={g} schema={data.schemas[g.kind]} onSaved={reload} onMove={(d) => move(i, d)} first={i === 0} last={i === data.games.length - 1} />
        ))}
      </div>
    </div>
  );
}

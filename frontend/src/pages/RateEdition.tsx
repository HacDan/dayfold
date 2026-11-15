import { useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { locale, t } from "../i18n";
import { get, put, type EditionSummary, type Feedback, type Rating } from "../api";
import { Loading, Press, SectionTitle, useLoad, useToast } from "../components/ui";

type Story = {
  id: number; section: string; section_name: string; is_headline: boolean; title: string;
  subtitle: string | null; excerpt: string | null; provider: string; url: string; rating: Rating | null;
};
type Detail = EditionSummary & { articles: Story[] };

const CHOICES: { value: Rating; label: string; cls: string; icon: ReactNode }[] = [
  { value: -1, label: "Menos disso", cls: "down", icon: <path d="M6 9l6 6 6-6" /> },
  { value: 0, label: "Indiferente", cls: "meh", icon: <path d="M6 12h12" /> },
  { value: 1, label: "Mais disso", cls: "up", icon: <path d="M6 15l6-6 6 6" /> },
];

function RateControl({ value, onChange, title }: { value: Rating | null; onChange: (v: Rating | null) => void; title: string }) {
  return (
    <span className="rate" role="group" aria-label={t("Avaliação de “{title}”", { title })}>
      {CHOICES.map((c) => (
        <button key={c.value} type="button" className={c.cls} aria-pressed={value === c.value}
          title={t(c.label)} onClick={() => onChange(value === c.value ? null : c.value)}>
          <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true" fill="none" stroke="currentColor"
            strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">{c.icon}</svg>
          <span>{t(c.label)}</span>
        </button>
      ))}
    </span>
  );
}

function Learned({ fb }: { fb: Feedback }) {
  const side = (s: Feedback["more"]) => [
    ...s.sections.map((x) => x.name), ...s.providers.map((x) => x.name), ...s.terms.map((x) => `“${x.name}”`),
  ];
  const more = side(fb.more);
  const less = side(fb.less);
  return (
    <section className="clip ruled">
      <p className="kicker">{t("O que a curadoria aprendeu")}</p>
      {fb.count === 0 ? (
        <p className="small muted">{t("Nenhuma avaliação ainda. Cada nota ajusta a pontuação das matérias parecidas nas próximas edições, por fonte, seção e palavras do título.")}</p>
      ) : (
        <>
          <p className="small muted">
            {t("{n} avaliações: {up} a favor, {meh} indiferentes, {down} contra.", { n: fb.count, up: fb.positive, meh: fb.neutral, down: fb.negative })}
          </p>
          <h4 className="learned-h">{t("Mais de")}</h4>
          <p className="small">{more.length ? more.join(", ") : <em className="muted">{t("ainda sem um padrão claro")}</em>}</p>
          <h4 className="learned-h">{t("Menos de")}</h4>
          <p className="small">{less.length ? less.join(", ") : <em className="muted">{t("ainda sem um padrão claro")}</em>}</p>
        </>
      )}
      <p className="hint">{t("Funciona sem IA. Com a curadoria por IA ligada, o resumo acima também vai no pedido.")}{" "}
        <Link to="/jornal">{t("Ajustar o peso")}</Link></p>
    </section>
  );
}

export default function RateEdition() {
  const { id } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const { data, setData } = useLoad(() => get<Detail>(`/api/editions/${id}`), [id]);
  const { data: fb, reload: reloadFb } = useLoad(() => get<Feedback>("/api/feedback"), []);
  const [saving, setSaving] = useState(0);
  if (!data) return <Loading />;

  const rated = data.articles.filter((a) => a.rating !== null && a.rating !== undefined).length;
  const total = data.articles.length;

  const rate = async (story: Story, value: Rating | null) => {
    const prev = story.rating;
    const patch = (v: Rating | null) => setData((d) => d && { ...d, articles: d.articles.map((a) => (a.id === story.id ? { ...a, rating: v } : a)) });
    patch(value);
    setSaving((n) => n + 1);
    try {
      await put(`/api/editions/${data.id}/ratings`, { ratings: { [story.id]: value } });
      reloadFb();
    } catch (e) {
      patch(prev);
      toast((e as Error).message, true);
    } finally {
      setSaving((n) => n - 1);
    }
  };

  const finish = () => {
    toast(rated ? t("Avaliação salva. As próximas edições vão levar isso em conta.") : t("Nenhuma matéria avaliada."));
    nav("/");
  };

  const sections = new Map<string, Story[]>();
  for (const a of data.articles) {
    const key = a.is_headline ? t("Manchete") : a.section_name;
    sections.set(key, [...(sections.get(key) ?? []), a]);
  }

  return (
    <div>
      <SectionTitle
        kicker={`${t("Edição nº {n}", { n: data.number })} · ${new Date(data.date + "T12:00").toLocaleDateString(locale(), { dateStyle: "long" })}`}
        title={t("Avaliar edição")}>
        <Link className="btn" to={`/edicoes/${data.id}`}>{t("Ver edição")}</Link>
        <button className="btn primary" disabled={saving > 0} onClick={finish}>{t("Concluir")}</button>
      </SectionTitle>

      <div className="lead-grid">
        <div>
          <p className="deck">{t("Diga do que você quer mais e do que quer menos. As notas são salvas na hora e entram na curadoria das próximas edições, mesmo sem IA.")}</p>
          <div className="rate-progress">
            <Press value={total ? rated / total : 0} />
            <p className="byline">{t("{rated} de {total} avaliadas", { rated, total })}</p>
          </div>
          {[...sections.entries()].map(([name, items]) => (
            <section key={name} className="rate-section">
              <h3>{name}</h3>
              {items.map((a) => (
                <article key={a.id} className="rate-row" data-rated={a.rating !== null && a.rating !== undefined}>
                  <div>
                    <div className="rate-title"><a href={a.url} target="_blank" rel="noreferrer">{a.title}</a></div>
                    {(a.subtitle || a.excerpt) && <div className="deck small rate-deck">{a.subtitle || a.excerpt}</div>}
                    <div className="byline">{a.provider}</div>
                  </div>
                  <RateControl value={a.rating ?? null} title={a.title} onChange={(v) => rate(a, v)} />
                </article>
              ))}
            </section>
          ))}
          <div className="row" style={{ justifyContent: "flex-end", marginTop: 18 }}>
            <button className="btn primary" disabled={saving > 0} onClick={finish}>{t("Concluir")}</button>
          </div>
        </div>
        <aside>{fb && <Learned fb={fb} />}</aside>
      </div>
    </div>
  );
}

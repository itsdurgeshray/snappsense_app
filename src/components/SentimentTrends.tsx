import { useState } from "react";
import { RANGES, SENTIMENTS, type Period, type Range } from "../data";

/** Longest range where at least half the periods have data. */
function bestRange(trends: Record<Range, Period[]>): Range {
  for (const r of [...RANGES].reverse()) {
    const ps = trends[r];
    if (ps.filter((p) => !p.empty).length >= Math.ceil(ps.length / 2)) return r;
  }
  return "1w";
}

export function SentimentTrends({ trends }: { trends: Record<Range, Period[]> }) {
  const [range, setRange] = useState<Range>(() => bestRange(trends));
  const [hover, setHover] = useState<{ i: number; x: number; y: number } | null>(null);
  const periods = trends[range];
  const pct = (v: number) => `${Math.round(v * 100)}%`;
  // Older reports (before share-based trends) only carry counts.
  const shareOf = (p: Period, k: (typeof SENTIMENTS)[number]["key"]) => {
    if (p.share) return p.share[k];
    const c = p.counts;
    const t = c ? SENTIMENTS.reduce((a, s) => a + c[s.key], 0) : 0;
    return c && t ? c[k] / t : 0;
  };
  const caption = (p: Period) =>
    p.empty ? "not enough data" : p.counts ? `${SENTIMENTS.reduce((a, s) => a + (p.counts?.[s.key] ?? 0), 0).toLocaleString()} reviews` : "estimated";

  return (
    <section className="card" aria-labelledby="trends-title">
      <div className="card__head">
        <h2 className="card__title" id="trends-title">
          Periodic Sentiment Trends
        </h2>
        <div className="range-tabs" role="tablist" aria-label="Time range">
          {RANGES.map((r) => (
            <button key={r} role="tab" type="button" className="range-tab" aria-selected={r === range} onClick={() => setRange(r)}>
              {r}
            </button>
          ))}
        </div>
      </div>

      <div className="bars" onMouseLeave={() => setHover(null)}>
        <div className="bars__plot">
          {periods.map((p, i) => (
            <div
              key={`${range}-${p.start}`}
              className={`bars__col${p.estimated ? " is-est" : ""}${p.empty ? " is-empty" : ""}`}
              role="img"
              aria-label={`${p.label}: ${caption(p)}${p.empty ? "" : ", " + SENTIMENTS.map((s) => `${s.label} ${pct(shareOf(p, s.key))}`).join(", ")}`}
              onMouseMove={(e) => {
                const host = e.currentTarget.parentElement!.getBoundingClientRect();
                const col = e.currentTarget.getBoundingClientRect();
                setHover({ i, x: col.left - host.left + col.width / 2, y: e.clientY - host.top });
              }}
            >
              {SENTIMENTS.map((s) => (
                <div key={s.key} className="bars__seg" style={{ height: p.empty ? 0 : `${shareOf(p, s.key) * 100}%`, background: s.color }} />
              ))}
            </div>
          ))}
        </div>
        <div className="bars__labels" aria-hidden="true">
          {periods.map((p) => (
            <span key={p.start}>{p.label}</span>
          ))}
        </div>

        {hover && (
          <div className="tooltip" style={{ left: hover.x, top: hover.y }}>
            <div className="tooltip__title">
              {periods[hover.i].label} · {caption(periods[hover.i])}
            </div>
            {!periods[hover.i].empty && [...SENTIMENTS].reverse().map((s) => (
              <div className="tooltip__row" key={s.key}>
                <span>
                  <i className="swatch" style={{ background: s.color }} />
                  {s.label}
                </span>
                <span>{pct(shareOf(periods[hover.i], s.key))}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

import { useState } from "react";
import { formatCompact } from "../data";

const CX = 200, CY = 200, R = 195, r = 125;

// 5★ → 1★ share the sentiment palette, so the gauge reads like the rest of the dashboard.
const STARS = [
  { star: "5", label: "5★", color: "var(--s-delighted)" },
  { star: "4", label: "4★", color: "var(--s-happy)" },
  { star: "3", label: "3★", color: "var(--s-neutral)" },
  { star: "2", label: "2★", color: "var(--s-angry)" },
  { star: "1", label: "1★", color: "var(--s-frustrated)" },
];

function arc(a0: number, a1: number) {
  const p = (rad: number, a: number) => `${CX + rad * Math.cos(a)} ${CY - rad * Math.sin(a)}`;
  const large = a0 - a1 > Math.PI ? 1 : 0;
  return `M ${p(R, a0)} A ${R} ${R} 0 ${large} 1 ${p(R, a1)} L ${p(r, a1)} A ${r} ${r} 0 ${large} 0 ${p(r, a0)} Z`;
}

/** All-time star ratings straight from the store's histogram. */
export function RatingsGauge({ ratings = {}, basis = "store" }: { ratings?: Record<string, number>; basis?: "store" | "sample" }) {
  const [active, setActive] = useState<number | null>(null);
  const total = STARS.reduce((t, s) => t + (ratings[s.star] ?? 0), 0) || 1;
  const unit = basis === "store" ? "Ratings" : "Reviews";
  let angle = Math.PI;
  const segs = STARS.map((s) => {
    const sweep = ((ratings[s.star] ?? 0) / total) * Math.PI;
    const seg = { ...s, d: arc(angle, angle - sweep) };
    angle -= sweep;
    return seg;
  });
  const a = active !== null ? STARS[active] : null;

  return (
    <section className="card" aria-labelledby="gauge-title">
      <h2 className="card__title" id="gauge-title">
        All Time Ratings
      </h2>
      <div className="gauge">
        <svg viewBox="0 0 400 202" role="img" aria-label={`${total.toLocaleString()} ratings by stars`} onMouseLeave={() => setActive(null)}>
          {segs.map((s, i) => (
            <path key={s.star} d={s.d} fill={s.color} onMouseEnter={() => setActive(i)} />
          ))}
        </svg>
        <div className="gauge__center">
          <div className="gauge__value">{a ? `${formatCompact(ratings[a.star] ?? 0)} × ${a.label}` : `${formatCompact(total)} ${unit}`}</div>
          <div className="gauge__hint">{a ? `${(((ratings[a.star] ?? 0) / total) * 100).toFixed(1)}% of all ${unit.toLowerCase()}` : " "}</div>
        </div>
      </div>
      <ul className="legend">
        {STARS.map((s, i) => (
          <li key={s.star} onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(null)}>
            <i className="swatch" style={{ background: s.color }} />
            {s.label}
          </li>
        ))}
      </ul>
    </section>
  );
}

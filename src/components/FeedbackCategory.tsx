import { CATEGORY_STYLE, type AppReport } from "../data";

/** One segmented bar + legend: what the complaints are about, at a glance. */
export function FeedbackCategory({ categories, emptyText }: { categories: AppReport["categories"]; emptyText?: string }) {
  return (
    <section className="card cat-card" aria-labelledby="cat-title">
      <h2 className="card__title" id="cat-title">
        Feedback Category
      </h2>
      {categories.length === 0 ? (
        <p className="card__note">{emptyText ?? "No complaints found in the analysed reviews."}</p>
      ) : (
        <>
          <div className="cat-bar" role="img" aria-label={categories.map((c) => `${c.label} ${c.share}%`).join(", ")}>
            {categories.map((c) => (
              <span
                key={c.label}
                className="cat-bar__seg"
                style={{ flexGrow: c.share, background: CATEGORY_STYLE[c.label]?.color ?? "var(--brand)" }}
                title={`${c.label}: ${c.share}% · ${c.count.toLocaleString()} reviews`}
              />
            ))}
          </div>
          <ul className="cat-legend">
            {categories.map((c) => (
              <li key={c.label}>
                <i style={{ background: CATEGORY_STYLE[c.label]?.color ?? "var(--brand)" }} />
                <span>{c.label}</span>
                <strong>{c.share.toFixed(1)}%</strong>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

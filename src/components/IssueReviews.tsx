import { useEffect, useState } from "react";
import { fetchIssueReviews, type ReviewPage } from "../api";
import type { FeedbackRow, IssueReview } from "../data";
import { Modal } from "./Modal";
import { CategoryPill, Evidence, PriorityBadge, Select } from "./FeedbackTable";

const PAGE = 40;
type Sort = "relevant" | "newest" | "helpful";

function fmtDate(d: string) {
  return new Date(d).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/** Review text with the sentence that states the concern highlighted. */
function Highlighted({ text, concern }: { text: string; concern: string }) {
  const i = concern ? text.toLowerCase().indexOf(concern.toLowerCase()) : -1;
  if (i < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, i)}
      <mark className="concern">{text.slice(i, i + concern.length)}</mark>
      {text.slice(i + concern.length)}
    </>
  );
}

export function IssueReviews({ reportId, row, versions, onClose }: { reportId: string; row: FeedbackRow; versions?: string[]; onClose: () => void }) {
  const [page, setPage] = useState<ReviewPage | null>(null);
  const [items, setItems] = useState<IssueReview[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [q, setQ] = useState(""); // debounced search sent to the server
  const [stars, setStars] = useState<number | null>(null);
  const [sort, setSort] = useState<Sort>("relevant");

  useEffect(() => {
    const t = window.setTimeout(() => setQ(query), 250);
    return () => window.clearTimeout(t);
  }, [query]);

  // First page whenever the filters change; big issues are never sent in one go.
  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    fetchIssueReviews(reportId, row.id, { q, stars, sort, limit: PAGE, versions }, ctrl.signal)
      .then((p) => {
        setPage(p);
        setItems(p.reviews);
        setError(null);
      })
      .catch((e) => e.name !== "AbortError" && setError(e.message))
      .finally(() => !ctrl.signal.aborted && setLoading(false));
    return () => ctrl.abort();
  }, [reportId, row.id, q, stars, sort, versions]);

  const more = () => {
    setLoading(true);
    fetchIssueReviews(reportId, row.id, { q, stars, sort, limit: PAGE, offset: items.length, versions })
      .then((p) => setItems((cur) => [...cur, ...p.reviews]))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  const starCount = (s: number) => page?.stars[String(s)] ?? 0;
  const left = (page?.matched ?? 0) - items.length;

  return (
    <Modal title={row.feedback} onClose={onClose} wide>
      <div className="ir">
        <header className="ir__head">
          <button type="button" className="ir__close" onClick={onClose} aria-label="Close">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
              <path d="M6 6l12 12M18 6 6 18" />
            </svg>
          </button>
          <h2>{row.feedback}</h2>
          <p className="ir__stats">
            <span>{row.count.toLocaleString()} reviews</span>
            <span>{row.impact}% of complaints</span>
            <span>avg {row.avgRating.toFixed(1)}★</span>
            <span>latest {fmtDate(row.latest)}</span>
          </p>
          <div className="ir__tags">
            <PriorityBadge priority={row.priority} />
            <CategoryPill category={row.category} />
          </div>
          <div className="ir__fix">
            <span className="ir__fix-label">Suggested fix</span>
            <p>{row.solution}</p>
            <Evidence items={row.evidence} />
          </div>
        </header>

        <div className="ir__controls">
          <div className="ir__search">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.5-3.5" />
            </svg>
            <input type="search" placeholder="Search reviews" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search reviews" />
          </div>
          <div className="ir__stars" role="group" aria-label="Filter by rating">
            <button type="button" aria-pressed={stars === null} onClick={() => setStars(null)}>
              All
            </button>
            {[1, 2, 3, 4, 5].map((s) =>
              starCount(s) ? (
                <button key={s} type="button" aria-pressed={stars === s} onClick={() => setStars(stars === s ? null : s)}>
                  {s}★ <span>{starCount(s).toLocaleString()}</span>
                </button>
              ) : null,
            )}
          </div>
          <div className="ir__sort">
            <Select
              label="Sort"
              value={sort}
              options={[
                { value: "relevant", label: "Most relevant" },
                { value: "newest", label: "Newest" },
                { value: "helpful", label: "Most helpful" },
              ]}
              onChange={(v) => setSort(v as Sort)}
            />
          </div>
        </div>

        <div className="ir__list" aria-live="polite" aria-busy={loading}>
          {error && <p className="ir__empty">{error}</p>}
          {!error && !page && (
            <div className="ir__loading" aria-label="Loading reviews">
              {[0, 1, 2].map((i) => (
                <span key={i} />
              ))}
            </div>
          )}
          {page && !loading && items.length === 0 && <p className="ir__empty">No reviews match.</p>}
          {items.map((r, i) => (
            <article className="ir__review" key={i}>
              <div className="ir__meta">
                <span className="quote__stars" aria-label={`${r.rating} stars`}>
                  {"★".repeat(r.rating)}
                  <span>{"★".repeat(5 - r.rating)}</span>
                </span>
                <span>{fmtDate(r.date)}</span>
                {r.thumbs > 0 && <span>{r.thumbs.toLocaleString()} found helpful</span>}
              </div>
              {r.title && <strong>{r.title}</strong>}
              <p>
                <Highlighted text={r.text} concern={r.concern} />
              </p>
            </article>
          ))}
          {left > 0 && (
            <button type="button" className="ir__more" onClick={more} disabled={loading}>
              {loading ? "Loading…" : `Show ${Math.min(PAGE, left).toLocaleString()} more of ${left.toLocaleString()}`}
            </button>
          )}
        </div>
      </div>
    </Modal>
  );
}

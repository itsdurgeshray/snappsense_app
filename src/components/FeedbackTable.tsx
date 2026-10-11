import { useMemo, useState, type ReactNode } from "react";
import { CATEGORY_STYLE, PRIORITY_RANK, type AppReport, type Category, type FeedbackRow, type Priority } from "../data";
import { IssueReviews } from "./IssueReviews";

type SortKey = "category" | "feedback" | "count" | "priority";

export interface TableFilters {
  category: Category | "All";
  priority: Priority | "All";
}

function SortIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.2" aria-hidden="true">
      <path d="M3.5 1.5v9M1.5 3.5l2-2 2 2M8.5 10.5v-9M6.5 8.5l2 2 2-2" />
    </svg>
  );
}

/** Speech bubble with lines: "read what users said". */
function ReviewsIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-4.6A8 8 0 1 1 21 12Z" />
      <path d="M8.5 10.5h7M8.5 14h4.5" />
    </svg>
  );
}

export function PriorityBadge({ priority = "low" }: { priority?: Priority }) {
  return <span className={`prio prio--${priority}`}>{priority[0].toUpperCase() + priority.slice(1)}</span>;
}

export function Evidence({ items }: { items?: string[] }) {
  if (!items?.length) return null;
  return (
    <ul className="evidence">
      {items.map((e) => (
        <li key={e}>{e}</li>
      ))}
    </ul>
  );
}

export function CategoryPill({ category }: { category: Category }) {
  const s = CATEGORY_STYLE[category] ?? { bg: "#f3eef5", fg: "var(--ink-2)" };
  return (
    <span className="tag" style={{ background: s.bg, color: s.fg }}>
      {category}
    </span>
  );
}

/** A labelled dropdown where the whole box is clickable (the native select covers it). */
export function Select({ label, value, options, onChange }: { label: string; value: string; options: { value: string; label: string }[]; onChange: (v: string) => void }) {
  const current = options.find((o) => o.value === value)?.label ?? value;
  return (
    <label className="select">
      <span className="select__label">{label}</span>
      <span className="select__value">{current}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function filterRows(rows: FeedbackRow[], f: TableFilters) {
  return rows.filter((r) => (f.category === "All" || r.category === f.category) && (f.priority === "All" || r.priority === f.priority));
}

export function exportFeedbackCsv(rows: FeedbackRow[], appName: string) {
  const esc = (v: string | number) => `"${String(v).replace(/"/g, '""')}"`;
  const csv = [
    ["Priority", "Category", "Generalized Feedback", "Suggested Fix", "Evidence", "Mentions", "Share of Concerns (%)", "Avg Rating", "Dominant Sentiment", "Latest Mention"],
    ...rows.map((r) => [r.priority, r.category, r.feedback, r.solution, (r.evidence ?? []).join("; "), r.count, r.impact, r.avgRating, r.sentiment, r.latest]),
  ]
    .map((line) => line.map(esc).join(","))
    .join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  a.download = `${appName.replace(/\W+/g, "-").toLowerCase()}-feedback.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function fmt(d: string, withYear: boolean) {
  return new Date(d).toLocaleDateString(undefined, withYear ? { day: "numeric", month: "short", year: "numeric" } : { day: "numeric", month: "short" });
}

const DAY = 86_400_000;

/**
 * One plain line saying what the table covers, e.g.
 * "Current versions v9.1.84 – v9.1.90 · since 21 Sep · 7,986 reviews · 2,140 complaints"
 * or "Last 90 days · 812 reviews · 240 complaints".
 */
function basisLine(sample: AppReport["sample"]) {
  const sc = sample.scope;
  if (sc) {
    const counts = `${sample.analyzed.toLocaleString()} reviews · ${sample.concerns.toLocaleString()} complaints`;
    const since = new Date(sc.since);
    const withYear = since.getFullYear() !== new Date().getFullYear();
    if (sc.kind === "versions") {
      const v = sc.versions;
      const which = v.length === 1 ? `Current version v${v[0]}` : `Current versions v${v[0]} – v${v[v.length - 1]}`;
      return `${which} · since ${fmt(sc.since, withYear)} · ${counts}`;
    }
    const days = Math.round(((sample.newest ? new Date(sample.newest).getTime() : Date.now()) - since.getTime()) / DAY);
    return `${days >= 85 ? "Last 90 days" : `Since ${fmt(sc.since, withYear)}`} · ${counts}`;
  }
  const scope = sample.featuredOnly
    ? `${sample.analyzed.toLocaleString()} public App Store reviews`
    : sample.complete
      ? `all ${sample.analyzed.toLocaleString()} reviews`
      : `the latest ${sample.analyzed.toLocaleString()} reviews`;
  const parts = [`From ${sample.concerns.toLocaleString()} complaints in ${scope}`];
  if (sample.oldest && sample.newest) {
    const year = new Date().getFullYear();
    const withYear = new Date(sample.oldest).getFullYear() !== year || new Date(sample.newest).getFullYear() !== year;
    parts.push(`${fmt(sample.oldest, withYear)} – ${fmt(sample.newest, withYear)}`);
  }
  return parts.join(" · ");
}

export function FeedbackTable({
  rows,
  reportId,
  sample,
  filters,
  onFilters,
  basis,
  versionControl,
  versions,
  emptyText,
}: {
  rows: FeedbackRow[];
  reportId: string;
  sample: AppReport["sample"];
  filters: TableFilters;
  onFilters: (f: TableFilters) => void;
  /** Summary line override (e.g. for the picked versions). */
  basis?: string;
  /** The version picker, shown with the other filters. */
  versionControl?: ReactNode;
  /** Picked versions: the reviews popup shows only these. */
  versions?: string[];
  /** Message when there are no rows (e.g. no version picked). */
  emptyText?: string;
}) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 } | null>(null);
  const [detail, setDetail] = useState<FeedbackRow | null>(null);

  const maxCount = Math.max(...rows.map((r) => r.count), 1);
  const categories = useMemo(() => [...new Set(rows.map((r) => r.category))], [rows]);
  const priorities = useMemo(() => (["high", "medium", "low"] as Priority[]).filter((p) => rows.some((r) => r.priority === p)), [rows]);
  const visible = useMemo(() => {
    const list = filterRows(rows, filters);
    if (!sort) return list;
    return [...list].sort((a, b) => {
      if (sort.key === "priority") return (PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority] || a.count - b.count) * sort.dir;
      const av = a[sort.key], bv = b[sort.key];
      return (typeof av === "number" ? av - (bv as number) : String(av).localeCompare(String(bv))) * sort.dir;
    });
  }, [rows, sort, filters]);

  const toggleSort = (key: SortKey) =>
    setSort((s) => (s?.key === key ? (s.dir === 1 ? { key, dir: -1 } : null) : { key, dir: key === "count" || key === "priority" ? -1 : 1 }));
  const ariaSort = (key: SortKey) => (sort?.key === key ? (sort.dir === 1 ? "ascending" : "descending") : "none");
  const filtered = filters.category !== "All" || filters.priority !== "All";

  return (
    <section aria-labelledby="table-title">
      <div className="card table-card">
        <div className="table-toolbar">
          <div className="table-toolbar__title">
            <h2 className="card__title" id="table-title">
              Feedback Analysis Table <span className="table-toolbar__n">({visible.length})</span>
            </h2>
            <p className="section-sub">
              {basis ?? basisLine(sample)}
              {filtered && (
                <button type="button" className="link-btn" onClick={() => onFilters({ category: "All", priority: "All" })}>
                  Clear filters
                </button>
              )}
            </p>
          </div>
          <div className="table-filters">
            {versionControl}
            <Select
              label="Category"
              value={filters.category}
              options={[{ value: "All", label: "All" }, ...categories.map((c) => ({ value: c, label: c }))]}
              onChange={(v) => onFilters({ ...filters, category: v as TableFilters["category"] })}
            />
            <Select
              label="Priority"
              value={filters.priority}
              options={[{ value: "All", label: "All" }, ...priorities.map((p) => ({ value: p, label: p[0].toUpperCase() + p.slice(1) }))]}
              onChange={(v) => onFilters({ ...filters, priority: v as TableFilters["priority"] })}
            />
          </div>
        </div>
        <div className="table-scroll">
          <table className="fb-table">
            <thead>
              <tr>
                <th aria-sort={ariaSort("category")}>
                  <button type="button" className="sort-btn" onClick={() => toggleSort("category")}>
                    Category <SortIcon />
                  </button>
                </th>
                <th aria-sort={ariaSort("feedback")}>
                  <button type="button" className="sort-btn" onClick={() => toggleSort("feedback")}>
                    Generalized Feedback <SortIcon />
                  </button>
                </th>
                <th aria-sort={ariaSort("priority")} className="th-prio">
                  <button type="button" className="sort-btn" onClick={() => toggleSort("priority")}>
                    Priority <SortIcon />
                  </button>
                </th>
                <th>Suggested Fix</th>
                <th className="th-num" aria-sort={ariaSort("count")}>
                  <button type="button" className="sort-btn" onClick={() => toggleSort("count")}>
                    Count <SortIcon />
                  </button>
                </th>
                <th style={{ width: 56 }}>
                  <span className="sr-only">Reviews</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => (
                <tr key={r.id}>
                  <td>
                    <CategoryPill category={r.category} />
                  </td>
                  <td className="td-feedback">{r.feedback}</td>
                  <td>
                    <PriorityBadge priority={r.priority} />
                  </td>
                  <td className="td-solution">
                    {r.solution}
                    <Evidence items={r.evidence} />
                  </td>
                  <td className="td-num">
                    <span className="count">
                      <span className="count__bar" style={{ width: (r.count / maxCount) * 36 }} />
                      {r.count}
                    </span>
                    <span className="count__share">{r.impact}%</span>
                  </td>
                  <td>
                    <button type="button" className="icon-btn reviews-btn" aria-label={`Read all ${r.count} reviews: ${r.feedback}`} title={`Read all ${r.count} reviews`} onClick={() => setDetail(r)}>
                      <ReviewsIcon />
                    </button>
                  </td>
                </tr>
              ))}
              {visible.length === 0 && (
                <tr>
                  <td colSpan={6} className="td-empty">
                    {emptyText ?? "No issues match these filters."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {detail && <IssueReviews reportId={reportId} row={detail} versions={versions} onClose={() => setDetail(null)} />}
    </section>
  );
}

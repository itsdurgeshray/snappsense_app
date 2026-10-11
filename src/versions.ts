// The feedback table for any set of app versions, computed in the browser.
// Issues are clustered once (server), each with per-version stats, so picking
// versions only re-counts and re-ranks: instant, no round trip. The ranking
// and priority rules mirror backend/app/analysis/pipeline.py.

import type { AppReport, Category, FeedbackRow, Priority, SentimentKey } from "./data";

const MAX_ISSUES = 20;
const SEVERITY: Record<string, number> = {
  Crash: 1.3, Transactional: 1.25, "Bug Report": 1.1, Support: 1.0, Performance: 1.0, "Pricing & Ads": 0.9, "UI/UX": 0.85, "Feature Request": 0.7,
};

export function versionsOf(report: AppReport): { all: string[]; labels: Record<string, string>; latest: string[] } | null {
  const sc = report.sample.scope;
  if (!sc || sc.kind !== "versions" || !sc.versions.length || !report.feedback.some((r) => r.byVersion)) return null;
  return { all: sc.versions, labels: sc.labels ?? {}, latest: sc.default?.length ? sc.default : [sc.versions[0]] };
}

function priorities(rows: FeedbackRow[]) {
  const total = rows.reduce((a, r) => a + r.count, 0) || 1;
  const scores = rows.map((r) => {
    const impact = r.count / total;
    r.impact = Math.round(1000 * impact) / 10;
    const anger = Math.max(0, Math.min(1, (5 - r.avgRating) / 4));
    return impact * (0.5 + anger) * (SEVERITY[r.category] ?? 1);
  });
  const top = Math.max(...scores, 0) || 1;
  let high = 4;
  rows
    .map((r, i) => ({ r, s: scores[i] }))
    .sort((a, b) => b.s - a.s)
    .forEach(({ r, s }) => {
      const rel = s / top;
      let level: Priority = rel >= 0.45 && r.count >= 5 && r.impact >= 5 && high > 0 ? "high" : rel >= 0.15 || r.count >= 15 ? "medium" : "low";
      if (r.category === "Feature Request" && level === "high" && r.count < 20) level = "medium";
      if (level === "high") high--;
      r.priority = level;
    });
}

/** Rows, category breakdown and totals for the picked versions. */
export function tableFor(report: AppReport, picked: string[]) {
  const sc = report.sample.scope;
  if (!versionsOf(report)) {
    return { rows: report.feedback, categories: report.categories, reviews: report.sample.analyzed, concerns: report.sample.concerns };
  }
  if (!picked.length) return { rows: [], categories: [], reviews: 0, concerns: 0 };
  const set = new Set(picked);
  const candidates: FeedbackRow[] = [];
  for (const row of report.feedback) {
    let n = 0, stars = 0, latest = "";
    const sent: Partial<Record<SentimentKey, number>> = {};
    for (const [v, d] of Object.entries(row.byVersion ?? {})) {
      if (!set.has(v)) continue;
      n += d.n;
      stars += d.stars;
      if (d.latest > latest) latest = d.latest;
      for (const [k, c] of Object.entries(d.sent)) sent[k as SentimentKey] = (sent[k as SentimentKey] ?? 0) + (c ?? 0);
    }
    if (!n) continue;
    const top = (Object.entries(sent) as [SentimentKey, number][]).sort((a, b) => b[1] - a[1])[0];
    candidates.push({ ...row, count: n, avgRating: Math.round((100 * stars) / n) / 100, latest, sentiment: top ? top[0] : row.sentiment });
  }
  const reviews = picked.reduce((a, v) => a + (sc?.totals?.[v]?.reviews ?? 0), 0);
  const concerns = picked.reduce((a, v) => a + (sc?.totals?.[v]?.concerns ?? 0), 0);

  // Same selection as the server: each category's biggest issue, then the rest by size.
  const byCat = new Map<Category, FeedbackRow[]>();
  for (const r of candidates) byCat.set(r.category, [...(byCat.get(r.category) ?? []), r]);
  const chosen = [...byCat.values()].map((rs) => rs.reduce((a, b) => (b.count > a.count ? b : a)));
  const rest = candidates.filter((r) => !chosen.includes(r) && r.count >= 2).sort((a, b) => b.count - a.count);
  const rows = [...chosen, ...rest.slice(0, Math.max(0, MAX_ISSUES - chosen.length))].sort((a, b) => b.count - a.count);
  for (const r of rows) r.share = Math.round((1000 * r.count) / Math.max(1, reviews)) / 10;
  priorities(rows);

  const catCount = new Map<Category, number>();
  for (const r of candidates) catCount.set(r.category, (catCount.get(r.category) ?? 0) + r.count);
  const catTotal = [...catCount.values()].reduce((a, b) => a + b, 0) || 1;
  const categories = [...catCount.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([label, count]) => ({ label, count, share: Math.round((1000 * count) / catTotal) / 10 }));
  return { rows, categories, reviews, concerns };
}

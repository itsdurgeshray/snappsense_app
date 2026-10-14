import { useEffect, useMemo, useState } from "react";
import { Header } from "../components/Header";
import { SentimentTrends } from "../components/SentimentTrends";
import { RatingsGauge } from "../components/RatingsGauge";
import { FeedbackTable, exportFeedbackCsv, filterRows, type TableFilters } from "../components/FeedbackTable";
import { FeedbackCategory } from "../components/FeedbackCategory";
import { Loader } from "../components/Loader";
import { VersionPicker } from "../components/VersionPicker";
import { tableFor, versionsOf } from "../versions";
import { useReport } from "../api";
import { STORE_LABEL, formatCompact, formatInstalls, type AppReport, type Depth, type Store } from "../data";
import { navigate } from "../router";

function AppIcon({ src, name }: { src: string | null | undefined; name: string }) {
  const [broken, setBroken] = useState(false);
  if (src && !broken) {
    return <img className="dash-app__icon" src={src} alt={`${name} app icon`} width={56} height={56} onError={() => setBroken(true)} />;
  }
  return (
    <div className="dash-app__icon dash-app__icon--blank" aria-hidden="true">
      {name.charAt(0).toUpperCase()}
    </div>
  );
}

/** "v2.25.1 · since 3 Oct · 4,120 reviews · 1,034 complaints" for the picked versions. */
function versionBasis(report: AppReport, picked: string[], reviews: number, concerns: number) {
  const sc = report.sample.scope!;
  const label = (v: string) => `v${sc.labels?.[v] ?? v}`;
  const ordered = sc.versions.filter((v) => picked.includes(v));
  const which = ordered.length === 1 ? label(ordered[0]) : `${label(ordered[ordered.length - 1])} – ${label(ordered[0])}`;
  const since = ordered.map((v) => sc.totals?.[v]?.since).filter(Boolean).sort()[0];
  const date = since ? ` · since ${new Date(since).toLocaleDateString(undefined, { day: "numeric", month: "short" })}` : "";
  return `${which}${date} · ${reviews.toLocaleString()} reviews · ${concerns.toLocaleString()} complaints`;
}

/** Shown while a long run keeps downloading: the report below updates by itself. */
function RunBanner({ analyzed }: { analyzed: number }) {
  return (
    <div className="run-banner dash-full" role="status" aria-live="polite">
      <span className="run-banner__spin" aria-hidden="true" />
      <p>
        <strong>Reading more reviews ({analyzed.toLocaleString()} so far).</strong> The report updates as they arrive.
      </p>
    </div>
  );
}

export function Dashboard({ store, appId, country, depth }: { store: Store; appId: string; country: string; depth: Depth }) {
  const { report, progress, appName, appIcon, error, reload } = useReport({ store, appId, country, depth });
  const [filters, setFilters] = useState<TableFilters>({ category: "All", priority: "All" });
  const [picked, setPicked] = useState<string[]>([]);
  const vers = useMemo(() => (report ? versionsOf(report) : null), [report]);
  // Opens on the latest version; a new report (e.g. partial → final) keeps the pick if it still exists.
  useEffect(() => {
    if (!vers) return;
    setPicked((p) => (p.length && p.every((v) => vers.all.includes(v)) ? p : vers.latest));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [report?.generatedAt]);
  const view = useMemo(() => (report ? tableFor(report, picked) : null), [report, picked]);

  const name = report?.app.name ?? appName ?? appId;
  const a = report?.app;
  useEffect(() => {
    document.title = report ? `${report.app.name} feedback analysis · Snappsense` : "Analysing… · Snappsense";
  }, [report]);

  if (!report && !error) return <Loader progress={progress} icon={appIcon} name={appName ?? ""} onCancel={() => navigate("/")} />;

  return (
    <>
      <div className="dash-hero">
        <Header tone="dark" />
        <div className="container">
          <div className="dash-app">
            <AppIcon src={report?.app.icon ?? appIcon} name={name} />
            <div className="dash-app__body">
              <h1 className="dash-app__title">{name}</h1>
              <div className="dash-tags">
                <span className="dash-tag">{STORE_LABEL[store]}</span>
                {a?.genre && <span className="dash-tag">{a.genre}</span>}
                {a?.rating != null && (
                  <span className="dash-tag">
                    ★ {a.rating.toFixed(1)}
                    {a.ratingsCount ? ` · ${formatCompact(a.ratingsCount)} ratings` : ""}
                  </span>
                )}
                {a?.installs && <span className="dash-tag">{formatInstalls(a.installs)} installs</span>}
              </div>
              {a?.developer && <p className="dash-app__dev">by {a.developer}</p>}
            </div>
            {report && (
              <div className="dash-actions">
                <button type="button" className="btn-ghost" onClick={() => exportFeedbackCsv(filterRows(view?.rows ?? report.feedback, filters), report.app.name)}>
                  Export CSV
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
                    <path d="M6 1.5v7M3 5.5l3 3 3-3M1.5 10.5h9" />
                  </svg>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      <main className="container dash-body">
        {error ? (
          <section className="card error-card" role="alert">
            <h2 className="card__title">{error.code === "not_found" ? "We couldn’t find that app" : "Something went wrong"}</h2>
            <p>{error.message}</p>
            <div className="error-card__actions">
              <button type="button" className="btn-sm btn-sm--dark" onClick={() => reload(false)}>
                Try again
              </button>
              <button type="button" className="btn-sm" onClick={() => navigate("/")}>
                Analyze another app
              </button>
            </div>
          </section>
        ) : !report ? null : (
          <div className="dash-grid">
            {report.partial && <RunBanner analyzed={Math.max(report.partial.analyzed, progress?.fetched ?? 0)} />}
            <SentimentTrends key={report.id + report.generatedAt} trends={report.trends} />
            <RatingsGauge ratings={report.ratings} basis={report.ratingsBasis} />
            <div className="dash-full">
              <FeedbackCategory categories={view?.categories ?? report.categories} emptyText={vers && !picked.length ? "Pick one or more versions in the table below." : undefined} />
            </div>
            <div className="dash-full">
              <FeedbackTable
                rows={view?.rows ?? report.feedback}
                reportId={report.id}
                sample={report.sample}
                filters={filters}
                onFilters={setFilters}
                basis={vers && view ? (picked.length ? versionBasis(report, picked, view.reviews, view.concerns) : "No version selected") : undefined}
                emptyText={vers && !picked.length ? "Pick one or more versions to see their issues." : undefined}
                versions={vers ? picked : undefined}
                versionControl={
                  vers && (
                    <VersionPicker
                      versions={vers.all}
                      labels={vers.labels}
                      latest={vers.latest}
                      counts={Object.fromEntries(vers.all.map((v) => [v, report.sample.scope?.totals?.[v]?.reviews ?? 0]))}
                      picked={picked}
                      onChange={setPicked}
                    />
                  )
                }
              />
            </div>
          </div>
        )}
      </main>
    </>
  );
}

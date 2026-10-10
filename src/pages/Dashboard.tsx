import { useEffect, useState } from "react";
import { Header } from "../components/Header";
import { SentimentTrends } from "../components/SentimentTrends";
import { RatingsGauge } from "../components/RatingsGauge";
import { FeedbackTable, exportFeedbackCsv, filterRows, type TableFilters } from "../components/FeedbackTable";
import { FeedbackCategory } from "../components/FeedbackCategory";
import { Loader } from "../components/Loader";
import { useReport } from "../api";
import { STORE_LABEL, formatCompact, formatInstalls, type Depth, type Store } from "../data";
import { navigate } from "../router";

function AppIcon({ src, name }: { src: string | null | undefined; name: string }) {
  const [broken, setBroken] = useState(false);
  if (src && !broken) {
    return <img className="dash-app__icon" src={src} alt="" width={56} height={56} onError={() => setBroken(true)} />;
  }
  return (
    <div className="dash-app__icon dash-app__icon--blank" aria-hidden="true">
      {name.charAt(0).toUpperCase()}
    </div>
  );
}

export function Dashboard({ store, appId, country, depth }: { store: Store; appId: string; country: string; depth: Depth }) {
  const { report, progress, appName, appIcon, error, status, reload } = useReport({ store, appId, country, depth });
  const [startedAt, setStartedAt] = useState(() => performance.now());
  const [filters, setFilters] = useState<TableFilters>({ category: "All", priority: "All" });
  useEffect(() => {
    if (status === "loading") setStartedAt(performance.now());
  }, [status]);

  const name = report?.app.name ?? appName ?? appId;
  const a = report?.app;

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
                <button type="button" className="btn-ghost" onClick={() => exportFeedbackCsv(filterRows(report.feedback, filters), report.app.name)}>
                  Export CSV
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
                    <path d="M6 1.5v7M3 5.5l3 3 3-3M1.5 10.5h9" />
                  </svg>
                </button>
                {depth !== "deep" && (
                  <button
                    type="button"
                    className="btn-ghost btn-ghost--solid"
                    onClick={() => navigate(`/app/${store}/${appId}?country=${country}&depth=deep`)}
                    title="Analyse up to 10,000 reviews for longer trends and rarer issues"
                  >
                    Deep analysis
                  </button>
                )}
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
        ) : !report ? (
          <Loader progress={progress} icon={appIcon} name={name} startedAt={startedAt} />
        ) : (
          <div className="dash-grid">
            <SentimentTrends key={report.id + report.generatedAt} trends={report.trends} />
            <RatingsGauge ratings={report.ratings} basis={report.ratingsBasis} />
            <div className="dash-full">
              <FeedbackCategory categories={report.categories} />
            </div>
            <div className="dash-full">
              <FeedbackTable
                rows={report.feedback}
                reportId={report.id}
                sample={report.sample}
                filters={filters}
                onFilters={setFilters}
              />
            </div>
          </div>
        )}
      </main>
    </>
  );
}

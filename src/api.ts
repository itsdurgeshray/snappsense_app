import { useCallback, useEffect, useRef, useState } from "react";
import type { AppReport, Depth, IssueReview, Store } from "./data";

const BASE = import.meta.env.VITE_API_URL ?? "";

export interface Progress {
  stage: "connecting" | "queued" | "meta" | "fetch" | "analyze" | "polish";
  fetched?: number;
  target?: number | null;
  limit?: number;
  name?: string;
  icon?: string | null;
  reviews?: number;
  issues?: number;
}

export interface ReportState {
  report: AppReport | null;
  progress: Progress | null;
  appName: string | null;
  appIcon: string | null;
  error: { code: string; message: string } | null;
  status: "loading" | "partial" | "done" | "error";
  cached: boolean;
  elapsedMs: number;
}

interface Params {
  store: Store;
  appId: string;
  country: string;
  depth: Depth;
}

const initial: ReportState = { report: null, progress: { stage: "connecting" }, appName: null, appIcon: null, error: null, status: "loading", cached: false, elapsedMs: 0 };

/** Starts (or reuses) an analysis and follows its progress stream. */
export function useReport({ store, appId, country, depth }: Params) {
  const [state, setState] = useState<ReportState>(initial);
  const [nonce, setNonce] = useState(0);
  const refresh = useRef(false);

  const reload = useCallback((force = true) => {
    refresh.current = force;
    setNonce((n) => n + 1);
  }, []);

  useEffect(() => {
    let es: EventSource | null = null;
    let poll: number | undefined;
    let cancelled = false;
    const t0 = performance.now();
    const elapsed = () => Math.round(performance.now() - t0);
    setState({ ...initial });

    const fail = (code: string, message: string) => !cancelled && setState((s) => ({ ...s, status: "error", error: { code, message }, elapsedMs: elapsed() }));

    (async () => {
      let res: Response;
      try {
        res = await fetch(`${BASE}/api/analyze`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ store, appId, country, depth, refresh: refresh.current }),
        });
      } catch {
        return fail("offline", "Can't reach the Snappsense API. Is the backend running?");
      }
      refresh.current = false;
      const body = await res.json().catch(() => ({}));
      if (cancelled) return;
      if (!res.ok) return fail("bad_request", body.detail ?? "That link couldn't be analysed.");
      if (body.status === "done" && body.report) {
        return setState({ ...initial, report: body.report, appName: body.report.app.name, status: "done", progress: null, cached: !!body.cached, elapsedMs: elapsed() });
      }

      const jobId: string = body.jobId;
      const onReport = (report: AppReport, final: boolean) =>
        setState((s) => ({ ...s, report, appName: report.app.name, status: final ? "done" : "partial", elapsedMs: s.elapsedMs || elapsed() }));

      es = new EventSource(`${BASE}/api/jobs/${jobId}/events`);
      es.addEventListener("progress", (e) => {
        const p = JSON.parse((e as MessageEvent).data) as Progress;
        setState((s) => ({ ...s, progress: p, appName: p.name ?? s.appName, appIcon: p.icon ?? s.appIcon }));
      });
      es.addEventListener("report", (e) => {
        const { report } = JSON.parse((e as MessageEvent).data) as { report: AppReport };
        onReport(report, false);
      });
      es.addEventListener("done", () => {
        setState((s) => ({ ...s, status: s.report ? "done" : s.status, progress: null }));
        es?.close();
      });
      es.addEventListener("error", (e) => {
        const data = (e as MessageEvent).data;
        if (data) {
          const err = JSON.parse(data);
          fail(err.code, err.message);
          es?.close();
          return;
        }
        // Transport error: fall back to polling the job.
        es?.close();
        poll = window.setInterval(async () => {
          try {
            const s = await (await fetch(`${BASE}/api/jobs/${jobId}`)).json();
            if (cancelled) return;
            if (s.report) onReport(s.report, s.status === "done");
            if (s.progress) setState((st) => ({ ...st, progress: s.progress }));
            if (s.status === "error") fail(s.error.code, s.error.message);
            if (s.status !== "running") window.clearInterval(poll);
          } catch {
            /* keep polling */
          }
        }, 1000);
      });
    })();

    return () => {
      cancelled = true;
      es?.close();
      window.clearInterval(poll);
    };
  }, [store, appId, country, depth, nonce]);

  return { ...state, reload };
}

export interface ReviewPage {
  /** Reviews behind the issue, and how many match the current search/filter. */
  total: number;
  matched: number;
  /** Count per star rating ("1" … "5") across the whole issue. */
  stars: Record<string, number>;
  reviews: IssueReview[];
}

export interface ReviewQuery {
  offset?: number;
  limit?: number;
  q?: string;
  stars?: number | null;
  sort?: "relevant" | "newest" | "helpful";
  versions?: string[];
}

/** One page of the reviews behind a feedback row (paged, searched and sorted on the server). */
export async function fetchIssueReviews(reportId: string, issueId: string, query: ReviewQuery = {}, signal?: AbortSignal): Promise<ReviewPage> {
  const params = new URLSearchParams({ report: reportId, issue: issueId, offset: String(query.offset ?? 0), limit: String(query.limit ?? 40), sort: query.sort ?? "relevant" });
  if (query.q?.trim()) params.set("q", query.q.trim());
  if (query.stars) params.set("stars", String(query.stars));
  if (query.versions?.length) params.set("versions", query.versions.join(","));
  const res = await fetch(`${BASE}/api/reviews?${params}`, { signal });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail ?? "Couldn't load these reviews.");
  return body as ReviewPage;
}

/** Sends a "Give feedback" message to the server. */
export async function sendFeedback(body: { rating: number | null; message: string; page: string }) {
  const res = await fetch(`${BASE}/api/feedback`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) throw new Error("send failed");
}

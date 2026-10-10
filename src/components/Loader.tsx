import { useEffect, useState } from "react";
import type { Progress } from "../api";
import { LogoMark } from "./Logo";

const STAGE_LABEL: Record<Progress["stage"], string> = {
  connecting: "Connecting to the store",
  queued: "Getting ready",
  meta: "Found the app",
  fetch: "Fetching reviews",
  analyze: "Reading sentiment & finding issues",
  polish: "Polishing issue titles",
};

/**
 * Snappsense mark spins while working; once the app is found it morphs into
 * the app's icon and back, looping until the report is ready.
 */
export function Loader({ progress, icon, name, startedAt }: { progress: Progress | null; icon: string | null; name: string; startedAt: number }) {
  const [, tick] = useState(0);
  const [iconOk, setIconOk] = useState(false);
  useEffect(() => {
    const t = window.setInterval(() => tick((n) => n + 1), 100);
    return () => window.clearInterval(t);
  }, []);

  const stage = progress?.stage ?? "connecting";
  const detail =
    stage === "fetch" && progress?.fetched
      ? `${progress.fetched.toLocaleString()}${progress.target ? ` of ${progress.target.toLocaleString()}` : ""} reviews`
      : stage === "analyze" && progress?.reviews
        ? `${progress.reviews.toLocaleString()} reviews`
        : stage === "meta"
          ? name
          : "";
  const pct = stage === "fetch" && progress?.target ? Math.min(100, (100 * (progress.fetched ?? 0)) / progress.target) : stage === "analyze" || stage === "polish" ? 100 : undefined;
  const morph = Boolean(icon && iconOk);

  return (
    <section className="loader" aria-live="polite" aria-busy="true">
      <div className={`loader__stage${morph ? " is-morphing" : ""}`}>
        <LogoMark size={88} className="loader__logo" />
        {icon && <img className="loader__icon" src={icon} alt="" width={88} height={88} onLoad={() => setIconOk(true)} onError={() => setIconOk(false)} />}
      </div>
      <p className="loader__stage-label" key={stage}>
        {STAGE_LABEL[stage]}
      </p>
      <p className="loader__detail">
        {detail || " "}
        <span className="loader__time">{((performance.now() - startedAt) / 1000).toFixed(1)}s</span>
      </p>
      <div className={`loader__bar${pct === undefined ? " is-indeterminate" : ""}`}>
        <span style={pct === undefined ? undefined : { width: `${pct}%` }} />
      </div>
    </section>
  );
}

import { useEffect, useState } from "react";
import type { Progress } from "../api";
import { MARK_ARC, MARK_CENTER, MARK_DASHES, MARK_SQUARE } from "./Logo";

/**
 * What we say while working. Each stage walks through its lines (one every
 * few seconds) and holds on the last, so a ~30 s run never repeats itself.
 */
const SCRIPT: Record<"connect" | "fetch" | "analyze", (name: string) => string[]> = {
  connect: () => ["Connecting to the store", "Waking up the analysis engine", "The first run after a quiet spell takes a little longer", "Still warming up — hang tight"],
  fetch: (name) => [
    name ? `Found ${name}` : "Found the app",
    "Collecting the latest reviews",
    "Covering every rating, 1★ to 5★",
    "Reading from the newest reviews back",
  ],
  analyze: () => [
    "Reading the mood of every review",
    "Separating complaints from praise",
    "Spotting crashes, bugs and payment issues",
    "Grouping complaints that share a root cause",
    "Telling feature requests apart",
    "Writing a one-line summary for each issue",
    "Checking which versions and devices are affected",
    "Ranking issues by how many people they hit",
    "Matching each issue with a suggested fix",
    "Building your dashboard",
    "Almost there",
  ],
};
const LINE_MS = 3000;
const SPIN_MS = 6200; // spinner time between app-icon reveals
const ICON_MS = 3400; // how long the app icon holds

function group(stage: Progress["stage"]): keyof typeof SCRIPT {
  return stage === "analyze" || stage === "polish" ? "analyze" : stage === "meta" || stage === "fetch" ? "fetch" : "connect";
}

/**
 * Full-screen loader. The Snappsense mark's centre square stays put while the
 * arc and dashes build up and wind down around it like a spinner. Once the
 * app's icon arrives, the square pops into that icon, holds, and shrinks back.
 */
export function Loader({ progress, icon, name }: { progress: Progress | null; icon: string | null; name: string }) {
  const stage = progress?.stage ?? "connecting";
  const g = group(stage);
  const lines = SCRIPT[g](name);

  // Advance through this stage's lines, restarting when the stage changes.
  const [line, setLine] = useState(0);
  useEffect(() => {
    setLine(0);
    const t = window.setInterval(() => setLine((n) => n + 1), LINE_MS);
    return () => window.clearInterval(t);
  }, [g]);
  const text = lines[Math.min(line, lines.length - 1)];

  // Spinner ↔ app icon. The icon shows as soon as it loads, then alternates.
  const [iconReady, setIconReady] = useState(false);
  const [showIcon, setShowIcon] = useState(false);
  const [round, setRound] = useState(0);
  useEffect(() => {
    if (!iconReady) return;
    setShowIcon(true);
    let on = true;
    let t = 0;
    const flip = () => {
      t = window.setTimeout(() => {
        on = !on;
        setShowIcon(on);
        if (!on) setRound((r) => r + 1); // restart the spinner from empty
        flip();
      }, on ? ICON_MS : SPIN_MS);
    };
    flip();
    return () => window.clearTimeout(t);
  }, [iconReady]);

  const detail =
    g === "fetch" && progress?.fetched
      ? `${progress.fetched.toLocaleString()}${progress.target ? ` of ${progress.target.toLocaleString()}` : ""} reviews`
      : g === "analyze" && progress?.reviews
        ? `${progress.reviews.toLocaleString()} reviews`
        : "";

  return (
    <div className="ld" role="status" aria-live="polite" aria-busy="true">
      <div className={`ld__mark${showIcon ? " is-icon" : ""}`}>
        <svg className="ld__svg" viewBox="6 16 49 49" aria-hidden="true">
          <defs>
            <mask id="ld-arc-mask" maskUnits="userSpaceOnUse" x="6" y="16" width="49" height="49">
              <circle
                className="ld__arc-reveal"
                cx={MARK_CENTER.x}
                cy={MARK_CENTER.y}
                r="19.8"
                pathLength={100}
                transform={`rotate(-90 ${MARK_CENTER.x} ${MARK_CENTER.y})`}
              />
            </mask>
          </defs>
          <g className="ld__ring" key={round}>
            <path className="ld__arc" d={MARK_ARC} mask="url(#ld-arc-mask)" fillRule="evenodd" />
            {MARK_DASHES.map((d, i) => (
              <path key={i} className="ld__dash" d={d} style={{ ["--i" as string]: i }} />
            ))}
          </g>
          <path className="ld__square" d={MARK_SQUARE} />
        </svg>
        {icon && (
          <img
            className="ld__icon"
            src={icon}
            alt=""
            onLoad={() => setIconReady(true)}
            onError={() => setIconReady(false)}
          />
        )}
      </div>
      <p className="ld__text" key={text}>
        {text}
      </p>
      <p className="ld__detail">{detail || " "}</p>
    </div>
  );
}

// Shared constants and the report types returned by the Snappsense API
// (backend/app/analysis/pipeline.py builds the same shape).

export const SENTIMENTS = [
  { key: "delighted", label: "Delighted", color: "var(--s-delighted)" },
  { key: "happy", label: "Happy", color: "var(--s-happy)" },
  { key: "neutral", label: "Neutral", color: "var(--s-neutral)" },
  { key: "angry", label: "Angry", color: "var(--s-angry)" },
  { key: "frustrated", label: "Frustrated", color: "var(--s-frustrated)" },
] as const;

export type SentimentKey = (typeof SENTIMENTS)[number]["key"];
export type SentimentCounts = Record<SentimentKey, number>;

export const RANGES = ["1w", "1m", "3m", "6m", "1y"] as const;
export type Range = (typeof RANGES)[number];

export type Store = "play" | "app";
export type Depth = "quick" | "standard" | "deep" | "all" | "current";

export type Category =
  | "Crash"
  | "Transactional"
  | "Bug Report"
  | "Performance"
  | "Support"
  | "Pricing & Ads"
  | "UI/UX"
  | "Feature Request";

// Brand-family palette (pinks, berries, plums, lilacs) so categories sit
// with the rest of the product instead of fighting it.
export const CATEGORY_STYLE: Record<Category, { color: string; bg: string; fg: string }> = {
  Transactional: { color: "#F250AC", bg: "#FDE3F1", fg: "#A8156A" },
  "Bug Report": { color: "#C2185B", bg: "#FBE1EB", fg: "#9E1449" },
  Crash: { color: "#7A0C3A", bg: "#F5DFE7", fg: "#7A0C3A" },
  Performance: { color: "#9C4DCC", bg: "#F2E6F9", fg: "#74359A" },
  Support: { color: "#FF9ECF", bg: "#FFEFF7", fg: "#B23F7E" },
  "Pricing & Ads": { color: "#4A2340", bg: "#ECE2EA", fg: "#4A2340" },
  "UI/UX": { color: "#D98BBF", bg: "#FAEDF5", fg: "#9A4A80" },
  "Feature Request": { color: "#BFA6C9", bg: "#F3EEF5", fg: "#6A5373" },
};
export const CATEGORY_COLOR: Record<Category, string> = Object.fromEntries(
  Object.entries(CATEGORY_STYLE).map(([k, v]) => [k, v.color]),
) as Record<Category, string>;

export interface FeedbackRow {
  id: string;
  category: Category;
  feedback: string;
  solution: string;
  count: number;
  share: number;
  sentiment: SentimentKey;
  avgRating: number;
  latest: string;
  priority: Priority;
  /** Share of all concern mentions in the table, %. */
  impact: number;
  /** Where/when it hurts: app version, devices, update blame, recency. */
  evidence: string[];
  /** Per app version (version-picked reports): mentions, star sum, latest date, sentiments. */
  byVersion?: Record<string, { n: number; stars: number; latest: string; sent: Partial<SentimentCounts> }>;
}

export type Priority = "high" | "medium" | "low";
export const PRIORITY_RANK: Record<Priority, number> = { high: 3, medium: 2, low: 1 };

/** One review behind a feedback row (GET /api/reviews). */
export interface IssueReview {
  text: string;
  title: string | null;
  rating: number;
  date: string;
  thumbs: number;
  sentiment: SentimentKey;
  concern: string;
  version?: string | null;
}

export interface Period {
  label: string;
  start: string;
  end: string;
  /** Share of the period's reviews in each sentiment (0–1); bars are 100% stacked. */
  share: SentimentCounts;
  /** Exact counts when every review of the period was read; null for estimates. */
  counts: SentimentCounts | null;
  /** Reviews behind the bar: exact count, or sampled reviews for estimates. */
  n: number;
  estimated: boolean;
  empty: boolean;
}

export interface AppReport {
  id: string;
  store: Store;
  appId: string;
  country: string;
  depth: Depth;
  app: {
    name: string;
    developer: string;
    icon: string | null;
    genre: string | null;
    rating: number | null;
    ratingsCount: number | null;
    installs: string | null;
    url: string | null;
  };
  totals: SentimentCounts;
  totalReviews: number;
  totalsBasis: "store_histogram" | "sample";
  /** All-time star ratings ("5" … "1") from the store, exact. */
  ratings: Record<string, number>;
  ratingsBasis: "store" | "sample";
  positiveShare: number;
  categories: { label: Category; share: number; count: number }[];
  feedback: FeedbackRow[];
  trends: Record<Range, Period[]>;
  sample: {
    analyzed: number;
    oldest: string | null;
    newest: string | null;
    exactFrom: string | null;
    featuredOnly: boolean;
    /** Every review the store has was read (Play "all reviews" on an app below the limit). */
    complete?: boolean;
    /** What the feedback table covers: the versions people use now, or a time window. */
    scope?: {
      kind: "versions" | "period";
      since: string;
      /** Versions offered in the picker, newest first, and the preselected (latest) ones. */
      versions: string[];
      labels?: Record<string, string>;
      default?: string[];
      totals?: Record<string, { reviews: number; concerns: number; since: string | null }>;
      widened: boolean;
    } | null;
    sources: string[];
    concerns: number;
  };
  /** Present while a long run is still downloading: this report covers the reviews analysed so far. */
  partial?: { analyzed: number; limit: number | null };
  generatedAt: string;
  cachedAt?: number;
  domain: string | null;
  timings?: { fetchMs: number; analyzeMs: number; polishMs?: number; totalMs: number };
}


export interface StoreRef {
  store: Store;
  appId: string;
  country: string;
}

const PKG = /^[a-zA-Z][\w]*(\.[a-zA-Z_][\w]*)+$/;
const CC = /^[a-z]{2}$/;

/** Client-side mirror of backend/app/links.py so the form can validate instantly. */
export function parseStoreLink(input: string): StoreRef | null {
  const value = input.trim();
  if (!value) return null;
  if (PKG.test(value)) return { store: "play", appId: value, country: "us" };
  const bareApple = value.match(/^(?:id)?(\d{6,12})$/);
  if (bareApple) return { store: "app", appId: bareApple[1], country: "us" };
  try {
    const url = new URL(value.includes("://") ? value : `https://${value}`);
    const host = url.hostname.toLowerCase();
    if (host.endsWith("play.google.com")) {
      const id = url.searchParams.get("id");
      const gl = (url.searchParams.get("gl") ?? "").toLowerCase();
      return id && PKG.test(id) ? { store: "play", appId: id, country: CC.test(gl) ? gl : "us" } : null;
    }
    if (host === "apps.apple.com" || host === "itunes.apple.com") {
      const m = url.pathname.match(/id(\d{6,12})/);
      if (!m) return null;
      const seg = url.pathname.split("/").filter(Boolean)[0]?.toLowerCase() ?? "";
      return { store: "app", appId: m[1], country: CC.test(seg) ? seg : "us" };
    }
  } catch {
    /* not a URL */
  }
  return null;
}

/** A short, friendly reason a link can't be used (only call when parseStoreLink failed). */
export function linkProblem(input: string): string {
  const value = input.trim().toLowerCase();
  if (!value) return "Paste an app link to get started.";
  if (value.includes("play.google.com") || value.includes("apps.apple.com") || value.includes("itunes.apple.com"))
    return "Open the app’s own store page and copy that link.";
  return "That’s not a store link. Copy it from the app’s store page.";
}

export const STORE_LABEL: Record<Store, string> = { play: "Google Play", app: "App Store" };

/** "1,000,000,000+" → "1B+", "500,000+" → "500K+" */
export function formatInstalls(raw: string) {
  const n = Number(raw.replace(/[^\d]/g, ""));
  if (!n) return raw;
  return `${formatCompact(n)}${raw.trim().endsWith("+") ? "+" : ""}`;
}

export function formatCompact(n: number) {
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

export function timeAgo(iso: string | number) {
  const t = typeof iso === "number" ? iso * 1000 : Date.parse(iso);
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

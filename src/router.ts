import { useSyncExternalStore } from "react";

// Path router. Content pages (home, landing pages, /blogs, legal) are
// prerendered HTML, so moving between them is a normal page load; the
// dashboard (/app/…) switches in place for instant navigation.
const listeners = new Set<() => void>();
let serverPath = "/";

/** Used by the prerender (no window there). */
export function setServerPath(path: string) {
  serverPath = path;
}

const subscribe = (cb: () => void) => {
  listeners.add(cb);
  window.addEventListener("popstate", cb);
  return () => {
    listeners.delete(cb);
    window.removeEventListener("popstate", cb);
  };
};
const getPath = () => window.location.pathname + window.location.search;
// While hydrating, React compares with the server snapshot: the page's own URL.
const getServerPath = () => (typeof window === "undefined" ? serverPath : getPath());

export function usePath() {
  return useSyncExternalStore(subscribe, getPath, getServerPath);
}

export function navigate(path: string) {
  if (path.startsWith("/app/")) {
    window.history.pushState(null, "", path);
    listeners.forEach((l) => l());
    window.scrollTo({ top: 0 });
    return;
  }
  window.location.assign(path); // a prerendered page
}

/** Old links used "/#/app/…": move them to the real path. Returns true if it did. */
export function upgradeHashLink(): boolean {
  const h = window.location.hash;
  if (h.startsWith("#/app/")) {
    window.history.replaceState(null, "", h.slice(1));
    return true;
  }
  return false;
}

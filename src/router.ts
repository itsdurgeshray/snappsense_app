import { useSyncExternalStore } from "react";

// Tiny hash router: "#/" is the landing page, "#/app/<package.id>" is a report.
const subscribe = (cb: () => void) => {
  window.addEventListener("hashchange", cb);
  return () => window.removeEventListener("hashchange", cb);
};
const getPath = () => window.location.hash.replace(/^#/, "") || "/";

export function usePath() {
  return useSyncExternalStore(subscribe, getPath);
}

export function navigate(path: string) {
  window.location.hash = path;
  window.scrollTo({ top: 0 });
}

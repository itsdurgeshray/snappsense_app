import { StrictMode } from "react";
import { createRoot, hydrateRoot } from "react-dom/client";
import "./index.css";
import { Analytics } from "@vercel/analytics/react";
import App from "./App.tsx";
import { ContentContext } from "./content/context";
import { withDefaults } from "./content/defaults";
import { fetchContent } from "./content/sanity";
import type { Content } from "./content/types";
import { upgradeHashLink } from "./router";

declare global {
  interface Window {
    __CONTENT__?: Partial<Content>;
    __PATH__?: string;
  }
}

const tree = (content: Content) => (
  <StrictMode>
    <ContentContext.Provider value={content}>
      <App />
    </ContentContext.Provider>
    {/* Cookieless page-view stats; only active once enabled in the Vercel dashboard. */}
    <Analytics />
  </StrictMode>
);

const root = document.getElementById("root")!;
const moved = upgradeHashLink(); // old "/#/app/…" links

if (window.__CONTENT__) {
  // Production: the page was prerendered with this content; pick up where the HTML left off.
  const content = withDefaults(window.__CONTENT__);
  // Reuse the HTML only if it was built for this very URL (a server may answer with another page).
  const here = window.location.pathname.replace(/(.)\/+$/, "$1");
  if (root.firstElementChild && !moved && window.__PATH__ === here) hydrateRoot(root, tree(content));
  else {
    root.textContent = "";
    createRoot(root).render(tree(content));
  }
} else {
  // Development: built-in content first, then whatever is published in Sanity (via the dev proxy).
  const app = createRoot(root);
  app.render(tree(withDefaults(null)));
  fetchContent(import.meta.env.DEV ? "/sanity" : undefined).then((c) => c && app.render(tree(withDefaults(c))));
}

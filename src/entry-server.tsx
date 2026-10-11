// Server render for the prerender step (scripts/prerender.mjs): turns each
// route into HTML with the same components the browser hydrates.
import { StrictMode } from "react";
import { renderToString } from "react-dom/server";
import App from "./App";
import { ContentContext } from "./content/context";
import type { Content } from "./content/types";
import { setServerPath } from "./router";
import { resolveRoute } from "./routes";
import { headFor, headTags } from "./head";

export { withDefaults } from "./content/defaults";
export { fetchContent } from "./content/sanity";
export { resolveRoute } from "./routes";
export { SITE_URL } from "./head";

export function render(url: string, content: Content) {
  setServerPath(url);
  const html = renderToString(
    <StrictMode>
      <ContentContext.Provider value={content}>
        <App />
      </ContentContext.Provider>
    </StrictMode>,
  );
  const route = resolveRoute(url, content);
  return { html, head: headTags(headFor(route, url, content)), kind: route.kind };
}

export function defaultHead(content: Content) {
  return headTags({ title: content.settings.seo.title ?? content.settings.siteName, description: content.settings.seo.description ?? "", image: content.settings.seo.image ?? "/og.png", path: "/", noindex: true });
}

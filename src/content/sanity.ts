// Reads published content from Sanity's CDN API. The dataset is public
// (published documents only; drafts stay private), so no key is needed.

import type { Content } from "./types";

export const SANITY = {
  projectId: (typeof import.meta !== "undefined" && import.meta.env?.VITE_SANITY_PROJECT_ID) || "1lvtpppu",
  dataset: (typeof import.meta !== "undefined" && import.meta.env?.VITE_SANITY_DATASET) || "production",
  apiVersion: "2025-02-19",
};

const IMG = `{"url": asset->url, alt, caption}`;
const SEO = `seo{title, description, noindex, "image": image.asset->url}`;

export const CONTENT_QUERY = `{
  "settings": *[_type == "siteSettings"][0]{
    siteName, ${SEO}, headerLinks[]{label, href}, footerLinks[]{label, href}, legalNote,
    announcement{enabled, text, link{label, href}, startsAt, endsAt},
    "loader": *[_type == "loaderMessages"][0]{connect, fetch, analyze}
  },
  "pages": *[_type == "page" && defined(slug.current)]{
    title, "slug": slug.current, hideFooter, ${SEO},
    sections[]{
      ...,
      image ${IMG},
      items[]{..., image ${IMG}},
      button{label, href}, cta{label, href}
    }
  },
  "posts": *[_type == "post" && defined(slug.current) && defined(publishedAt)] | order(publishedAt desc){
    title, "slug": slug.current, excerpt, publishedAt, tags, ${SEO},
    "cover": cover ${IMG},
    body[]{..., _type == "image" => {"_type": "image", _key, "url": asset->url, alt, caption}}
  }
}`;

/** Remove nulls (GROQ returns null for empty fields) so defaults can fill them in. */
function clean<T>(v: T): T {
  if (Array.isArray(v)) return v.filter((x) => x !== null).map(clean) as T;
  if (v && typeof v === "object") {
    return Object.fromEntries(Object.entries(v).filter(([, x]) => x !== null).map(([k, x]) => [k, clean(x)])) as T;
  }
  return v;
}

/**
 * Fetch every published page, post and setting. `base` lets the dev server
 * proxy the API (no CORS setup needed locally).
 */
export async function fetchContent(base = `https://${SANITY.projectId}.apicdn.sanity.io`): Promise<Partial<Content> | null> {
  const url = `${base}/v${SANITY.apiVersion}/data/query/${SANITY.dataset}?query=${encodeURIComponent(CONTENT_QUERY)}`;
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    const body = await res.json();
    return clean(body.result ?? null);
  } catch {
    return null;
  }
}

/** Sanity image CDN: resize and serve modern formats. Local paths pass through. */
export function img(url: string | undefined, width: number): string | undefined {
  if (!url) return undefined;
  return url.includes("cdn.sanity.io") ? `${url}?w=${width}&auto=format&fit=max` : url;
}

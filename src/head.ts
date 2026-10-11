import type { Content } from "./content/types";
import type { Route } from "./routes";

export const SITE_URL = "https://snappsense-app.vercel.app";

export interface Head {
  title: string;
  description: string;
  image: string;
  path: string;
  noindex?: boolean;
  type?: "website" | "article";
}

/** Title, description and share image for a route (prerendered into each page's <head>). */
export function headFor(route: Route, path: string, content: Content): Head {
  const base = content.settings.seo;
  const site = content.settings.siteName;
  const d = { title: base.title ?? site, description: base.description ?? "", image: base.image ?? "/og.png", path };
  switch (route.kind) {
    case "page": {
      const s = route.page.seo ?? {};
      const title = s.title ?? (route.page.slug === "home" ? d.title : `${route.page.title} · ${site}`);
      return { ...d, title, description: s.description ?? d.description, image: s.image ?? d.image, noindex: s.noindex };
    }
    case "post": {
      const p = route.post;
      return {
        ...d,
        title: p.seo?.title ?? `${p.title} · ${site}`,
        description: p.seo?.description ?? p.excerpt ?? d.description,
        image: p.seo?.image ?? p.cover?.url ?? d.image,
        type: "article",
      };
    }
    case "blogs":
      return { ...d, title: `Blogs · ${site}`, description: `Articles from ${site} on understanding app reviews and user feedback.` };
    case "notFound":
      return { ...d, title: route.page.seo?.title ?? `Page not found · ${site}`, noindex: true };
    default:
      return { ...d, noindex: true };
  }
}

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

export function headTags(h: Head): string {
  const url = `${SITE_URL}${h.path === "/" ? "/" : h.path}`;
  const image = h.image.startsWith("http") ? h.image : `${SITE_URL}${h.image}`;
  return [
    `<title>${esc(h.title)}</title>`,
    `<meta name="description" content="${esc(h.description)}" />`,
    `<link rel="canonical" href="${esc(url)}" />`,
    h.noindex ? `<meta name="robots" content="noindex" />` : "",
    `<meta property="og:type" content="${h.type ?? "website"}" />`,
    `<meta property="og:site_name" content="Snappsense" />`,
    `<meta property="og:url" content="${esc(url)}" />`,
    `<meta property="og:title" content="${esc(h.title)}" />`,
    `<meta property="og:description" content="${esc(h.description)}" />`,
    `<meta property="og:image" content="${esc(image)}" />`,
    `<meta name="twitter:card" content="summary_large_image" />`,
    `<meta name="twitter:title" content="${esc(h.title)}" />`,
    `<meta name="twitter:description" content="${esc(h.description)}" />`,
    `<meta name="twitter:image" content="${esc(image)}" />`,
  ]
    .filter(Boolean)
    .join("\n    ");
}

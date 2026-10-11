// Build step: fetch published content from Sanity and write every page as
// finished HTML (good for search engines, instant first paint), plus the
// dashboard shell, 404, sitemap.xml and the blog RSS feed.
// Runs after `vite build` (client) and `vite build --ssr` (server render).
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dist = path.join(root, "dist");
const ssr = await import(path.join(root, "dist-ssr", "entry-server.js"));
const template = fs.readFileSync(path.join(dist, "index.html"), "utf8");

const fetched = await ssr.fetchContent();
if (!fetched) console.warn("prerender: Sanity unreachable or empty, building with the built-in content");
const content = ssr.withDefaults(fetched);
const summaries = content.posts.map(({ body, ...p }) => p); // eslint-disable-line no-unused-vars

const json = (v) => JSON.stringify(v).replace(/</g, "\\u003c");

/** Just what a page needs to hydrate: settings, its own page or post, and post summaries for listings. */
function payload(extra = {}) {
  return { settings: content.settings, pages: extra.pages ?? [], posts: extra.post ? [extra.post, ...summaries.filter((p) => p.slug !== extra.post.slug)] : summaries };
}

function write(file, url, data) {
  const { html, head } = ssr.render(url, content);
  const out = template
    .replace("<!--app-head-->", head)
    .replace("<!--app-data-->", `<script>window.__CONTENT__=${json(data)};window.__PATH__=${json(url)}</script>`)
    .replace("<!--app-html-->", html);
  const target = path.join(dist, file);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, out);
}

const pages = content.pages.filter((p) => p.slug !== "404");
for (const page of pages) {
  const url = page.slug === "home" ? "/" : `/${page.slug}`;
  write(page.slug === "home" ? "index.html" : `${page.slug}/index.html`, url, payload({ pages: [page] }));
}
write("blogs/index.html", "/blogs", payload());
for (const post of content.posts) write(`blogs/${post.slug}/index.html`, `/blogs/${post.slug}`, payload({ post }));
write("404.html", "/404", payload({ pages: content.pages.filter((p) => p.slug === "404") }));

// The dashboard renders in the browser (Vercel rewrites /app/* here).
const shell = template
  .replace("<!--app-head-->", ssr.defaultHead(content))
  .replace("<!--app-data-->", `<script>window.__CONTENT__=${json(payload())}</script>`)
  .replace("<!--app-html-->", "");
fs.writeFileSync(path.join(dist, "app-shell.html"), shell);

// sitemap.xml and RSS
const site = ssr.SITE_URL;
const urls = [
  ...pages.filter((p) => !p.seo?.noindex).map((p) => (p.slug === "home" ? "/" : `/${p.slug}`)),
  "/blogs",
  ...content.posts.map((p) => `/blogs/${p.slug}`),
];
fs.writeFileSync(
  path.join(dist, "sitemap.xml"),
  `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.map((u) => `  <url><loc>${site}${u}</loc></url>`).join("\n")}\n</urlset>\n`,
);
const xml = (s = "") => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
fs.writeFileSync(
  path.join(dist, "blogs", "rss.xml"),
  `<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>Snappsense blogs</title><link>${site}/blogs</link><description>Articles from Snappsense</description>\n${content.posts
    .map((p) => `<item><title>${xml(p.title)}</title><link>${site}/blogs/${p.slug}</link><guid>${site}/blogs/${p.slug}</guid>${p.publishedAt ? `<pubDate>${new Date(p.publishedAt).toUTCString()}</pubDate>` : ""}<description>${xml(p.excerpt)}</description></item>`)
    .join("\n")}\n</channel></rss>\n`,
);

fs.rmSync(path.join(root, "dist-ssr"), { recursive: true, force: true });
console.log(`prerender: ${pages.length} pages, ${content.posts.length} posts, sitemap with ${urls.length} URLs${fetched ? "" : " (built-in content)"}`);

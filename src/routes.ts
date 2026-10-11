import type { Depth, Store } from "./data";
import type { Content, Page, Post } from "./content/types";

export type Route =
  | { kind: "app"; store: Store; appId: string; country: string; depth: Depth; key: string }
  | { kind: "page"; page: Page }
  | { kind: "blogs" }
  | { kind: "post"; post: Post }
  | { kind: "notFound"; page: Page };

const DEPTHS = ["quick", "standard", "deep", "all", "current"];

/** Which screen a URL shows. Paths: /, /app/<store>/<id>, /blogs, /blogs/<slug>, /<page-slug>. */
export function resolveRoute(url: string, content: Content): Route {
  const [rawPath, query = ""] = url.split("?");
  const path = rawPath.length > 1 ? rawPath.replace(/\/+$/, "") : rawPath;
  const notFound = (): Route => ({ kind: "notFound", page: content.pages.find((p) => p.slug === "404")! });

  const app = path.match(/^\/app\/(play|app)\/([\w.]+)$/);
  if (app) {
    const q = new URLSearchParams(query);
    const depth = (DEPTHS.includes(q.get("depth") ?? "") ? q.get("depth") : "current") as Depth;
    return { kind: "app", store: app[1] as Store, appId: app[2], country: q.get("country") ?? "us", depth, key: url };
  }
  if (path === "/blogs") return { kind: "blogs" };
  const post = path.match(/^\/blogs\/([\w-]+)$/);
  if (post) {
    const found = content.posts.find((p) => p.slug === post[1]);
    return found ? { kind: "post", post: found } : notFound();
  }
  const slug = path === "/" ? "home" : path.slice(1);
  if (slug === "404" || slug.includes("/")) return notFound();
  const page = content.pages.find((p) => p.slug === slug);
  return page ? { kind: "page", page } : notFound();
}

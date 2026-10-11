import { defineArrayMember, defineField, defineType } from "sanity";
import { SECTION_TYPES } from "./sections";

// Addresses the site itself uses: a page can't take them.
const RESERVED = ["app", "blogs", "api", "assets", "fonts", "sanity"];

export const page = defineType({
  name: "page",
  title: "Page",
  type: "document",
  fields: [
    defineField({ name: "title", type: "string", validation: (r) => r.required() }),
    defineField({
      name: "slug",
      title: "Address",
      type: "slug",
      description: '"home" is the homepage, "404" the page-not-found page; anything else becomes snappsense…/your-slug.',
      options: { source: "title", maxLength: 80 },
      validation: (r) =>
        r.required().custom((v) => (v?.current && RESERVED.includes(v.current) ? `"${v.current}" is used by the site itself` : true)),
    }),
    defineField({ name: "sections", type: "array", of: SECTION_TYPES.map((t) => defineArrayMember({ type: t })), validation: (r) => r.min(1) }),
    defineField({ name: "hideFooter", title: "Hide the footer", type: "boolean", initialValue: false }),
    defineField({ name: "seo", type: "seo" }),
  ],
  preview: { select: { title: "title", slug: "slug.current" }, prepare: ({ title, slug }) => ({ title, subtitle: slug === "home" ? "/" : `/${slug ?? ""}` }) },
});

export const post = defineType({
  name: "post",
  title: "Blog post",
  type: "document",
  fields: [
    defineField({ name: "title", type: "string", validation: (r) => r.required() }),
    defineField({ name: "slug", title: "Address", type: "slug", description: "The post lives at /blogs/your-slug.", options: { source: "title", maxLength: 96 }, validation: (r) => r.required() }),
    defineField({ name: "publishedAt", title: "Publish date", type: "datetime", description: "Posts without a date aren't shown.", initialValue: () => new Date().toISOString(), validation: (r) => r.required() }),
    defineField({ name: "excerpt", title: "Summary", type: "text", rows: 3, description: "Shown on the blog listing and in link previews.", validation: (r) => r.max(220) }),
    defineField({ name: "cover", title: "Cover image", type: "altImage" }),
    defineField({ name: "tags", type: "array", of: [{ type: "string" }], options: { layout: "tags" } }),
    defineField({ name: "body", type: "articleText" }),
    defineField({ name: "seo", type: "seo" }),
  ],
  orderings: [{ title: "Newest first", name: "newest", by: [{ field: "publishedAt", direction: "desc" }] }],
  preview: { select: { title: "title", date: "publishedAt", media: "cover" }, prepare: ({ title, date, media }) => ({ title, media, subtitle: date ? new Date(date).toDateString() : "No date: not shown" }) },
});

export const siteSettings = defineType({
  name: "siteSettings",
  title: "Site settings",
  type: "document",
  fields: [
    defineField({ name: "siteName", type: "string", initialValue: "Snappsense" }),
    defineField({ name: "seo", title: "Default search & sharing", type: "seo" }),
    defineField({ name: "headerLinks", type: "array", of: [defineArrayMember({ type: "link" })] }),
    defineField({ name: "footerLinks", type: "array", of: [defineArrayMember({ type: "link" })] }),
    defineField({ name: "legalNote", title: "Legal note under the search box", type: "simpleText" }),
    defineField({
      name: "announcement",
      title: "Announcement banner",
      type: "object",
      options: { collapsible: true },
      fields: [
        defineField({ name: "enabled", title: "Show the banner", type: "boolean", initialValue: false }),
        defineField({ name: "text", type: "string" }),
        defineField({ name: "link", type: "link" }),
        defineField({ name: "startsAt", title: "Show from", type: "datetime" }),
        defineField({ name: "endsAt", title: "Show until", type: "datetime" }),
      ],
    }),
  ],
  preview: { prepare: () => ({ title: "Site settings" }) },
});

export const loaderMessages = defineType({
  name: "loaderMessages",
  title: "Loading messages",
  type: "document",
  description: 'Lines shown on the loading screen while an app is analysed, a few seconds each. "{app}" becomes the app’s name.',
  fields: [
    defineField({ name: "connect", title: "While connecting", type: "array", of: [{ type: "string" }] }),
    defineField({ name: "fetch", title: "While reading reviews", type: "array", of: [{ type: "string" }] }),
    defineField({ name: "analyze", title: "While analysing", type: "array", of: [{ type: "string" }] }),
  ],
  preview: { prepare: () => ({ title: "Loading messages" }) },
});

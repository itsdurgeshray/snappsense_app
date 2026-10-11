// Page-builder sections. Each one has a matching component on the site
// (src/components/sections.tsx); new section types need code there too.
import { defineArrayMember, defineField, defineType } from "sanity";

const words = defineField({ name: "marqueeWords", title: "Moving strip words", type: "array", of: [{ type: "string" }], description: "Shown in the black strip pinned to the bottom of the screen. Leave empty for no strip." });

export const hero = defineType({
  name: "hero",
  title: "Hero",
  type: "object",
  fields: [
    defineField({ name: "heading", type: "string", validation: (r) => r.required() }),
    defineField({ name: "subheading", type: "text", rows: 3 }),
    defineField({ name: "showSearch", title: "Show the app-link search box", type: "boolean", initialValue: true }),
    defineField({ name: "showLegalNote", title: "Show the legal note under the search box", type: "boolean", initialValue: true }),
    defineField({ name: "fullscreen", title: "Full screen (homepage style)", type: "boolean", description: "Only applies when this is the first section.", initialValue: false }),
    words,
  ],
  preview: { select: { title: "heading" }, prepare: ({ title }) => ({ title: title || "Hero", subtitle: "Hero" }) },
});

export const marquee = defineType({
  name: "marquee",
  title: "Moving words strip",
  type: "object",
  fields: [defineField({ name: "words", type: "array", of: [{ type: "string" }], validation: (r) => r.min(1) })],
  preview: { select: { w: "words" }, prepare: ({ w }) => ({ title: (w ?? []).join(" · ") || "Moving words", subtitle: "Moving words strip" }) },
});

export const richText = defineType({
  name: "richText",
  title: "Text block",
  type: "object",
  fields: [
    defineField({ name: "heading", type: "string" }),
    defineField({ name: "body", type: "simpleText", validation: (r) => r.required() }),
    defineField({ name: "narrow", title: "Narrow reading width", type: "boolean", initialValue: true }),
  ],
  preview: { select: { title: "heading" }, prepare: ({ title }) => ({ title: title || "Text", subtitle: "Text block" }) },
});

export const imageText = defineType({
  name: "imageText",
  title: "Image + text",
  type: "object",
  fields: [
    defineField({ name: "heading", type: "string", validation: (r) => r.required() }),
    defineField({ name: "body", type: "simpleText" }),
    defineField({ name: "image", type: "altImage" }),
    defineField({ name: "imageSide", type: "string", options: { list: ["right", "left"], layout: "radio" }, initialValue: "right" }),
    defineField({ name: "cta", title: "Button", type: "link" }),
  ],
  preview: { select: { title: "heading", media: "image" }, prepare: ({ title, media }) => ({ title, media, subtitle: "Image + text" }) },
});

export const featureGrid = defineType({
  name: "featureGrid",
  title: "Feature grid",
  type: "object",
  fields: [
    defineField({ name: "heading", type: "string" }),
    defineField({ name: "intro", type: "text", rows: 2 }),
    defineField({
      name: "items",
      type: "array",
      of: [defineArrayMember({ type: "object", name: "feature", fields: [defineField({ name: "title", type: "string", validation: (r) => r.required() }), defineField({ name: "text", type: "text", rows: 3 }), defineField({ name: "image", title: "Icon", type: "altImage" })] })],
    }),
  ],
  preview: { select: { title: "heading" }, prepare: ({ title }) => ({ title: title || "Features", subtitle: "Feature grid" }) },
});

export const stats = defineType({
  name: "stats",
  title: "Stats row",
  type: "object",
  fields: [
    defineField({ name: "heading", type: "string" }),
    defineField({
      name: "items",
      type: "array",
      of: [defineArrayMember({ type: "object", name: "stat", fields: [defineField({ name: "value", type: "string", description: "e.g. 20s", validation: (r) => r.required() }), defineField({ name: "label", type: "string", validation: (r) => r.required() })] })],
    }),
  ],
  preview: { select: { title: "heading" }, prepare: ({ title }) => ({ title: title || "Stats", subtitle: "Stats row" }) },
});

export const faq = defineType({
  name: "faq",
  title: "FAQ",
  type: "object",
  fields: [
    defineField({ name: "heading", type: "string", initialValue: "Frequently asked questions" }),
    defineField({
      name: "items",
      type: "array",
      of: [defineArrayMember({ type: "object", name: "qa", fields: [defineField({ name: "question", type: "string", validation: (r) => r.required() }), defineField({ name: "answer", type: "simpleText", validation: (r) => r.required() })], preview: { select: { title: "question" } } })],
    }),
  ],
  preview: { select: { title: "heading" }, prepare: ({ title }) => ({ title: title || "FAQ", subtitle: "FAQ" }) },
});

export const quote = defineType({
  name: "quote",
  title: "Quote",
  type: "object",
  fields: [
    defineField({ name: "text", type: "text", rows: 3, validation: (r) => r.required() }),
    defineField({ name: "author", type: "string" }),
    defineField({ name: "role", type: "string" }),
  ],
  preview: { select: { title: "text", subtitle: "author" } },
});

export const cta = defineType({
  name: "cta",
  title: "Call to action",
  type: "object",
  fields: [
    defineField({ name: "heading", type: "string", validation: (r) => r.required() }),
    defineField({ name: "text", type: "text", rows: 2 }),
    defineField({ name: "showSearch", title: "Show the app-link search box", type: "boolean", initialValue: false }),
    defineField({ name: "button", type: "link" }),
  ],
  preview: { select: { title: "heading" }, prepare: ({ title }) => ({ title, subtitle: "Call to action" }) },
});

export const latestPosts = defineType({
  name: "latestPosts",
  title: "Latest blog posts",
  type: "object",
  fields: [defineField({ name: "heading", type: "string", initialValue: "From the blog" }), defineField({ name: "count", type: "number", initialValue: 3, validation: (r) => r.min(1).max(12) })],
  preview: { select: { title: "heading" }, prepare: ({ title }) => ({ title: title || "Latest posts", subtitle: "Latest blog posts" }) },
});

export const SECTION_TYPES = ["hero", "marquee", "richText", "imageText", "featureGrid", "stats", "faq", "quote", "cta", "latestPosts"];

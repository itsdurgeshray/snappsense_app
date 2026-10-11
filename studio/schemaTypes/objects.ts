import { defineArrayMember, defineField, defineType } from "sanity";

export const link = defineType({
  name: "link",
  title: "Link",
  type: "object",
  fields: [
    defineField({ name: "label", type: "string", validation: (r) => r.required() }),
    defineField({ name: "href", title: "URL", type: "string", description: "A page on this site (/blogs, /privacy) or a full https:// address.", validation: (r) => r.required() }),
  ],
  preview: { select: { title: "label", subtitle: "href" } },
});

export const seo = defineType({
  name: "seo",
  title: "Search & sharing",
  type: "object",
  options: { collapsible: true, collapsed: true },
  fields: [
    defineField({ name: "title", type: "string", description: "Shown in Google and browser tabs. Leave empty to use the page title.", validation: (r) => r.max(70).warning("Over 70 characters gets cut off in search results") }),
    defineField({ name: "description", type: "text", rows: 3, validation: (r) => r.max(170).warning("Over 170 characters gets cut off in search results") }),
    defineField({ name: "image", title: "Share image", type: "image", description: "1200 × 630 works best for link previews." }),
    defineField({ name: "noindex", title: "Hide from search engines", type: "boolean", initialValue: false }),
  ],
});

/** An image that must describe itself (alt text is required for accessibility and SEO). */
export const altImage = defineType({
  name: "altImage",
  title: "Image",
  type: "image",
  options: { hotspot: true },
  fields: [
    defineField({ name: "alt", title: "Alt text", type: "string", description: "Describe the image for people who can't see it.", validation: (r) => r.required() }),
    defineField({ name: "caption", type: "string" }),
  ],
});

export const callout = defineType({
  name: "callout",
  title: "Callout",
  type: "object",
  fields: [
    defineField({ name: "tone", type: "string", options: { list: ["info", "warning"], layout: "radio" }, initialValue: "info" }),
    defineField({ name: "text", type: "text", rows: 3, validation: (r) => r.required() }),
  ],
  preview: { select: { title: "text", subtitle: "tone" } },
});

export const code = defineType({
  name: "code",
  title: "Code",
  type: "object",
  fields: [defineField({ name: "code", type: "text", rows: 8, validation: (r) => r.required() })],
  preview: { select: { title: "code" }, prepare: ({ title }) => ({ title: "Code", subtitle: title?.slice(0, 60) }) },
});

const block = defineArrayMember({
  type: "block",
  styles: [
    { title: "Normal", value: "normal" },
    { title: "Heading 2", value: "h2" },
    { title: "Heading 3", value: "h3" },
    { title: "Quote", value: "blockquote" },
  ],
  marks: {
    annotations: [{ name: "link", type: "object", title: "Link", fields: [{ name: "href", type: "string", title: "URL", validation: (r) => r.required() }] }],
  },
});

/** Text with headings, lists and links. */
export const simpleText = defineType({ name: "simpleText", title: "Text", type: "array", of: [block] });

/** Everything a blog post body can hold. */
export const articleText = defineType({
  name: "articleText",
  title: "Body",
  type: "array",
  of: [block, defineArrayMember({ type: "altImage" }), defineArrayMember({ type: "callout" }), defineArrayMember({ type: "code" })],
});

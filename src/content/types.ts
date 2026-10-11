// The shape of everything editable in Sanity (studio/schemas mirror these).
// Every field is optional on the wire: missing content falls back to
// src/content/defaults.ts, so the site never breaks on an unpublished field.

import type { PortableTextBlock } from "@portabletext/react";

export type RichText = PortableTextBlock[];

export interface Img {
  url: string;
  alt?: string;
  caption?: string;
}

export interface Seo {
  title?: string;
  description?: string;
  image?: string;
  noindex?: boolean;
}

export interface Link {
  label: string;
  href: string;
}

export interface Announcement {
  enabled?: boolean;
  text?: string;
  link?: Link;
  startsAt?: string;
  endsAt?: string;
}

export interface SiteSettings {
  siteName: string;
  seo: Seo;
  headerLinks: Link[];
  footerLinks: Link[];
  legalNote?: RichText;
  announcement?: Announcement;
  loader: { connect: string[]; fetch: string[]; analyze: string[] };
}

export type Section =
  | { _type: "hero"; _key: string; heading: string; subheading?: string; showSearch?: boolean; showLegalNote?: boolean; fullscreen?: boolean; marqueeWords?: string[] }
  | { _type: "marquee"; _key: string; words: string[] }
  | { _type: "richText"; _key: string; heading?: string; body: RichText; narrow?: boolean }
  | { _type: "imageText"; _key: string; heading: string; body?: RichText; image?: Img; imageSide?: "left" | "right"; cta?: Link }
  | { _type: "featureGrid"; _key: string; heading?: string; intro?: string; items: { _key: string; title: string; text?: string; image?: Img }[] }
  | { _type: "stats"; _key: string; heading?: string; items: { _key: string; value: string; label: string }[] }
  | { _type: "faq"; _key: string; heading?: string; items: { _key: string; question: string; answer: RichText }[] }
  | { _type: "quote"; _key: string; text: string; author?: string; role?: string }
  | { _type: "cta"; _key: string; heading: string; text?: string; button?: Link; showSearch?: boolean }
  | { _type: "latestPosts"; _key: string; heading?: string; count?: number };

export interface Page {
  slug: string; // "home" is the homepage, "404" the not-found page
  title: string;
  seo?: Seo;
  hideFooter?: boolean;
  sections: Section[];
}

export interface PostSummary {
  slug: string;
  title: string;
  excerpt?: string;
  publishedAt?: string;
  tags?: string[];
  cover?: Img;
  seo?: Seo;
}

export interface Post extends PostSummary {
  body?: RichText;
}

export interface Content {
  settings: SiteSettings;
  pages: Page[];
  posts: Post[];
}

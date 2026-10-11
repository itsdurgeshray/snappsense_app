import { altImage, articleText, callout, code, link, seo, simpleText } from "./objects";
import { cta, faq, featureGrid, hero, imageText, latestPosts, marquee, quote, richText, stats } from "./sections";
import { loaderMessages, page, post, siteSettings } from "./documents";

export const schemaTypes = [
  link, seo, altImage, callout, code, simpleText, articleText,
  hero, marquee, richText, imageText, featureGrid, stats, faq, quote, cta, latestPosts,
  page, post, siteSettings, loaderMessages,
];

/** One-of-a-kind documents: edited in place, never created or deleted. */
export const SINGLETONS = ["siteSettings", "loaderMessages"];

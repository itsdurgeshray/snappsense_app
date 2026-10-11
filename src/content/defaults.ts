// Built-in content: what the site shows when Sanity has nothing published
// (or can't be reached during a build). It's also the seed imported into
// Sanity (studio/seed), so the first edit starts from what's live today.

import type { Content, Page, RichText, SiteSettings } from "./types";

let key = 0;
const k = () => `d${(key++).toString(36)}`;

/** Compact authoring for rich text: ["h2", "…"], ["p", "…"], ["li", "…"]; **bold** and [label](/href) inline. */
export function rich(lines: [string, string][]): RichText {
  return lines.map(([tag, text]) => {
    const markDefs: { _key: string; _type: "link"; href: string }[] = [];
    const children: { _type: "span"; _key: string; text: string; marks: string[] }[] = [];
    for (const part of text.split(/(\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/).filter(Boolean)) {
      const bold = part.match(/^\*\*(.+)\*\*$/);
      const link = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (bold) children.push({ _type: "span", _key: k(), text: bold[1], marks: ["strong"] });
      else if (link) {
        const def = { _key: k(), _type: "link" as const, href: link[2] };
        markDefs.push(def);
        children.push({ _type: "span", _key: k(), text: link[1], marks: [def._key] });
      } else children.push({ _type: "span", _key: k(), text: part, marks: [] });
    }
    const list = tag === "li";
    return {
      _type: "block",
      _key: k(),
      style: list ? "normal" : tag === "p" ? "normal" : tag,
      ...(list ? { listItem: "bullet", level: 1 } : {}),
      markDefs,
      children,
    } as RichText[number];
  });
}

export const defaultSettings: SiteSettings = {
  siteName: "Snappsense",
  seo: {
    title: "Snappsense · App review analysis for Play Store & App Store",
    description:
      "Paste a Google Play or App Store link and see what users complain about, ranked by impact, with a suggested fix for each issue. Free, in seconds.",
    image: "/og.png",
  },
  headerLinks: [{ label: "Blogs", href: "/blogs" }],
  footerLinks: [
    { label: "Blogs", href: "/blogs" },
    { label: "Privacy", href: "/privacy" },
    { label: "Terms", href: "/terms" },
  ],
  legalNote: rich([["p", "Free to use. By analysing an app you agree to our [Terms](/terms) and [Privacy Policy](/privacy)."]]),
  announcement: { enabled: false },
  loader: {
    connect: ["Connecting to the store", "Waking up the analysis engine", "The first run after a quiet spell takes a little longer", "Still warming up — hang tight"],
    fetch: [
      "Found {app}",
      "Collecting the latest reviews",
      "Finding the app versions people use now",
      "Reading back to when those versions came out",
      "Covering every rating, 1★ to 5★",
    ],
    analyze: [
      "Reading the mood of every review",
      "Separating complaints from praise",
      "Spotting crashes, bugs and payment issues",
      "Grouping complaints that share a root cause",
      "Telling feature requests apart",
      "Writing a one-line summary for each issue",
      "Checking which versions and devices are affected",
      "Ranking issues by how many people they hit",
      "Matching each issue with a suggested fix",
      "Building your dashboard",
      "Almost there",
    ],
  },
};

const home: Page = {
  slug: "home",
  title: "Home",
  hideFooter: true,
  sections: [
    {
      _type: "hero",
      _key: "home-hero",
      heading: "Capture sense of user feedback with snap",
      subheading:
        "Paste the link of the app you want to analyze and discover powerful insights into user feedback within seconds. See trends, understand feedback, and enhance your app experience effortlessly.",
      showSearch: true,
      showLegalNote: true,
      fullscreen: true,
      marqueeWords: ["GET INSIGHTS", "PASTE LINK", "SNAP SENSE"],
    },
  ],
};

const UPDATED = "Last updated 11 October 2026";

const privacy: Page = {
  slug: "privacy",
  title: "Privacy Policy",
  seo: { title: "Privacy Policy · Snappsense", description: "How Snappsense handles data: no accounts, no cookies, anonymous analytics, reports kept for 6 hours." },
  sections: [
    {
      _type: "richText",
      _key: "privacy-body",
      heading: "Privacy Policy",
      narrow: true,
      body: rich([
        ["p", UPDATED],
        ["p", "Snappsense analyses public app reviews. You don’t need an account, and we don’t ask for your name, email or any other personal details to use it."],
        ["h2", "What we collect"],
        ["li", "**The app links you analyse.** We use them to fetch that app’s public reviews and build your report."],
        ["li", "**Basic, anonymous usage statistics.** Page views, country and device type, collected with Vercel Web Analytics. It uses no cookies and doesn’t identify you or follow you across sites."],
        ["li", "**Feedback you choose to send** through “Give feedback”: your rating and message, nothing else."],
        ["li", "**Standard server logs.** Our hosting providers keep short-lived technical logs (such as IP address and request time) to keep the service running and secure."],
        ["h2", "Reviews we process"],
        ["p", "Reports are built from reviews that are already public on Google Play and the App Store. We store a finished report for up to 6 hours so repeat visits load instantly, then it’s discarded. We don’t sell, share or build profiles from review data."],
        ["h2", "Cookies"],
        ["p", "Snappsense doesn’t set cookies and doesn’t store anything in your browser."],
        ["h2", "Who processes data for us"],
        ["li", "Vercel: hosts the website and provides the anonymous analytics."],
        ["li", "Render: hosts the analysis server."],
        ["li", "Sanity: hosts the site’s editable content."],
        ["li", "Google Play and Apple App Store: the sources of the public reviews."],
        ["h2", "Your choices"],
        ["p", "Because we don’t hold accounts or personal profiles, there is usually nothing to delete. You can block analytics with any standard content blocker without affecting how Snappsense works."],
        ["h2", "Changes"],
        ["p", "If this policy changes, we’ll update the date at the top of this page."],
      ]),
    },
  ],
};

const terms: Page = {
  slug: "terms",
  title: "Terms of Use",
  seo: { title: "Terms of Use · Snappsense", description: "The terms for using Snappsense, the free app review analysis tool." },
  sections: [
    {
      _type: "richText",
      _key: "terms-body",
      heading: "Terms of Use",
      narrow: true,
      body: rich([
        ["p", UPDATED],
        ["p", "By using Snappsense you agree to these terms. If you don’t agree, please don’t use the service."],
        ["h2", "The service"],
        ["p", "Snappsense fetches public reviews for an app you choose and summarises them automatically: sentiment, recurring issues, priorities and suggested fixes. It is provided free of charge, as is, and may change or be unavailable at any time."],
        ["h2", "Automated results"],
        ["p", "Reports are generated by software from public reviews. They can be incomplete or wrong. Use them as a starting point, and check important decisions against your own data."],
        ["h2", "Fair use"],
        ["li", "Don’t overload the service, scrape it automatically, or try to get around its limits."],
        ["li", "Don’t use it for anything unlawful, or to harass the people who wrote reviews."],
        ["li", "Don’t copy, resell or rebuild Snappsense, its design or its code."],
        ["h2", "Content and trademarks"],
        ["p", "Reviews belong to their authors and the stores that publish them. Google Play is a trademark of Google LLC; App Store is a trademark of Apple Inc. Snappsense is not affiliated with or endorsed by either. The Snappsense name, logo, design and software are our property and all rights are reserved."],
        ["h2", "Liability"],
        ["p", "To the extent the law allows, Snappsense is not liable for any loss arising from using the service or relying on its reports."],
        ["h2", "Changes"],
        ["p", "We may update these terms. Continuing to use Snappsense after an update means you accept the new terms."],
      ]),
    },
  ],
};

const notFound: Page = {
  slug: "404",
  title: "Page not found",
  seo: { title: "Page not found · Snappsense", noindex: true },
  sections: [
    { _type: "cta", _key: "nf", heading: "This page snapped out of existence", text: "The link may be broken or the page may have moved.", button: { label: "Analyse an app", href: "/" } },
  ],
};

export const defaultContent: Content = {
  settings: defaultSettings,
  pages: [home, privacy, terms, notFound],
  posts: [],
};

/** Sanity content over the defaults: published pages replace built-in ones with the same slug. */
export function withDefaults(fetched: Partial<Content> | null | undefined): Content {
  if (!fetched) return defaultContent;
  const s = fetched.settings;
  const settings: SiteSettings = {
    ...defaultSettings,
    ...(s ?? {}),
    seo: { ...defaultSettings.seo, ...(s?.seo ?? {}) },
    headerLinks: s?.headerLinks?.length ? s.headerLinks : defaultSettings.headerLinks,
    footerLinks: s?.footerLinks?.length ? s.footerLinks : defaultSettings.footerLinks,
    legalNote: s?.legalNote?.length ? s.legalNote : defaultSettings.legalNote,
    loader: {
      connect: s?.loader?.connect?.length ? s.loader.connect : defaultSettings.loader.connect,
      fetch: s?.loader?.fetch?.length ? s.loader.fetch : defaultSettings.loader.fetch,
      analyze: s?.loader?.analyze?.length ? s.loader.analyze : defaultSettings.loader.analyze,
    },
  };
  const pages = new Map(defaultContent.pages.map((p) => [p.slug, p]));
  for (const p of fetched.pages ?? []) if (p?.slug && p.sections?.length) pages.set(p.slug, p);
  return { settings, pages: [...pages.values()], posts: fetched.posts ?? [] };
}

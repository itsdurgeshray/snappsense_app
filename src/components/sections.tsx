// Page-builder sections. Each Sanity section type has one component here,
// styled with the site's brand (src/sections.css). New types need code.

import { Header } from "./Header";
import { SnapForm } from "./SnapForm";
import { Marquee } from "./home/Marquee";
import { RichText } from "./RichText";
import { useContent } from "../content/context";
import { img } from "../content/sanity";
import type { Section } from "../content/types";

type Of<T extends Section["_type"]> = Extract<Section, { _type: T }>;

function LegalNote() {
  const note = useContent().settings.legalNote;
  return note?.length ? <RichText value={note} className="landing__legal" /> : null;
}

/** The homepage hero: full viewport, gradient into the pinned marquee strip. */
function HeroFullscreen({ s }: { s: Of<"hero"> }) {
  return (
    <div className="landing">
      <div className="landing__body">
        <Header tone="light" />
        <main className="landing__main">
          <div className="container landing__hero">
            <h1 className="landing__title">{s.heading}</h1>
            {s.subheading && <p className="landing__sub">{s.subheading}</p>}
          </div>
          <div className="landing__stage">
            <div className="landing__bg" aria-hidden="true">
              <img className="landing__rings" src="/hero-rings.svg" width={1440} height={594} alt="" />
            </div>
            <div className="container">
              {s.showSearch && <SnapForm />}
              {s.showLegalNote && <LegalNote />}
            </div>
          </div>
        </main>
      </div>
      {s.marqueeWords?.length ? <Marquee words={s.marqueeWords} /> : null}
    </div>
  );
}

function Hero({ s, first }: { s: Of<"hero">; first: boolean }) {
  const Tag = first ? "h1" : "h2";
  return (
    <section className="sx-hero">
      <div className="container sx-hero__inner">
        <Tag className="sx-hero__title">{s.heading}</Tag>
        {s.subheading && <p className="sx-hero__sub">{s.subheading}</p>}
        {s.showSearch && <SnapForm />}
        {s.showLegalNote && <LegalNote />}
      </div>
    </section>
  );
}

function ImageText({ s }: { s: Of<"imageText"> }) {
  return (
    <section className={`sx sx-imagetext${s.imageSide === "left" ? " is-left" : ""}`}>
      <div className="container sx-imagetext__inner">
        <div className="sx-imagetext__copy">
          <h2 className="sx__title">{s.heading}</h2>
          <RichText value={s.body} />
          {s.cta?.href && (
            <a className="btn-dark sx__btn" href={s.cta.href}>
              {s.cta.label}
            </a>
          )}
        </div>
        {s.image?.url && <img className="sx-imagetext__img" src={img(s.image.url, 1200)} alt={s.image.alt ?? ""} loading="lazy" />}
      </div>
    </section>
  );
}

function FeatureGrid({ s }: { s: Of<"featureGrid"> }) {
  return (
    <section className="sx sx-features">
      <div className="container">
        {s.heading && <h2 className="sx__title">{s.heading}</h2>}
        {s.intro && <p className="sx__intro">{s.intro}</p>}
        <ul className="sx-features__grid">
          {s.items?.map((it) => (
            <li key={it._key} className="sx-features__item">
              {it.image?.url && <img src={img(it.image.url, 160)} alt={it.image.alt ?? ""} width={40} height={40} loading="lazy" />}
              <h3>{it.title}</h3>
              {it.text && <p>{it.text}</p>}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function Stats({ s }: { s: Of<"stats"> }) {
  return (
    <section className="sx sx-stats">
      <div className="container">
        {s.heading && <h2 className="sx__title">{s.heading}</h2>}
        <dl className="sx-stats__grid">
          {s.items?.map((it) => (
            <div key={it._key}>
              <dt>{it.label}</dt>
              <dd>{it.value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}

function Faq({ s }: { s: Of<"faq"> }) {
  return (
    <section className="sx sx-faq">
      <div className="container sx-faq__inner">
        {s.heading && <h2 className="sx__title">{s.heading}</h2>}
        {s.items?.map((it) => (
          <details key={it._key} className="sx-faq__item">
            <summary>{it.question}</summary>
            <RichText value={it.answer} />
          </details>
        ))}
      </div>
    </section>
  );
}

function Quote({ s }: { s: Of<"quote"> }) {
  return (
    <section className="sx sx-quote">
      <figure className="container sx-quote__inner">
        <blockquote>“{s.text}”</blockquote>
        {(s.author || s.role) && (
          <figcaption>
            {s.author}
            {s.role && <span>{s.role}</span>}
          </figcaption>
        )}
      </figure>
    </section>
  );
}

function Cta({ s, first }: { s: Of<"cta">; first: boolean }) {
  const Tag = first ? "h1" : "h2";
  return (
    <section className="sx sx-cta">
      <div className="container">
        <div className="sx-cta__inner">
          <Tag className="sx__title">{s.heading}</Tag>
          {s.text && <p className="sx__intro">{s.text}</p>}
          {s.showSearch && <SnapForm />}
          {s.button?.href && (
            <a className="btn-dark sx__btn" href={s.button.href}>
              {s.button.label}
            </a>
          )}
        </div>
      </div>
    </section>
  );
}

export function PostCards({ count, heading }: { count?: number; heading?: string }) {
  const posts = useContent().posts.slice(0, count ?? 3);
  if (!posts.length) return null;
  return (
    <section className="sx sx-posts">
      <div className="container">
        {heading && <h2 className="sx__title">{heading}</h2>}
        <ul className="post-grid">
          {posts.map((p) => (
            <li key={p.slug}>
              <a className="post-card" href={`/blogs/${p.slug}`}>
                {p.cover?.url && <img src={img(p.cover.url, 800)} alt={p.cover.alt ?? ""} loading="lazy" />}
                <div className="post-card__body">
                  {p.publishedAt && <time dateTime={p.publishedAt}>{formatDate(p.publishedAt)}</time>}
                  <h3>{p.title}</h3>
                  {p.excerpt && <p>{p.excerpt}</p>}
                </div>
              </a>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

export function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
}

export function Sections({ sections }: { sections: Section[] }) {
  return (
    <>
      {sections.map((s, i) => {
        const first = i === 0;
        switch (s._type) {
          case "hero":
            return s.fullscreen && first ? <HeroFullscreen key={s._key} s={s} /> : <Hero key={s._key} s={s} first={first} />;
          case "marquee":
            return s.words?.length ? <Marquee key={s._key} words={s.words} /> : null;
          case "richText":
            return (
              <section key={s._key} className="sx sx-rich">
                <div className={`container${s.narrow ? " sx-rich--narrow" : ""}`}>
                  {s.heading && (first ? <h1 className="sx__title">{s.heading}</h1> : <h2 className="sx__title">{s.heading}</h2>)}
                  <RichText value={s.body} />
                </div>
              </section>
            );
          case "imageText":
            return <ImageText key={s._key} s={s} />;
          case "featureGrid":
            return <FeatureGrid key={s._key} s={s} />;
          case "stats":
            return <Stats key={s._key} s={s} />;
          case "faq":
            return <Faq key={s._key} s={s} />;
          case "quote":
            return <Quote key={s._key} s={s} />;
          case "cta":
            return <Cta key={s._key} s={s} first={first} />;
          case "latestPosts":
            return <PostCards key={s._key} count={s.count} heading={s.heading ?? "From the blog"} />;
          default:
            return null; // a section type this build doesn't know yet
        }
      })}
    </>
  );
}

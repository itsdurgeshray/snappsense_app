import { PortableText, type PortableTextComponents } from "@portabletext/react";
import { img } from "../content/sanity";
import type { RichText as RT } from "../content/types";

const components: PortableTextComponents = {
  marks: {
    link: ({ value, children }) => {
      const href: string = value?.href ?? "#";
      const external = /^https?:\/\//.test(href);
      return (
        <a href={href} {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}>
          {children}
        </a>
      );
    },
  },
  types: {
    image: ({ value }) =>
      value?.url ? (
        <figure className="rt-figure">
          <img src={img(value.url, 1400)} alt={value.alt ?? ""} loading="lazy" />
          {value.caption && <figcaption>{value.caption}</figcaption>}
        </figure>
      ) : null,
    callout: ({ value }) => (
      <aside className={`rt-callout rt-callout--${value?.tone ?? "info"}`}>
        <p>{value?.text}</p>
      </aside>
    ),
    code: ({ value }) => (
      <pre className="rt-code">
        <code>{value?.code}</code>
      </pre>
    ),
  },
};

/** Sanity rich text (Portable Text) in the site's typography. */
export function RichText({ value, className = "rt" }: { value?: RT; className?: string }) {
  if (!value?.length) return null;
  return (
    <div className={className}>
      <PortableText value={value} components={components} />
    </div>
  );
}

import { useContent } from "../content/context";
import type { Announcement } from "../content/types";

/** Is the banner on right now? (Checked when the page is built and again in the browser.) */
export function announcementActive(a: Announcement | undefined, now = Date.now()): boolean {
  if (!a?.enabled || !a.text) return false;
  if (a.startsAt && Date.parse(a.startsAt) > now) return false;
  if (a.endsAt && Date.parse(a.endsAt) < now) return false;
  return true;
}

/** Thin notice above the header, edited in Sanity (Site settings → Announcement). */
export function AnnouncementBar() {
  const a = useContent().settings.announcement;
  if (!announcementActive(a)) return null;
  return (
    <div className="announce" role="region" aria-label="Announcement">
      <p>
        {a!.text}
        {a!.link?.href && (
          <a href={a!.link.href}>
            {a!.link.label || "Learn more"}
            <span aria-hidden="true"> →</span>
          </a>
        )}
      </p>
    </div>
  );
}

export function Footer() {
  const { settings } = useContent();
  return (
    <footer className="site-footer">
      <div className="container site-footer__inner">
        <nav aria-label="Footer">
          {settings.footerLinks.map((l) => (
            <a key={l.href} href={l.href}>
              {l.label}
            </a>
          ))}
        </nav>
        <span>© {new Date().getFullYear()} {settings.siteName}</span>
      </div>
    </footer>
  );
}

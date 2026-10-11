import { useEffect, useState } from "react";
import { Logo } from "./Logo";
import { FeedbackModal } from "./FeedbackModal";
import { navigate } from "../router";
import { useContent } from "../content/context";

export interface NavItem {
  id: string;
  label: string;
}

/** Smooth-scrolls to a section without touching the hash (the hash is the router). */
export function scrollToSection(id: string) {
  const el = document.getElementById(id);
  if (!el) return;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const top = el.getBoundingClientRect().top + window.scrollY - 72;
  window.scrollTo({ top, behavior: reduce ? "auto" : "smooth" });
}

export function Header({ tone, nav, floating = false }: { tone: "light" | "dark"; nav?: NavItem[]; floating?: boolean }) {
  const [open, setOpen] = useState(false);
  const [menu, setMenu] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [active, setActive] = useState<string | null>(null);
  const links = useContent().settings.headerLinks;

  useEffect(() => {
    if (!floating) return;
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [floating]);

  // Highlight the nav item for the section currently in view.
  useEffect(() => {
    if (!nav?.length || !("IntersectionObserver" in window)) return;
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => e.isIntersecting && setActive(e.target.id)),
      { rootMargin: "-45% 0px -50% 0px" },
    );
    nav.forEach((n) => {
      const el = document.getElementById(n.id);
      if (el) io.observe(el);
    });
    return () => io.disconnect();
  }, [nav]);

  const cls = ["site-header", `site-header--${tone}`, floating && "site-header--floating", scrolled && "is-scrolled", menu && "is-menu"]
    .filter(Boolean)
    .join(" ");

  return (
    <header className={cls}>
      <div className="container site-header__inner">
        <Logo
          onClick={() => {
            navigate("/");
            setMenu(false);
          }}
        />
        {nav && (
          <nav className="site-nav" aria-label="Sections">
            {nav.map((n) => (
              <a
                key={n.id}
                href={`#${n.id}`}
                aria-current={active === n.id ? "true" : undefined}
                onClick={(e) => {
                  e.preventDefault();
                  setMenu(false);
                  scrollToSection(n.id);
                }}
              >
                {n.label}
              </a>
            ))}
            <button
              type="button"
              className="site-nav__cta"
              onClick={() => {
                setMenu(false);
                setOpen(true);
              }}
            >
              Give Feedback
            </button>
          </nav>
        )}
        <div className="site-header__actions">
          {links.map((l) => (
            <a key={l.href} href={l.href} className="site-header__link">
              {l.label}
            </a>
          ))}
          <button type="button" className="btn-outline" onClick={() => setOpen(true)}>
            Give Feedback
          </button>
          {nav && (
            <button type="button" className="menu-btn" aria-label="Menu" aria-expanded={menu} onClick={() => setMenu((m) => !m)}>
              <span />
              <span />
            </button>
          )}
        </div>
      </div>
      {open && <FeedbackModal onClose={() => setOpen(false)} />}
    </header>
  );
}

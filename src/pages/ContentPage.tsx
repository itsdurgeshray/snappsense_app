import { Header } from "../components/Header";
import { AnnouncementBar, Footer } from "../components/SiteChrome";
import { Sections } from "../components/sections";
import type { Page } from "../content/types";
import "../home.css";
import "../sections.css";

/** Any page built in Sanity: the homepage, landing pages, legal pages, 404. */
export function ContentPage({ page }: { page: Page }) {
  const first = page.sections[0];
  const ownHeader = first?._type === "hero" && first.fullscreen; // the full-screen hero draws its own header
  return (
    <div className="content-page">
      <AnnouncementBar />
      {!ownHeader && <Header tone="light" />}
      <Sections sections={page.sections} />
      {!page.hideFooter && <Footer />}
    </div>
  );
}

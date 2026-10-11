import { Header } from "../components/Header";
import { AnnouncementBar, Footer } from "../components/SiteChrome";
import { PostCards, formatDate } from "../components/sections";
import { RichText } from "../components/RichText";
import { useContent } from "../content/context";
import { img } from "../content/sanity";
import type { Post } from "../content/types";
import "../sections.css";

/** /blogs: every published post, newest first. */
export function BlogIndex() {
  const { posts } = useContent();
  return (
    <div className="content-page">
      <AnnouncementBar />
      <Header tone="light" />
      <section className="sx-hero sx-hero--compact">
        <div className="container sx-hero__inner">
          <h1 className="sx-hero__title">Blogs</h1>
          <p className="sx-hero__sub">Notes on reading user feedback, finding what to fix, and shipping better apps.</p>
        </div>
      </section>
      {posts.length ? <PostCards count={posts.length} /> : <p className="container sx-empty">No posts yet. Check back soon.</p>}
      <Footer />
    </div>
  );
}

/** /blogs/<slug>: one post. */
export function BlogPost({ post }: { post: Post }) {
  return (
    <div className="content-page">
      <AnnouncementBar />
      <Header tone="light" />
      <article className="post">
        <header className="container post__head">
          <a className="post__back" href="/blogs">
            ← All posts
          </a>
          <h1>{post.title}</h1>
          <p className="post__meta">
            {post.publishedAt && <time dateTime={post.publishedAt}>{formatDate(post.publishedAt)}</time>}
            {post.tags?.map((t) => (
              <span key={t} className="tag">
                {t}
              </span>
            ))}
          </p>
        </header>
        {post.cover?.url && (
          <div className="container post__cover">
            <img src={img(post.cover.url, 1600)} alt={post.cover.alt ?? ""} />
          </div>
        )}
        <div className="container post__body">
          <RichText value={post.body} />
        </div>
      </article>
      <Footer />
    </div>
  );
}

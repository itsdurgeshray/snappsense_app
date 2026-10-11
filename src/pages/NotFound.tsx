import { useEffect } from "react";
import { Header } from "../components/Header";
import { navigate } from "../router";

export function NotFound() {
  useEffect(() => {
    document.title = "Page not found · Snappsense";
  }, []);
  return (
    <div className="not-found">
      <Header tone="light" />
      <main className="container not-found__body">
        <p className="not-found__code">404</p>
        <h1>This page snapped out of existence</h1>
        <p>The link may be broken or the page may have moved.</p>
        <button type="button" className="btn-dark" onClick={() => navigate("/")}>
          Analyse an app
        </button>
      </main>
    </div>
  );
}

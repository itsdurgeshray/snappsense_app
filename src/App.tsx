import { useEffect } from "react";
import { Dashboard } from "./pages/Dashboard";
import { ContentPage } from "./pages/ContentPage";
import { BlogIndex, BlogPost } from "./pages/Blog";
import { usePath } from "./router";
import { resolveRoute } from "./routes";
import { headFor } from "./head";
import { useContent } from "./content/context";

export default function App() {
  const path = usePath();
  const content = useContent();
  const route = resolveRoute(path, content);
  useEffect(() => {
    if (route.kind !== "app") document.title = headFor(route, path, content).title;
  }, [route, path, content]);

  switch (route.kind) {
    case "app":
      return <Dashboard key={route.key} store={route.store} appId={route.appId} country={route.country} depth={route.depth} />;
    case "blogs":
      return <BlogIndex />;
    case "post":
      return <BlogPost post={route.post} />;
    case "page":
    case "notFound":
      return <ContentPage page={route.page} />;
  }
}

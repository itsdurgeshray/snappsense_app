import { Landing } from "./pages/Landing";
import { Dashboard } from "./pages/Dashboard";
import { usePath } from "./router";
import type { Depth, Store } from "./data";

export default function App() {
  const path = usePath();
  // #/app/<store>/<appId>?country=xx&depth=standard
  const match = path.match(/^\/app\/(play|app)\/([\w.]+)(?:\?(.*))?$/);
  if (!match) return <Landing />;
  const q = new URLSearchParams(match[3] ?? "");
  const depth = (["quick", "standard", "deep"].includes(q.get("depth") ?? "") ? q.get("depth") : "standard") as Depth;
  return <Dashboard key={path} store={match[1] as Store} appId={match[2]} country={q.get("country") ?? "us"} depth={depth} />;
}

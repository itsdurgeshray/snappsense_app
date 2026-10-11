import { useEffect, useRef, useState } from "react";

/**
 * "Version  v2.25.1 ▾" — a multi-select that looks like the other table
 * filters. Opens on the latest version.
 */
export function VersionPicker({
  versions,
  labels,
  latest,
  counts,
  picked,
  onChange,
}: {
  versions: string[];
  labels: Record<string, string>;
  latest: string[];
  counts: Record<string, number>;
  picked: string[];
  onChange: (v: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const label = (v: string) => `v${labels[v] ?? v}`;

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => root.current && !root.current.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  const toggle = (v: string) => {
    const next = picked.includes(v) ? picked.filter((p) => p !== v) : [...picked, v];
    onChange(versions.filter((x) => next.includes(x))); // keep newest-first order
  };
  const summary =
    picked.length === 0 ? "None" : picked.length === 1 ? label(picked[0]) : picked.length === versions.length ? "All" : `${picked.length} versions`;

  return (
    <div className="vpick" ref={root}>
      <button type="button" className="select vpick__btn" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className="select__label">Version</span>
        <span className="select__value">{summary}</span>
      </button>
      {open && (
        <div className="vpick__menu" role="listbox" aria-multiselectable="true" aria-label="App versions">
          {versions.map((v) => (
            <label key={v} className="vpick__row" role="option" aria-selected={picked.includes(v)}>
              <input type="checkbox" checked={picked.includes(v)} onChange={() => toggle(v)} />
              <span className="vpick__name">{label(v)}</span>
              {v === latest[0] && <span className="vpick__tag">Latest</span>}
              <span className="vpick__n">{(counts[v] ?? 0).toLocaleString()}</span>
            </label>
          ))}
          <div className="vpick__foot">
            <button type="button" className="link-btn" onClick={() => onChange(versions)}>
              Select all
            </button>
            <button type="button" className="link-btn" onClick={() => onChange([])}>
              Clear all
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

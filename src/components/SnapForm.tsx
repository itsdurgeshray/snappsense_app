import { useId, useState, type FormEvent } from "react";
import { linkProblem, parseStoreLink } from "../data";
import { navigate } from "../router";

export function SnapForm({ tone = "light" }: { tone?: "light" | "dark" }) {
  const id = useId();
  const [link, setLink] = useState("");
  const [error, setError] = useState("");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const ref = parseStoreLink(link);
    if (!ref) {
      setError(linkProblem(link));
      return;
    }
    setError("");
    navigate(`/app/${ref.store}/${ref.appId}?country=${ref.country}`);
  };

  return (
    <div className={`snap snap--${tone}`}>
      <form className="snap-form" onSubmit={submit} noValidate>
        <div className="snap-form__field">
          <label htmlFor={`${id}-link`} className="sr-only">
            Google Play or App Store link
          </label>
          <input
            id={`${id}-link`}
            type="url"
            inputMode="url"
            autoComplete="off"
            placeholder="paste a Play Store or App Store link"
            value={link}
            onChange={(e) => {
              setLink(e.target.value);
              if (error) setError("");
            }}
            aria-invalid={!!error}
            aria-describedby={error ? `${id}-error` : undefined}
          />
          {error && (
            <p id={`${id}-error`} className="snap-form__error" role="alert">
              {error}
            </p>
          )}
        </div>
        <button type="submit" className="btn-dark">
          Snap Sense
        </button>
      </form>

    </div>
  );
}

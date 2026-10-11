const WORDS = ["GET INSIGHTS", "PASTE LINK", "SNAP SENSE"];

function Sparkle() {
  return (
    <svg width="28" height="28" viewBox="0 0 40 40" aria-hidden="true">
      <path d="M20 0c1 11 9 19 20 20-11 1-19 9-20 20-1-11-9-19-20-20C11 19 19 11 20 0Z" fill="currentColor" />
    </svg>
  );
}

export function Marquee({ reverse = false, words = WORDS }: { reverse?: boolean; words?: string[] }) {
  return (
    <div className={`marquee${reverse ? " marquee--reverse" : ""}`} aria-hidden="true">
      <div className="marquee__track">
        {Array.from({ length: Math.max(4, Math.ceil(12 / words.length)) }, () => words).flat().map((word, i) => (
          <span className="marquee__item" key={i}>
            {word}
            <Sparkle />
          </span>
        ))}
      </div>
    </div>
  );
}

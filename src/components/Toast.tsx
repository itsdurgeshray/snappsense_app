import { useEffect } from "react";
import { createPortal } from "react-dom";

export function Toast({ message, onDone }: { message: string; onDone: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDone, 2600);
    return () => clearTimeout(t);
  }, [message, onDone]);
  return createPortal(
    <div className="toast" role="status">
      {message}
    </div>,
    document.body,
  );
}

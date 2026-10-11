import { useState, type FormEvent } from "react";
import { Modal } from "./Modal";
import { Toast } from "./Toast";
import { sendFeedback } from "../api";

const FACES = ["😡", "😕", "😐", "🙂", "😍"];

export function FeedbackModal({ onClose }: { onClose: () => void }) {
  const [rating, setRating] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSending(true);
    setError(false);
    try {
      await sendFeedback({ rating, message: message.trim(), page: window.location.hash || "/" });
      setSent(true);
    } catch {
      setError(true);
    } finally {
      setSending(false);
    }
  };

  if (sent) return <Toast message="Thanks! Your feedback helps us sharpen Snappsense." onDone={onClose} />;

  return (
    <Modal title="Give feedback" onClose={onClose}>
      <form onSubmit={submit}>
        <h2>Tell us what you think</h2>
        <p>How is Snappsense working for you? We read every message.</p>
        <span className="sr-only" id="rating-label">Rating</span>
        <div className="rating" role="group" aria-labelledby="rating-label">
          {FACES.map((f, i) => (
            <button key={f} type="button" aria-pressed={rating === i + 1} aria-label={`${i + 1} of 5`} onClick={() => setRating(i + 1)}>
              {f}
            </button>
          ))}
        </div>
        <label htmlFor="fb-msg">Your feedback</label>
        <textarea id="fb-msg" rows={4} value={message} onChange={(e) => setMessage(e.target.value)} placeholder="What should we improve?" />
        {error && (
          <p className="modal__error" role="alert">
            Couldn’t send that. Check your connection and try again.
          </p>
        )}
        <div className="modal__actions">
          <button type="button" className="btn-sm" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-sm btn-sm--dark" disabled={sending || (!rating && !message.trim())}>
            {sending ? "Sending…" : "Send feedback"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

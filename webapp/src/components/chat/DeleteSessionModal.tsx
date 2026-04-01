import { useEffect } from "react";
import type { SessionRecord } from "../../types";

export function DeleteSessionModal({
  session,
  isDeleting,
  error,
  onConfirm,
  onClose,
}: {
  session: SessionRecord;
  isDeleting: boolean;
  error: string | null;
  onConfirm: () => void;
  onClose: () => void;
}) {
  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !isDeleting) {
        onClose();
      }
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [isDeleting, onClose]);

  const title = session.title || "Untitled session";

  return (
    <div className="modal-backdrop" onClick={isDeleting ? undefined : onClose}>
      <div
        className="modal-card modal-card--confirm"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-card__header">
          <h2 className="modal-card__title">Delete chat?</h2>
          <button
            type="button"
            className="modal-card__close"
            onClick={onClose}
            disabled={isDeleting}
            aria-label="Close"
          >
            &times;
          </button>
        </div>

        <div className="confirm-modal">
          <p className="confirm-modal__body">
            This will permanently delete <strong>{title}</strong> and all of its
            saved messages.
          </p>

          {error ? <div className="confirm-modal__error">{error}</div> : null}

          <div className="confirm-modal__actions">
            <button
              type="button"
              className="btn btn--ghost"
              onClick={onClose}
              disabled={isDeleting}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn btn--danger"
              onClick={onConfirm}
              disabled={isDeleting}
            >
              {isDeleting ? "Deleting..." : "Delete chat"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

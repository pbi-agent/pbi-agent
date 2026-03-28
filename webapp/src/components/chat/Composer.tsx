import { useCallback, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

export function Composer({
  inputEnabled,
  sessionEnded,
  liveSessionId,
  onSubmit,
}: {
  inputEnabled: boolean;
  sessionEnded: boolean;
  liveSessionId: string | null;
  onSubmit: (text: string, imagePaths: string[]) => Promise<void>;
}) {
  const [input, setInput] = useState("");
  const [imagePaths, setImagePaths] = useState("");
  const [showImages, setShowImages] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const autoResize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, []);

  const handleSubmit = async (event?: FormEvent<HTMLFormElement>) => {
    event?.preventDefault();
    const trimmed = input.trim();
    if (!trimmed && !imagePaths.trim()) return;
    await onSubmit(
      trimmed,
      imagePaths
        .split("\n")
        .map((v) => v.trim())
        .filter(Boolean),
    );
    setInput("");
    setImagePaths("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  };

  const canSend = Boolean(liveSessionId) && inputEnabled && !sessionEnded;

  const statusText = sessionEnded
    ? "Session ended"
    : inputEnabled
      ? "Ready"
      : "Waiting for agent...";

  const statusClass = sessionEnded
    ? "composer__status composer__status--ended"
    : inputEnabled
      ? "composer__status composer__status--ready"
      : "composer__status";

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <div className="composer__input-row">
        <textarea
          ref={textareaRef}
          className="composer__textarea"
          value={input}
          onChange={(e) => {
            setInput(e.target.value);
            autoResize();
          }}
          onKeyDown={handleKeyDown}
          placeholder={sessionEnded ? "Start a new session to continue..." : "Send a message..."}
          rows={1}
          disabled={!canSend}
        />
        <button
          type="submit"
          className="composer__send"
          disabled={!canSend}
          title="Send (Enter)"
        >
          &#8593;
        </button>
      </div>

      <div className="composer__footer">
        <span className={statusClass}>{statusText}</span>
        <button
          type="button"
          className="composer__attach-toggle"
          onClick={() => setShowImages((prev) => !prev)}
        >
          {showImages ? "Hide images" : "+ Images"}
        </button>
      </div>

      {showImages ? (
        <div className="composer__image-input">
          <textarea
            className="composer__image-textarea"
            value={imagePaths}
            onChange={(e) => setImagePaths(e.target.value)}
            placeholder="Image paths, one per line"
            rows={2}
            disabled={!canSend}
          />
        </div>
      ) : null}
    </form>
  );
}

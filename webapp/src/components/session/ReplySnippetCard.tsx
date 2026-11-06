import type { JSX } from "react";
import { MessageSquareQuoteIcon, XIcon } from "lucide-react";
import { Button } from "../ui/button";

export function ReplySnippetCard({
  quote,
  comment,
  onRemove,
}: {
  quote: string;
  comment: string;
  onRemove?: () => void;
}): JSX.Element {
  return (
    <div className="reply-snippet-card" data-testid="reply-snippet-card">
      <div className="reply-snippet-card__header">
        <MessageSquareQuoteIcon aria-hidden="true" className="reply-snippet-card__icon" />
        <span className="reply-snippet-card__label">Reply</span>
        {onRemove ? (
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            className="reply-snippet-card__remove"
            onClick={onRemove}
            aria-label="Remove reply snippet"
          >
            <XIcon aria-hidden="true" />
          </Button>
        ) : null}
      </div>
      <blockquote className="reply-snippet-card__quote">{quote}</blockquote>
      <p className="reply-snippet-card__comment">{comment}</p>
    </div>
  );
}

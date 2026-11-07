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
    <div className="flex min-w-0 flex-col gap-1 rounded-md border border-border bg-card p-2 text-left text-card-foreground" data-testid="reply-snippet-card">
      <div className="flex min-h-5 items-center gap-1 text-xs text-muted-foreground">
        <MessageSquareQuoteIcon aria-hidden="true" className="size-3.5" />
        <span className="font-medium">Reply</span>
        {onRemove ? (
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            className="ml-auto"
            onClick={onRemove}
            aria-label="Remove reply snippet"
          >
            <XIcon aria-hidden="true" />
          </Button>
        ) : null}
      </div>
      <blockquote className="m-0 line-clamp-4 border-l-2 border-border pl-2 text-xs wrap-anywhere whitespace-pre-wrap text-muted-foreground">{quote}</blockquote>
      <p className="m-0 text-sm wrap-anywhere whitespace-pre-wrap">{comment}</p>
    </div>
  );
}

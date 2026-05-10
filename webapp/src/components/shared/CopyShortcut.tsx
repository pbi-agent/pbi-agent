import { useEffect, useState } from "react";
import { CheckIcon, CopyIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "../ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui/tooltip";

type CopyStatus = "idle" | "copied" | "failed";
const COPY_FEEDBACK_DURATION_MS = 3000;

async function writeClipboardText(text: string): Promise<void> {
  if (typeof navigator === "undefined" || !navigator.clipboard?.writeText) {
    throw new Error("Clipboard is unavailable");
  }
  await navigator.clipboard.writeText(text);
}

export function CopyShortcut({
  text,
  ariaLabel = "Copy",
  className,
}: {
  text: string;
  ariaLabel?: string;
  className?: string;
}) {
  const [status, setStatus] = useState<CopyStatus>("idle");

  useEffect(() => {
    if (status === "idle") {
      return undefined;
    }

    const timeout = window.setTimeout(() => setStatus("idle"), COPY_FEEDBACK_DURATION_MS);
    return () => window.clearTimeout(timeout);
  }, [status]);

  const tooltipLabel =
    status === "copied" ? "Copied"
    : status === "failed" ? "Copy failed"
    : "Copy";
  const buttonLabel = status === "idle" ? ariaLabel : tooltipLabel;
  const Icon = status === "copied" ? CheckIcon : CopyIcon;

  async function copyText(): Promise<void> {
    try {
      await writeClipboardText(text);
      setStatus("copied");
    } catch {
      setStatus("failed");
    }
  }

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="icon-sm"
            className={cn("copy-shortcut", className)}
            aria-label={buttonLabel}
            data-copy-status={status}
            onClick={(event) => {
              event.stopPropagation();
              void copyText();
            }}
          >
            <Icon aria-hidden="true" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>{tooltipLabel}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

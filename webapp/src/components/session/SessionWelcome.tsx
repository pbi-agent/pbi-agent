import {
  AtSignIcon,
  MessageSquareTextIcon,
  SlashIcon,
  TerminalIcon,
  WandSparklesIcon,
} from "lucide-react";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "../ui/empty";

type Tip = {
  icon: React.ComponentType<{ className?: string }>;
  kbd?: string;
  label: string;
};

const TIPS: Tip[] = [
  {
    icon: MessageSquareTextIcon,
    label: "Send any prompt to begin",
  },
  {
    icon: SlashIcon,
    kbd: "/",
    label: "Insert a saved command",
  },
  {
    icon: TerminalIcon,
    kbd: "!",
    label: "Run a shell command",
  },
  {
    icon: AtSignIcon,
    kbd: "@",
    label: "Reference a workspace file",
  },
];

export function SessionWelcome() {
  return (
    <Empty
      className="session-welcome border-0"
      role="status"
      aria-live="polite"
    >
      <EmptyHeader>
        <EmptyMedia variant="icon" className="size-10 [&_svg:not([class*='size-'])]:size-5">
          <WandSparklesIcon />
        </EmptyMedia>
        <EmptyTitle className="text-base">{'>'}_ work smart</EmptyTitle>
      </EmptyHeader>
      <EmptyContent>
        <ul className="session-welcome__tips grid w-full gap-2 text-left">
          {TIPS.map((tip) => {
            const Icon = tip.icon;
            return (
              <li
                key={tip.label}
                className="flex items-center gap-3 rounded-md border border-border/60 bg-muted/40 px-3 py-2 text-sm text-muted-foreground"
              >
                <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-background text-foreground">
                  <Icon className="size-3.5" />
                </span>
                <span className="flex-1 leading-snug">{tip.label}</span>
                {tip.kbd ? (
                  <kbd className="inline-flex h-5 min-w-5 items-center justify-center rounded border border-border bg-background px-1.5 font-mono text-[11px] font-medium text-foreground">
                    {tip.kbd}
                  </kbd>
                ) : null}
              </li>
            );
          })}
        </ul>
      </EmptyContent>
    </Empty>
  );
}

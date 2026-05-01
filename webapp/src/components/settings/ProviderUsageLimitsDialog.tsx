import { useQuery } from "@tanstack/react-query";
import {
  ActivityIcon,
  AlertTriangleIcon,
  CalendarClockIcon,
  CoinsIcon,
  GaugeIcon,
  InfinityIcon,
  RefreshCcwIcon,
  ShieldCheckIcon,
  SparklesIcon,
} from "lucide-react";
import { fetchProviderUsageLimits } from "../../api";
import type {
  ProviderUsageLimitsResponse,
  ProviderView,
  UsageLimitBucket,
  UsageLimitWindow,
} from "../../types";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Skeleton } from "../ui/skeleton";
import { cn } from "@/lib/utils";

interface Props {
  provider: ProviderView;
  onClose: () => void;
}

type StatusKey = UsageLimitBucket["status"];

const STATUS_LABEL: Record<StatusKey, string> = {
  ok: "Healthy",
  warning: "Warning",
  exhausted: "Exhausted",
  unknown: "Unknown",
};

const STATUS_BADGE_CLASSES: Record<StatusKey, string> = {
  ok: "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  warning:
    "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  exhausted:
    "border-rose-500/30 bg-rose-500/10 text-rose-600 dark:text-rose-400",
  unknown: "border-border bg-muted text-muted-foreground",
};

function getProgressTone(percent: number | null): {
  bar: string;
  track: string;
  text: string;
} {
  if (percent == null) {
    return {
      bar: "bg-muted-foreground/40",
      track: "bg-muted",
      text: "text-muted-foreground",
    };
  }
  if (percent >= 90) {
    return {
      bar: "bg-rose-500",
      track: "bg-rose-500/15",
      text: "text-rose-600 dark:text-rose-400",
    };
  }
  if (percent >= 70) {
    return {
      bar: "bg-amber-500",
      track: "bg-amber-500/15",
      text: "text-amber-600 dark:text-amber-400",
    };
  }
  return {
    bar: "bg-emerald-500",
    track: "bg-emerald-500/15",
    text: "text-emerald-600 dark:text-emerald-400",
  };
}

function formatPercent(value: number | null): string | null {
  if (value == null) {
    return null;
  }
  return `${Math.round(value)}%`;
}

function formatUsageReset(window: UsageLimitWindow): string | null {
  if (window.reset_at_iso) {
    return new Date(window.reset_at_iso).toLocaleString();
  }
  if (window.resets_at != null) {
    return new Date(window.resets_at * 1000).toLocaleString();
  }
  return null;
}

function formatWindowLabel(window: UsageLimitWindow): string {
  if (window.name) {
    const lower = window.name.toLowerCase();
    if (lower === "primary" || lower === "secondary" || lower === "tertiary") {
      // Fall through to duration-based label.
    } else {
      return `${window.name} limit`;
    }
  }
  const minutes = window.window_minutes;
  if (minutes == null) {
    return "Limit";
  }
  const day = 24 * 60;
  const week = 7 * day;
  const month = 30 * day;
  const bias = 3;
  if (minutes <= day + bias) {
    return `${Math.max(1, Math.floor((minutes + bias) / 60))}h limit`;
  }
  if (minutes <= week + bias) {
    return "Weekly limit";
  }
  if (minutes <= month + bias) {
    return "Monthly limit";
  }
  return "Annual limit";
}

function formatFetchedAt(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date.toLocaleString();
}

function bucketTone(bucket: UsageLimitBucket): {
  bar: string;
  track: string;
  text: string;
} {
  if (bucket.unlimited) {
    return getProgressTone(0);
  }
  const peak = bucket.windows.reduce<number | null>((best, window) => {
    const used =
      window.used_percent ??
      (window.remaining_percent != null ? 100 - window.remaining_percent : null);
    if (used == null) {
      return best;
    }
    if (best == null || used > best) {
      return used;
    }
    return best;
  }, null);
  return getProgressTone(peak);
}

export function ProviderUsageLimitsDialog({ provider, onClose }: Props) {
  const usageQuery = useQuery({
    queryKey: ["provider-usage-limits", provider.id],
    queryFn: () => fetchProviderUsageLimits(provider.id),
    staleTime: 30_000,
  });

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="provider-usage-dialog flex max-h-[85vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl">
        <UsageDialogHeader
          provider={provider}
          usage={usageQuery.data}
          onRefresh={() => {
            void usageQuery.refetch();
          }}
          isFetching={usageQuery.isFetching}
        />
        <div className="provider-usage-dialog__scroll flex-1 overflow-y-auto">
          {usageQuery.isLoading ? (
            <UsageLoadingState />
          ) : usageQuery.isError ? (
            <UsageErrorState
              message={usageQuery.error.message}
              onRetry={() => {
                void usageQuery.refetch();
              }}
            />
          ) : !usageQuery.data || usageQuery.data.buckets.length === 0 ? (
            <UsageEmptyState />
          ) : (
            <div className="provider-usage-dialog__buckets">
              {usageQuery.data.buckets.map((bucket) => (
                <BucketCard key={bucket.id} bucket={bucket} />
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function UsageDialogHeader({
  provider,
  usage,
  onRefresh,
  isFetching,
}: {
  provider: ProviderView;
  usage: ProviderUsageLimitsResponse | undefined;
  onRefresh: () => void;
  isFetching: boolean;
}) {
  const planType = usage?.plan_type ?? provider.auth_status.plan_type ?? null;
  const accountLabel =
    usage?.account_label ?? provider.auth_status.email ?? null;
  const fetchedAtText = formatFetchedAt(usage?.fetched_at);

  return (
    <DialogHeader className="provider-usage-dialog__header gap-0 border-b border-border/60">
      <div className="provider-usage-dialog__header-top">
        <div className="provider-usage-dialog__header-identity">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <GaugeIcon className="size-5" />
          </div>
          <div className="provider-usage-dialog__header-content min-w-0">
            <DialogTitle className="text-base leading-tight">
              Usage &amp; limits
            </DialogTitle>
            <DialogDescription className="mt-1 truncate">
              <span className="font-medium text-foreground">
                {provider.name}
              </span>
              {accountLabel ? (
                <span className="text-muted-foreground"> · {accountLabel}</span>
              ) : null}
            </DialogDescription>
          </div>
        </div>
        {planType ? (
          <Badge
            variant="outline"
            className="provider-usage-dialog__plan-badge border-primary/30 bg-primary/5 capitalize text-primary"
          >
            <SparklesIcon className="size-3" />
            {planType}
          </Badge>
        ) : null}
      </div>
      <div className="provider-usage-dialog__meta flex items-center justify-between gap-3 text-xs text-muted-foreground">
        {fetchedAtText ? (
          <span className="inline-flex min-w-0 items-center gap-1.5">
            <CalendarClockIcon className="size-3.5 shrink-0" />
            <span className="truncate">Updated {fetchedAtText}</span>
          </span>
        ) : (
          <span aria-hidden="true" />
        )}
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onRefresh}
          disabled={isFetching}
          className="provider-usage-dialog__refresh shrink-0"
          aria-label="Refresh usage limits"
        >
          <RefreshCcwIcon
            data-icon="inline-start"
            className={cn(isFetching && "animate-spin")}
          />
          Refresh
        </Button>
      </div>
    </DialogHeader>
  );
}

function BucketCard({ bucket }: { bucket: UsageLimitBucket }) {
  const tone = bucketTone(bucket);
  const noteEntries = bucketNoteEntries(bucket);
  const hasWindows = bucket.windows.length > 0;

  return (
    <section
      aria-label={`Usage limit: ${bucket.label}`}
      className={cn(
        "provider-usage-bucket rounded-xl border border-border bg-card/60 shadow-xs transition-colors",
        bucket.status === "exhausted" && "border-rose-500/30 bg-rose-500/5",
        bucket.status === "warning" && "border-amber-500/30 bg-amber-500/5",
      )}
    >
      <header className="provider-usage-bucket__header flex flex-wrap items-center justify-between gap-2 border-b border-border/40">
        <div className="flex min-w-0 items-center gap-2.5">
          <span
            className={cn(
              "flex size-8 shrink-0 items-center justify-center rounded-md",
              tone.track,
              tone.text,
            )}
          >
            {bucket.unlimited ? (
              <InfinityIcon className="size-4" />
            ) : (
              <ActivityIcon className="size-4" />
            )}
          </span>
          <h3 className="truncate text-sm font-semibold text-foreground">
            {bucket.label}
          </h3>
        </div>
        <Badge
          variant="outline"
          className={cn(
            "provider-usage-bucket__status-badge uppercase tracking-wide",
            STATUS_BADGE_CLASSES[bucket.status],
          )}
        >
          {STATUS_LABEL[bucket.status]}
        </Badge>
      </header>

      <div className="provider-usage-bucket__body">
        {bucket.unlimited ? (
          <UnlimitedBlock />
        ) : hasWindows ? (
          <div className="provider-usage-window-list">
            {bucket.windows.map((window, index) => (
              <UsageWindowRow
                key={`${bucket.id}-${window.name}-${index}`}
                window={window}
              />
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">
            No window details returned.
          </p>
        )}

        {noteEntries.length > 0 && (
          <ul className="provider-usage-bucket__notes flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-border/40 text-xs text-muted-foreground">
            {noteEntries.map((entry) => (
              <li
                key={entry.label}
                className="inline-flex items-center gap-1.5"
              >
                <entry.icon className="size-3.5" />
                <span>{entry.label}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function UnlimitedBlock() {
  return (
    <div className="flex items-center gap-2.5 rounded-lg border border-dashed border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
      <InfinityIcon className="size-4 text-foreground" />
      <span>No usage cap on this limit.</span>
    </div>
  );
}

function UsageWindowRow({ window }: { window: UsageLimitWindow }) {
  const used = window.used_percent ?? null;
  const remaining = window.remaining_percent ?? null;
  const progressValue = used ?? (remaining == null ? null : 100 - remaining);
  const tone = getProgressTone(progressValue);
  const requestText =
    window.remaining_requests != null
      ? `${window.remaining_requests}${
          window.total_requests != null ? `/${window.total_requests}` : ""
        } requests left`
      : null;
  const usedRequestText =
    window.used_requests != null && window.total_requests != null
      ? `${window.used_requests}/${window.total_requests} used`
      : null;
  const resetText = formatUsageReset(window);

  const summaryParts: string[] = [];
  if (used != null) summaryParts.push(`Used ${formatPercent(used)}`);
  if (remaining != null)
    summaryParts.push(`Remaining ${formatPercent(remaining)}`);
  if (requestText) summaryParts.push(requestText);
  else if (usedRequestText) summaryParts.push(usedRequestText);

  return (
    <div className="provider-usage-window rounded-lg border border-border/60 bg-background/40">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-sm font-medium text-foreground">
          {formatWindowLabel(window)}
        </span>
        {progressValue != null ? (
          <span className={cn("text-xs font-semibold", tone.text)}>
            {formatPercent(progressValue)} used
          </span>
        ) : remaining != null ? (
          <span className={cn("text-xs font-semibold", tone.text)}>
            {formatPercent(remaining)} left
          </span>
        ) : null}
      </div>

      <div
        className={cn(
          "mt-2.5 h-2 w-full overflow-hidden rounded-full",
          tone.track,
        )}
        role="progressbar"
        aria-valuenow={progressValue ?? undefined}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        {progressValue != null ? (
          <div
            className={cn("h-full rounded-full transition-all", tone.bar)}
            style={{ width: `${Math.max(0, Math.min(100, progressValue))}%` }}
          />
        ) : null}
      </div>

      {summaryParts.length > 0 && (
        <p className="mt-2.5 text-xs text-muted-foreground">
          {summaryParts.join(" · ")}
        </p>
      )}
      {resetText && (
        <p className="mt-1.5 inline-flex items-center gap-1.5 text-xs text-muted-foreground">
          <CalendarClockIcon className="size-3.5" />
          Resets {resetText}
        </p>
      )}
    </div>
  );
}

type NoteEntry = {
  label: string;
  icon: typeof ShieldCheckIcon;
};

function bucketNoteEntries(bucket: UsageLimitBucket): NoteEntry[] {
  const entries: NoteEntry[] = [];
  if (bucket.overage_allowed) {
    entries.push({ label: "Overage allowed", icon: ShieldCheckIcon });
  }
  if (bucket.overage_count) {
    entries.push({
      label: `Overage used: ${bucket.overage_count}`,
      icon: AlertTriangleIcon,
    });
  }
  if (bucket.credits?.unlimited) {
    entries.push({ label: "Credits: unlimited", icon: CoinsIcon });
  } else if (bucket.credits?.balance) {
    entries.push({
      label: `Credits: ${bucket.credits.balance}`,
      icon: CoinsIcon,
    });
  }
  return entries;
}

function UsageLoadingState() {
  return (
    <div className="grid gap-4">
      <Skeleton className="h-32 w-full rounded-xl" />
      <Skeleton className="h-32 w-full rounded-xl" />
    </div>
  );
}

function UsageEmptyState() {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-muted/30 px-6 py-12 text-center">
      <GaugeIcon className="size-7 text-muted-foreground" />
      <p className="text-sm font-medium text-foreground">
        No usage limits returned
      </p>
      <p className="text-xs text-muted-foreground">
        This subscription doesn't expose any usage windows right now.
      </p>
    </div>
  );
}

function UsageErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-rose-500/30 bg-rose-500/5 px-6 py-10 text-center">
      <AlertTriangleIcon className="size-7 text-rose-500" />
      <div>
        <p className="text-sm font-medium text-foreground">
          Couldn't load usage limits
        </p>
        <p className="mt-1 text-xs text-muted-foreground">{message}</p>
      </div>
      <Button type="button" variant="outline" size="sm" onClick={onRetry}>
        <RefreshCcwIcon data-icon="inline-start" />
        Try again
      </Button>
    </div>
  );
}

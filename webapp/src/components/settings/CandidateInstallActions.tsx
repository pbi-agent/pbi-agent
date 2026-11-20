import { useState } from "react";
import { CheckIcon, DownloadIcon, RefreshCwIcon } from "lucide-react";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { ConfirmDialog } from "../ui/confirm-dialog";

/**
 * Returns `listing` with every candidate matching `isTarget` flagged as
 * installed, so the open Add dialog reflects an install without refetching.
 */
export function markCandidateInstalled<
  TListing extends { candidates: { installed: boolean }[] },
>(
  listing: TListing | null,
  isTarget: (candidate: TListing["candidates"][number]) => boolean,
): TListing | null {
  if (!listing) return listing;
  return {
    ...listing,
    candidates: listing.candidates.map((candidate) =>
      isTarget(candidate) ? { ...candidate, installed: true } : candidate,
    ),
  };
}

/**
 * Install controls for a candidate row in the Add Skill/Command/Agent dialogs.
 *
 * Not installed: a single Install button. Installed (the install target
 * already exists in the project): an Installed badge plus a secondary Replace
 * action that overwrites the local copy after confirmation.
 */
export function CandidateInstallActions({
  kind,
  itemName,
  isInstalling,
  isInstalled,
  disabled,
  onInstall,
  onReplace,
}: {
  kind: "skill" | "command" | "agent";
  itemName: string;
  isInstalling: boolean;
  isInstalled: boolean;
  disabled: boolean;
  onInstall: () => void;
  onReplace: () => void;
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);

  if (!isInstalled) {
    return (
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={onInstall}
        disabled={disabled}
        className="shrink-0"
      >
        {isInstalling ? (
          <LoadingSpinner size="sm" />
        ) : (
          <DownloadIcon data-icon="inline-start" />
        )}
        Install
      </Button>
    );
  }

  return (
    <div className="flex shrink-0 items-center gap-2">
      <Badge variant="secondary">
        <CheckIcon data-icon="inline-start" />
        Installed
      </Badge>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        onClick={() => setConfirmOpen(true)}
        disabled={disabled}
      >
        {isInstalling ? (
          <LoadingSpinner size="sm" />
        ) : (
          <RefreshCwIcon data-icon="inline-start" />
        )}
        Replace
      </Button>
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={`Replace ${kind} "${itemName}"?`}
        description={`The installed ${kind} will be overwritten with the version from this source. Local changes to it will be lost.`}
        icon={<RefreshCwIcon />}
        confirmLabel="Replace"
        onConfirm={() => {
          setConfirmOpen(false);
          onReplace();
        }}
      />
    </div>
  );
}

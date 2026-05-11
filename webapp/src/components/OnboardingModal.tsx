import { SparklesIcon } from "lucide-react";
import { FormDialog } from "./ui/form-dialog";

export function OnboardingModal({
  openSettings,
  isOnSettingsPage,
  onDismissOnSettings,
}: {
  openSettings: () => void;
  isOnSettingsPage: boolean;
  onDismissOnSettings: () => void;
}) {
  return (
    <FormDialog
      open
      onOpenChange={() => undefined}
      showCloseButton={false}
      title="Setup Required"
      icon={<SparklesIcon />}
      description={
        isOnSettingsPage
          ? "No model profiles are configured yet. Add a provider below, complete sign-in if prompted, then create a model profile to get started."
          : "No model profiles are configured yet. You need to add at least one provider, complete sign-in if prompted, and create a model profile before you can use the app."
      }
      primaryAction={{
        label: isOnSettingsPage ? "Configure below" : "Go to Settings",
        type: "button",
        onClick: isOnSettingsPage ? onDismissOnSettings : openSettings,
      }}
    >
      <span className="sr-only">Model profile setup is required.</span>
    </FormDialog>
  );
}

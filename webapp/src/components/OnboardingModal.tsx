import { useNavigate } from "react-router-dom";
import { SparklesIcon } from "lucide-react";
import { Button } from "./ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";

interface Props {
  isOnSettingsPage: boolean;
  onDismissOnSettings: () => void;
}

export function OnboardingModal({ isOnSettingsPage, onDismissOnSettings }: Props) {
  const navigate = useNavigate();

  return (
    <Dialog open>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <div className="modal-icon-shell">
            <SparklesIcon />
          </div>
          <DialogTitle>Setup Required</DialogTitle>
          <DialogDescription>
            {isOnSettingsPage
              ? "No model profiles are configured yet. Add a provider below, complete sign-in if prompted, then create a model profile to get started."
              : "No model profiles are configured yet. You need to add at least one provider, complete sign-in if prompted, and create a model profile before you can use the app."}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          {isOnSettingsPage ? (
            <Button type="button" onClick={onDismissOnSettings}>
              Configure below
            </Button>
          ) : (
            <Button
              type="button"
              onClick={() => {
                void navigate("/settings");
              }}
            >
              Go to Settings
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

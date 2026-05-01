import { useNavigate } from "react-router-dom";
import { SparklesIcon } from "lucide-react";
import { Button } from "./ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
      <DialogContent className="task-form-dialog" showCloseButton={false}>
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
        <div className="app-action-row app-action-row--end task-form__footer">
          {isOnSettingsPage ? (
            <Button
              className="task-form__action-button"
              type="button"
              onClick={onDismissOnSettings}
            >
              Configure below
            </Button>
          ) : (
            <Button
              className="task-form__action-button"
              type="button"
              onClick={() => {
                void navigate("/settings");
              }}
            >
              Go to Settings
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

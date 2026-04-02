import { useNavigate } from "react-router-dom";

interface Props {
  isOnSettingsPage: boolean;
  onDismissOnSettings: () => void;
}

export function OnboardingModal({ isOnSettingsPage, onDismissOnSettings }: Props) {
  const navigate = useNavigate();

  return (
    <div className="modal-backdrop">
      <div
        className="modal-card modal-card--confirm"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-card__header">
          <h2 className="modal-card__title">Setup Required</h2>
        </div>
        <div className="confirm-modal">
          <div className="confirm-modal__body">
            {isOnSettingsPage
              ? "No model profiles are configured yet. Add a provider below, then create a model profile to get started."
              : "No model profiles are configured yet. You need to add at least one provider and model profile before you can use the app."}
          </div>
          <div className="confirm-modal__actions">
            {isOnSettingsPage ? (
              <button
                type="button"
                className="btn btn--primary"
                onClick={onDismissOnSettings}
              >
                Configure below
              </button>
            ) : (
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => navigate("/settings")}
              >
                Go to Settings
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

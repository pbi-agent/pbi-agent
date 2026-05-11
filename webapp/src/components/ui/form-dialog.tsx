import * as React from "react";
import type { VariantProps } from "class-variance-authority";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

type ButtonVariant = NonNullable<VariantProps<typeof buttonVariants>["variant"]>;

type FormDialogPrimaryAction = {
  label: React.ReactNode;
  type?: "submit" | "button";
  variant?: ButtonVariant;
  onClick?: () => void;
  pendingLabel?: React.ReactNode;
  disabled?: boolean;
};

type FormDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: React.ReactNode;
  description?: React.ReactNode;
  icon?: React.ReactNode;
  onSubmit?: (event: React.FormEvent<HTMLFormElement>) => void;
  isPending?: boolean;
  error?: React.ReactNode;
  primaryAction?: FormDialogPrimaryAction;
  cancelLabel?: React.ReactNode;
  onCancel?: () => void;
  size?: "sm" | "md" | "lg" | "wide";
  showCloseButton?: boolean;
  children: React.ReactNode;
};

const sizeClassName: Record<NonNullable<FormDialogProps["size"]>, string> = {
  sm: "sm:max-w-sm",
  md: "sm:max-w-lg",
  lg: "sm:max-w-2xl",
  wide: "sm:max-w-4xl",
};

export function FormDialog({
  open,
  onOpenChange,
  title,
  description,
  icon,
  onSubmit,
  isPending = false,
  error,
  primaryAction,
  cancelLabel = "Cancel",
  onCancel,
  size = "md",
  showCloseButton = true,
  children,
}: FormDialogProps) {
  const body = (
    <>
      <div className="task-form__body">{children}</div>
      {error ? (
        <Alert variant="destructive" className="task-form__error">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {primaryAction ? (
        <DialogFooter>
          {onCancel ? (
            <Button
              type="button"
              variant="outline"
              onClick={onCancel}
              disabled={isPending}
            >
              {cancelLabel}
            </Button>
          ) : null}
          <Button
            type={primaryAction.type ?? (onSubmit ? "submit" : "button")}
            variant={primaryAction.variant ?? "default"}
            onClick={primaryAction.onClick}
            disabled={isPending || primaryAction.disabled}
          >
            {isPending && primaryAction.pendingLabel
              ? primaryAction.pendingLabel
              : primaryAction.label}
          </Button>
        </DialogFooter>
      ) : null}
    </>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={showCloseButton}
        className={cn(
          "flex max-h-[calc(100dvh-2rem)] flex-col overflow-hidden",
          sizeClassName[size],
        )}
      >
        <DialogHeader className="pr-10">
          {icon ? <div className="modal-icon-shell">{icon}</div> : null}
          <DialogTitle>{title}</DialogTitle>
          {description ? (
            <DialogDescription asChild>
              <div>{description}</div>
            </DialogDescription>
          ) : null}
        </DialogHeader>

        {onSubmit ? (
          <form className="task-form" onSubmit={onSubmit}>
            {body}
          </form>
        ) : (
          <div className="task-form">{body}</div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export { DialogClose };

import * as React from "react";
import type { VariantProps } from "class-variance-authority";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { FieldGroup } from "@/components/ui/field";
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
  headerContent?: React.ReactNode;
  icon?: React.ReactNode;
  onSubmit?: (event: React.FormEvent<HTMLFormElement>) => void;
  isPending?: boolean;
  error?: React.ReactNode;
  primaryAction?: FormDialogPrimaryAction;
  cancelLabel?: React.ReactNode;
  onCancel?: () => void;
  size?: "sm" | "md" | "lg" | "wide";
  contentClassName?: string;
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
  headerContent,
  icon,
  onSubmit,
  isPending = false,
  error,
  primaryAction,
  cancelLabel = "Cancel",
  onCancel,
  size = "md",
  contentClassName,
  showCloseButton = true,
  children,
}: FormDialogProps) {
  const body = (
    <>
      <FieldGroup data-form-dialog-body="" className="min-h-0 flex-1 overflow-y-auto">{children}</FieldGroup>
      {error ? (
        <Alert variant="destructive">
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
        data-size={size}
        showCloseButton={showCloseButton}
        className={cn(
          "flex max-h-dvh flex-col overflow-hidden",
          sizeClassName[size],
          contentClassName,
        )}
      >
        <DialogHeader className="shrink-0 pr-10">
          {icon ? <div className="flex size-10 items-center justify-center rounded-lg bg-muted text-muted-foreground">{icon}</div> : null}
          <DialogTitle>{title}</DialogTitle>
          {description ? (
            <DialogDescription asChild>
              <div>{description}</div>
            </DialogDescription>
          ) : null}
          {headerContent ? headerContent : null}
        </DialogHeader>

        {onSubmit ? (
          <form className="flex min-h-0 flex-1 flex-col gap-4" onSubmit={onSubmit}>
            {body}
          </form>
        ) : (
          <div className="flex min-h-0 flex-1 flex-col gap-4">{body}</div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export { DialogClose };

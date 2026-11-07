import type * as React from "react";
import { Alert, AlertDescription } from "../ui/alert";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../ui/card";

/** Vertical stack wrapping one settings tab. */
export function SettingsSection({ children }: { children: React.ReactNode }) {
  return <section className="flex min-w-0 flex-col gap-4">{children}</section>;
}

/** Standard settings panel: stock shadcn Card with title, description and actions. */
export function SettingsPanel({
  title,
  description,
  actions,
  children,
  ...props
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children?: React.ReactNode;
} & Omit<React.ComponentProps<typeof Card>, "title" | "children">) {
  return (
    <Card {...props}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
        {actions ? (
          <CardAction>
            <div className="flex flex-wrap items-center gap-2">{actions}</div>
          </CardAction>
        ) : null}
      </CardHeader>
      {children ? (
        <CardContent>
          <div className="flex min-w-0 flex-col gap-3">{children}</div>
        </CardContent>
      ) : null}
    </Card>
  );
}

/** Informational callout used at the top of settings tabs. */
export function SettingsNote({ children }: { children: React.ReactNode }) {
  return (
    <Alert>
      <AlertDescription>{children}</AlertDescription>
    </Alert>
  );
}

/** Row container for item lists inside a panel. */
export function SettingsList({ children }: { children: React.ReactNode }) {
  return <div className="flex min-w-0 flex-col gap-2">{children}</div>;
}

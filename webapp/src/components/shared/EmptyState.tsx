import type { ReactNode } from "react";
import { InboxIcon } from "lucide-react";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "../ui/empty";

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <Empty>
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <InboxIcon />
        </EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        {description ? (
          <EmptyDescription>
            {description}
          </EmptyDescription>
        ) : null}
      </EmptyHeader>
      {action ? (
        <EmptyContent>{action}</EmptyContent>
      ) : null}
    </Empty>
  );
}

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
    <Empty className="empty-state">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <InboxIcon />
        </EmptyMedia>
        <EmptyTitle className="empty-state__title">{title}</EmptyTitle>
        {description ? (
          <EmptyDescription className="empty-state__description">
            {description}
          </EmptyDescription>
        ) : null}
      </EmptyHeader>
      {action ? (
        <EmptyContent className="empty-state__action">{action}</EmptyContent>
      ) : null}
    </Empty>
  );
}

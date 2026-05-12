import type * as React from "react";

import { cn } from "../lib/utils";
import { Badge } from "./ui/badge";

type MetaBadgeProps = Omit<React.ComponentProps<typeof Badge>, "asChild" | "variant" | "size"> & {
  labelClassName?: string;
  truncate?: boolean;
};

export function MetaBadge({
  className,
  labelClassName,
  truncate = false,
  children,
  ...props
}: MetaBadgeProps) {
  return (
    <Badge
      variant="secondary"
      size="meta"
      className={cn(truncate && "max-w-full min-w-0 justify-start overflow-hidden", className)}
      {...props}
    >
      <span className={cn("whitespace-nowrap", truncate && "min-w-0 truncate", labelClassName)}>
        {children}
      </span>
    </Badge>
  );
}
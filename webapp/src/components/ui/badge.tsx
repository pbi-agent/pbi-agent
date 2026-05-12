import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "group/badge inline-flex min-h-6 w-fit shrink-0 items-center justify-center gap-1 rounded-4xl border border-transparent px-2 py-0.5 text-xs leading-normal font-medium whitespace-nowrap transition-all focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&>svg]:pointer-events-none [&>svg]:size-3!",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground [a]:hover:bg-primary/80",
        secondary:
          "bg-secondary text-secondary-foreground [a]:hover:bg-secondary/80",
        destructive:
          "bg-destructive/10 text-destructive focus-visible:ring-destructive/20 dark:bg-destructive/20 dark:focus-visible:ring-destructive/40 [a]:hover:bg-destructive/20",
        outline:
          "border-border text-foreground [a]:hover:bg-muted [a]:hover:text-muted-foreground",
        ghost:
          "hover:bg-muted hover:text-muted-foreground dark:hover:bg-muted/50",
        link: "text-primary underline-offset-4 hover:underline",
        success:
          "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 [a]:hover:bg-emerald-500/20",
        warning:
          "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400 [a]:hover:bg-amber-500/20",
        info:
          "border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-400 [a]:hover:bg-sky-500/20",
        running:
          "border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-400 [a]:hover:bg-sky-500/20",
        completed:
          "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 [a]:hover:bg-emerald-500/20",
        failed:
          "border-rose-500/30 bg-rose-500/10 text-rose-600 dark:text-rose-400 [a]:hover:bg-rose-500/20",
      },
      size: {
        default: "",
        meta: "px-2 py-[2px] pb-[3px] font-mono text-[0.6875rem] leading-normal",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

const statusDotClassName: Record<string, string> = {
  running: "bg-sky-500",
  completed: "bg-emerald-500",
  failed: "bg-rose-500",
}

function Badge({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  children,
  ...props
}: React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "span"
  const dotClassName = !asChild && variant ? statusDotClassName[variant] : undefined

  if (asChild) {
    return (
      <Comp
        data-slot="badge"
        data-variant={variant}
        data-size={size}
        className={cn(badgeVariants({ variant, size }), className)}
        {...props}
      >
        {children}
      </Comp>
    )
  }

  return (
    <Comp
      data-slot="badge"
      data-variant={variant}
      data-size={size}
      className={cn(badgeVariants({ variant, size }), className)}
      {...props}
    >
      {dotClassName ? (
        <span
          data-slot="badge-dot"
          className={cn("size-1.5 rounded-full", dotClassName)}
          aria-hidden="true"
        />
      ) : null}
      {children}
    </Comp>
  )
}

export { Badge, badgeVariants }

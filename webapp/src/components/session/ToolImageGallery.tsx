import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { cn } from "@/lib/utils";
import { workspaceImageUrl } from "../../api";
import { Button } from "../ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "../ui/dialog";

export type ToolImage = { key: string; path: string };

export const TOOL_IMAGE_GALLERY_VISIBLE = 5;

export function ToolImageGallery({ images, className }: { images: ToolImage[]; className?: string }) {
  const [active, setActive] = useState(0);
  const [fullscreen, setFullscreen] = useState<number | null>(null);
  const thumbRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const count = images.length;
  const current = Math.min(active, Math.max(0, count - 1));

  const focusIndex = useCallback((index: number) => {
    const next = (index + count) % count;
    setActive(next);
    const el = thumbRefs.current[next];
    el?.focus();
    el?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }, [count]);

  const handleKeyDown = useCallback((event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      focusIndex(current + 1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      focusIndex(current - 1);
    }
  }, [current, focusIndex]);

  if (count === 0) return null;
  const scrollable = count > TOOL_IMAGE_GALLERY_VISIBLE;

  return (
    <div className={cn("flex min-w-0 flex-col gap-1", className)} data-tool-image-gallery>
      <div
        role="listbox"
        aria-label={`Inspected images (${count})`}
        aria-orientation="horizontal"
        className={cn("-mx-1 flex pb-1", scrollable && "snap-x overflow-x-auto")}
        onKeyDown={handleKeyDown}
      >
        {images.map((image, index) => (
          <div key={image.key} className="w-1/5 min-w-24 shrink-0 snap-start px-1">
          <button
            ref={(el) => { thumbRefs.current[index] = el; }}
            type="button"
            role="option"
            aria-selected={index === current}
            tabIndex={index === current ? 0 : -1}
            title={image.path}
            className={cn(
              "flex w-full flex-col gap-1 rounded-md border border-border bg-background p-1 text-left outline-none transition-colors hover:border-primary/40 focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/50",
              index === current && "border-primary/40",
            )}
            onFocus={() => setActive(index)}
            onClick={() => { setActive(index); setFullscreen(index); }}
          >
            <img
              src={workspaceImageUrl(image.path)}
              alt={image.path}
              loading="lazy"
              className="aspect-square w-full rounded-sm bg-muted object-cover"
            />
            <span className="block truncate text-xs text-muted-foreground">{baseName(image.path)}</span>
          </button>
          </div>
        ))}
      </div>
      {fullscreen !== null ? (
        <ImageLightbox
          images={images}
          index={fullscreen}
          onIndexChange={(next) => { setFullscreen(next); setActive(next); }}
          onClose={() => { setFullscreen(null); }}
        />
      ) : null}
    </div>
  );
}

function ImageLightbox({
  images,
  index,
  onIndexChange,
  onClose,
}: {
  images: ToolImage[];
  index: number;
  onIndexChange: (index: number) => void;
  onClose: () => void;
}) {
  const count = images.length;
  const image = images[index];
  const go = useCallback((delta: number) => onIndexChange((index + delta + count) % count), [count, index, onIndexChange]);

  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "ArrowRight") { event.preventDefault(); go(1); }
      else if (event.key === "ArrowLeft") { event.preventDefault(); go(-1); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go]);

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent size="fullscreen">
        <DialogTitle>{image.path}</DialogTitle>
        <DialogDescription>
          {count > 1 ? `Image ${index + 1} of ${count} · use ← → to navigate` : "Inspected image"}
        </DialogDescription>
        <div className="relative flex min-h-0 flex-1 items-center justify-center">
          <img src={workspaceImageUrl(image.path)} alt={image.path} className="max-h-full max-w-full object-contain" />
          {count > 1 ? (
            <>
              <Button type="button" variant="secondary" size="icon" className="absolute left-2" aria-label="Previous image" onClick={() => go(-1)}>
                <ChevronLeftIcon />
              </Button>
              <Button type="button" variant="secondary" size="icon" className="absolute right-2" aria-label="Next image" onClick={() => go(1)}>
                <ChevronRightIcon />
              </Button>
            </>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function baseName(value: string) {
  const parts = value.replace(/[\\/]+$/, "").split(/[\\/]/);
  return parts[parts.length - 1] || value;
}

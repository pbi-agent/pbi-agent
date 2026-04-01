import { useCallback, useEffect, useRef, useState } from "react";

const SCROLL_THRESHOLD = 80;

export function useAutoScroll(
  deps: unknown[],
  options?: {
    followOnChange?: boolean;
  },
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [showNewMessages, setShowNewMessages] = useState(false);
  const userScrolledRef = useRef(false);
  const rafRef = useRef<number>(0);
  const followOnChange = options?.followOnChange ?? true;

  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < SCROLL_THRESHOLD;
    userScrolledRef.current = !atBottom;
    if (atBottom) setShowNewMessages(false);
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => el.removeEventListener("scroll", handleScroll);
  }, [handleScroll]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    if (!followOnChange) return;
    if (!userScrolledRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(() => {
        el.scrollTo({ top: el.scrollHeight, behavior: "instant" });
      });
    } else {
      setShowNewMessages(true);
    }
  }, [followOnChange, ...deps]);

  useEffect(() => {
    return () => cancelAnimationFrame(rafRef.current);
  }, []);

  const scrollToBottom = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    userScrolledRef.current = false;
    setShowNewMessages(false);
  }, []);

  return { containerRef, showNewMessages, setShowNewMessages, scrollToBottom, userScrolledRef };
}

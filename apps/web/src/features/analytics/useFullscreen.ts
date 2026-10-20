import { useCallback, useEffect, useState, type RefObject } from "react";

/** Fullscreen state for one element; Esc or the browser UI also exit and are reflected here. */
export function useFullscreen(target: RefObject<HTMLElement | null>) {
  const isSupported = typeof document !== "undefined" && Boolean(document.fullscreenEnabled);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    const sync = () => setIsFullscreen(Boolean(target.current) && document.fullscreenElement === target.current);
    document.addEventListener("fullscreenchange", sync);
    return () => document.removeEventListener("fullscreenchange", sync);
  }, [target]);

  const toggle = useCallback(async () => {
    if (!isSupported || !target.current) return;
    if (document.fullscreenElement === target.current) await document.exitFullscreen();
    else await target.current.requestFullscreen();
  }, [isSupported, target]);

  return { isSupported, isFullscreen, toggle };
}

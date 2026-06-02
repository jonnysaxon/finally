"use client";

import { useEffect } from "react";
import { useTerminal } from "@/hooks/useTerminalStore";

export function ErrorToast() {
  const { lastError, clearError } = useTerminal();

  useEffect(() => {
    if (!lastError) return;
    const id = setTimeout(clearError, 4500);
    return () => clearTimeout(id);
  }, [lastError, clearError]);

  if (!lastError) return null;
  return (
    <div
      data-testid="error-toast"
      className="fixed bottom-5 left-1/2 z-50 -translate-x-1/2 animate-riseIn rounded-md border border-down/50 bg-panel px-4 py-2.5 text-data text-down shadow-glow"
      role="alert"
    >
      {lastError}
      <button
        type="button"
        onClick={clearError}
        className="ml-3 text-inkFaint hover:text-ink"
        aria-label="Dismiss"
      >
        ✕
      </button>
    </div>
  );
}

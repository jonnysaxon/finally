// The terminal's structural unit: a bordered, labelled surface. Every region
// of the workstation is a Panel so the whole screen reads as one instrument.

import type { ReactNode } from "react";

interface PanelProps {
  label: string;
  /** Optional right-aligned content in the header strip (e.g. a control). */
  accessory?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  testId?: string;
}

export function Panel({
  label,
  accessory,
  children,
  className = "",
  bodyClassName = "",
  testId,
}: PanelProps) {
  return (
    <section
      data-testid={testId}
      className={`flex min-h-0 flex-col overflow-hidden rounded-md border border-hairline bg-panel shadow-panel ${className}`}
    >
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-hairline bg-surface/60 px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="h-3 w-[2px] bg-amber/70" aria-hidden />
          <span className="panel-label">{label}</span>
        </div>
        {accessory}
      </header>
      <div className={`min-h-0 flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  );
}

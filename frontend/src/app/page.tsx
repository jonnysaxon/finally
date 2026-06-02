"use client";

import dynamic from "next/dynamic";

// The workstation owns an EventSource + Recharts (browser-only), so render it
// purely client-side. The static export still emits a valid index.html shell.
const Workstation = dynamic(
  () => import("@/components/Workstation").then((m) => m.Workstation),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-screen items-center justify-center text-data text-inkMute">
        <span className="font-display tracking-[0.3em] text-amber">
          FINALLY · BOOTING TERMINAL…
        </span>
      </div>
    ),
  },
);

export default function Page() {
  return <Workstation />;
}

"use client";

import AppShell from "./AppShell";
import DemoOverlay from "./DemoOverlay";
import { DemoProvider } from "../lib/demo";
import { StreamProvider } from "../lib/stream";

export default function Providers({ children }) {
  return (
    <StreamProvider>
      <DemoProvider>
        <AppShell>{children}</AppShell>
        <DemoOverlay />
      </DemoProvider>
    </StreamProvider>
  );
}

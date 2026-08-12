"use client";

import { MemoryView } from "@/components/MemoryView";
import { useWorkspace } from "@/components/WorkspaceProvider";

export default function MemoryPage() {
  const { memory } = useWorkspace();
  return <MemoryView entries={memory} />;
}

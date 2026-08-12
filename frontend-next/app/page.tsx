"use client";

import { HomeView } from "@/components/HomeView";
import { useWorkspace } from "@/components/WorkspaceProvider";
import { useRouter } from "next/navigation";

export default function HomePage() {
  const { docs, status, submit, upload } = useWorkspace();
  const router = useRouter();
  return (
    <HomeView
      docs={docs}
      status={status}
      onAsk={submit}
      onUpload={upload}
      onOpenLibrary={() => router.push("/library")}
    />
  );
}

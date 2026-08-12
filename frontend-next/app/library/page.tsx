"use client";

import { LibraryView } from "@/components/LibraryView";
import { useWorkspace } from "@/components/WorkspaceProvider";

export default function LibraryPage() {
  const { docs, uploading, upload, remove, openDoc } = useWorkspace();
  return (
    <LibraryView
      docs={docs}
      uploading={uploading}
      onUpload={upload}
      onDelete={remove}
      onOpen={openDoc}
    />
  );
}

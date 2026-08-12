"use client";

import { ChatView } from "@/components/ChatView";
import { useWorkspace } from "@/components/WorkspaceProvider";

export default function ChatPage() {
  const { scope, docs, exchanges, input, setInput, submit, busy, viewer, openSource, pickDoc } =
    useWorkspace();
  return (
    <ChatView
      scope={scope}
      docs={docs}
      exchanges={exchanges}
      input={input}
      onInput={setInput}
      onSubmit={submit}
      busy={busy}
      viewer={viewer}
      onOpenSource={openSource}
      onPickDoc={pickDoc}
    />
  );
}

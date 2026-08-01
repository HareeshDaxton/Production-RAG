"use client";

import { useState } from "react";
import { Menu } from "lucide-react";
import { ChatView } from "@/components/chat-view";
import { HistoryView } from "@/components/history-view";
import { Sidebar, type View } from "@/components/sidebar";
import { Button } from "@/components/ui/button";
import { useChat } from "@/hooks/use-chat";
import { useDocuments } from "@/hooks/use-documents";

export function AppShell() {
  const {
    conversations,
    active,
    hydrated,
    busy,
    send,
    regenerate,
    stop,
    newChat,
    deleteChat,
    selectChat,
    setFeedback,
    staged,
    scope,
    attach,
    detach,
  } = useChat();

  const {
    documents,
    system,
    uploading,
    uploadError,
    upload,
    remove: removeDocument,
  } = useDocuments();

  // Chips show only what is staged for the next message; once sent, the files
  // move onto that message's bubble. The sidebar still counts the whole corpus.
  const stagedDocuments = documents.filter((d) => staged.includes(d.source));

  /** Picked or dropped files ingest straight away, then stage for the next message. */
  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    attach(await upload(Array.from(files)));
  }

  async function removeAttachment(source: string) {
    await removeDocument(source); // index-wide delete
    detach(source);
  }

  const [view, setView] = useState<View>("chat");
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex h-dvh overflow-hidden">
      <Sidebar
        view={view}
        onView={setView}
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed((v) => !v)}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
        system={system}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile-only sidebar trigger; the desktop rail is always visible. */}
        <Button
          size="icon"
          onClick={() => setMobileOpen(true)}
          aria-label="Open sidebar"
          className="absolute left-3 top-4 z-20 md:hidden"
        >
          <Menu className="h-4 w-4" aria-hidden="true" />
        </Button>

        {view === "chat" ? (
          <ChatView
            conversation={active}
            busy={busy}
            ready={hydrated}
            onSend={send}
            onStop={stop}
            onRegenerate={regenerate}
            onFeedback={setFeedback}
            onNewChat={newChat}
            onFiles={handleFiles}
            documents={stagedDocuments}
            uploading={uploading}
            uploadError={uploadError}
            onRemoveDocument={removeAttachment}
            scope={scope}
          />
        ) : (
          <HistoryView
            conversations={conversations}
            onResume={(id) => {
              selectChat(id);
              setView("chat");
            }}
            onDelete={deleteChat}
          />
        )}
      </div>
    </div>
  );
}

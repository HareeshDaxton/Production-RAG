"use client";

import { useState } from "react";
import { Menu } from "lucide-react";
import { ChatView } from "@/components/chat-view";
import { HistoryView } from "@/components/history-view";
import { Sidebar, type View } from "@/components/sidebar";
import { UploadDialog } from "@/components/upload-dialog";
import { Button } from "@/components/ui/button";
import { useChat } from "@/hooks/use-chat";

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
    setActiveId,
    setFeedback,
  } = useChat();

  const [view, setView] = useState<View>("chat");
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);

  return (
    <div className="flex h-dvh overflow-hidden">
      <Sidebar
        view={view}
        onView={setView}
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed((v) => !v)}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
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
            onOpenUpload={() => setUploadOpen(true)}
          />
        ) : (
          <HistoryView
            conversations={conversations}
            onResume={(id) => {
              setActiveId(id);
              setView("chat");
            }}
            onDelete={deleteChat}
          />
        )}
      </div>

      <UploadDialog open={uploadOpen} onClose={() => setUploadOpen(false)} />
    </div>
  );
}

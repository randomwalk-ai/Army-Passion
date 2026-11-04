"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Conversation, { type Entry } from "@/components/Conversation";
import PromptBox from "@/components/PromptBox";
import Sidebar from "@/components/Sidebar";
import {
  addChatMessage,
  answerSuggestion,
  askQuestion,
  deleteChat,
  listChats,
  openChat,
  startChat,
  uploadSheet,
  type AskAnswer,
  type AskTurn,
  type ChatSummary,
  type SuggestionCard,
} from "@/lib/api";
import { classify } from "@/lib/files";

export default function Home() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  // Earlier questions in this chat, so a follow-up ("list them") can be
  // understood. Carries only what was typed and what the AI wrote back —
  // never the rows that came back. Cleared by "New chat".
  const history = useRef<AskTurn[]>([]);

  // Saved chats. Each conversation keeps a promise of its chat id, so saves
  // happen in order and the first answer creates the chat. "New chat" or
  // opening an old chat swaps in a fresh conversation, so a late save from
  // the previous one can never land in the wrong chat.
  const [recent, setRecent] = useState<ChatSummary[]>([]);
  const [activeChatId, setActiveChatId] = useState<number | null>(null);
  const conversation = useRef<{ chatId: Promise<number | null> }>({
    chatId: Promise.resolve(null),
  });

  const refreshRecent = useCallback(() => {
    listChats()
      .then(setRecent)
      // An empty list is fine; the chat itself still works.
      .catch(() => {});
  }, []);

  useEffect(() => {
    refreshRecent();
  }, [refreshRecent]);

  function save(question: string, answer: AskAnswer) {
    const current = conversation.current;
    current.chatId = current.chatId.then(async (id) => {
      try {
        const chat = id
          ? await addChatMessage(id, question, answer)
          : await startChat(question, answer);
        if (conversation.current === current) setActiveChatId(chat.id);
        refreshRecent();
        return chat.id;
      } catch {
        // Not saved, but the answer is still on screen; try again next time.
        return id;
      }
    });
  }

  function remember(question: string, answer: AskAnswer) {
    // An error is left out: there is nothing to follow up on.
    if (answer.kind === "error") return;
    history.current = [
      ...history.current,
      { question, title: answer.title, sql: answer.sql, reply: answer.message, tool: answer.tool },
    ].slice(-10);
  }

  function newChat() {
    setEntries([]);
    history.current = [];
    conversation.current = { chatId: Promise.resolve(null) };
    setActiveChatId(null);
    setSidebarOpen(false);
  }

  async function showChat(chatId: number) {
    setSidebarOpen(false);
    try {
      const chat = await openChat(chatId);
      history.current = [];
      const restored: Entry[] = [];
      for (const message of chat.messages) {
        restored.push({ id: crypto.randomUUID(), kind: "text", text: message.question });
        restored.push({ id: crypto.randomUUID(), kind: "answer", state: "ready", answer: message.answer });
        remember(message.question, message.answer);
      }
      setEntries(restored);
      conversation.current = { chatId: Promise.resolve(chat.id) };
      setActiveChatId(chat.id);
    } catch {
      refreshRecent(); // it may have been deleted meanwhile
    }
  }

  async function removeChat(chatId: number) {
    try {
      await deleteChat(chatId);
    } catch {
      // Already gone, or the server is down; the refresh shows the truth.
    }
    if (chatId === activeChatId) newChat();
    refreshRecent();
  }

  // Drag events fire for every child element, so count them instead of
  // toggling a flag — otherwise the overlay flickers as the pointer moves.
  const dragDepth = useRef(0);

  function update(id: string, changes: Partial<Extract<Entry, { kind: "file" }>>) {
    setEntries((prev) =>
      prev.map((entry) =>
        entry.id === id && entry.kind === "file" ? { ...entry, ...changes } : entry,
      ),
    );
  }

  function addFiles(files: FileList) {
    for (const file of Array.from(files)) {
      const id = crypto.randomUUID();
      const fileKind = classify(file);

      setEntries((prev) => [
        ...prev,
        {
          id,
          kind: "file",
          name: file.name,
          size: file.size,
          fileKind,
          state: fileKind === "excel" ? "reading" : undefined,
          // Audio and documents are uploaded by their own components, which need the file.
          file: fileKind === "audio" || fileKind === "document" ? file : undefined,
        },
      ]);

      if (fileKind === "excel") {
        uploadSheet(file)
          .then((upload) => update(id, { state: "ready", upload }))
          .catch((error: unknown) =>
            update(id, {
              state: "failed",
              error:
                error instanceof Error
                  ? error.message
                  : "I could not reach the server. Is the backend running?",
            }),
          );
      }
    }
  }


  function setAnswer(id: string, changes: Partial<Extract<Entry, { kind: "answer" }>>) {
    setEntries((prev) =>
      prev.map((entry) =>
        entry.id === id && entry.kind === "answer" ? { ...entry, ...changes } : entry,
      ),
    );
  }

  /** Show the question, then fill in its answer when it arrives. */
  function ask(text: string, fetchAnswer: () => Promise<AskAnswer>) {
    const answerId = crypto.randomUUID();
    setEntries((prev) => [
      ...prev,
      { id: crypto.randomUUID(), kind: "text", text },
      { id: answerId, kind: "answer", state: "thinking" },
    ]);
    fetchAnswer()
      .then((answer) => {
        setAnswer(answerId, { state: "ready", answer });
        // Remembered so a follow-up ("show their phones") makes sense.
        remember(text, answer);
        save(text, answer);
      })
      .catch((error: unknown) =>
        setAnswer(answerId, {
          state: "failed",
          error:
            error instanceof Error
              ? error.message
              : "I could not reach the server. Is the backend running?",
        }),
      );
  }

  function addText(text: string) {
    ask(text, () => askQuestion(text, history.current));
  }

  function pickSuggestion(card: SuggestionCard) {
    ask(card.text, () => answerSuggestion(card.key));
  }

  return (
    <div className="app-height flex overflow-hidden bg-bg">
      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewChat={newChat}
        recent={recent}
        activeChatId={activeChatId}
        onOpenChat={showChat}
        onDeleteChat={removeChat}
      />

      <main
        className="relative flex min-w-0 flex-1 flex-col"
        onDragEnter={(e) => {
          e.preventDefault();
          dragDepth.current += 1;
          if (e.dataTransfer.types.includes("Files")) setDragging(true);
        }}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={(e) => {
          e.preventDefault();
          dragDepth.current -= 1;
          if (dragDepth.current <= 0) setDragging(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          dragDepth.current = 0;
          setDragging(false);
          if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files);
        }}
      >
        <header className="pt-safe flex min-h-14 shrink-0 items-center gap-2 px-3 md:px-5">
          <button
            onClick={() => setSidebarOpen(true)}
            aria-label="Open menu"
            className="flex h-11 w-11 items-center justify-center rounded-xl text-muted hover:bg-surface-2 hover:text-text md:hidden"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="M4 7h16M4 12h16M4 17h16"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </button>
          <span className="text-base font-medium text-muted md:hidden">Army Passion</span>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto">
          <Conversation
            entries={entries}
            onMappingConfirmed={(id) => update(id, { mappingConfirmed: true })}
            onSuggestion={pickSuggestion}
            onAsk={addText}
          />
        </div>

        <PromptBox onFiles={addFiles} onSend={addText} />

        {dragging && (
          <div className="pointer-events-none absolute inset-3 z-20 flex items-center justify-center">
            <div
              className="flex h-full w-full items-center justify-center rounded-3xl border-2
                border-dashed border-accent bg-accent-soft/90"
            >
              <p className="text-xl font-medium text-text">
                Drop the file here
              </p>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

// Chat sessions + the streaming request live ABOVE the routed pages so an
// in-progress answer keeps streaming (and the "…düşünüyor" indicator stays
// correct) even when the user navigates to another page and the ChatTerminal
// component unmounts/remounts.

export interface Line {
  role: "user" | "agent" | "system";
  text: string;
  // Marks special system lines so the UI can render distinct blocks:
  //   "tool"     → a tool-call card (e.g. add_task / deep_research)
  //   "research" → a live Deep Research progress panel (transient)
  kind?: "tool" | "research";
  // Epoch ms when the message was sent; used by Günüm to group/deep-link a day.
  ts?: number;
}

export interface ChatSession {
  id: string;
  title: string;
  updatedAt: number;
  lines: Line[];
}

export interface SendOptions {
  message: string;
  attachmentIds?: string[];
  model?: string;
  systemPrompt?: string;
  mentions?: { type: string; id: string }[];
  historyOverride?: Line[];
}

interface ChatState {
  sessions: ChatSession[];
  activeSessionId: string;
  activeSession: ChatSession;
  lines: Line[];
  busy: boolean;
  setActiveSessionId: (id: string) => void;
  updateActiveSessionLines: (lines: Line[]) => void;
  newChat: () => void;
  deleteChat: (id: string) => void;
  send: (opts: SendOptions) => Promise<void>;
  abort: () => void;
}

const ChatCtx = createContext<ChatState | null>(null);

function generateId() {
  return Math.random().toString(36).substring(2, 9);
}

function initialSessions(): ChatSession[] {
  const saved = localStorage.getItem("jarvis_chat_sessions");
  if (saved) {
    try {
      return JSON.parse(saved);
    } catch {
      /* ignore */
    }
  }
  const oldSaved = localStorage.getItem("chat_history");
  const defaultLines: Line[] = oldSaved
    ? JSON.parse(oldSaved)
    : [
        {
          role: "system",
          text: "Athena hazır. Soru sor, görev/PDF/antrenman iste, ya da /yardim yaz.",
        },
      ];
  return [
    {
      id: generateId(),
      title: "Yeni Sohbet",
      updatedAt: Date.now(),
      lines: defaultLines,
    },
  ];
}

export function ChatProvider({ children }: { children: ReactNode }) {
  const [sessions, setSessions] = useState<ChatSession[]>(initialSessions);
  const [activeSessionId, setActiveSessionId] = useState<string>(() => {
    const savedId = localStorage.getItem("jarvis_active_session");
    const init = initialSessions();
    if (savedId && init.some((s) => s.id === savedId)) return savedId;
    return init[0]?.id || "";
  });
  const [busy, setBusy] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const streamActiveRef = useRef(false);

  useEffect(() => {
    localStorage.setItem("jarvis_chat_sessions", JSON.stringify(sessions));
    localStorage.setItem("jarvis_active_session", activeSessionId);
  }, [sessions, activeSessionId]);

  const activeSession =
    sessions.find((s) => s.id === activeSessionId) || sessions[0];
  const lines = activeSession?.lines || [];

  // Update lines of whichever session is active *at call time*. We capture the
  // id at send() start so streaming writes to the right session even if the user
  // switches sessions mid-stream.
  const updateLinesOf = useCallback((sessionId: string, newLines: Line[]) => {
    setSessions((prev) =>
      prev.map((s) => {
        if (s.id !== sessionId) return s;
        const title =
          newLines.length > 1 && newLines[1].role === "user"
            ? newLines[1].text.substring(0, 30) + "..."
            : s.title;
        return { ...s, lines: newLines, title, updatedAt: Date.now() };
      })
    );
  }, []);

  const updateActiveSessionLines = useCallback(
    (newLines: Line[]) => updateLinesOf(activeSessionId, newLines),
    [activeSessionId, updateLinesOf]
  );

  const newChat = useCallback(() => {
    const s: ChatSession = {
      id: generateId(),
      title: "Yeni Sohbet",
      updatedAt: Date.now(),
      lines: [
        {
          role: "system",
          text: "Athena hazır. Yeni sohbete hoş geldiniz.",
        },
      ],
    };
    setSessions((prev) => [s, ...prev]);
    setActiveSessionId(s.id);
  }, []);

  const deleteChat = useCallback(
    (id: string) => {
      setSessions((prev) => {
        const remaining = prev.filter((s) => s.id !== id);
        if (remaining.length === 0) {
          const newS: ChatSession = {
            id: generateId(),
            title: "Yeni Sohbet",
            updatedAt: Date.now(),
            lines: [{ role: "system", text: "Athena hazır." }],
          };
          setActiveSessionId(newS.id);
          return [newS];
        }
        if (activeSessionId === id) setActiveSessionId(remaining[0].id);
        return remaining;
      });
    },
    [activeSessionId]
  );

  const abort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const send = useCallback(
    async (opts: SendOptions) => {
      const message = opts.message.trim();
      const ids = opts.attachmentIds ?? [];
      if ((!message && ids.length === 0) || streamActiveRef.current) return;

      const sessionId = activeSessionId;
      const currentSession = sessions.find((s) => s.id === sessionId);
      const baseLines = opts.historyOverride || currentSession?.lines || [];
      // Timestamp the turn so the Günüm page can group a day's conversation and
      // deep-link to it. (Older, untimestamped messages stay unlinkable.)
      const turnTs = Date.now();
      const newLines: Line[] = [
        ...baseLines,
        {
          role: "user",
          text: message + (ids.length ? ` 📎${ids.length}` : ""),
          ts: turnTs,
        },
      ];
      updateLinesOf(sessionId, newLines);

      setBusy(true);
      streamActiveRef.current = true;
      let currentAgentMessage = "";
      // Tool-call cards persist with the turn; the research panel is transient.
      const toolNotes: Line[] = [];
      let researchStatus: Line | null = null;

      const renderStreaming = () => {
        const out: Line[] = [...newLines, ...toolNotes];
        if (currentAgentMessage) out.push({ role: "agent", text: currentAgentMessage, ts: turnTs });
        if (researchStatus) out.push(researchStatus);
        updateLinesOf(sessionId, out);
      };

      const abortController = new AbortController();
      abortRef.current = abortController;

      try {
        const { API_URL } = await import("./api");
        const res = await fetch(`${API_URL}/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message,
            attachment_ids: ids,
            model: opts.model,
            // Backend expects list[dict[str, str]]; strip non-string fields
            // (ts is a number, kind is optional) or Pydantic rejects with 422.
            history: baseLines
              .slice(-10)
              .map((l) => ({ role: l.role, text: l.text })),
            system_prompt: opts.systemPrompt,
            mentions: opts.mentions ?? [],
          }),
          signal: abortController.signal,
        });
        if (!res.ok || !res.body) throw new Error(`chat ${res.status}`);
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        for (;;) {
          const { value, done } = await reader.read();
          if (done) {
            // Persist tool-call cards with the turn; drop the transient research
            // progress panel. Keep the final agent message last.
            const finalLines: Line[] = [...newLines, ...toolNotes];
            if (currentAgentMessage) {
              finalLines.push({ role: "agent", text: currentAgentMessage, ts: turnTs });
            }
            if (toolNotes.length || currentAgentMessage) {
              updateLinesOf(sessionId, finalLines);
            }
            break;
          }
          buffer += decoder.decode(value, { stream: true });
          const frames = buffer.split("\n\n");
          buffer = frames.pop() ?? "";

          let shouldUpdate = false;
          for (const frame of frames) {
            const line = frame.trim();
            if (!line.startsWith("data:")) continue;
            try {
              const evt = JSON.parse(line.slice(5).trim());
              // Token-level stream from chat_node (1C) + whole messages from
              // tool nodes both append to the current agent bubble.
              if (evt.type === "delta" || evt.type === "message") {
                currentAgentMessage += String(evt.content ?? "");
                shouldUpdate = true;
              } else if (evt.type === "tool_start" || evt.type === "tool") {
                const tool = String(evt.tool ?? evt.active_tool ?? "");
                // deep_research gets a live panel instead of a static card.
                if (tool && tool !== "deep_research" &&
                    !toolNotes.some((t) => t.text === tool)) {
                  toolNotes.push({ role: "system", kind: "tool", text: tool });
                }
                shouldUpdate = true;
              } else if (evt.type === "research_progress") {
                const phase = String(evt.phase ?? "");
                const round = evt.round ? ` · tur ${evt.round}` : "";
                const sources = evt.total_sources
                  ? ` · ${evt.total_sources} kaynak`
                  : "";
                researchStatus = {
                  role: "system",
                  kind: "research",
                  text: `${phase}${round}${sources}`,
                };
                shouldUpdate = true;
              } else if (evt.type === "error") {
                toolNotes.push({ role: "system", text: `error: ${String(evt.error)}` });
                shouldUpdate = true;
              }
            } catch {
              /* ignore malformed frame */
            }
          }
          if (shouldUpdate) renderStreaming();
        }
      } catch (e) {
        if ((e as Error).name === "AbortError") {
          if (currentAgentMessage) {
            updateLinesOf(sessionId, [
              ...newLines,
              { role: "agent", text: currentAgentMessage, ts: turnTs },
            ]);
          }
        } else {
          updateLinesOf(sessionId, [
            ...newLines,
            { role: "system", text: `error: ${(e as Error).message}` },
          ]);
        }
      } finally {
        streamActiveRef.current = false;
        abortRef.current = null;
        setBusy(false);
      }
    },
    [activeSessionId, sessions, updateLinesOf]
  );

  return (
    <ChatCtx.Provider
      value={{
        sessions,
        activeSessionId,
        activeSession,
        lines,
        busy,
        setActiveSessionId,
        updateActiveSessionLines,
        newChat,
        deleteChat,
        send,
        abort,
      }}
    >
      {children}
    </ChatCtx.Provider>
  );
}

export function useChat(): ChatState {
  const ctx = useContext(ChatCtx);
  if (!ctx) throw new Error("useChat must be used within a ChatProvider");
  return ctx;
}

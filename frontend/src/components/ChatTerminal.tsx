import { useRef, useState, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  uploadChatFile,
  getModels,
  getTags,
  type ChatAttachment,
  type Task,
  type Workout,
} from "../api";
import personasData from "../data/personas.json";
import NotionEditor from "./NotionEditor";
import Modal from "./Modal";
import { useChat, type Line } from "../ChatContext";

// Render assistant replies as markdown (headings, lists, code, tables, links)
// styled for the dark theme. User/system lines stay plain pre-wrapped text.
function AgentMarkdown({ text }: { text: string }) {
  return (
    <div className="prose prose-invert prose-sm max-w-none break-words font-sans prose-pre:my-2">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: (props) => <a {...props} target="_blank" rel="noreferrer" />,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

const COMMANDS = [
  ["/görev", "görev ekle"],
  ["/agörev", "akademik görev ekle"],
  ["/altgörev", "otomatik alt görevler"],
  ["/altakademik", "otomatik akademik alt görevler"],
  ["/fikir", "fikir çıkar (örn: /fikir(3))"],
  ["/antrenman", "tek antrenman ekle"],
  ["/seans", "akademik seans ekle (@görev_adi)"],
  ["/plan", "plan içe aktar"],
  ["/aralık", "aralıklı tekrar görevi"],
  ["/yardim", "komutlar"],
];

// Replace a @mention token with the chosen display label in the input.
function applyMention(
  input: string,
  trigger: "@" | "#",
  label: string,
  isModel: boolean
) {
  const parts = input.split(trigger);
  parts.pop();
  return parts.join(trigger) + trigger + label + " ";
}

export default function ChatTerminal() {
  // Session + streaming state live in ChatProvider (above the router) so an
  // in-progress answer survives navigating to another page and back.
  const {
    sessions,
    activeSessionId,
    activeSession,
    lines,
    busy,
    setActiveSessionId,
    updateActiveSessionLines,
    newChat: handleNewChat,
    deleteChat: handleDeleteChat,
    send,
  } = useChat();

  // Chat State
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [allTags, setAllTags] = useState<string[]>([]);
  // User-created tags persist locally so newly added #tags reappear in the dropdown.
  const [customTags, setCustomTags] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem("jarvis_custom_tags") || "[]");
    } catch {
      return [];
    }
  });
  const addCustomTag = useCallback((tag: string) => {
    const t = tag.trim();
    if (!t) return;
    setCustomTags((prev) => {
      if (prev.some((x) => x.toLowerCase() === t.toLowerCase())) return prev;
      const next = [...prev, t];
      localStorage.setItem("jarvis_custom_tags", JSON.stringify(next));
      return next;
    });
  }, []);
  const [tasksCache, setTasksCache] = useState<Task[]>([]);
  const [workoutsCache, setWorkoutsCache] = useState<Workout[]>([]);
  // Mentions the user explicitly picked from the dropdown; sent to the backend so
  // it resolves the real referenced content (not just a fuzzy label match).
  const [pickedMentions, setPickedMentions] = useState<
    { type: string; id: string; label: string }[]
  >([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Expand modal for message composition
  const [showExpand, setShowExpand] = useState(false);

  useEffect(() => {
    getModels().then(setAvailableModels).catch(() => {});
    getTags().then(setAllTags).catch(() => {});
  }, []);

  // Extras State
  const [searchQuery, setSearchQuery] = useState("");
  const [showSearch, setShowSearch] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [activePersona, setActivePersona] = useState(personasData[0].id);

  // Auto-scroll to the newest line whenever the active conversation changes
  // (covers both local sends and streaming updates that arrive from the provider).
  useEffect(() => {
    requestAnimationFrame(() =>
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
    );
  }, [lines]);

  function push(line: Line) {
    updateActiveSessionLines([...lines, line]);
  }

  async function attach(file: File) {
    push({ role: "system", text: `↑ ${file.name} yükleniyor…` });
    try {
      const a = await uploadChatFile(file);
      setAttachments((prev) => [...prev, a]);
      push({ role: "system", text: `✓ ${a.name} eklendi (${a.chars} karakter)` });
    } catch (e) {
      push({ role: "system", text: `dosya hatası: ${(e as Error).message}` });
    }
  }

  const color = {
    user: "text-primary-300",
    agent: "text-primary-300",
    system: "text-zinc-500",
  } as const;

  const cmdMatch = input.match(/(?:^|\s)(\/[a-zğüşıöçA-ZĞÜŞİÖÇ]*)$/);
  const showHint = cmdMatch !== null;
  const activeCommandKey = cmdMatch ? cmdMatch[1].toLowerCase() : "";
  const isDefaultCmd = input.startsWith("/default ");
  const mentionMatch = input.match(/@([\w\s.-]*)$/);
  const showMentions = mentionMatch !== null;
  const tagMatch = input.match(/#([\w\s-]*)$/);
  const showTags = tagMatch !== null;

  const [mentionOptions, setMentionOptions] = useState<
    { id: string; type: string; label: string }[]
  >([]);

  const refreshMentionData = useCallback(async () => {
    const { getTasks, getWorkouts, getIdeas } = await import("../api");
    const [tasks, workouts, ideas] = await Promise.all([
      getTasks(),
      getWorkouts(),
      getIdeas().catch(() => []),
    ]);
    setTasksCache(tasks);
    setWorkoutsCache(workouts);
    return { tasks, workouts, ideas };
  }, []);

  useEffect(() => {
    // Warm caches so dropdowns resolve quickly.
    refreshMentionData().catch(() => {});
  }, [refreshMentionData]);

  useEffect(() => {
    if (showMentions) {
      const q = mentionMatch[1].trim().toLowerCase();
      refreshMentionData()
        .then(({ tasks, workouts, ideas }) => {
          const models = availableModels.map((m) => ({
            id: m,
            type: "model",
            label: m,
          }));
          // Include subtasks in the mentionable task pool.
          const allTasks = [...tasks];
          const tOptions = allTasks
            .filter((t) => t.title.toLowerCase().includes(q))
            .map((t) => ({ id: t.id, type: t.parent_id ? "alt görev" : "görev", label: t.title }));
          const wOptions = workouts
            .filter(
              (w) =>
                (w.title || "").toLowerCase().includes(q) || w.date.includes(q)
            )
            .map((w) => ({
              id: w.id,
              type: "antrenman",
              label: w.title || w.date,
            }));
          const iOptions = ideas
            .filter((i) => (i.title || "").toLowerCase().includes(q))
            .map((i) => ({
              id: i.id,
              type: "fikir",
              label: i.title || "Başlıksız fikir",
            }));
          const mOptions = models.filter((m) => m.label.toLowerCase().includes(q));
          setMentionOptions(
            [...mOptions, ...tOptions, ...wOptions, ...iOptions].slice(0, 12)
          );
        })
        .catch(() => {});
    } else if (showTags) {
      const q = tagMatch[1].trim().toLowerCase();
      const defaultTags = ["İş", "Günlük Yazma", "Okuma", "Kişisel gelişim", "Genel"];
      const mergedTags = Array.from(
        new Set([...defaultTags, ...allTags, ...customTags])
      );
      const opts = mergedTags
        .filter((t) => t.toLowerCase().includes(q))
        .map((t) => ({ id: t, type: "etiket", label: t }));
      if (q && !opts.some((o) => o.label.toLowerCase() === q)) {
        opts.push({ id: q, type: "yeni etiket", label: tagMatch[1].trim() });
      }
      setMentionOptions(opts);
    }
  }, [input, showMentions, showTags, availableModels, allTags, customTags, refreshMentionData, mentionMatch, tagMatch]);

  async function handleSend(customMessage?: string, historyOverride?: Line[]) {
    const message = customMessage !== undefined ? customMessage : input.trim();
    if ((!message && attachments.length === 0) || busy) return;

    // "/default @model" sets the default model rather than sending a message.
    if (message.startsWith("/default ")) {
      const parts = message.split(" ");
      if (parts.length > 1 && parts[1].startsWith("@")) {
        const modelName = parts[1].slice(1).trim();
        localStorage.setItem("defaultModel", modelName);
        push({ role: "system", text: `Varsayılan model ayarlandı: ${modelName}` });
        if (customMessage === undefined) setInput("");
        return;
      }
    }

    const ids = attachments.map((a) => a.id);

    let modelOverride = localStorage.getItem("defaultModel") || undefined;
    const modelMatch = message.match(/@([\w.-]+)\b/);
    if (modelMatch && availableModels.map((m) => m.toLowerCase()).includes(modelMatch[1].toLowerCase())) {
      modelOverride = availableModels.find(
        (m) => m.toLowerCase() === modelMatch[1].toLowerCase()
      );
    }

    // Only send mentions whose label still appears in the message (the user may
    // have deleted a token after picking it).
    const activeMentions = pickedMentions
      .filter((m) => message.includes(m.label))
      .map((m) => ({ type: m.type, id: m.id }));

    const persona = personasData.find((p) => p.id === activePersona);
    const systemPrompt = persona && persona.prompt ? persona.prompt : undefined;

    if (customMessage === undefined) setInput("");
    setAttachments([]);
    setPickedMentions([]);

    // Streaming runs in the ChatProvider, so navigating away no longer drops the
    // in-progress answer.
    await send({
      message,
      attachmentIds: ids,
      model: modelOverride,
      systemPrompt,
      mentions: activeMentions,
      historyOverride,
    });
  }

  const handleEdit = (index: number) => {
    if (busy) return;
    const msg = lines[index];
    if (msg.role !== "user") return;
    // Set input to message text (remove attachment hints if any)
    setInput(msg.text.replace(/ 📎\d+$/, ""));
    // Cut history up to this point
    updateActiveSessionLines(lines.slice(0, index));
  };

  const handleRegenerate = (index: number) => {
    if (busy) return;
    // Find the last user message before this agent message
    let lastUserIdx = -1;
    for (let i = index - 1; i >= 0; i--) {
      if (lines[i].role === "user") {
        lastUserIdx = i;
        break;
      }
    }
    if (lastUserIdx === -1) return;
    const userMsg = lines[lastUserIdx].text.replace(/ 📎\d+$/, "");
    const historyOverride = lines.slice(0, lastUserIdx);
    handleSend(userMsg, historyOverride);
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  const exportChat = () => {
    const text = lines
      .map((l) => `${l.role.toUpperCase()}:\n${l.text}`)
      .join("\n\n---\n\n");
    const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `chat-${activeSession.id}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const filteredLines = searchQuery
    ? lines.filter((l) =>
        l.text.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : lines;

  const isTextareaSend = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  const CommandHints = () => (
    <div className="flex flex-wrap gap-1.5 border-t border-line px-3 py-2 text-xs bg-surface-2">
      {COMMANDS.filter(([c]) => c.toLowerCase().startsWith(activeCommandKey)).map(
        ([c, d]) => (
          <button
            key={c}
            onClick={() => {
              const prefix = input.substring(0, cmdMatch!.index);
              const space = (cmdMatch!.index! > 0 && !prefix.endsWith(" ")) ? " " : "";
              setInput(prefix + space + c + " ");
            }}
            className="rounded border border-line-strong px-2 py-0.5 text-zinc-400 hover:border-primary-500 hover:text-primary-300"
          >
            {c} <span className="text-zinc-600">{d}</span>
          </button>
        )
      )}
    </div>
  );

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-line bg-black/60 shadow-lg shadow-black/20 relative">
      {/* HEADER */}
      <div className="flex items-center justify-between border-b border-line bg-elevated/60 px-4 py-2.5">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="text-zinc-400 hover:text-zinc-200"
            title="Geçmiş Sohbetler"
          >
            ☰
          </button>
          <span className="text-xs font-semibold uppercase tracking-wider text-zinc-300">
            {activeSession.title}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={activePersona}
            onChange={(e) => setActivePersona(e.target.value)}
            className="bg-zinc-800 text-zinc-300 text-xs rounded border border-line-strong px-2 py-1 outline-none"
            title="Sistem Promptu Seçici"
          >
            {personasData.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <button
            onClick={() => setShowSearch(!showSearch)}
            className="text-zinc-400 hover:text-zinc-200 text-sm"
            title="Chat İçi Arama"
          >
            🔍
          </button>
          <button
            onClick={exportChat}
            className="text-zinc-400 hover:text-zinc-200 text-sm"
            title="Dışa Aktar (Markdown)"
          >
            📥
          </button>
          <button
            onClick={handleNewChat}
            className="text-zinc-400 hover:text-primary-400 text-sm font-medium ml-2"
            title="Yeni Sohbet"
          >
            ＋ Yeni
          </button>
        </div>
      </div>

      {/* SEARCH BAR */}
      {showSearch && (
        <div className="border-b border-line bg-surface-2 p-2 flex gap-2">
          <input
            autoFocus
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Mesajlarda ara..."
            className="flex-1 rounded border border-line-strong bg-elevated px-2 py-1 text-sm text-zinc-200 outline-none focus:border-primary-500"
          />
          <button
            onClick={() => {
              setShowSearch(false);
              setSearchQuery("");
            }}
            className="text-zinc-500 hover:text-zinc-300 px-2"
          >
            Kapat
          </button>
        </div>
      )}

      {/* HISTORY DRAWER */}
      {showHistory && (
        <div className="absolute top-[45px] left-0 bottom-0 w-64 bg-surface-2 border-r border-line z-10 flex flex-col">
          <div className="p-3 border-b border-line flex justify-between items-center">
            <span className="text-sm font-medium text-zinc-200">Sohbetler</span>
            <button
              onClick={() => setShowHistory(false)}
              className="text-zinc-500 hover:text-zinc-300"
            >
              ×
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {sessions.map((s) => (
              <div
                key={s.id}
                className={`flex items-center justify-between p-2 rounded cursor-pointer ${
                  activeSessionId === s.id
                    ? "bg-zinc-800 text-zinc-100"
                    : "text-zinc-400 hover:bg-zinc-800/50"
                }`}
                onClick={() => {
                  setActiveSessionId(s.id);
                  setShowHistory(false);
                }}
              >
                <span className="text-sm truncate flex-1">{s.title}</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteChat(s.id);
                  }}
                  className="text-rose-500/50 hover:text-rose-400 ml-2"
                  title="Sil"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div
        ref={scrollRef}
        className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4 font-mono text-sm"
      >
        {filteredLines.map((l, i) => (
          <div
            key={i}
            className={`group flex flex-col ${
              l.role === "user" ? "items-end" : "items-start"
            }`}
          >
            <div
              className={`relative max-w-[85%] rounded-lg px-4 py-2 ${
                l.role === "user"
                  ? "bg-zinc-800 text-primary-200"
                  : l.role === "agent"
                  ? "bg-elevated text-primary-200 border border-line"
                  : "bg-transparent text-zinc-500"
              }`}
            >
              {l.role === "system" && <span className="select-none mr-2">#</span>}
              {l.role === "agent" ? (
                <AgentMarkdown text={l.text} />
              ) : (
                <span className="whitespace-pre-wrap">{l.text}</span>
              )}

              {/* ACTION BUTTONS (Hover) */}
              {l.role !== "system" && !searchQuery && (
                <div
                  className={`absolute top-0 flex gap-1 bg-elevated border border-line-strong rounded p-0.5 opacity-0 transition-opacity group-hover:opacity-100 ${
                    l.role === "user" ? "-left-16" : "-right-16"
                  }`}
                >
                  <button
                    onClick={() => copyToClipboard(l.text)}
                    className="text-zinc-400 hover:text-zinc-200 px-1"
                    title="Kopyala"
                  >
                    📋
                  </button>
                  {l.role === "user" && (
                    <button
                      onClick={() => handleEdit(i)}
                      className="text-zinc-400 hover:text-primary-300 px-1"
                      title="Düzenle"
                    >
                      ✏️
                    </button>
                  )}
                  {l.role === "agent" && (
                    <button
                      onClick={() => handleRegenerate(i)}
                      className="text-zinc-400 hover:text-primary-300 px-1"
                      title="Yeniden Üret"
                    >
                      🔄
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && (
          <div className="text-zinc-600 ml-4 animate-pulse">…düşünüyor</div>
        )}
        {searchQuery && filteredLines.length === 0 && (
          <div className="text-zinc-500 text-center mt-4">Sonuç bulunamadı.</div>
        )}
      </div>

      {showHint && !isDefaultCmd && !showExpand && <CommandHints />}

      {(showMentions || showTags) && mentionOptions.length > 0 && (
        <div className="flex flex-col gap-1 border-t border-line px-3 py-2 text-xs max-h-40 overflow-y-auto bg-elevated">
          {mentionOptions.map((opt) => (
            <button
              key={opt.id + opt.type}
              onClick={() => {
                if (showMentions) {
                  setPickedMentions((prev) => [
                    ...prev.filter((p) => p.id !== opt.id),
                    { type: opt.type, id: opt.id, label: opt.label },
                  ]);
                  setInput(applyMention(input, "@", opt.label, opt.type === "model"));
                } else if (showTags) {
                  addCustomTag(opt.label);
                  setPickedMentions((prev) => [
                    ...prev.filter((p) => p.id !== opt.id),
                    { type: "etiket", id: opt.label, label: opt.label },
                  ]);
                  setInput(applyMention(input, "#", opt.label, false));
                }
              }}
              className="text-left rounded px-2 py-1 text-zinc-300 hover:bg-zinc-800"
            >
              <span className="text-zinc-500 mr-2">[{opt.type}]</span> {opt.label}
            </button>
          ))}
        </div>
      )}

      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-1.5 border-t border-line px-3 py-2 bg-surface-2">
          {attachments.map((a) => (
            <span
              key={a.id}
              className="inline-flex items-center gap-1 rounded border border-primary-500/40 bg-primary-500/10 px-2 py-0.5 text-xs text-primary-300"
            >
              📎 {a.name}
              <button
                onClick={() =>
                  setAttachments((p) => p.filter((x) => x.id !== a.id))
                }
                className="text-primary-400/70 hover:text-primary-200"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="flex gap-2 border-t border-line p-3 bg-surface-2/60">
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,image/*,.md,.markdown,.txt,.json"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void attach(f);
            e.target.value = "";
          }}
        />
        <button
          onClick={() => fileRef.current?.click()}
          title="Dosya ekle (PDF/görüntü/.md/.json)"
          className="rounded-lg border border-line-strong px-3 py-2 text-sm text-zinc-300 hover:border-zinc-500 bg-elevated"
        >
          📎
        </button>
        <textarea
          value={input}
          rows={1}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={isTextareaSend}
          placeholder="Mesaj yaz… ('/' ile komutlar, '@' ile bahset)"
          className="flex-1 rounded-lg border border-line-strong bg-elevated px-3 py-2 font-mono text-sm text-zinc-100 outline-none focus:border-primary-500 resize-none min-h-[2.5rem] max-h-[8rem]"
        />
        <button
          onClick={() => setShowExpand(true)}
          title="Mesajı genişlet"
          className="rounded-lg border border-line-strong px-3 py-2 text-sm text-zinc-400 hover:text-zinc-200 hover:border-zinc-500 bg-elevated"
        >
          ⛶
        </button>
        <button
          onClick={() => void handleSend()}
          disabled={busy}
          className="rounded-lg bg-primary-500/90 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-primary-400 disabled:opacity-50 transition-colors"
        >
          Gönder
        </button>
      </div>

      {/* Expand modal for message input */}
      {showExpand && (
        <Modal
          open={showExpand}
          onClose={() => setShowExpand(false)}
          title="Mesajı düzenle"
          widthClass="max-w-3xl"
        >
          <div className="flex h-[70vh] flex-col gap-3">
            <div className="min-h-0 flex-1 flex flex-col overflow-hidden rounded-lg border border-line-strong">
              <div className="flex-1 min-h-0 overflow-y-auto">
                <NotionEditor
                  key="expand-input"
                  initialContent={input}
                  onChange={(html) => {
                    // Store minimal plain-text representation back to the textarea.
                    const tmp = document.createElement("div");
                    tmp.innerHTML = html;
                    const text = (tmp.textContent || tmp.innerText || "").trim();
                    setInput(text);
                  }}
                />
              </div>
              {showHint && !isDefaultCmd && <CommandHints />}
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowExpand(false)}
                className="rounded-lg border border-line-strong px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800"
              >
                Kapat
              </button>
              <button
                onClick={() => {
                  setShowExpand(false);
                  void handleSend();
                }}
                className="rounded-lg bg-primary-500/90 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-primary-400"
              >
                Gönder
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

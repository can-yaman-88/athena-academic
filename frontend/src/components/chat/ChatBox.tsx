import { useRef, useState, useEffect, useCallback } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  uploadChatFile,
  getModels,
  getTags,
  type ChatAttachment,
  type Task,
} from "../../api";
import personasData from "../../data/personas.json";
import NotionEditor from "../NotionEditor";
import Modal from "../Modal";
import { useChat, type Line } from "../../ChatContext";
import ChatMessage from "./ChatMessage";
import ChatInput from "./ChatInput";

const COMMANDS = [
  ["/görev", "görev ekle"],
  ["/agörev", "akademik görev ekle"],
  ["/altgörev", "otomatik alt görevler"],
  ["/altakademik", "otomatik akademik alt görevler"],
  ["/fikir", "fikir çıkar (örn: /fikir(3))"],
  ["/arastir", "derin web araştırması"],
  ["/seans", "akademik seans ekle (@görev_adi)"],
  ["/plan", "plan içe aktar"],
  ["/aralık", "aralıklı tekrar görevi"],
  ["/yardim", "komutlar"],
];

// Replace a @/# mention token with the chosen display label in the input.
function applyMention(input: string, trigger: "@" | "#", label: string) {
  const parts = input.split(trigger);
  parts.pop();
  return parts.join(trigger) + trigger + label + " ";
}

export default function ChatBox() {
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

  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [allTags, setAllTags] = useState<string[]>([]);
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
  const [, setTasksCache] = useState<Task[]>([]);
  const [pickedMentions, setPickedMentions] = useState<
    { type: string; id: string; label: string }[]
  >([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showExpand, setShowExpand] = useState(false);

  // Deep-link from the Günüm page: open a session and scroll to a day's message.
  const location = useLocation();
  const navigate = useNavigate();
  const pendingJump = useRef<{ session: string; ts: number } | null>(null);
  useEffect(() => {
    const st = location.state as { jumpSession?: string; jumpTs?: number } | null;
    if (st?.jumpSession) {
      pendingJump.current = { session: st.jumpSession, ts: st.jumpTs ?? 0 };
      setActiveSessionId(st.jumpSession);
      navigate(".", { replace: true, state: null });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state]);

  useEffect(() => {
    getModels().then(setAvailableModels).catch(() => {});
    getTags().then(setAllTags).catch(() => {});
  }, []);

  const [searchQuery, setSearchQuery] = useState("");
  const [showSearch, setShowSearch] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [activePersona, setActivePersona] = useState(personasData[0].id);

  // Auto-scroll to the newest line — unless a Günüm deep-link asked to jump to a
  // specific message, in which case scroll there once.
  useEffect(() => {
    const jump = pendingJump.current;
    if (jump && activeSessionId === jump.session) {
      requestAnimationFrame(() => {
        const el = scrollRef.current?.querySelector(`[data-ts="${jump.ts}"]`);
        if (el) el.scrollIntoView({ block: "center" });
        else scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
        pendingJump.current = null;
      });
      return;
    }
    requestAnimationFrame(() =>
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
    );
  }, [lines, activeSessionId]);

  function push(line: Line) {
    updateActiveSessionLines([...lines, line]);
  }

  const attachFiles = useCallback(
    async (files: File[]) => {
      for (const file of files) {
        push({ role: "system", text: `↑ ${file.name} yükleniyor…` });
        try {
          const a = await uploadChatFile(file);
          setAttachments((prev) => [...prev, a]);
          push({ role: "system", text: `✓ ${a.name} eklendi (${a.chars} karakter)` });
        } catch (e) {
          push({ role: "system", text: `dosya hatası: ${(e as Error).message}` });
        }
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [lines]
  );

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
    const { getTasks, getIdeas } = await import("../../api");
    const [tasks, ideas] = await Promise.all([
      getTasks(),
      getIdeas().catch(() => []),
    ]);
    setTasksCache(tasks);
    return { tasks, ideas };
  }, []);

  useEffect(() => {
    refreshMentionData().catch(() => {});
  }, [refreshMentionData]);

  useEffect(() => {
    if (showMentions) {
      const q = mentionMatch[1].trim().toLowerCase();
      refreshMentionData()
        .then(({ tasks, ideas }) => {
          const models = availableModels.map((m) => ({ id: m, type: "model", label: m }));
          const tOptions = tasks
            .filter((t) => t.title.toLowerCase().includes(q))
            .map((t) => ({ id: t.id, type: t.parent_id ? "alt görev" : "görev", label: t.title }));
          const iOptions = ideas
            .filter((i) => (i.title || "").toLowerCase().includes(q))
            .map((i) => ({ id: i.id, type: "fikir", label: i.title || "Başlıksız fikir" }));
          const mOptions = models.filter((m) => m.label.toLowerCase().includes(q));
          setMentionOptions([...mOptions, ...tOptions, ...iOptions].slice(0, 12));
        })
        .catch(() => {});
    } else if (showTags) {
      const q = tagMatch[1].trim().toLowerCase();
      const defaultTags = ["İş", "Günlük Yazma", "Okuma", "Kişisel gelişim", "Genel"];
      const mergedTags = Array.from(new Set([...defaultTags, ...allTags, ...customTags]));
      const opts = mergedTags
        .filter((t) => t.toLowerCase().includes(q))
        .map((t) => ({ id: t, type: "etiket", label: t }));
      if (q && !opts.some((o) => o.label.toLowerCase() === q)) {
        opts.push({ id: q, type: "yeni etiket", label: tagMatch[1].trim() });
      }
      setMentionOptions(opts);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [input, showMentions, showTags, availableModels, allTags, customTags]);

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
      modelOverride = availableModels.find((m) => m.toLowerCase() === modelMatch[1].toLowerCase());
    }

    const activeMentions = pickedMentions
      .filter((m) => message.includes(m.label))
      .map((m) => ({ type: m.type, id: m.id }));

    const persona = personasData.find((p) => p.id === activePersona);
    const systemPrompt = persona && persona.prompt ? persona.prompt : undefined;

    if (customMessage === undefined) setInput("");
    setAttachments([]);
    setPickedMentions([]);

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
    setInput(msg.text.replace(/ 📎\d+$/, ""));
    updateActiveSessionLines(lines.slice(0, index));
  };

  const handleRegenerate = (index: number) => {
    if (busy) return;
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
    void handleSend(userMsg, historyOverride);
  };

  const copyToClipboard = (text: string) => navigator.clipboard.writeText(text);

  const exportChat = () => {
    const text = lines.map((l) => `${l.role.toUpperCase()}:\n${l.text}`).join("\n\n---\n\n");
    const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `chat-${activeSession.id}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const filteredLines = searchQuery
    ? lines.filter((l) => l.text.toLowerCase().includes(searchQuery.toLowerCase()))
    : lines;

  const CommandHints = () => (
    <div className="border-t border-line bg-surface-2 px-3 py-2 text-xs">
      <div className="mx-auto flex max-w-5xl flex-wrap gap-1.5">
        {COMMANDS.filter(([c]) => c.toLowerCase().startsWith(activeCommandKey)).map(([c, d]) => (
          <button
            key={c}
            onClick={() => {
              const prefix = input.substring(0, cmdMatch!.index);
              const space = cmdMatch!.index! > 0 && !prefix.endsWith(" ") ? " " : "";
              setInput(prefix + space + c + " ");
            }}
            className="rounded border border-line-strong px-2 py-0.5 text-zinc-400 hover:border-primary-500 hover:text-primary-300"
          >
            {c} <span className="text-zinc-600">{d}</span>
          </button>
        ))}
      </div>
    </div>
  );

  return (
    <div className="relative flex h-full flex-col overflow-hidden rounded-xl border border-line bg-surface/60 font-chat shadow-lg shadow-black/20">
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
            className="rounded border border-line-strong bg-surface-2 px-2 py-1 text-xs text-zinc-300 outline-none"
            title="Sistem Promptu Seçici"
          >
            {personasData.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <button onClick={() => setShowSearch(!showSearch)} className="text-sm text-zinc-400 hover:text-zinc-200" title="Chat İçi Arama">
            🔍
          </button>
          <button onClick={exportChat} className="text-sm text-zinc-400 hover:text-zinc-200" title="Dışa Aktar (Markdown)">
            📥
          </button>
          <button onClick={handleNewChat} className="ml-2 text-sm font-medium text-zinc-400 hover:text-primary-400" title="Yeni Sohbet">
            ＋ Yeni
          </button>
        </div>
      </div>

      {/* SEARCH BAR */}
      {showSearch && (
        <div className="flex gap-2 border-b border-line bg-surface-2 p-2">
          <input
            autoFocus
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Mesajlarda ara..."
            className="field flex-1 px-2 py-1 text-sm text-zinc-200"
          />
          <button
            onClick={() => {
              setShowSearch(false);
              setSearchQuery("");
            }}
            className="px-2 text-zinc-500 hover:text-zinc-300"
          >
            Kapat
          </button>
        </div>
      )}

      {/* HISTORY DRAWER */}
      {showHistory && (
        <div className="absolute bottom-0 left-0 top-[45px] z-10 flex w-64 flex-col border-r border-line bg-surface-2">
          <div className="flex items-center justify-between border-b border-line p-3">
            <span className="text-sm font-medium text-zinc-200">Sohbetler</span>
            <button onClick={() => setShowHistory(false)} className="text-zinc-500 hover:text-zinc-300">
              ×
            </button>
          </div>
          <div className="flex-1 space-y-1 overflow-y-auto p-2">
            {sessions.map((s) => (
              <div
                key={s.id}
                className={`flex cursor-pointer items-center justify-between rounded p-2 ${
                  activeSessionId === s.id ? "bg-surface-2 text-zinc-100 ring-1 ring-inset ring-line-strong" : "text-zinc-400 hover:bg-white/[0.04]"
                }`}
                onClick={() => {
                  setActiveSessionId(s.id);
                  setShowHistory(false);
                }}
              >
                <span className="flex-1 truncate text-sm">{s.title}</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteChat(s.id);
                  }}
                  className="ml-2 text-rose-500/50 hover:text-rose-400"
                  title="Sil"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* MESSAGES */}
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-6 py-5 text-sm">
        <div className="mx-auto max-w-5xl space-y-4">
          {filteredLines.map((l, i) => (
            <div key={i} data-ts={l.ts ?? ""}>
              <ChatMessage
                line={l}
                index={i}
                showActions={!searchQuery}
                onCopy={copyToClipboard}
                onEdit={handleEdit}
                onRegenerate={handleRegenerate}
              />
            </div>
          ))}
          {busy && <div className="ml-4 animate-pulse text-zinc-600">…düşünüyor</div>}
          {searchQuery && filteredLines.length === 0 && (
            <div className="mt-4 text-center text-zinc-500">Sonuç bulunamadı.</div>
          )}
        </div>
      </div>

      {showHint && !isDefaultCmd && !showExpand && <CommandHints />}

      {(showMentions || showTags) && mentionOptions.length > 0 && (
        <div className="border-t border-line bg-elevated px-3 py-2 text-xs">
          <div className="mx-auto flex max-h-40 max-w-5xl flex-col gap-1 overflow-y-auto">
            {mentionOptions.map((opt) => (
              <button
                key={opt.id + opt.type}
                onClick={() => {
                  if (showMentions) {
                    setPickedMentions((prev) => [
                      ...prev.filter((p) => p.id !== opt.id),
                      { type: opt.type, id: opt.id, label: opt.label },
                    ]);
                    setInput(applyMention(input, "@", opt.label));
                  } else if (showTags) {
                    addCustomTag(opt.label);
                    setPickedMentions((prev) => [
                      ...prev.filter((p) => p.id !== opt.id),
                      { type: "etiket", id: opt.label, label: opt.label },
                    ]);
                    setInput(applyMention(input, "#", opt.label));
                  }
                }}
                className="rounded px-2 py-1 text-left text-zinc-300 hover:bg-white/[0.05]"
              >
                <span className="mr-2 text-zinc-500">[{opt.type}]</span> {opt.label}
              </button>
            ))}
          </div>
        </div>
      )}

      <ChatInput
        input={input}
        setInput={setInput}
        onSend={() => void handleSend()}
        busy={busy}
        attachments={attachments}
        onRemoveAttachment={(id) => setAttachments((p) => p.filter((x) => x.id !== id))}
        onAttachFiles={(files) => void attachFiles(files)}
        onExpand={() => setShowExpand(true)}
      />

      {/* Expand modal */}
      {showExpand && (
        <Modal open={showExpand} onClose={() => setShowExpand(false)} title="Mesajı düzenle" widthClass="max-w-3xl">
          <div className="flex h-[70vh] flex-col gap-3">
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-line-strong">
              <div className="min-h-0 flex-1 overflow-y-auto">
                <NotionEditor
                  key="expand-input"
                  initialContent={input}
                  onChange={(html) => {
                    const tmp = document.createElement("div");
                    tmp.innerHTML = html;
                    setInput((tmp.textContent || tmp.innerText || "").trim());
                  }}
                />
              </div>
              {showHint && !isDefaultCmd && <CommandHints />}
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowExpand(false)}
                className="rounded-lg border border-line-strong px-4 py-2 text-sm text-zinc-300 hover:bg-white/[0.05]"
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

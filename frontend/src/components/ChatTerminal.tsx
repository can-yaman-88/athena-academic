import { useRef, useState, useEffect } from "react";
import { streamChat, uploadChatFile, type ChatAttachment } from "../api";
import personasData from "../data/personas.json";

interface Line {
  role: "user" | "agent" | "system";
  text: string;
}

interface ChatSession {
  id: string;
  title: string;
  updatedAt: number;
  lines: Line[];
}

const COMMANDS = [
  ["/akademik", "akademik görev"],
  ["/proje", "proje (+dosya)"],
  ["/odev", "ödev"],
  ["/seans", "çalışma seansı"],
  ["/gunluk", "günlük görev"],
  ["/duzenle", "görev düzenle"],
  ["/antrenman", "tek antrenman"],
  ["/plan", "plan içe aktar"],
  ["/not", "<ipucu>: not"],
  ["/yardim", "komutlar"],
];

function generateId() {
  return Math.random().toString(36).substring(2, 9);
}

export default function ChatTerminal() {
  // Session Management
  const [sessions, setSessions] = useState<ChatSession[]>(() => {
    const saved = localStorage.getItem("jarvis_chat_sessions");
    if (saved) {
      try { return JSON.parse(saved); } catch { /* ignore */ }
    }
    // Migration from old chat_history
    const oldSaved = localStorage.getItem("chat_history");
    const defaultLines: Line[] = oldSaved ? JSON.parse(oldSaved) : [{ role: "system", text: "Athena-Academic hazır. Soru sor, görev/PDF/antrenman iste, ya da /yardim yaz." }];
    return [{ id: generateId(), title: "Yeni Sohbet", updatedAt: Date.now(), lines: defaultLines }];
  });

  const [activeSessionId, setActiveSessionId] = useState<string>(() => {
    const savedId = localStorage.getItem("jarvis_active_session");
    if (savedId && sessions.some(s => s.id === savedId)) return savedId;
    return sessions[0]?.id || "";
  });

  const activeSession = sessions.find(s => s.id === activeSessionId) || sessions[0];
  const lines = activeSession?.lines || [];

  const updateActiveSessionLines = (newLines: Line[]) => {
    setSessions(prev => prev.map(s => {
      if (s.id === activeSessionId) {
        const title = newLines.length > 1 && newLines[1].role === "user" ? newLines[1].text.substring(0, 30) + "..." : s.title;
        return { ...s, lines: newLines, title, updatedAt: Date.now() };
      }
      return s;
    }));
  };

  useEffect(() => {
    localStorage.setItem("jarvis_chat_sessions", JSON.stringify(sessions));
    localStorage.setItem("jarvis_active_session", activeSessionId);
  }, [sessions, activeSessionId]);

  const handleNewChat = () => {
    const newSession: ChatSession = {
      id: generateId(),
      title: "Yeni Sohbet",
      updatedAt: Date.now(),
      lines: [{ role: "system" as const, text: "Athena-Academic hazır. Yeni sohbete hoş geldiniz." }]
    };
    setSessions(prev => [newSession, ...prev]);
    setActiveSessionId(newSession.id);
  };

  const handleDeleteChat = (id: string) => {
    setSessions(prev => {
      const remaining = prev.filter(s => s.id !== id);
      if (remaining.length === 0) {
        const newS: ChatSession = { id: generateId(), title: "Yeni Sohbet", updatedAt: Date.now(), lines: [{ role: "system" as const, text: "Athena-Academic hazır." }] };
        setActiveSessionId(newS.id);
        return [newS];
      }
      if (activeSessionId === id) setActiveSessionId(remaining[0].id);
      return remaining;
    });
  };

  // Chat State
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Extras State
  const [searchQuery, setSearchQuery] = useState("");
  const [showSearch, setShowSearch] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [activePersona, setActivePersona] = useState(personasData[0].id);

  function push(line: Line) {
    updateActiveSessionLines([...lines, line]);
    requestAnimationFrame(() =>
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
    );
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
    user: "text-sky-300",
    agent: "text-emerald-300",
    system: "text-zinc-500",
  } as const;

  const showHint = input.startsWith("/");
  const isDefaultCmd = input.startsWith("/default ");
  const mentionMatch = input.match(/@([\w-]*)$/);
  const showMentions = mentionMatch !== null;
  const tagMatch = input.match(/#([\w-]*)$/);
  const showTags = tagMatch !== null;

  const [mentionOptions, setMentionOptions] = useState<{ id: string, type: string, label: string }[]>([]);

  useEffect(() => {
    if (showMentions) {
      const q = mentionMatch[1].toLowerCase();
      import("../api").then(({ getTasks, getWorkouts }) => {
        Promise.all([getTasks(), getWorkouts()]).then(([tasks, workouts]) => {
          const models = [
            { id: "haiku", type: "model", label: "haiku" },
            { id: "opus", type: "model", label: "opus" },
            { id: "gemini-flash", type: "model", label: "gemini-flash" },
            { id: "gemini-pro", type: "model", label: "gemini-pro" },
          ];
          const tOptions = tasks.filter(t => t.title.toLowerCase().includes(q)).map(t => ({ id: t.id, type: "görev", label: t.title }));
          const wOptions = workouts.filter(w => (w.title || "").toLowerCase().includes(q) || w.date.includes(q)).map(w => ({ id: w.id, type: "antrenman", label: w.title || w.date }));
          const mOptions = models.filter(m => m.label.includes(q));
          setMentionOptions([...mOptions, ...tOptions, ...wOptions].slice(0, 10));
        });
      });
    } else if (showTags) {
      const q = tagMatch[1].toLowerCase();
      const defaultTags = ["İş", "Günlük Yazma", "Okuma", "Kişisel gelişim", "Genel"];
      const opts = defaultTags.filter(t => t.toLowerCase().includes(q)).map(t => ({ id: t, type: "etiket", label: t }));
      if (q && !opts.some(o => o.label.toLowerCase() === q)) {
        opts.push({ id: q, type: "yeni etiket", label: tagMatch[1] });
      }
      setMentionOptions(opts);
    }
  }, [input, showMentions, showTags]);

  async function handleSend(customMessage?: string, historyOverride?: Line[]) {
    let message = customMessage !== undefined ? customMessage : input.trim();
    if ((!message && attachments.length === 0) || busy) return;
    if (customMessage === undefined) setInput("");

    if (message.startsWith("/default ")) {
      const parts = message.split(" ");
      if (parts.length > 1 && parts[1].startsWith("@")) {
        const modelName = parts[1].slice(1);
        localStorage.setItem("defaultModel", modelName);
        push({ role: "system", text: `Varsayılan model ayarlandı: ${modelName}` });
        return;
      }
    }

    const ids = attachments.map((a) => a.id);
    const currentLines = historyOverride || lines;
    const newLines = [...currentLines, { role: "user", text: message + (ids.length ? ` 📎${ids.length}` : "") } as Line];
    updateActiveSessionLines(newLines);
    
    setAttachments([]);
    setBusy(true);

    requestAnimationFrame(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight }));

    let modelOverride = localStorage.getItem("defaultModel") || undefined;
    const modelMatch = message.match(/@(haiku|opus|gemini-flash|gemini-pro)\b/);
    if (modelMatch) {
      modelOverride = modelMatch[1];
    }

    const persona = personasData.find(p => p.id === activePersona);
    const systemPrompt = persona && persona.prompt ? persona.prompt : undefined;

    try {
      const { API_URL } = await import("../api");
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          message, 
          attachment_ids: ids, 
          model: modelOverride, 
          history: currentLines.slice(-10),
          system_prompt: systemPrompt
        }),
      });
      if (!res.ok || !res.body) throw new Error(`chat ${res.status}`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      
      // Temporary buffer for the incoming agent message
      let currentAgentMessage = "";
      
      for (;;) {
        const { value, done } = await reader.read();
        if (done) {
          if (currentAgentMessage) {
            updateActiveSessionLines([...newLines, { role: "agent", text: currentAgentMessage }]);
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
            if (evt.type === "message") {
              currentAgentMessage += String(evt.content);
              shouldUpdate = true;
            }
            else if (evt.type === "tool") {
              updateActiveSessionLines([...newLines, { role: "agent", text: currentAgentMessage }, { role: "system", text: `→ tool: ${String(evt.active_tool)}` }]);
            }
            else if (evt.type === "error") {
              updateActiveSessionLines([...newLines, { role: "agent", text: currentAgentMessage }, { role: "system", text: `error: ${String(evt.error)}` }]);
            }
          } catch { /* ignore */ }
        }
        if (shouldUpdate) {
           updateActiveSessionLines([...newLines, { role: "agent", text: currentAgentMessage }]);
           requestAnimationFrame(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight }));
        }
      }
    } catch (e) {
      updateActiveSessionLines([...newLines, { role: "system", text: `error: ${(e as Error).message}` }]);
    } finally {
      setBusy(false);
    }
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
    const text = lines.map(l => `${l.role.toUpperCase()}:\n${l.text}`).join("\n\n---\n\n");
    const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `chat-${activeSession.id}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const filteredLines = searchQuery 
    ? lines.filter(l => l.text.toLowerCase().includes(searchQuery.toLowerCase()))
    : lines;

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
            {personasData.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          <button onClick={() => setShowSearch(!showSearch)} className="text-zinc-400 hover:text-zinc-200 text-sm" title="Chat İçi Arama">🔍</button>
          <button onClick={exportChat} className="text-zinc-400 hover:text-zinc-200 text-sm" title="Dışa Aktar (Markdown)">📥</button>
          <button onClick={handleNewChat} className="text-zinc-400 hover:text-emerald-400 text-sm font-medium ml-2" title="Yeni Sohbet">＋ Yeni</button>
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
            className="flex-1 rounded border border-line-strong bg-elevated px-2 py-1 text-sm text-zinc-200 outline-none focus:border-emerald-500"
          />
          <button onClick={() => { setShowSearch(false); setSearchQuery(""); }} className="text-zinc-500 hover:text-zinc-300 px-2">Kapat</button>
        </div>
      )}

      {/* HISTORY DRAWER */}
      {showHistory && (
        <div className="absolute top-[45px] left-0 bottom-0 w-64 bg-surface-2 border-r border-line z-10 flex flex-col">
          <div className="p-3 border-b border-line flex justify-between items-center">
            <span className="text-sm font-medium text-zinc-200">Sohbetler</span>
            <button onClick={() => setShowHistory(false)} className="text-zinc-500 hover:text-zinc-300">×</button>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {sessions.map(s => (
              <div 
                key={s.id} 
                className={`flex items-center justify-between p-2 rounded cursor-pointer ${activeSessionId === s.id ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:bg-zinc-800/50'}`}
                onClick={() => { setActiveSessionId(s.id); setShowHistory(false); }}
              >
                <span className="text-sm truncate flex-1">{s.title}</span>
                <button 
                  onClick={(e) => { e.stopPropagation(); handleDeleteChat(s.id); }}
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

      <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4 font-mono text-sm">
        {filteredLines.map((l, i) => (
          <div key={i} className={`group flex flex-col ${l.role === "user" ? "items-end" : "items-start"}`}>
            <div className={`relative max-w-[85%] rounded-lg px-4 py-2 ${l.role === "user" ? "bg-zinc-800 text-sky-200" : l.role === "agent" ? "bg-elevated text-emerald-200 border border-line" : "bg-transparent text-zinc-500"}`}>
              {l.role === "system" && <span className="select-none mr-2">#</span>}
              <span className="whitespace-pre-wrap">{l.text}</span>
              
              {/* ACTION BUTTONS (Hover) */}
              {l.role !== "system" && !searchQuery && (
                <div className={`absolute top-0 flex gap-1 bg-elevated border border-line-strong rounded p-0.5 opacity-0 transition-opacity group-hover:opacity-100 ${l.role === "user" ? "-left-16" : "-right-16"}`}>
                  <button onClick={() => copyToClipboard(l.text)} className="text-zinc-400 hover:text-zinc-200 px-1" title="Kopyala">📋</button>
                  {l.role === "user" && <button onClick={() => handleEdit(i)} className="text-zinc-400 hover:text-sky-300 px-1" title="Düzenle">✏️</button>}
                  {l.role === "agent" && <button onClick={() => handleRegenerate(i)} className="text-zinc-400 hover:text-emerald-300 px-1" title="Yeniden Üret">🔄</button>}
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && <div className="text-zinc-600 ml-4 animate-pulse">…düşünüyor</div>}
        {searchQuery && filteredLines.length === 0 && <div className="text-zinc-500 text-center mt-4">Sonuç bulunamadı.</div>}
      </div>

      {showHint && !isDefaultCmd && (
        <div className="flex flex-wrap gap-1.5 border-t border-line px-3 py-2 text-xs bg-surface-2">
          {COMMANDS.filter(([c]) => c.startsWith(input.split(" ")[0])).map(([c, d]) => (
            <button
              key={c}
              onClick={() => setInput(c + " ")}
              className="rounded border border-line-strong px-2 py-0.5 text-zinc-400 hover:border-emerald-500 hover:text-emerald-300"
            >
              {c} <span className="text-zinc-600">{d}</span>
            </button>
          ))}
        </div>
      )}

      {(showMentions || showTags) && mentionOptions.length > 0 && (
        <div className="flex flex-col gap-1 border-t border-line px-3 py-2 text-xs max-h-40 overflow-y-auto bg-elevated">
          {mentionOptions.map((opt) => (
            <button
              key={opt.id + opt.type}
              onClick={() => {
                if (showMentions) {
                  const parts = input.split("@");
                  parts.pop();
                  setInput(parts.join("@") + "@" + (opt.type === "model" ? opt.label : `"${opt.label}"`) + " ");
                } else if (showTags) {
                  const parts = input.split("#");
                  parts.pop();
                  setInput(parts.join("#") + "#" + opt.label + " ");
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
            <span key={a.id} className="inline-flex items-center gap-1 rounded border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-300">
              📎 {a.name}
              <button onClick={() => setAttachments((p) => p.filter((x) => x.id !== a.id))} className="text-emerald-400/70 hover:text-emerald-200">×</button>
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
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void handleSend()}
          placeholder="Mesaj yaz… ('/' ile komutlar, '@' ile bahset)"
          className="flex-1 rounded-lg border border-line-strong bg-elevated px-3 py-2 font-mono text-sm text-zinc-100 outline-none focus:border-emerald-500"
        />
        <button
          onClick={() => void handleSend()}
          disabled={busy}
          className="rounded-lg bg-emerald-500/90 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-emerald-400 disabled:opacity-50 transition-colors"
        >
          Gönder
        </button>
      </div>
    </div>
  );
}

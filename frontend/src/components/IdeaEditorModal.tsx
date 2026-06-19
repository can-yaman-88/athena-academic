import { useRef, useState } from "react";
import NotionEditor from "./NotionEditor";
import { Button } from "../ui";
import {
  addIdeaMaterial,
  ideaFileUrl,
  updateIdea,
  uploadIdeaFile,
  type Idea,
} from "../api";

function stripHtml(html: string): string {
  const tmp = document.createElement("div");
  tmp.innerHTML = html;
  return (tmp.textContent || tmp.innerText || "").trim();
}

// Full-page, Notion-style editor for a single idea: title on top, the whole
// surface below is writable rich text, plus a materials (links/files) section.
export default function IdeaEditorModal({
  idea,
  onClose,
  onSaved,
}: {
  idea: Idea;
  onClose: () => void;
  onSaved: (saved: Idea) => void;
}) {
  const [title, setTitle] = useState(idea.title);
  const [content, setContent] = useState(idea.content);
  const [materials, setMaterials] = useState(idea.materials);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [showLinkInput, setShowLinkInput] = useState(false);
  const [matName, setMatName] = useState("");
  const [matUrl, setMatUrl] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const autoSaveTimer = useRef<number | null>(null);

  const persist = async (t: string, c: string) => {
    const saved = await updateIdea(idea.id, { title: t, content: c });
    onSaved(saved);
    return saved;
  };

  const scheduleAutoSave = (t: string, c: string) => {
    if (autoSaveTimer.current) window.clearTimeout(autoSaveTimer.current);
    autoSaveTimer.current = window.setTimeout(async () => {
      if (stripHtml(c).length === 0 && !t.trim()) return;
      try {
        await persist(t, c);
        setSaveMsg("Otomatik kaydedildi");
      } catch {
        setSaveMsg("Otomatik kaydetme başarısız");
      } finally {
        window.setTimeout(() => setSaveMsg(""), 2000);
      }
    }, 1500);
  };

  const handleManualSave = async () => {
    setSaving(true);
    setSaveMsg("");
    try {
      await persist(title, content);
      setSaveMsg("✓ Kaydedildi");
    } catch (e) {
      setSaveMsg(`✗ ${(e as Error).message}`);
    } finally {
      setSaving(false);
      window.setTimeout(() => setSaveMsg(""), 2000);
    }
  };

  const handleClose = () => {
    if (autoSaveTimer.current) window.clearTimeout(autoSaveTimer.current);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-3 backdrop-blur-sm">
      <div
        className="flex h-[96vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-line bg-surface-2 shadow-card-hover"
        style={{ animation: "modal-pop 180ms ease-out" }}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-line px-5 py-3">
          <span className="text-[11px] uppercase tracking-wider text-zinc-500">
            Fikir
          </span>
          <div className="flex items-center gap-3">
            {saveMsg && <span className="text-xs text-zinc-400">{saveMsg}</span>}
            <Button size="sm" variant="ghost" disabled={saving} onClick={() => void handleManualSave()}>
              {saving ? "Kaydediliyor…" : "Kaydet"}
            </Button>
            <button
              onClick={handleClose}
              className="rounded-lg px-2 py-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
              aria-label="Kapat"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Title block on top */}
        <input
          value={title}
          onChange={(e) => {
            setTitle(e.target.value);
            scheduleAutoSave(e.target.value, content);
          }}
          placeholder="Başlıksız fikir"
          className="border-b border-line bg-transparent px-6 py-4 text-2xl font-semibold text-zinc-100 outline-none placeholder:text-zinc-600"
        />

        {/* Whole surface below is writable */}
        <div className="min-h-0 flex-1 overflow-y-auto">
          <NotionEditor
            key={idea.id}
            initialContent={content}
            fullPage
            onChange={(html) => {
              setContent(html);
              scheduleAutoSave(title, html);
            }}
          />
        </div>

        {/* Materials */}
        <div className="border-t border-line bg-surface-2/80 px-6 py-3">
          <div className="mb-1 text-[11px] uppercase tracking-wider text-zinc-500">
            Materyaller <span className="text-zinc-600">(yapay zekâya gönderilmez)</span>
          </div>
          <ul className="mb-2 space-y-1 text-sm">
            {materials.map((m) => (
              <li key={m.id} className="text-zinc-300">
                {m.kind === "link" ? (
                  <a href={m.source} target="_blank" rel="noreferrer" className="text-sky-300 hover:underline">
                    🔗 {m.name}
                  </a>
                ) : (
                  <a href={ideaFileUrl(idea.id, m.id)} target="_blank" rel="noreferrer" className="text-zinc-200 hover:text-emerald-300">
                    📄 {m.name}
                  </a>
                )}
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => fileRef.current?.click()}>
              Dosya +
            </Button>
            <input
              ref={fileRef}
              type="file"
              className="hidden"
              onChange={async (e) => {
                const f = e.target.files?.[0];
                if (f) {
                  const saved = await uploadIdeaFile(idea.id, f);
                  setMaterials(saved.materials);
                  onSaved(saved);
                }
                if (e.target) e.target.value = "";
              }}
            />
            <Button variant="ghost" size="sm" onClick={() => setShowLinkInput((s) => !s)}>
              Bağlantı +
            </Button>
            {showLinkInput && (
              <>
                <input
                  value={matName}
                  onChange={(e) => setMatName(e.target.value)}
                  placeholder="ad"
                  className="w-24 rounded border border-line-strong bg-surface-2 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-emerald-500"
                />
                <input
                  value={matUrl}
                  onChange={(e) => setMatUrl(e.target.value)}
                  placeholder="https://…"
                  className="flex-1 rounded border border-line-strong bg-surface-2 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-emerald-500"
                />
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={!matName.trim() || !matUrl.trim()}
                  onClick={async () => {
                    const saved = await addIdeaMaterial(idea.id, {
                      kind: "link",
                      name: matName.trim(),
                      source: matUrl.trim(),
                    });
                    setMaterials(saved.materials);
                    onSaved(saved);
                    setMatName("");
                    setMatUrl("");
                    setShowLinkInput(false);
                  }}
                >
                  Ekle
                </Button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";
import NotionEditor from "./NotionEditor";
import { Button } from "../ui";

function stripHtml(html: string): string {
  const tmp = document.createElement("div");
  tmp.innerHTML = html;
  return (tmp.textContent || tmp.innerText || "").trim();
}

function draftKey(date: string) {
  return `journal_draft_${date}`;
}

export default function JournalEditorModal({
  date,
  initialContent,
  onClose,
  onSave,
}: {
  date: string;
  initialContent: string;
  onClose: () => void;
  onSave: (html: string) => Promise<void> | void;
}) {
  const [content, setContent] = useState(initialContent);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const autoSaveTimer = useRef<number | null>(null);
  const isEmpty = stripHtml(content).length === 0;

  // Load draft if content is initially empty and a draft exists.
  useEffect(() => {
    if (stripHtml(initialContent).length > 0) return;
    const draft = localStorage.getItem(draftKey(date));
    if (draft) setContent(draft);
  }, [date, initialContent]);

  // Auto-save: write to localStorage on every change, and debounce-save to backend.
  const handleChange = (html: string) => {
    setContent(html);
    localStorage.setItem(draftKey(date), html);
    if (autoSaveTimer.current) window.clearTimeout(autoSaveTimer.current);
    autoSaveTimer.current = window.setTimeout(async () => {
      if (stripHtml(html).length === 0) return;
      try {
        await onSave(html);
        setSaveMsg("Otomatik kaydedildi");
      } catch {
        setSaveMsg("Otomatik kaydetme başarısız");
      } finally {
        window.setTimeout(() => setSaveMsg(""), 2000);
      }
    }, 2000);
  };

  const handleManualSave = async () => {
    if (isEmpty) return;
    setSaving(true);
    setSaveMsg("");
    try {
      await onSave(content);
      localStorage.removeItem(draftKey(date));
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
    if (isEmpty) {
      localStorage.removeItem(draftKey(date));
    } else {
      localStorage.setItem(draftKey(date), content);
    }
    onClose();
  };

  // Confirm before closing if there are unsaved changes visible to the user.
  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!isEmpty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [isEmpty, content]);

  const title = useMemo(() => {
    try {
      return new Date(date).toLocaleDateString("tr-TR");
    } catch {
      return date;
    }
  }, [date]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-3 backdrop-blur-sm">
      <div
        className="flex h-[96vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-line bg-surface-2 shadow-card-hover"
        style={{ animation: "modal-pop 180ms ease-out" }}
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-3">
          <h2 className="text-sm font-semibold tracking-wide text-zinc-200">
            {title}
          </h2>
          <div className="flex items-center gap-3">
            {saveMsg && (
              <span className="text-xs text-zinc-400">{saveMsg}</span>
            )}
            <Button
              size="sm"
              variant="ghost"
              disabled={saving || isEmpty}
              onClick={() => void handleManualSave()}
            >
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
        <div className="min-h-0 flex-1 overflow-y-auto">
          <NotionEditor
            key={date}
            initialContent={content}
            onChange={handleChange}
            fullPage
          />
        </div>
      </div>
    </div>
  );
}

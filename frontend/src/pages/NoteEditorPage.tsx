import { useEffect, useRef, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  getNote,
  getNoteChildren,
  createNote,
  updateNote,
  uploadInline,
  type NotePage,
} from "../api";
import NotionEditor from "../components/NotionEditor";
import { ChevronRight, FileText } from "lucide-react";

/** Full-page note editor with breadcrumb, autosave and nested sub-pages. */
export default function NoteEditorPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();

  const [note, setNote] = useState<NotePage | null>(null);
  const [ancestors, setAncestors] = useState<NotePage[]>([]);
  const [children, setChildren] = useState<NotePage[]>([]);
  const [title, setTitle] = useState("");
  const [saveMsg, setSaveMsg] = useState("");
  const [error, setError] = useState("");
  const contentRef = useRef("");
  const saveTimer = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const n = await getNote(id);
      setNote(n);
      setTitle(n.title);
      contentRef.current = n.content;
      setChildren(await getNoteChildren(id));
      // Build breadcrumb by walking up parents.
      const chain: NotePage[] = [];
      let parentId = n.parent_id;
      while (parentId) {
        const p = await getNote(parentId);
        chain.unshift(p);
        parentId = p.parent_id;
      }
      setAncestors(chain);
      setError("");
    } catch (e) {
      setError(`Not yüklenemedi: ${(e as Error).message}`);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  const persist = useCallback(
    async (t: string, c: string) => {
      try {
        await updateNote(id, { title: t, content: c });
        setSaveMsg("Otomatik kaydedildi");
      } catch {
        setSaveMsg("Kaydetme başarısız");
      } finally {
        window.setTimeout(() => setSaveMsg(""), 2000);
      }
    },
    [id]
  );

  const scheduleSave = useCallback(
    (t: string, c: string) => {
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
      saveTimer.current = window.setTimeout(() => void persist(t, c), 1200);
    },
    [persist]
  );

  if (error) {
    return <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-300">{error}</div>;
  }
  if (!note) {
    return <div className="p-4 text-sm text-zinc-500">Yükleniyor…</div>;
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-line bg-surface-2">
      {/* Breadcrumb + save status */}
      <div className="flex items-center gap-1 border-b border-line px-4 py-2 text-xs text-zinc-400">
        <button onClick={() => navigate("/notlar")} className="hover:text-zinc-200">Notlar</button>
        {ancestors.map((a) => (
          <span key={a.id} className="flex items-center gap-1">
            <ChevronRight size={12} className="text-zinc-600" />
            <button onClick={() => navigate(`/notlar/${a.id}`)} className="max-w-[160px] truncate hover:text-zinc-200">
              {a.title || "Başlıksız"}
            </button>
          </span>
        ))}
        <ChevronRight size={12} className="text-zinc-600" />
        <span className="max-w-[200px] truncate text-zinc-200">{title || "Başlıksız"}</span>
        <span className="ml-auto text-zinc-500">{saveMsg}</span>
      </div>

      {/* Title */}
      <input
        value={title}
        onChange={(e) => {
          setTitle(e.target.value);
          scheduleSave(e.target.value, contentRef.current);
        }}
        placeholder="Başlıksız"
        className="border-b border-line bg-transparent px-6 py-4 text-2xl font-semibold text-zinc-100 outline-none placeholder:text-zinc-600"
      />

      {/* Body */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <NotionEditor
          key={note.id}
          initialContent={note.content}
          fullPage
          onInlineUpload={uploadInline}
          enableSubPages={note.depth < 2}
          onOpenPage={(pid) => navigate(`/notlar/${pid}`)}
          onCreateSubPage={async () => {
            const child = await createNote("Yeni alt sayfa", note.id);
            setChildren((prev) => [...prev, child]);
            return { id: child.id, title: child.title || "Yeni alt sayfa" };
          }}
          onChange={(html) => {
            contentRef.current = html;
            scheduleSave(title, html);
          }}
        />
      </div>

      {/* Sub-pages */}
      {children.length > 0 && (
        <div className="border-t border-line px-6 py-3">
          <div className="mb-1.5 text-[11px] uppercase tracking-wider text-zinc-500">Alt sayfalar</div>
          <div className="flex flex-col gap-1">
            {children.map((c) => (
              <button
                key={c.id}
                onClick={() => navigate(`/notlar/${c.id}`)}
                className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm text-zinc-300 hover:bg-white/[0.04]"
              >
                <FileText size={14} className="text-zinc-500" /> {c.title || "Başlıksız"}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

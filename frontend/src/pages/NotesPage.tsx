import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getNotes, createNote, deleteNotePage, type NotePage } from "../api";
import { Card, Button } from "../ui";
import { Plus, FileText } from "lucide-react";

/**
 * Notlar — Notion-style list view of top-level pages. Sub-pages live inside
 * their parent (opened from the page editor). "Yeni Not" opens a fresh full-page
 * note that auto-saves.
 */
export default function NotesPage() {
  const [notes, setNotes] = useState<NotePage[]>([]);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();

  const refresh = async () => {
    try {
      setNotes(await getNotes());
      setError("");
    } catch (e) {
      setError(`Notlar yüklenemedi: ${(e as Error).message}`);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const handleNew = async () => {
    setCreating(true);
    try {
      const note = await createNote("");
      navigate(`/notlar/${note.id}`);
    } catch (e) {
      setError(`Not oluşturulamadı: ${(e as Error).message}`);
    } finally {
      setCreating(false);
    }
  };

  const topLevel = notes.filter((n) => n.parent_id === null);

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto">
      {error && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-300">
          {error}
        </div>
      )}
      <Card
        title="Notlar"
        right={
          <Button variant="ghost" disabled={creating} onClick={() => void handleNew()}>
            <Plus size={15} strokeWidth={2.25} />
            {creating ? "Ekleniyor…" : "Yeni Not"}
          </Button>
        }
        bodyClassName="flex flex-col gap-1 p-3"
      >
        {topLevel.length === 0 && (
          <p className="p-3 text-sm text-zinc-500">Henüz not yok. “Yeni Not” ile başla.</p>
        )}
        {topLevel.map((n) => (
          <div
            key={n.id}
            onClick={() => navigate(`/notlar/${n.id}`)}
            className="group flex cursor-pointer items-center gap-2.5 rounded-lg px-3 py-2 transition-colors hover:bg-white/[0.04]"
          >
            <FileText size={15} className="shrink-0 text-zinc-500" />
            <span className="flex-1 truncate text-sm text-zinc-200">
              {n.title || "Başlıksız"}
            </span>
            <button
              onClick={async (e) => {
                e.stopPropagation();
                if (confirm("Bu notu ve tüm alt sayfalarını silmek istediğine emin misin?")) {
                  await deleteNotePage(n.id);
                  await refresh();
                }
              }}
              className="hidden text-xs text-zinc-500 hover:text-rose-400 group-hover:block"
            >
              Sil
            </button>
          </div>
        ))}
      </Card>
    </div>
  );
}

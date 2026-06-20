import { useEffect, useState } from "react";
import {
  getIdeas,
  createIdea,
  deleteIdea,
  getDailyNotes,
  type Idea,
  type DailyNote,
} from "../api";
import { Card, Button } from "../ui";
import IdeaEditorModal from "../components/IdeaEditorModal";
import Modal from "../components/Modal";
import { Paperclip, Plus, CalendarDays } from "lucide-react";

function preview(html: string): string {
  const tmp = document.createElement("div");
  tmp.innerHTML = html;
  return (tmp.textContent || tmp.innerText || "").trim();
}

function fmtDay(iso: string): string {
  try {
    return new Date(iso + "T00:00:00").toLocaleDateString("tr-TR", {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

export default function IdeasPage() {
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [dailyNotes, setDailyNotes] = useState<DailyNote[]>([]);
  const [openNote, setOpenNote] = useState<DailyNote | null>(null);
  const [editing, setEditing] = useState<Idea | null>(null);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);

  const refresh = async () => {
    try {
      const [ideaList, noteList] = await Promise.all([getIdeas(), getDailyNotes()]);
      setIdeas(ideaList);
      // Newest first; backend already orders by date DESC but sort defensively.
      setDailyNotes(
        [...noteList]
          .filter((n) => preview(n.content))
          .sort((a, b) => b.date.localeCompare(a.date)),
      );
      setError("");
    } catch (e) {
      setError(`Veriler yüklenemedi: ${(e as Error).message}`);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const handleNew = async () => {
    setCreating(true);
    setError("");
    try {
      const idea = await createIdea("", "");
      setIdeas((prev) => [idea, ...prev]);
      setEditing(idea);
    } catch (e) {
      setError(`Fikir oluşturulamadı: ${(e as Error).message}`);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto">
      {error && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-300">
          {error}
        </div>
      )}

      <Card
        title="Günüm"
        right={
          <span className="text-[11px] text-zinc-500">
            {dailyNotes.length} gün
          </span>
        }
        bodyClassName="flex flex-col gap-2 p-4"
      >
        {dailyNotes.length === 0 && (
          <p className="text-sm text-zinc-500">
            Henüz günlük not yok. Ana sayfadaki “Günüm” alanından yazmaya başla.
          </p>
        )}
        {dailyNotes.map((note) => (
          <button
            key={note.id}
            type="button"
            onClick={() => setOpenNote(note)}
            className="w-full rounded-xl border border-line bg-elevated/60 p-3 text-left transition-colors hover:border-line-strong"
          >
            <div className="flex items-center gap-1.5 text-xs font-medium text-accent-400">
              <CalendarDays size={12} /> {fmtDay(note.date)}
            </div>
            <p className="mt-1.5 line-clamp-2 whitespace-pre-wrap text-sm text-zinc-300">
              {preview(note.content)}
            </p>
          </button>
        ))}
      </Card>

      <Card
        title="Fikirler"
        right={
          <Button variant="ghost" disabled={creating} onClick={() => void handleNew()}>
            <Plus size={15} strokeWidth={2.25} />
            {creating ? "Ekleniyor…" : "Fikir Ekle"}
          </Button>
        }
        bodyClassName="flex flex-col gap-3 p-4"
      >
        {ideas.length === 0 && (
          <p className="text-sm text-zinc-500">
            Henüz fikir yok. “+ Fikir Ekle” ile başla.
          </p>
        )}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {ideas.map((idea) => (
            <div
              key={idea.id}
              className="group relative cursor-pointer rounded-xl border border-line bg-elevated/60 p-4 transition-colors hover:border-line-strong"
              onClick={() => setEditing(idea)}
            >
              <h3 className="truncate font-semibold text-primary-400">
                {idea.title || "Başlıksız fikir"}
              </h3>
              <div className="mt-2 line-clamp-4 text-sm text-zinc-400">
                {preview(idea.content) || "Boş…"}
              </div>
              {idea.materials.length > 0 && (
                <div className="mt-2 flex items-center gap-1 text-xs text-zinc-500">
                  <Paperclip size={11} /> {idea.materials.length} materyal
                </div>
              )}
              <button
                className="absolute right-3 top-3 hidden text-zinc-500 hover:text-rose-400 group-hover:block"
                onClick={async (e) => {
                  e.stopPropagation();
                  if (confirm("Bu fikri silmek istediğine emin misin?")) {
                    await deleteIdea(idea.id);
                    await refresh();
                  }
                }}
              >
                Sil
              </button>
            </div>
          ))}
        </div>
      </Card>

      {editing && (
        <IdeaEditorModal
          idea={editing}
          onClose={() => {
            setEditing(null);
            void refresh();
          }}
          onSaved={(saved) => {
            setIdeas((prev) => prev.map((i) => (i.id === saved.id ? saved : i)));
            setEditing(saved);
          }}
        />
      )}

      <Modal
        open={openNote !== null}
        onClose={() => setOpenNote(null)}
        title={openNote ? fmtDay(openNote.date) : ""}
        widthClass="max-w-2xl"
      >
        {openNote && (
          <div
            className="prose prose-invert max-w-none overflow-y-auto px-1 text-zinc-200"
            // Daily-note content is rich-text HTML written in the homepage editor.
            dangerouslySetInnerHTML={{
              __html: preview(openNote.content)
                ? openNote.content
                : "<p class='text-zinc-500'>Bu gün için not boş.</p>",
            }}
          />
        )}
      </Modal>
    </div>
  );
}

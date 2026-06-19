import { useEffect, useState } from "react";
import { getIdeas, createIdea, deleteIdea, type Idea } from "../api";
import { Card, Button } from "../ui";
import IdeaEditorModal from "../components/IdeaEditorModal";

function preview(html: string): string {
  const tmp = document.createElement("div");
  tmp.innerHTML = html;
  return (tmp.textContent || tmp.innerText || "").trim();
}

export default function IdeasPage() {
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [editing, setEditing] = useState<Idea | null>(null);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);

  const refresh = async () => {
    try {
      setIdeas(await getIdeas());
      setError("");
    } catch (e) {
      setError(`Fikirler yüklenemedi: ${(e as Error).message}`);
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
    <div className="h-full">
      <Card
        title="Fikirler"
        right={
          <Button variant="ghost" disabled={creating} onClick={() => void handleNew()}>
            {creating ? "Ekleniyor…" : "+ Fikir Ekle"}
          </Button>
        }
        bodyClassName="flex flex-col gap-3 overflow-y-auto p-4"
      >
        {error && (
          <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-300">
            {error}
          </div>
        )}
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
              <h3 className="truncate font-semibold text-emerald-400">
                {idea.title || "Başlıksız fikir"}
              </h3>
              <div className="mt-2 line-clamp-4 text-sm text-zinc-400">
                {preview(idea.content) || "Boş…"}
              </div>
              {idea.materials.length > 0 && (
                <div className="mt-2 text-xs text-zinc-500">
                  📎 {idea.materials.length} materyal
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
    </div>
  );
}

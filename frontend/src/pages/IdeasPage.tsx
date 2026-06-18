import { useEffect, useState } from "react";
import { getJournals, getJournalItems, deleteJournal, deleteJournalItem, analyzeJournals, upsertJournal, type Journal, type JournalItem } from "../api";
import { Card, Button, Badge } from "../ui";
import NotionEditor from "../components/NotionEditor";
import ReactMarkdown from "react-markdown";

export default function IdeasPage() {
  const [journals, setJournals] = useState<Journal[]>([]);
  const [items, setItems] = useState<JournalItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"fikir" | "görev" | "söz" | "eleştiri" | "hedef">("fikir");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Editor Modal
  const [editingJournal, setEditingJournal] = useState<Journal | null>(null);

  const refresh = async () => {
    const [j, i] = await Promise.all([getJournals(), getJournalItems()]);
    setJournals(j);
    setItems(i);
  };

  useEffect(() => {
    void refresh();
  }, []);

  const handleAnalyze = async () => {
    if (selectedIds.size === 0) return;
    setLoading(true);
    try {
      const res = await analyzeJournals(Array.from(selectedIds));
      alert(`${res.extracted} yeni öğe çıkarıldı.`);
      setSelectedIds(new Set());
      await refresh();
    } catch (e) {
      alert("Hata: " + (e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const toggleSelect = (id: string) => {
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedIds(next);
  };

  const filteredItems = items.filter((i) => {
    if (activeTab === "fikir") return i.type === "idea";
    if (activeTab === "görev") return i.type === "task";
    if (activeTab === "söz") return i.type === "promise";
    if (activeTab === "eleştiri") return i.type === "criticism";
    if (activeTab === "hedef") return i.type === "goal";
    return true;
  });

  return (
    <div className="grid h-full grid-cols-1 gap-4 lg:grid-cols-2">
      {/* Left: Journals */}
      <Card
        title="Günlükler & Notlar"
        right={
          <Button 
            variant="ghost" 
            onClick={handleAnalyze} 
            disabled={selectedIds.size === 0 || loading}
          >
            {loading ? "Analiz Ediliyor..." : `Yapay Zekaya Gönder (${selectedIds.size})`}
          </Button>
        }
        bodyClassName="flex flex-col gap-3 overflow-y-auto p-4"
      >
        {journals.map((j) => (
          <div key={j.id} className="group relative rounded-xl border border-line bg-elevated/60 p-4 transition-colors hover:border-line-strong">
            <div className="flex items-center gap-3">
              <input 
                type="checkbox" 
                className="h-4 w-4 rounded border-line-strong bg-zinc-800 text-emerald-500 focus:ring-emerald-500/50 focus:ring-offset-0"
                checked={selectedIds.has(j.id)}
                onChange={() => toggleSelect(j.id)}
                disabled={j.processed}
              />
              <div 
                className="flex-1 cursor-pointer"
                onClick={() => setEditingJournal(j)}
              >
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold text-emerald-400">{j.date}</h3>
                  {j.processed && <Badge tone="emerald">İşlendi</Badge>}
                </div>
                <div className="mt-2 line-clamp-3 text-sm text-zinc-400">
                  {j.content.replace(/<[^>]+>/g, '').slice(0, 150) || "Boş sayfa..."}
                </div>
              </div>
              <button 
                className="absolute right-4 top-4 hidden text-zinc-500 hover:text-rose-400 group-hover:block"
                onClick={async () => {
                  if (confirm("Emin misiniz?")) {
                    await deleteJournal(j.id);
                    await refresh();
                  }
                }}
              >
                Sil
              </button>
            </div>
          </div>
        ))}
      </Card>

      {/* Right: Items Tabbed View */}
      <Card
        title="Yapay Zeka Çıkarımları"
        bodyClassName="flex flex-col overflow-hidden"
      >
        <div className="flex shrink-0 gap-2 overflow-x-auto border-b border-line p-2">
          {["fikir", "görev", "hedef", "söz", "eleştiri"].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab as any)}
              className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === tab
                  ? "bg-emerald-500/10 text-emerald-400"
                  : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"
              }`}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {filteredItems.map((item) => (
              <div key={item.id} className="relative rounded-xl border border-line bg-surface-2/40 p-4">
                <div className="prose prose-sm prose-invert max-w-none text-zinc-300">
                  <ReactMarkdown>{item.content}</ReactMarkdown>
                </div>
                <button
                  onClick={async () => {
                    await deleteJournalItem(item.id);
                    await refresh();
                  }}
                  className="absolute right-2 top-2 text-xs text-zinc-600 hover:text-rose-400"
                >
                  ✕
                </button>
              </div>
            ))}
            {filteredItems.length === 0 && (
              <div className="col-span-full py-10 text-center text-sm text-zinc-500">
                Bu kategoride henüz bir çıkarım yok.
              </div>
            )}
          </div>
        </div>
      </Card>

      {/* Modal for editing journal */}
      {editingJournal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="flex h-[80vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-line bg-surface-2 shadow-2xl">
            <div className="flex items-center justify-between border-b border-line p-4">
              <h2 className="text-lg font-semibold text-zinc-100">{editingJournal.date}</h2>
              <button 
                className="text-zinc-400 hover:text-white"
                onClick={() => {
                  setEditingJournal(null);
                  void refresh();
                }}
              >
                Kapat
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">
              <NotionEditor 
                initialContent={editingJournal.content}
                onChange={async (html) => {
                  try {
                    const saved = await upsertJournal(editingJournal.date, html);
                    // update local state so we don't lose processed status on next refresh
                    setEditingJournal(saved);
                  } catch(e) {
                    console.error(e);
                  }
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

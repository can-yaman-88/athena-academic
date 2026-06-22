import { useEffect, useState } from "react";
import Modal from "./Modal";
import { useChat } from "../ChatContext";
import {
  getBrainFacts,
  createBrainFact,
  updateBrainFact,
  deleteBrainFact,
  extractBrainFacts,
  type BrainFact,
} from "../api";

/**
 * Brain modal — view / add / edit / delete the agent's long-term memory facts,
 * plus an on-demand "extract from recent chat" action (manual, per Phase 1
 * decision). Backed by the /brain REST endpoints.
 */
export default function BrainModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { lines } = useChat();
  const [facts, setFacts] = useState<BrainFact[]>([]);
  const [loading, setLoading] = useState(false);
  const [newText, setNewText] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [status, setStatus] = useState("");

  const refresh = async () => {
    setLoading(true);
    try {
      setFacts(await getBrainFacts());
    } catch (e) {
      setStatus(`Yüklenemedi: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) void refresh();
  }, [open]);

  const add = async () => {
    const t = newText.trim();
    if (!t) return;
    setNewText("");
    try {
      const fact = await createBrainFact(t);
      setFacts((prev) => [fact, ...prev]);
    } catch (e) {
      setStatus(`Eklenemedi: ${(e as Error).message}`);
    }
  };

  const saveEdit = async (id: string) => {
    const t = editText.trim();
    if (!t) return;
    try {
      const updated = await updateBrainFact(id, { text: t });
      setFacts((prev) => prev.map((f) => (f.id === id ? updated : f)));
    } catch (e) {
      setStatus(`Güncellenemedi: ${(e as Error).message}`);
    } finally {
      setEditingId(null);
    }
  };

  const togglePin = async (f: BrainFact) => {
    try {
      const updated = await updateBrainFact(f.id, { pinned: !f.pinned });
      setFacts((prev) =>
        [...prev.map((x) => (x.id === f.id ? updated : x))].sort(
          (a, b) => Number(b.pinned) - Number(a.pinned)
        )
      );
    } catch {
      /* ignore */
    }
  };

  const remove = async (id: string) => {
    try {
      await deleteBrainFact(id);
      setFacts((prev) => prev.filter((f) => f.id !== id));
    } catch (e) {
      setStatus(`Silinemedi: ${(e as Error).message}`);
    }
  };

  const extract = async () => {
    const history = lines
      .filter((l) => l.role !== "system")
      .slice(-20)
      .map((l) => ({ role: l.role === "agent" ? "assistant" : "user", text: l.text }));
    if (history.length === 0) {
      setStatus("Çıkarılacak sohbet geçmişi yok.");
      return;
    }
    setStatus("Sohbetten çıkarılıyor…");
    try {
      const { added, count } = await extractBrainFacts(history);
      if (count > 0) setFacts((prev) => [...added, ...prev]);
      setStatus(count > 0 ? `${count} yeni anı eklendi.` : "Yeni anı bulunamadı.");
    } catch (e) {
      setStatus(`Çıkarılamadı: ${(e as Error).message}`);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="🧠 Brain — Uzun Vadeli Hafıza" widthClass="max-w-2xl">
      <div className="flex h-[70vh] flex-col gap-3">
        {/* Add + extract */}
        <div className="flex gap-2">
          <input
            value={newText}
            onChange={(e) => setNewText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void add()}
            placeholder="Yeni bir anı ekle (örn: Kullanıcı bilgisayar mühendisliği okuyor)"
            className="field flex-1 px-3 py-2 text-sm"
          />
          <button
            onClick={() => void add()}
            className="rounded-lg bg-primary-500/90 px-3 py-2 text-sm font-medium text-zinc-950 hover:bg-primary-400"
          >
            Ekle
          </button>
          <button
            onClick={() => void extract()}
            title="Son sohbetten kalıcı bilgileri çıkar"
            className="rounded-lg border border-line-strong bg-elevated px-3 py-2 text-sm text-zinc-300 hover:border-primary-500 hover:text-primary-300"
          >
            Sohbetten çıkar
          </button>
        </div>

        {status && <div className="text-xs text-zinc-400">{status}</div>}

        {/* List */}
        <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto">
          {loading && <p className="text-sm text-zinc-500">Yükleniyor…</p>}
          {!loading && facts.length === 0 && (
            <p className="text-sm text-zinc-500">
              Henüz anı yok. Elle ekle veya bir sohbetten çıkar.
            </p>
          )}
          {facts.map((f) => (
            <div
              key={f.id}
              className="group flex items-start gap-2 rounded-lg border border-line bg-surface px-3 py-2"
            >
              <button
                onClick={() => void togglePin(f)}
                title={f.pinned ? "Sabitlemeyi kaldır" : "Sabitle"}
                className={`mt-0.5 text-sm ${f.pinned ? "text-primary-300" : "text-zinc-600 hover:text-zinc-400"}`}
              >
                📌
              </button>
              <div className="min-w-0 flex-1">
                {editingId === f.id ? (
                  <input
                    autoFocus
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void saveEdit(f.id);
                      if (e.key === "Escape") setEditingId(null);
                    }}
                    onBlur={() => void saveEdit(f.id)}
                    className="field w-full px-2 py-1 text-sm"
                  />
                ) : (
                  <p className="break-words text-sm text-zinc-200">{f.text}</p>
                )}
                <span className="text-[10px] uppercase tracking-wider text-zinc-600">
                  {f.category} · {f.source}
                </span>
              </div>
              <div className="flex shrink-0 gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                <button
                  onClick={() => {
                    setEditingId(f.id);
                    setEditText(f.text);
                  }}
                  className="px-1 text-zinc-400 hover:text-primary-300"
                  title="Düzenle"
                >
                  ✏️
                </button>
                <button
                  onClick={() => void remove(f.id)}
                  className="px-1 text-rose-500/60 hover:text-rose-400"
                  title="Sil"
                >
                  🗑
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </Modal>
  );
}

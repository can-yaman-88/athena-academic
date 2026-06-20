import { useRef, useState } from "react";
import { uploadPdf } from "../api";
import { Button } from "../ui";

export default function Dropzone({ onUploaded }: { onUploaded?: () => void }) {
  const [dragging, setDragging] = useState(false);
  const [status, setStatus] = useState("");
  const [instructions, setInstructions] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  async function send(file: File) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setStatus("Yalnızca .pdf dosyaları kabul edilir.");
      return;
    }
    setStatus(`Yükleniyor: ${file.name}…`);
    try {
      const res = await uploadPdf(file, instructions);
      setStatus(`✓ ${res.message}`);
      onUploaded?.();
    } catch (e) {
      setStatus(`✗ Yükleme başarısız: ${(e as Error).message}`);
    }
  }

  return (
    <div className="flex h-full flex-col gap-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const file = e.dataTransfer.files?.[0];
          if (file) void send(file);
        }}
        onClick={() => inputRef.current?.click()}
        className={`flex flex-1 cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed text-center transition ${
          dragging
            ? "border-primary-400 bg-primary-400/10"
            : "border-line-strong hover:border-zinc-500"
        }`}
      >
        <p className="text-sm text-zinc-200">PDF'i buraya sürükle ya da tıkla</p>
        <p className="mt-1 text-xs text-zinc-500">
          PDF → OCR/MD → LaTeX → sınav + Anki, sonra sohbet için indekslenir
        </p>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void send(file);
          }}
        />
      </div>
      <input
        value={instructions}
        onChange={(e) => setInstructions(e.target.value)}
        placeholder="İsteğe bağlı yönerge (örn. 'sadece özet ve formüller')"
        className="rounded-lg border border-line-strong bg-surface-2 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-primary-500"
        onClick={(e) => e.stopPropagation()}
      />
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-xs text-zinc-400">{status}</span>
        <Button variant="ghost" onClick={() => inputRef.current?.click()}>
          Dosya seç
        </Button>
      </div>
    </div>
  );
}

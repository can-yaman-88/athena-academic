import { useCallback, useEffect, useState } from "react";
import { getPdfJobs, type PdfJob } from "../api";
import { Button, Card } from "../ui";
import PdfHistory from "../components/PdfHistory";
import UsageMeters from "../components/UsageMeters";
import Dropzone from "../components/Dropzone";
import LogStream from "../components/LogStream";
import Modal from "../components/Modal";

export default function PdfPage() {
  const [jobs, setJobs] = useState<PdfJob[]>([]);
  const [logOpen, setLogOpen] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setJobs(await getPdfJobs());
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = setInterval(() => void refresh(), 5000);
    return () => clearInterval(id);
  }, [refresh]);

  return (
    // Two rows: top = history + (cost/upload); bottom = a large, full-width log
    // panel (≈2× its previous footprint).
    <div className="grid h-full grid-rows-[minmax(0,1fr)_minmax(0,22rem)] gap-4">
      <div className="grid min-h-0 grid-cols-1 gap-4 lg:grid-cols-[20rem_1fr]">
        {/* Left: past PDFs */}
        <Card
          title="Geçmiş PDF'ler"
          right={
            <Button variant="subtle" onClick={() => void refresh()}>
              ↻
            </Button>
          }
          bodyClassName="min-h-0 overflow-hidden"
        >
          <PdfHistory jobs={jobs} />
        </Card>

        {/* Middle: cost analytics (top) + upload (bottom) */}
        <div className="grid min-h-0 grid-rows-2 gap-4">
          <Card title="API Maliyet & Kullanım" bodyClassName="overflow-y-auto p-4">
            <UsageMeters />
          </Card>
          <Card title="PDF Yükle" bodyClassName="p-4">
            <Dropzone onUploaded={() => void refresh()} />
          </Card>
        </div>
      </div>

      {/* Bottom: large live log panel (with expand-to-modal) */}
      <div className="min-h-0">
        <LogStream
          right={
            <Button variant="ghost" onClick={() => setLogOpen(true)}>
              Genişlet
            </Button>
          }
        />
      </div>

      <Modal open={logOpen} onClose={() => setLogOpen(false)} title="Canlı Sistem Logları">
        <div className="h-[70vh]">
          <LogStream large />
        </div>
      </Modal>
    </div>
  );
}

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { syncRunalyze } from "./api";

// Runalyze sync state lives above the routed pages so it survives navigation —
// the button on WorkoutsPage no longer "resets" to its idle label when you leave
// and come back while a sync is running or after it finished.
interface SyncState {
  syncBusy: boolean;
  syncMsg: string;
  runSync: (onDone?: () => void | Promise<void>) => Promise<void>;
}

const SyncCtx = createContext<SyncState | null>(null);

export function SyncProvider({ children }: { children: ReactNode }) {
  const [syncBusy, setSyncBusy] = useState(false);
  const [syncMsg, setSyncMsg] = useState("");

  const runSync = useCallback(async (onDone?: () => void | Promise<void>) => {
    setSyncBusy(true);
    setSyncMsg("");
    try {
      const res = await syncRunalyze();
      setSyncMsg(`✓ ${res.imported} aktivite senkronize edildi`);
      if (onDone) await onDone();
    } catch (e) {
      setSyncMsg(`✗ ${(e as Error).message}`);
    } finally {
      setSyncBusy(false);
    }
  }, []);

  return (
    <SyncCtx.Provider value={{ syncBusy, syncMsg, runSync }}>
      {children}
    </SyncCtx.Provider>
  );
}

export function useSync(): SyncState {
  const ctx = useContext(SyncCtx);
  if (!ctx) throw new Error("useSync must be used within a SyncProvider");
  return ctx;
}

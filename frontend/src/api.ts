// Centralized API client. Base URL is injected at build time by Vite.
export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// --------------------------------------------------------------------------- //
// Types
// --------------------------------------------------------------------------- //
export interface Note {
  id: string;
  text: string;
  created_at: string;
}

export interface Material {
  id: string;
  kind: string;
  name: string;
  source: string;
  markdown_path: string | null;
}

export interface Task {
  id: string;
  title: string;
  // deadline & estimated_hours are nullable on the backend (optional fields).
  deadline: string | null;
  discipline: string;
  status: string;
  estimated_hours: number | null;
  category: "academic" | "daily";
  subtype: "project" | "assignment" | "study_session" | null;
  parent_id: string | null;
  progress: number;
  materials: Material[];
  notes: Note[];
  tags: string[];
}

export interface BrainFact {
  id: string;
  text: string;
  category: string;
  source: string;
  pinned: boolean;
  created_at: string;
  updated_at: string;
}

export interface PdfJob {
  id: string;
  filename: string;
  status: "processing" | "completed" | "failed";
  created_at: string;
  completed_at: string | null;
  artifacts: string[];
  cost_usd: number;
  chunks_ingested: number;
  error: string | null;
  summary: string;
}

export interface UsageCategory {
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  total_cost_usd: number;
  avg_cost_per_call_usd: number;
  avg_tokens_per_call: number;
  models: Record<string, { calls: number; cost_usd: number }>;
}

export interface UsageSnapshot {
  pdf: UsageCategory;
  agent: UsageCategory;
  total: { total_cost_usd: number; total_tokens: number };
}

export interface UsageLog {
  timestamp: string;
  category: string;
  model: string;
  label: string;
  prompt_tokens: string;
  completion_tokens: string;
  total_tokens: string;
  cost_usd: string;
}

export interface DashboardData {
  tasks: Task[];
  pending_count: number;
}

export interface LogRecord {
  ts: number;
  level: string;
  stage: string;
  message: string;
}

// --------------------------------------------------------------------------- //
// Helpers
// --------------------------------------------------------------------------- //
async function jget<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return res.json();
}

async function jsend<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return res.json();
}

// --------------------------------------------------------------------------- //
// Dashboard
// --------------------------------------------------------------------------- //
export const getModels = () => jget<{ models: string[] }>("/models").then((d) => d.models);

// --------------------------------------------------------------------------- //
export const getDashboard = () => jget<DashboardData>("/dashboard_data");

// --------------------------------------------------------------------------- //
// Tasks
// --------------------------------------------------------------------------- //
export const getTasks = () => jget<{ tasks: Task[] }>("/tasks").then((d) => d.tasks);

export const createTask = (t: {
  title: string;
  deadline?: string | null;
  discipline?: string;
  estimated_hours?: number;
  category?: "academic" | "daily";
  subtype?: "project" | "assignment" | "study_session" | null;
  parent_id?: string | null;
}) => jsend<Task>("/tasks", "POST", t);

export const getSubtasks = (id: string) =>
  jget<{ subtasks: Task[] }>(`/tasks/${id}/subtasks`).then((d) => d.subtasks);

// Notes
export const addNote = (taskId: string, text: string) =>
  jsend<Task>(`/tasks/${taskId}/notes`, "POST", { text });
export const editNote = (taskId: string, noteId: string, text: string) =>
  jsend<Task>(`/tasks/${taskId}/notes/${noteId}`, "PATCH", { text });
export const deleteNote = (taskId: string, noteId: string) =>
  jsend<Task>(`/tasks/${taskId}/notes/${noteId}`, "DELETE");

// Materials
export const addMaterial = (
  taskId: string,
  m: { kind?: string; name: string; source: string }
) => jsend<Task>(`/tasks/${taskId}/materials`, "POST", m);

export async function uploadTaskFile(taskId: string, file: File): Promise<Task> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}/tasks/${taskId}/files`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(`task file upload ${res.status}`);
  return res.json();
}

export const taskFileUrl = (taskId: string, materialId: string) =>
  `${API_URL}/tasks/${taskId}/materials/${materialId}/download`;

// AI features
export const generateSubtasks = (taskId: string) =>
  jsend<{ created: number; subtasks: Task[] }>(
    `/tasks/${taskId}/generate_subtasks`,
    "POST"
  );
export const analyzeNotes = () =>
  jsend<{
    task_progress_updates: number;
    message?: string;
  }>("/notes/analyze", "POST");

export const updateTask = (id: string, patch: Partial<Task>) =>
  jsend<Task>(`/tasks/${id}`, "PATCH", patch);

export const completeTask = (id: string) =>
  jsend<Task>(`/tasks/${id}/complete`, "POST");

export const deleteTask = (id: string) =>
  jsend<{ status: string }>(`/tasks/${id}`, "DELETE");

// --------------------------------------------------------------------------- //
// Brain (long-term memory)
// --------------------------------------------------------------------------- //
export const getBrainFacts = () =>
  jget<{ facts: BrainFact[] }>("/brain").then((d) => d.facts);

export const createBrainFact = (text: string, category = "fact", pinned = false) =>
  jsend<{ fact: BrainFact }>("/brain", "POST", { text, category, pinned }).then(
    (d) => d.fact
  );

export const updateBrainFact = (
  id: string,
  patch: Partial<Pick<BrainFact, "text" | "category" | "pinned">>
) => jsend<{ fact: BrainFact }>(`/brain/${id}`, "PATCH", patch).then((d) => d.fact);

export const deleteBrainFact = (id: string) =>
  jsend<{ status: string }>(`/brain/${id}`, "DELETE");

export const extractBrainFacts = (history: { role: string; text: string }[]) =>
  jsend<{ added: BrainFact[]; count: number }>("/brain/extract", "POST", { history });

// --------------------------------------------------------------------------- //
// PDF jobs + usage
// --------------------------------------------------------------------------- //
export const getPdfJobs = () =>
  jget<{ jobs: PdfJob[] }>("/pdf_jobs").then((d) => d.jobs);

export const artifactUrl = (jobId: string, fullPath: string) => {
  const name = fullPath.split("/").pop() ?? fullPath;
  return `${API_URL}/pdf_jobs/${jobId}/artifact/${encodeURIComponent(name)}`;
};

export const getUsage = () => jget<UsageSnapshot>("/usage");
export const getUsageLogs = (limit = 50) => jget<{ logs: UsageLog[] }>(`/usage/logs?limit=${limit}`).then(d => d.logs);

// --------------------------------------------------------------------------- //
// Upload
// --------------------------------------------------------------------------- //
export async function uploadPdf(
  file: File,
  instructions: string
): Promise<{ status: string; filename: string; message: string }> {
  const form = new FormData();
  form.append("file", file);
  form.append("instructions", instructions);
  const res = await fetch(`${API_URL}/upload`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`upload ${res.status}`);
  return res.json();
}

// --------------------------------------------------------------------------- //
// Chat attachments
// --------------------------------------------------------------------------- //
export interface ChatAttachment {
  id: string;
  name: string;
  kind: string;
  markdown_preview: string;
  chars: number;
}

export async function uploadChatFile(file: File): Promise<ChatAttachment> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}/chat/upload`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`chat upload ${res.status}`);
  return res.json();
}

// --------------------------------------------------------------------------- //
// Chat SSE
// --------------------------------------------------------------------------- //
export async function streamChat(
  message: string,
  onEvent: (evt: Record<string, unknown>) => void,
  attachmentIds: string[] = []
): Promise<void> {
  const res = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, attachment_ids: attachmentIds }),
  });
  if (!res.ok || !res.body) throw new Error(`chat ${res.status}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.trim();
      if (!line.startsWith("data:")) continue;
      try {
        onEvent(JSON.parse(line.slice(5).trim()));
      } catch {
        /* ignore malformed frame */
      }
    }
  }
}

// --------------------------------------------------------------------------- //
// Journals & Ideas
// --------------------------------------------------------------------------- //

export interface Journal {
  id: string;
  date: string; // YYYY-MM-DD
  content: string;
  processed: boolean;
}

export interface JournalItem {
  id: string;
  journal_id: string;
  type: "idea" | "promise" | "criticism" | "goal" | "task";
  content: string;
}

export const getJournals = () => jget<Journal[]>("/journals");
export const upsertJournal = (date: string, content: string) =>
  jsend<Journal>("/journals", "POST", { date, content });
export const deleteJournal = (id: string) => jsend<{ status: string }>(`/journals/${id}`, "DELETE");

export const getJournalItems = () => jget<JournalItem[]>("/journal-items");
export const deleteJournalItem = (id: string) => jsend<{ status: string }>(`/journal-items/${id}`, "DELETE");

export const analyzeJournals = (journalIds: string[]) =>
  jsend<{ status: string; extracted: number }>("/journals/ai-analyze", "POST", {
    journal_ids: journalIds,
  });

// --------------------------------------------------------------------------- //
// Daily Notes
// --------------------------------------------------------------------------- //
export interface DailyNote {
  id: string;
  date: string;
  content: string;
  created_at: string;
  updated_at: string;
}

export const getDailyNotes = () => jget<DailyNote[]>("/daily_notes");
export const upsertDailyNote = (date: string, content: string) =>
  jsend<DailyNote>("/daily_notes", "POST", { date, content });

// --------------------------------------------------------------------------- //
// Ideas (free-form notes with materials; no AI processing)
// --------------------------------------------------------------------------- //
export interface Idea {
  id: string;
  title: string;
  content: string;
  materials: Material[];
  created_at: string;
  updated_at: string;
}

export const getIdeas = () => jget<Idea[]>("/ideas");
export const createIdea = (title = "", content = "") =>
  jsend<Idea>("/ideas", "POST", { title, content });
export const updateIdea = (id: string, patch: { title?: string; content?: string }) =>
  jsend<Idea>(`/ideas/${id}`, "PATCH", patch);
export const deleteIdea = (id: string) =>
  jsend<{ status: string }>(`/ideas/${id}`, "DELETE");

export const addIdeaMaterial = (
  id: string,
  m: { kind?: string; name: string; source: string }
) => jsend<Idea>(`/ideas/${id}/materials`, "POST", m);

export async function uploadIdeaFile(id: string, file: File): Promise<Idea> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}/ideas/${id}/files`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(`idea file upload ${res.status}`);
  return res.json();
}

export const ideaFileUrl = (id: string, materialId: string) =>
  `${API_URL}/ideas/${id}/materials/${materialId}/download`;

// --------------------------------------------------------------------------- //
// Notes (Notion-style nested pages)
// --------------------------------------------------------------------------- //
export interface NotePage {
  id: string;
  title: string;
  content: string;
  parent_id: string | null;
  depth: number;
  created_at: string;
  updated_at: string;
}

export const getNotes = () => jget<NotePage[]>("/notes");
export const getNote = (id: string) => jget<NotePage>(`/notes/${id}`);
export const getNoteChildren = (id: string) =>
  jget<NotePage[]>(`/notes/${id}/children`);
export const createNote = (title = "", parentId?: string, content = "") =>
  jsend<NotePage>("/notes", "POST", { title, content, parent_id: parentId ?? null });
export const updateNote = (id: string, patch: { title?: string; content?: string }) =>
  jsend<NotePage>(`/notes/${id}`, "PATCH", patch);
export const deleteNotePage = (id: string) =>
  jsend<{ status: string }>(`/notes/${id}`, "DELETE");

// Inline editor asset upload (images/files embedded in note/idea bodies).
export interface InlineUploadResult {
  url: string;
  name: string;
  kind: string;
}
export async function uploadInline(file: File): Promise<InlineUploadResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}/uploads/inline`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`inline upload ${res.status}`);
  return res.json();
}

// --------------------------------------------------------------------------- //
// Tags
// --------------------------------------------------------------------------- //
export const getTags = () => jget<string[]>("/tags");

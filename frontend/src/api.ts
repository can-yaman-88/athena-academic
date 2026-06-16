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
  deadline: string;
  discipline: string;
  status: string;
  estimated_hours: number;
  category: "academic" | "daily";
  subtype: "project" | "assignment" | "study_session" | null;
  parent_id: string | null;
  progress: number;
  materials: Material[];
  notes: Note[];
}

export interface CognitiveLoad {
  calculated_load: number;
  heavy_cognitive_blocked: boolean;
  block_duration_hours: number;
  recommended_tasks: string[];
  blocked_until: string | null;
  directive: string;
}

export interface Workout {
  id: string;
  date: string;
  duration_minutes: number;
  rpe_score: number;
  calculated_load: number;
  status: "planned" | "completed";
  title: string | null;
  distance_km: number | null;
  pace: string | null;
  avg_speed_kmh: number | null;
  avg_hr: number | null;
}

export interface WorkoutInput {
  duration_minutes: number;
  rpe_score: number;
  date?: string;
  status?: "planned" | "completed";
  title?: string | null;
  distance_km?: number | null;
  pace?: string | null;
  avg_speed_kmh?: number | null;
  avg_hr?: number | null;
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

export interface DashboardData {
  tasks: Task[];
  pending_count: number;
  cognitive_load: CognitiveLoad;
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
export const getDashboard = () => jget<DashboardData>("/dashboard_data");

// --------------------------------------------------------------------------- //
// Tasks
// --------------------------------------------------------------------------- //
export const getTasks = () => jget<{ tasks: Task[] }>("/tasks").then((d) => d.tasks);

export const createTask = (t: {
  title: string;
  deadline: string;
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
    cognitive_load_additions: number;
    task_progress_updates: number;
    added_load?: number;
    message?: string;
  }>("/notes/analyze", "POST");

export const updateTask = (id: string, patch: Partial<Task>) =>
  jsend<Task>(`/tasks/${id}`, "PATCH", patch);

export const completeTask = (id: string) =>
  jsend<Task>(`/tasks/${id}/complete`, "POST");

export const deleteTask = (id: string) =>
  jsend<{ status: string }>(`/tasks/${id}`, "DELETE");

// --------------------------------------------------------------------------- //
// Workouts
// --------------------------------------------------------------------------- //
export const getWorkouts = () =>
  jget<{ workouts: Workout[] }>("/workouts").then((d) => d.workouts);

export const createWorkout = (w: WorkoutInput) =>
  jsend<{ physical_load: Workout; cognitive_allowance: CognitiveLoad }>(
    "/workouts",
    "POST",
    w
  );

export const updateWorkout = (id: string, patch: Partial<WorkoutInput>) =>
  jsend<Workout>(`/workouts/${id}`, "PATCH", patch);

export const completeWorkout = (id: string) =>
  jsend<Workout>(`/workouts/${id}/complete`, "POST");

export const deleteWorkout = (id: string) =>
  jsend<{ status: string }>(`/workouts/${id}`, "DELETE");

export async function uploadWorkoutFile(
  file: File
): Promise<{ imported: number; workouts: Workout[] }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}/workouts/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(`workout upload ${res.status}`);
  return res.json();
}

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

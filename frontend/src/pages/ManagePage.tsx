import { Card } from "../ui";
import TaskManager from "../components/TaskManager";

export default function ManagePage() {
  return (
    <div className="h-full">
      <Card title="Görevler — Akademik & Günlük" bodyClassName="min-h-0 p-4 h-full">
        <TaskManager />
      </Card>
    </div>
  );
}

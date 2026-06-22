import { Card } from "../ui";
import TaskManager from "../components/TaskManager";

export default function AcademicTasksPage() {
  return (
    <div className="h-full">
      <Card title="Akademik Görevler" bodyClassName="min-h-0 p-4 h-full">
        <TaskManager category="academic" />
      </Card>
    </div>
  );
}

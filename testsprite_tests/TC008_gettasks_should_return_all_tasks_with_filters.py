import requests

BASE_URL = "http://localhost:8888"
TIMEOUT = 30
HEADERS = {
    "Accept": "application/json"
}

def test_gettasks_should_return_all_tasks_with_filters():
    created_task_ids = []
    try:
        # Create two tasks with different categories and statuses for filtering
        task_data_1 = {
            "title": "Academic Task for Test TC008",
            "category": "academic",
            "status": "pending",
            "deadline": "2026-07-01T12:00:00Z",
            "discipline": "Matematik",
            "estimated_hours": 2
        }
        resp1 = requests.post(f"{BASE_URL}/tasks", json=task_data_1, headers=HEADERS, timeout=TIMEOUT)
        assert resp1.status_code == 201, f"Failed to create academic task, status {resp1.status_code}"
        task1 = resp1.json()
        created_task_ids.append(task1.get("id"))
        assert task1.get("category") == "academic"
        assert task1.get("status") == "pending"

        task_data_2 = {
            "title": "Daily Task for Test TC008",
            "category": "daily",
            "status": "completed",
            "deadline": "2026-07-02T15:00:00Z",
            "discipline": None,
            "estimated_hours": 1
        }
        resp2 = requests.post(f"{BASE_URL}/tasks", json=task_data_2, headers=HEADERS, timeout=TIMEOUT)
        assert resp2.status_code == 201, f"Failed to create daily task, status {resp2.status_code}"
        task2 = resp2.json()
        created_task_ids.append(task2.get("id"))
        assert task2.get("category") == "daily"
        assert task2.get("status") == "completed"

        # 1) Retrieve all tasks without filters
        resp_all = requests.get(f"{BASE_URL}/tasks", headers=HEADERS, timeout=TIMEOUT)
        assert resp_all.status_code == 200, f"GET /tasks failed with status {resp_all.status_code}"
        all_tasks = resp_all.json()["tasks"]
        # Check that previously created tasks are present in full list
        all_task_ids = [t.get("id") for t in all_tasks]
        assert task1["id"] in all_task_ids
        assert task2["id"] in all_task_ids

        # 2) Filter by category = academic
        resp_academic = requests.get(f"{BASE_URL}/tasks", params={"category": "academic"}, headers=HEADERS, timeout=TIMEOUT)
        assert resp_academic.status_code == 200, f"GET /tasks?category=academic failed with status {resp_academic.status_code}"
        academic_tasks = resp_academic.json()["tasks"]
        # All returned tasks category must be academic
        assert all(t.get("category") == "academic" for t in academic_tasks)
        # The academic test task created must be included
        assert any(t.get("id") == task1["id"] for t in academic_tasks)

        # 3) Filter by category = daily
        resp_daily = requests.get(f"{BASE_URL}/tasks", params={"category": "daily"}, headers=HEADERS, timeout=TIMEOUT)
        assert resp_daily.status_code == 200, f"GET /tasks?category=daily failed with status {resp_daily.status_code}"
        daily_tasks = resp_daily.json()["tasks"]
        assert all(t.get("category") == "daily" for t in daily_tasks)
        assert any(t.get("id") == task2["id"] for t in daily_tasks)

        # 4) Filter by status = completed
        resp_completed = requests.get(f"{BASE_URL}/tasks", params={"status": "completed"}, headers=HEADERS, timeout=TIMEOUT)
        assert resp_completed.status_code == 200, f"GET /tasks?status=completed failed with status {resp_completed.status_code}"
        completed_tasks = resp_completed.json()["tasks"]
        assert all(t.get("status") == "completed" for t in completed_tasks)
        assert any(t.get("id") == task2["id"] for t in completed_tasks)

        # 5) Filter by status = pending
        resp_pending = requests.get(f"{BASE_URL}/tasks", params={"status": "pending"}, headers=HEADERS, timeout=TIMEOUT)
        assert resp_pending.status_code == 200, f"GET /tasks?status=pending failed with status {resp_pending.status_code}"
        pending_tasks = resp_pending.json()["tasks"]
        assert all(t.get("status") == "pending" for t in pending_tasks)
        assert any(t.get("id") == task1["id"] for t in pending_tasks)

        # 6) Filter by category=academic and status=pending together
        resp_filtered = requests.get(f"{BASE_URL}/tasks", params={"category": "academic", "status": "pending"}, headers=HEADERS, timeout=TIMEOUT)
        assert resp_filtered.status_code == 200, f"GET /tasks with combined filters failed with status {resp_filtered.status_code}"
        filtered_tasks = resp_filtered.json()["tasks"]
        assert all(t.get("category") == "academic" and t.get("status") == "pending" for t in filtered_tasks)
        assert any(t.get("id") == task1["id"] for t in filtered_tasks)

    finally:
        # Cleanup created tasks
        for tid in created_task_ids:
            try:
                requests.delete(f"{BASE_URL}/tasks/{tid}", headers=HEADERS, timeout=TIMEOUT)
            except Exception:
                pass

test_gettasks_should_return_all_tasks_with_filters()
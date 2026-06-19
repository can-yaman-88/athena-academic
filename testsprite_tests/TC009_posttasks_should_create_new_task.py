import requests
import uuid

BASE_URL = "http://localhost:8888"
TIMEOUT = 30

def test_posttasks_should_create_new_task():
    # NOTE: `category` is the English enum (`academic`/`daily`), and GET /tasks
    # returns `{"tasks": [...]}`. Updated to match the real API contract.
    headers = {"Content-Type": "application/json"}
    unique_title = f"Test Görev {uuid.uuid4()}"
    new_task_payload = {
        "title": unique_title,
        "category": "academic",  # academic | daily
        "deadline": "2026-12-31T23:59:59+00:00",
        "discipline": "Matematik",
        "estimated_hours": 3,
        "subtype": "project",
    }

    task_id = None
    try:
        # Create a new task
        response = requests.post(f"{BASE_URL}/tasks", json=new_task_payload, headers=headers, timeout=TIMEOUT)
        assert response.status_code == 201 or response.status_code == 200, f"Beklenmeyen durum kodu: {response.status_code}"
        task = response.json()
        assert "id" in task, "Yanıt içinde 'id' yok"
        task_id = task["id"]
        assert task["title"] == unique_title, "Görev başlığı eşleşmiyor"
        assert task.get("category") in ["academic", "daily"], "Kategori geçerli değil"

        # Verify the new task appears in the task list
        list_response = requests.get(f"{BASE_URL}/tasks", headers=headers, timeout=TIMEOUT)
        assert list_response.status_code == 200, f"Beklenmeyen listeme durum kodu: {list_response.status_code}"
        tasks_list = list_response.json()["tasks"]
        assert any(t.get("id") == task_id for t in tasks_list), "Yeni oluşturulan görev listede bulunamadı"
    finally:
        # Clean up: delete the created task if it was created
        if task_id:
            del_response = requests.delete(f"{BASE_URL}/tasks/{task_id}", headers=headers, timeout=TIMEOUT)
            assert del_response.status_code == 200 or del_response.status_code == 204, f"Silme başarısız, durum kodu: {del_response.status_code}"

test_posttasks_should_create_new_task()

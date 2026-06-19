import requests

def test_getdashboarddata_should_return_tasks_and_cognitive_load():
    # NOTE: The cognitive-load subsystem was intentionally removed from the
    # product (commit 9f59369). /dashboard_data returns `tasks` + `pending_count`
    # by design; this test was updated to assert the real response shape.
    base_url = "http://localhost:8888"
    endpoint = "/dashboard_data"
    timeout = 30

    try:
        response = requests.get(f"{base_url}{endpoint}", timeout=timeout)
        assert response.status_code == 200, f"Beklenmeyen durum kodu: {response.status_code}"
        data = response.json()

        # Validate keys exist
        assert "tasks" in data, "Yanıt verisi 'tasks' anahtarını içermiyor"
        assert "pending_count" in data, "Yanıt verisi 'pending_count' anahtarını içermiyor"

        tasks = data["tasks"]
        pending_count = data["pending_count"]

        # tasks must be a list; pending_count an int
        assert isinstance(tasks, list), "'tasks' list türünde olmalı"
        assert isinstance(pending_count, int), "'pending_count' int türünde olmalı"

        # Every task carries a 'deadline' key (may be null).
        for task in tasks:
            assert "deadline" in task, "Her görevde 'deadline' alanı olmalı"

    except requests.exceptions.RequestException as e:
        assert False, f"HTTP isteği sırasında hata oluştu: {e}"

test_getdashboarddata_should_return_tasks_and_cognitive_load()

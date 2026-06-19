import requests

BASE_URL = "http://localhost:8888"
TIMEOUT = 30

def test_getpdfjobs_should_return_pdf_job_history_with_statuses():
    url = f"{BASE_URL}/pdf_jobs"
    headers = {
        "Accept": "application/json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        assert response.status_code == 200, f"Beklenen 200 değil, gelen: {response.status_code}"

        data = response.json()
        # Check if response is list or dict containing a list under 'jobs'
        if isinstance(data, dict) and "jobs" in data and isinstance(data["jobs"], list):
            jobs = data["jobs"]
        else:
            jobs = data

        assert isinstance(jobs, list), "Dönen veri liste olmalı."

        for job in jobs:
            # Each job should be a dict with expected keys
            assert isinstance(job, dict), "Her iş tekil obje olmalı."
            # Check required keys presence
            assert "id" in job, "Her işte 'id' olmalı."
            assert "status" in job, "Her işte 'status' olmalı."
            assert "created_at" in job or "updated_at" in job, "Her işte 'created_at' veya 'updated_at' olmalı."
            # Status is the PdfJobStatus enum value (English): processing | completed | failed.
            assert isinstance(job["status"], str), "'status' alanı metin olmalı."
            assert job["status"] in [
                "processing", "completed", "failed"
            ], f"Bilinmeyen durum: {job['status']}"
            
            # Check updated entries (updated_at in ISO 8601 format)
            if "updated_at" in job:
                assert isinstance(job["updated_at"], str), "'updated_at' metin formatında olmalı."
                # Simple ISO8601 format check: ends with Z or contains T
                assert "T" in job["updated_at"], "'updated_at' ISO format (örn. 2020-01-01T12:00:00Z) olmalı."

    except requests.Timeout:
        assert False, "İstek zaman aşımına uğradı"
    except requests.RequestException as e:
        assert False, f"İstek sırasında hata oluştu: {e}"

test_getpdfjobs_should_return_pdf_job_history_with_statuses()

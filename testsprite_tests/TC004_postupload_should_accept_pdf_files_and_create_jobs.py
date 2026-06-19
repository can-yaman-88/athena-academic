import requests
import time
import uuid

BASE_URL = "http://localhost:8888"
UPLOAD_ENDPOINT = f"{BASE_URL}/upload"
PDF_JOBS_ENDPOINT = f"{BASE_URL}/pdf_jobs"
TIMEOUT = 120  # seconds

def test_postupload_should_accept_pdf_files_and_create_jobs():
    # Prepare a small PDF file content (simple valid PDF header and minimal content)
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj\n"
        b"2 0 obj <</Type /Pages /Count 1 /Kids [3 0 R]>> endobj\n"
        b"3 0 obj <</Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R>> endobj\n"
        b"4 0 obj <</Length 44>> stream\n"
        b"BT /F1 24 Tf 50 180 Td (Test PDF) Tj ET\n"
        b"endstream endobj\n"
        b"xref\n0 5\n0000000000 65535 f \n0000000010 00000 n \n0000000053 00000 n \n0000000100 00000 n \n0000000193 00000 n \n"
        b"trailer <</Size 5 /Root 1 0 R>>\nstartxref\n278\n%%EOF\n"
    )

    # Unique processing instruction with UUID to avoid collision for test data
    unique_instruction = f"Test processing instructions - {uuid.uuid4()}"

    files = {
        "file": ("test.pdf", pdf_content, "application/pdf"),
    }
    data = {
        "processing_instructions": unique_instruction
    }

    # POST /upload to upload PDF with optional instructions
    try:
        response = requests.post(
            UPLOAD_ENDPOINT,
            files=files,
            data=data,
            timeout=TIMEOUT
        )
        # Verify response status code is 200 or 201 (depending on server behavior)
        assert response.status_code in (200, 201), f"Upload failed with status {response.status_code}: {response.text}"

        json_resp = response.json()
        # There should be some job identifier or success message in response
        assert "job_id" in json_resp or "id" in json_resp or "message" in json_resp, "No job identifier or confirmation in response"

        # The job_id or id to check in history, fallback keys
        job_identifier = json_resp.get("job_id") or json_resp.get("id")

        # Poll pdf_jobs endpoint until the new job appears or timeout
        start_time = time.time()
        job_found = False
        while time.time() - start_time < TIMEOUT:
            jobs_response = requests.get(PDF_JOBS_ENDPOINT, timeout=30)
            assert jobs_response.status_code == 200, f"Failed to get pdf_jobs list: {jobs_response.status_code}"
            jobs = jobs_response.json()
            # /pdf_jobs returns {"jobs": [...]}; unwrap to the list.
            if isinstance(jobs, dict):
                jobs = jobs.get("jobs", [])
            for job in jobs:
                # Check for job by id or by matching unique_processing_instruction in details
                if job_identifier and str(job.get("id")) == str(job_identifier):
                    job_found = True
                    # Verify job has a status attribute and title or filename mentions PDF
                    assert "status" in job, "Job missing status field"
                    # Optionally check processing instructions reflected or filename includes ".pdf"
                    job_desc_fields = [str(job.get(k, "")).lower() for k in ["processing_instructions", "filename", "title", "description"]]
                    assert any(".pdf" in f or unique_instruction.lower() in f for f in job_desc_fields), "Job details do not match uploaded PDF or instructions"
                    break
                # If identifier not returned, try matching processing_instructions on any job
                elif not job_identifier and "processing_instructions" in job:
                    if unique_instruction == job["processing_instructions"]:
                        job_found = True
                        break
            if job_found:
                break
            time.sleep(3)

        assert job_found, "Uploaded PDF job did not appear in /pdf_jobs history within timeout"

    except requests.RequestException as e:
        assert False, f"Request failed: {e}"

test_postupload_should_accept_pdf_files_and_create_jobs()
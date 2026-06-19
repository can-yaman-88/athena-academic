import requests
import io
import json
import csv

BASE_URL = "http://localhost:8888"
TIMEOUT = 30

def postworkoutsupload_should_import_workouts_from_files():
    url = f"{BASE_URL}/workouts/upload"
    headers = {}

    def post_file(file_content, filename, content_type):
        file_content.seek(0)
        files = {
            'file': (filename, file_content, content_type)
        }
        try:
            response = requests.post(url, files=files, headers=headers, timeout=TIMEOUT)
            response.raise_for_status()
            data = response.json()
            assert isinstance(data, dict), "Response JSON should be a dictionary"
        except requests.exceptions.RequestException as e:
            assert False, f"Request failed: {e}"
        except json.JSONDecodeError:
            assert False, "Response is not a valid JSON"
        return response

    # 1) Test JSON file upload
    json_workouts = [
        {"name": "Koşu", "duration": 3600, "RPE": 7},
        {"name": "Bisiklet", "duration": 5400, "RPE": 6}
    ]
    json_bytes = io.BytesIO(json.dumps(json_workouts, ensure_ascii=False).encode('utf-8'))
    response_json = post_file(json_bytes, "workouts.json", "application/json")
    assert response_json.status_code == 200

    # 2) Test CSV file upload
    csv_buffer = io.StringIO()
    csv_writer = csv.writer(csv_buffer)
    csv_writer.writerow(["name", "duration", "RPE"])
    csv_writer.writerow(["Yüzme", "1800", "5"])
    csv_writer.writerow(["Kuvvet Antremanı", "3600", "8"])
    csv_bytes = io.BytesIO(csv_buffer.getvalue().encode('utf-8'))
    response_csv = post_file(csv_bytes, "workouts.csv", "text/csv")
    assert response_csv.status_code == 200

    # 3) Test FIT file upload - minimal valid FIT file content for test
    fit_bytes_content = b'\x0E\x10\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
    fit_bytes_io = io.BytesIO(fit_bytes_content)
    response_fit = post_file(fit_bytes_io, "workout.fit", "application/octet-stream")
    assert response_fit.status_code == 200

postworkoutsupload_should_import_workouts_from_files()
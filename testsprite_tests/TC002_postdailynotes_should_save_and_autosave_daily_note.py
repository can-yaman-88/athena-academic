import requests
import uuid

BASE_URL = "http://localhost:8888"
TIMEOUT = 30

def postdailynotes_should_save_daily_note():
    headers = {
        "Content-Type": "application/json"
    }
    
    unique_id = str(uuid.uuid4())
    content = f"<p>Günlük not içerik testi {unique_id} - Kayıt</p>"

    # Step 1: POST to /daily_notes to create a new daily note
    post_payload = {
        "content": content
    }
    post_response = requests.post(f"{BASE_URL}/daily_notes", json=post_payload, headers=headers, timeout=TIMEOUT)
    assert post_response.status_code == 200 or post_response.status_code == 201, f"Expected 200 or 201, got {post_response.status_code}"
    post_data = post_response.json()
    # According to PRD, response fields not defined, so just ensure content is in response
    assert isinstance(post_data, dict), "Expected response to be a dict"
    assert post_data.get("content") == content, "Saved content does not match the posted content"

    # Step 2: GET /daily_notes to verify note presence
    get_response = requests.get(f"{BASE_URL}/daily_notes", headers=headers, timeout=TIMEOUT)
    assert get_response.status_code == 200, f"Expected 200, got {get_response.status_code}"
    notes_list = get_response.json()
    assert isinstance(notes_list, list), "Expected response to be a list of daily notes"

    matched_notes = [note for note in notes_list if note.get("content") == content]
    assert len(matched_notes) > 0, "Created daily note not found in GET /daily_notes response"

postdailynotes_should_save_daily_note()

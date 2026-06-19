import requests
import time

BASE_URL = "http://localhost:8888"
TIMEOUT = 30
HEADERS = {
    "Content-Type": "application/json",
}

def test_postchat_should_process_messages_and_slash_commands():
    # NOTE: /chat takes a single `message` string and replies as an SSE stream
    # (it is not an OpenAI-style `messages[]` endpoint). Updated to match.
    url = f"{BASE_URL}/chat"

    payload = {
        "message": "/yardim"
    }

    try:
        response = requests.post(url, json=payload, headers=HEADERS, timeout=TIMEOUT, stream=True)
        assert response.status_code == 200, f"Beklenmeyen durum kodu: {response.status_code}"

        received_events = 0
        start_time = time.time()

        # Manually parse lines in SSE format
        for line in response.iter_lines(decode_unicode=True):
            if line and line.startswith('data:'):
                data = line[5:].strip()
                assert data != "", "Boş event datası geldi"
                received_events += 1
            if received_events >= 1 or (time.time() - start_time) > 25:
                break

        assert received_events >= 1, "En az bir SSE event alınmalı"

    except requests.exceptions.RequestException as e:
        assert False, f"HTTP isteği hatası: {e}"
    except Exception as e:
        assert False, f"Test sırasında hata: {e}"


test_postchat_should_process_messages_and_slash_commands()

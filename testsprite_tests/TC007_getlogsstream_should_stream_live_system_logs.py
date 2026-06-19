import requests
import threading
import time

BASE_URL = "http://localhost:8888"
LOGS_STREAM_ENDPOINT = f"{BASE_URL}/logs/stream"
TIMEOUT = 30

def test_getlogsstream_should_stream_live_system_logs():
    """
    Verify that the GET /logs/stream endpoint streams live system logs continuously
    and at least one event is received (SSE).
    """

    received_events = []

    def listen_to_stream():
        try:
            with requests.get(LOGS_STREAM_ENDPOINT, stream=True, timeout=TIMEOUT) as response:
                response.raise_for_status()
                start_time = time.time()
                buffer = ''
                for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
                    if chunk:
                        buffer += chunk
                        while '\n\n' in buffer:
                            event_data, buffer = buffer.split('\n\n', 1)
                            lines = event_data.split('\n')
                            for line in lines:
                                if line.startswith('data:'):
                                    data_value = line[5:].strip()
                                    if data_value:
                                        received_events.append(data_value)
                                        return  # Stop after receiving the first event
                    if time.time() - start_time > TIMEOUT:
                        break
        except requests.exceptions.RequestException as e:
            received_events.append(f"error: {str(e)}")

    listener_thread = threading.Thread(target=listen_to_stream)
    listener_thread.start()
    listener_thread.join(TIMEOUT + 5)

    assert len(received_events) > 0, "No events received from /logs/stream endpoint"
    assert not received_events[0].startswith("error"), f"Request error occurred: {received_events[0]}"

test_getlogsstream_should_stream_live_system_logs()

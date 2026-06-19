import requests

BASE_URL = "http://localhost:8888"
TIMEOUT = 30

def test_getusage_should_return_api_cost_meters_for_pdf_and_agent():
    url = f"{BASE_URL}/usage"
    headers = {
        "Accept": "application/json",
    }

    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as e:
        assert False, f"Request to /usage failed: {e}"

    data = response.json()

    # Assert that data has keys for both 'pdf' and 'agent' cost metrics
    assert isinstance(data, dict), "Response should be a JSON object"
    assert "pdf" in data, "'pdf' key missing in usage response"
    assert "agent" in data, "'agent' key missing in usage response"

    # Validate that pdf and agent cost metrics are present and are dictionaries
    assert isinstance(data["pdf"], dict), "'pdf' value should be an object with cost metrics"
    assert isinstance(data["agent"], dict), "'agent' value should be an object with cost metrics"

    # Check presence of expected cost metric keys
    expected_keys = ["cost_usd"]
    for category in ["pdf", "agent"]:
        for key in expected_keys:
            assert key in data[category], f"'{key}' missing in '{category}' cost metrics"
            # Validate numeric values and non-negative
            value = data[category][key]
            assert isinstance(value, (int, float)), f"'{key}' in '{category}' should be a number"
            assert value >= 0, f"'{key}' in '{category}' should be non-negative"

test_getusage_should_return_api_cost_meters_for_pdf_and_agent()

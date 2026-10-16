import pytest
import requests_mock

from cis_report.defender import CIS_STANDARDS, DefenderClient, DefenderError

SUB = "5374e8d3-9703-4a09-ac4a-af6f9f5c013b"
API_VERSION = "2019-01-01-preview"
BASE = f"https://management.azure.com/subscriptions/{SUB}/providers/Microsoft.Security"
STD = "CIS-Azure-Foundations-v2.0.0"
CONTROLS_URL = f"{BASE}/regulatoryComplianceStandards/{STD}/regulatoryComplianceControls"


def assessments_url(control):
    return f"{CONTROLS_URL}/{control}/regulatoryComplianceAssessments"


class FakeToken:
    def __init__(self, token):
        self.token = token


class FakeCredential:
    """Stands in for azure-identity; the real credential needs Azure."""

    def get_token(self, *scopes):
        self.scopes = scopes
        return FakeToken("tok-123")


@pytest.fixture
def client():
    return DefenderClient(SUB, FakeCredential(), retry_backoff=0)


def test_cis_standards_are_the_two_benchmarks_in_scope():
    assert CIS_STANDARDS == (
        "CIS-Azure-Foundations-v1.4.0",
        "CIS-Azure-Foundations-v2.0.0",
    )


def test_requests_send_bearer_token_and_api_version(client):
    with requests_mock.Mocker() as m:
        m.get(CONTROLS_URL, json={"value": []})
        client.list_controls(STD)
        request = m.request_history[0]
    assert request.headers["Authorization"] == "Bearer tok-123"
    assert request.qs["api-version"] == [API_VERSION]


def test_list_controls_follows_next_link_across_pages(client):
    next_url = f"{CONTROLS_URL}?page=2&api-version={API_VERSION}"
    with requests_mock.Mocker() as m:
        m.get(CONTROLS_URL, json={"value": [{"name": "1.1"}], "nextLink": next_url})
        m.get(next_url, json={"value": [{"name": "1.2"}]})
        controls = client.list_controls(STD)
    assert [c["name"] for c in controls] == ["1.1", "1.2"]


def test_list_assessments_returns_empty_for_control_without_data(client):
    error = {"error": {"code": "NoRegulatoyComplianceDataFound", "message": "none"}}
    with requests_mock.Mocker() as m:
        m.get(assessments_url("1.1"), status_code=404, json=error)
        assert client.list_assessments(STD, "1.1") == []


def test_other_not_found_errors_raise(client):
    error = {"error": {"code": "ResourceNotFound", "message": "gone"}}
    with requests_mock.Mocker() as m:
        m.get(assessments_url("1.1"), status_code=404, json=error)
        with pytest.raises(DefenderError, match="ResourceNotFound"):
            client.list_assessments(STD, "1.1")


def test_authorization_failures_raise(client):
    error = {"error": {"code": "AuthorizationFailed", "message": "denied"}}
    with requests_mock.Mocker() as m:
        m.get(CONTROLS_URL, status_code=403, json=error)
        with pytest.raises(DefenderError, match="AuthorizationFailed"):
            client.list_controls(STD)


def test_throttled_requests_are_retried(client):
    with requests_mock.Mocker() as m:
        m.get(
            CONTROLS_URL,
            [
                {"status_code": 429, "headers": {"Retry-After": "0"}, "json": {}},
                {"json": {"value": [{"name": "1.1"}]}},
            ],
        )
        controls = client.list_controls(STD)
    assert [c["name"] for c in controls] == ["1.1"]


def test_fetch_standard_pairs_each_control_with_its_assessments(client):
    with requests_mock.Mocker() as m:
        m.get(CONTROLS_URL, json={"value": [{"name": "1.1"}, {"name": "1.2"}]})
        m.get(assessments_url("1.1"), json={"value": [{"name": "a1"}]})
        m.get(
            assessments_url("1.2"),
            status_code=404,
            json={"error": {"code": "NoRegulatoyComplianceDataFound", "message": "none"}},
        )
        result = client.fetch_standard(STD)
    assert result["standard"] == STD
    pairs = [
        (c["control"]["name"], [a["name"] for a in c["assessments"]])
        for c in result["controls"]
    ]
    assert pairs == [("1.1", ["a1"]), ("1.2", [])]

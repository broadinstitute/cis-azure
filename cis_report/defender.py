"""Client for the Defender for Cloud regulatory compliance REST API."""

import time

import requests

ARM_URL = "https://management.azure.com"
TOKEN_SCOPE = f"{ARM_URL}/.default"
API_VERSION = "2019-01-01-preview"
CIS_STANDARDS = ("CIS-Azure-Foundations-v1.4.0", "CIS-Azure-Foundations-v2.0.0")

# The API misspells this code ("Regulatory" -> "Regulatoy"). Match it as-is.
NO_DATA_CODE = "NoRegulatoyComplianceDataFound"
RETRY_STATUSES = (429, 500, 502, 503, 504)
MAX_ATTEMPTS = 5


class DefenderError(Exception):
    """An error response from the Defender API."""

    def __init__(self, status, code, message):
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code


class DefenderClient:
    def __init__(self, subscription_id, credential, retry_backoff=1.0):
        self.base = f"{ARM_URL}/subscriptions/{subscription_id}/providers/Microsoft.Security"
        self.credential = credential
        self.session = requests.Session()
        self.retry_backoff = retry_backoff

    def list_controls(self, standard):
        url = f"{self.base}/regulatoryComplianceStandards/{standard}/regulatoryComplianceControls"
        return self._list(url)

    def list_assessments(self, standard, control):
        url = (
            f"{self.base}/regulatoryComplianceStandards/{standard}"
            f"/regulatoryComplianceControls/{control}/regulatoryComplianceAssessments"
        )
        try:
            return self._list(url)
        except DefenderError as error:
            if error.code == NO_DATA_CODE:
                return []
            raise

    def fetch_standard(self, standard):
        return {
            "standard": standard,
            "controls": [
                {
                    "control": control,
                    "assessments": self.list_assessments(standard, control["name"]),
                }
                for control in self.list_controls(standard)
            ],
        }

    def _list(self, url):
        items = []
        body = self._get(url, params={"api-version": API_VERSION})
        items.extend(body.get("value", []))
        # nextLink is an absolute URL that already carries api-version.
        while next_url := body.get("nextLink"):
            body = self._get(next_url)
            items.extend(body.get("value", []))
        return items

    def _get(self, url, params=None):
        token = self.credential.get_token(TOKEN_SCOPE).token
        for attempt in range(MAX_ATTEMPTS):
            response = self.session.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            if response.status_code not in RETRY_STATUSES or attempt == MAX_ATTEMPTS - 1:
                break
            time.sleep(self._retry_delay(response, attempt))
        if response.status_code >= 400:
            error = _error_body(response)
            raise DefenderError(response.status_code, error.get("code"), error.get("message"))
        return response.json()

    def _retry_delay(self, response, attempt):
        retry_after = response.headers.get("Retry-After", "")
        if retry_after.isdigit():
            return float(retry_after)
        return self.retry_backoff * 2**attempt


def _error_body(response):
    try:
        return response.json().get("error", {})
    except ValueError:
        return {}

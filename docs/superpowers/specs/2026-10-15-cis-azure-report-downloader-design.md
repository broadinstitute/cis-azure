# CIS Azure Report Downloader: Design

Status: architecture approved in conversation on 2026-10-15. Written spec pending review.

## Goal

Replace the manual weekly download of the CIS Azure Foundations Benchmark reports
(v1.4.0 and v2.0.0) from the Microsoft Defender for Cloud Regulatory Compliance page.
The manual process requires break-glass Prod Admin access through Beehive. The
automated job uses a standing, read-only identity instead.

## Decisions

| Area | Decision |
|---|---|
| Data source | Defender for Cloud regulatory compliance REST API (ARM), not portal UI automation |
| Scope | One subscription: `5374e8d3-9703-4a09-ac4a-af6f9f5c013b` (`8201553-terra-prod`) |
| Azure identity | Function's system-assigned managed identity, with Security Reader on the subscription |
| Runtime | Azure Function App, Python, timer trigger |
| Schedule | Thursdays 08:00 America/New_York |
| Output | `gs://<project>-cis-azure`, with `<project>` = `dsp-appsec-dev` first, then `dsp-appsec-infra-prod` |
| GCP auth | Keyless workload identity federation from the Azure managed identity; no service account keys |
| GCP roles | `roles/storage.objectCreator` (writes) and `roles/storage.objectViewer` (history reads) |
| Postprocessing | Convert to CSV, diff against last week, pass/fail summary |
| Failures | Logged to Application Insights, with an Azure Monitor alert by email |
| Fallback | Playwright portal automation, only if the API cannot produce the reports |

## Verified API facts (read-only probe, 2026-10-15)

- Standards: `GET /subscriptions/{sub}/providers/Microsoft.Security/regulatoryComplianceStandards?api-version=2019-01-01-preview`
  - Names include `CIS-Azure-Foundations-v1.4.0` and `CIS-Azure-Foundations-v2.0.0`.
- Controls: `.../regulatoryComplianceStandards/{std}/regulatoryComplianceControls?api-version=2019-01-01-preview`
  - v2.0.0 returns 85 controls. Each has pass/fail/skip counts and a `state`.
- Assessments: `.../regulatoryComplianceStandards/{std}/regulatoryComplianceControls/{control}/regulatoryComplianceAssessments?api-version=2019-01-01-preview`
  - Each has `description`, `state`, and resource counts. Control `1.1` in v2.0.0 returns
    `NoRegulatoyComplianceDataFound` (the error code is misspelled in the API). Treat that as
    "no assessments" rather than a failure.
- Assessments carry counts, not resource lists. Whether the portal CSV includes per-resource
  rows is still unknown.

## Architecture

```
Timer (Thu 08:00 ET)
  -> function_app.py     wires modules together, no logic
     -> defender.py      ARM REST calls with managed identity (fetch)
     -> reports.py       render the two CSVs in portal layout
     -> history.py       load last week's raw JSON from GCS, compute changes
     -> summary.py       pass/fail counts per benchmark
     -> gcs.py           upload via workload identity federation
```

Each run writes `gs://<bucket>/YYYY-MM-DD/`:

- `cis-azure-foundations-v1.4.0.csv`
- `cis-azure-foundations-v2.0.0.csv`
- `raw/CIS-Azure-Foundations-v1.4.0.json`, `raw/CIS-Azure-Foundations-v2.0.0.json`
- `summary.json`
- `changes.json`

The diff reads the previous dated folder's raw JSON, not the CSVs. The comparison does not
depend on re-parsing CSV output.

## Module responsibilities

- **`defender.py`:** Fetches standards, controls, and per-control assessments for the
  subscription. Returns plain dicts. Owns the api-version, paging, and the
  `NoRegulatoyComplianceDataFound` handling. Auth is the managed identity via
  `azure-identity`. No knowledge of CSVs or GCS.
- **`reports.py`:** Renders CSVs from the fetched data. Column layout must match the portal
  export; pending sample CSVs from the user.
- **`history.py`:** Finds the previous dated folder, loads its raw JSON, and returns changed
  controls and assessments.
- **`summary.py`:** Counts passed/failed per benchmark.
- **`gcs.py`:** Writes objects. The credential config is a file with no key material.
- **`function_app.py`:** Timer entry point.

## Error handling

- Defender calls retry transient HTTP errors (429, 5xx) with backoff. Other errors fail the run.
- A failed run writes nothing to GCS, so no partial week is published.
- Failures raise, which Application Insights captures; an Azure Monitor alert emails the owner.

## Testing

- Unit tests for `defender.py` against recorded JSON fixtures, with HTTP mocked.
- Fixtures come from the read-only probe above, saved under `tests/fixtures/`.
- Local run for `defender.py` uses the developer's `az login` credential.

## Portal CSV format (sample exports, 2026-10-15)

Sample exports are kept locally and are git-ignored (`docs/**/MicrosoftDefenderForCloudRegulatoryCompliance_*.csv`).

- One row per recommendation per resource. Columns: `exportedTimestamp`, `complianceStandard`,
  `complianceControl`, `complianceControlName`, `recommendationState`, `subscriptionId`,
  `subscriptionName`, `resourceGroup`, `resourceType`, `resourceName`, `resourceId`,
  `recommendationId`, `recommendationName`, `recommendationDisplayName`, `description`,
  `remediationSteps`, `severity`, `resourceState`, `notApplicableReason`,
  `azurePortalRecommendationLink`. The file starts with a UTF-8 BOM.
- v1.4.0: 563 rows, 186 recommendation IDs, 108 controls. States: Skipped 455, Passed 63, Failed 45.
- v2.0.0: 193 rows, 137 recommendation IDs, 42 controls. States: Passed 119, Failed 74.

What the portal CSV is built from, verified by read-only probes:

- Each `recommendationId` is a real `Microsoft.Security/assessments/{id}` record. For example,
  `GET .../assessments/56a6e81f-…?api-version=2021-06-01` returns the matching displayName and status.
- The regulatory compliance `assessmentKey` IDs (from `regulatoryComplianceAssessments`) do not
  match the CSV's `recommendationId`s, and neither do the CIS initiative policy GUIDs
  (`c3f5c4d9…` for v1.4.0, `06f19060…` for v2.0.0). Zero overlap in both cases.
- The recommendation's `properties.metadata` is empty, so it does not expose the control mapping.

Still unresolved: which API gives the control-to-recommendation mapping that the portal uses. Until
that is found, `defender.py` can fetch per-resource recommendations, but `reports.py` cannot
reproduce the portal's `complianceControl` column.

## Open items

- Find the API that maps CIS controls to recommendation IDs (see above).
- Azure Functions time zone support on the chosen plan (Eastern schedule vs. UTC).
- Infrastructure-as-code tool for the Function App, identity, and role assignment.
- Alert recipient: `tconner@broadinstitute.org` (confirm the full address).
- Dev bucket confirmed: `dsp-appsec-dev-cis-azure`.

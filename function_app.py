import logging
import os
from collections import Counter

import azure.functions as func
from azure.identity import DefaultAzureCredential

from cis_report.defender import CIS_STANDARDS, DefenderClient

app = func.FunctionApp()


# NCRONTAB, in UTC: 12:00 UTC is 08:00 Eastern during daylight time.
@app.timer_trigger(schedule="0 0 12 * * 4", arg_name="timer", run_on_startup=False)
def cis_report(timer: func.TimerRequest) -> None:
    client = DefenderClient(os.environ["AZURE_SUBSCRIPTION_ID"], DefaultAzureCredential())
    for standard in CIS_STANDARDS:
        data = client.fetch_standard(standard)
        states = Counter(c["control"]["properties"]["state"] for c in data["controls"])
        assessments = sum(len(c["assessments"]) for c in data["controls"])
        logging.info(
            "%s: %d controls, %d assessments, states=%s",
            standard,
            len(data["controls"]),
            assessments,
            dict(states),
        )

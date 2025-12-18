#!/usr/bin/env python3

import os
import sys
import requests
from pathlib import Path
from string import Template

def send_error_to_teams(github_server, github_repository, github_run_id, github_workflow, github_job, check_outcome):
    teams_webhook = os.getenv("TEAMS_MONITOR_WEBHOOK")
    urls = os.getenv('ERRORED_INTERVIEWS', '').split(',')

    content = f"""
        Your Hall Monitor Action has a status of {check_outcome}.
        Check the links below: 

        {urls}
        
        More info:

        Github workflow: {github_workflow}, Github job: {github_job}, Job status: {check_outcome}
        """
    run_url = f"{ github_server }/{ github_repository }/actions/runs/{ github_run_id }"

    p = Path(__file__).with_name("teams_card.json")
    with p.open("r") as f:
        card_raw = f.read()
        main_url = next(iter(urls), "")
        card = Template(card_raw).substitute(incident_context=content, logs_url=run_url, server_url=main_url)

    requests.post(teams_webhook, headers={"Content-Type": "application/json"}, data=card)
    return 0

if __name__ == "__main__":
    if len(sys.argv) <= 4:
        print("Required args: github server url, github repository, workflow run id, workflow, job, and check step's outcome.")
        exit(3)
    return_value = send_error_to_teams(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6])
    exit(return_value)

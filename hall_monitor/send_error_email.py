#!/usr/bin/env python3

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import os
import sys
import requests

def main(github_repository, github_workflow, github_job, check_outcome):
    if not os.getenv("ERROR_EMAILS"):
        print("No error emails passed in! Not going to notify them of this failure")
        return 0

    send_from = os.getenv("ERROR_EMAIL_FROM", "no-reply@suffolklitlab.org")
    send_to = [to_send.strip() for to_send in os.environ["ERROR_EMAILS"].split(",")]
    subject = f"{github_job} job of {github_repository} has {check_outcome}"

    content = f"""
        <p>Hey there! Your Hall Monitor Action has a status of {check_outcome}.</p>
        <p>You should check all of the interviews at this URL: <a href="{os.environ['SERVER_URL']}/list">{os.environ['SERVER_URL']}/list</a></p>
        <p>{os.getenv('ERRORED_INTERVIEWS', '') }</p>
        <p>More info:
        <ul>
          <li> Github Repository: {github_repository} </li>
          <li> Github workflow: {github_workflow} </li>
          <li> Github job: {github_job} </li>
          <li> Job status: {check_outcome} </li>
        </ul></p>
        """

    if os.getenv("SENDGRID_API_KEY"):
        message = Mail(
            from_email=send_from, to_emails=send_to, subject=subject, html_content=content
        )
        sg = SendGridAPIClient(api_key=os.environ["SENDGRID_API_KEY"])
        try:
            resp = sg.send(message)
        except Exception as e:
            print(f"Error sending email: {e}")
            return 2
    elif os.getenv("MAILGUN_API_KEY") and os.getenv("MAILGUN_DOMAIN"):
        url = f"https://api.mailgun.net/v3/{os.environ['MAILGUN_DOMAIN']}/messages"
        resp = requests.post(
            url,
            auth=("api", os.environ["MAILGUN_API_KEY"]),
            data={
                "from": send_from,
                "to": send_to,
                "subject": subject,
                "text": "Your hall monitor action has failed",
                "html": content,
            },
        )
    else:
        print("Not sending emails, neither sendgrid or mailgun is setup!")
        return 2

    print(f"{resp.status_code}, {resp.body} {resp.headers}")
    return 0

if __name__ == "__main__":
    if len(sys.argv) <= 4:
        print("Required args: github repository, workflow, job, and check step's outcome.")
        exit(3)
    return_value = main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
    exit(return_value)
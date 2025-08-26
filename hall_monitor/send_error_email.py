#!/usr/bin/env python3

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import os
import requests

def main():
    if not os.getenv("ERROR_EMAILS"):
        print("No error emails passed in! Not going to notify them of this failure")
        return 0

    send_from = os.getenv("ERROR_EMAIL_FROM", "no-reply@suffolklitlab.org")
    send_to = [to_send.strip() for to_send in os.environ["ERROR_EMAILS"].split(",")]
    subject = "${{ github.job }} job of ${{ github.repository }} has ${{ steps.check_server.outcome }}"

    content = f"""
        <p>Hey there! Your Hall Monitor Action has a status of ${{ steps.check_server.outcome }}.</p>
        <p>You should check all of the interviews at this URL: <a href="{os.environ['SERVER_URL']}/list">{os.environ['SERVER_URL']}/list</a></p>
        <p>{os.getenv('ERRORED_INTERVIEWS', '') }</p>
        <p>More info:
        <ul>
          <li> Github Repository: ${{ github.repository }} </li>
          <li> Github workflow: ${{ github.workflow }} </li>
          <li> Github job: ${{ github.job }} </li>
          <li> Job status: ${{ steps.check_server.outcome }} </li>
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
    return_value = main()
    exit(return_value)
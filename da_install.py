#!/usr/bin/env python3

import requests
import os
import time
import zipfile
from io import BytesIO

def zip_current_dir():
  zip_bytes = BytesIO()
  with zipfile.ZipFile(zip_bytes, 'w', zipfile.ZIP_DEFLATED) as zip_handle:
    for root, dirs, files in os.walk(".", topdown=True):
        # Modifying dirs in place will skip the .git directory
        dirs[:] = [d for d in dirs if d != '.git' and d != '.mypy_cache']
        for file in files:
            zip_handle.write(os.path.join(root, file), 
                             os.path.relpath(os.path.join(root, file), 
                                             os.path.join(".", '..')))
  zip_bytes.seek(0, 0)
  return zip_bytes.getvalue()

def make_playground_payload():
  user_id = os.getenv('USER_ID')
  project = os.getenv('PROJECT_NAME')
  restart = os.getenv('RESTART')

  data = {}
  if user_id:
    data["user_id"] = user_id
  if project:
    data["project"] = project
  if restart:
    data["restart"] = restart

  files = {'file': ('deploy.zip', zip_current_dir())}
  print(f"Installing using {list(data.keys())} and zip")
  return {'data': data or None, 'files': files}

def make_server_payload():
  # optional env vars
  github_url = os.getenv('GITHUB_URL')
  github_branch = os.getenv('GITHUB_BRANCH')
  pypi_package = os.getenv('PYPI_PACKAGE')
  payload = {}
  files = {}
  if pypi_package:
    payload["pip"] = pypi_package
  elif github_url:
    payload["github_url"] = github_url
    if github_branch:
      payload['branch'] = github_branch
  else:
    files["zip"] = ('deploy.zip', zip_current_dir())

  print(f"Installing using {list(payload.keys())}, {list(files.keys())}")
  return {'data': payload or None, 'files': files or None}

def install_to_server(install_url, headers, payload, polling_url):
  resp = requests.post(install_url, headers=headers, data=payload['data'], files=payload['files'])
  if not resp.ok:
    print(f"Not able to install {payload['data']} at {install_url}: {resp.text}")
    return 1

  if resp.status_code == 204:
    print("Success! DA server did not need to restart")
    return 0

  # Just loop a bunch of times until we are sure that it installed.
  task_id = resp.json()["task_id"]
  sleep_count = 0
  while sleep_count < 10:
    updated_resp = requests.get(polling_url, params={"task_id": task_id}, headers=headers)
    if not updated_resp.ok:
      print(f"Not able to determine if {payload['data']} finished installing: {resp.text}")
      return 2
    body = updated_resp.json()
    if body['status'] == 'working':
      time.sleep(10)
      sleep_count += 1

    if body['status'] == 'completed':
      if body.get('ok', True):
        print("Success!")
        return 0
      else:
        print(f"Not successful installing {payload['data']}: {body['error_message']}")
        return 3

    if body['status'] == 'unknown':
      print(f"task_id unknown?: {body}")
      return 4

  print(f"Timed out waiting to determine if {payload['data']} finished installing. Check the server, it might have still!")
  return 5

def main():
  print("Starting install to docassemble server")
  server_url = os.environ['SERVER_URL']

  headers = {"X-API-KEY": os.environ['DOCASSEMBLE_DEVELOPER_API_KEY']}
  if os.environ['INSTALL_TYPE'] == 'playground':
    install_url = f"{server_url}/api/playground_install"
    polling_url = f"{server_url}/api/restart_status"
    payload = make_playground_payload()
  else:
    install_url = f"{server_url}/api/package"
    polling_url = f"{server_url}/api/package_update_status"
    payload = make_server_payload()

  return install_to_server(install_url, headers, payload, polling_url)

if __name__ == "__main__":
  retval = main()
  exit(retval)
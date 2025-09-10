#!/usr/bin/env python3

# Beautiful soup to find failing interview links
import bs4
import requests
import os

def check_homepage(server_url):
    with requests.get(f"{server_url}") as conn:
        if not conn.ok:
            print(f"Hall monitor couldn't connect to {server_url}: {conn.status_code}")
            # Empty string just gets added to the end of the URL, so it's valid.
            return [""]
    return []

def check_server(server_url):
    with requests.get(f"{server_url}/list") as conn:
        if conn.ok:
            soup = bs4.BeautifulSoup(conn.text, "html.parser")
        else:
            print(f"Hall monitor couldn't connect to {server_url}: {conn.status_code}")
            return [f"{server_url}/list"]
    links = soup.find_all("a")
    # These links are already checked by docassemble when the page is served
    failed_links = [link for link in links if "dainterviewhaserror" in (link.get("class") or [])]
    return [fl.attrs['href'] for fl in failed_links]

def main():
    server_url = os.environ['SERVER_URL']
    try:
        if os.getenv('CHECK_TYPE') == 'homepage':
            failed_links = check_homepage(server_url)
        else:
            failed_links = check_server(server_url)
    except Exception as ex:
        failed_links = [""]

    if failed_links:
        updated_links = [f"{server_url}{fl}" for fl in failed_links ]
        links_str = f"{','.join(updated_links)}"
        env_file = os.getenv('GITHUB_ENV')
        if env_file:
            with open(env_file, "a") as myfile:
                myfile.write(f'ERRORED_INTERVIEWS={links_str}')
        else:
            print(f"Hall Monitor found these links are broken: {links_str} (can't print to GitHub's env file)")
        exit(1)
    else:
        print(f"Hall Monitor: all good, no failed links found!")

if __name__ == "__main__":
    main()
"""
Royalty Statement Puller — semi-automated login + download
============================================================

HOW THIS WORKS
- Run this script manually (or ask Claude Code to run it) once a month.
- A real, visible browser window opens for each site.
- YOU log in and clear any 2FA/CAPTCHA by hand — this cannot be automated
  reliably and platforms actively block bots that try.
- Once you're past login, the script takes over navigation and downloads
  new statement documents into a dated local folder.

SETUP (do this once, with Claude Code)
1. pip install playwright keyring
2. playwright install chromium
3. Store your credentials in the OS keychain (never in this file):
     python -m keyring set royalty_puller prs_username
     python -m keyring set royalty_puller prs_password
     python -m keyring set royalty_puller ditto_username
     python -m keyring set royalty_puller ditto_password
4. Fill in the SELECTORS below by inspecting the real PRS / Ditto pages
   (right-click element -> Inspect -> copy the CSS selector). Ask Claude
   Code to help you find these live — I can't see the actual site from here.

USAGE
   python royalty_puller.py prs
   python royalty_puller.py ditto
   python royalty_puller.py all
"""

import sys
import keyring
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

SERVICE_NAME = "royalty_puller"
DOWNLOAD_ROOT = Path.home() / "RoyaltyStatements"

# ---------------------------------------------------------------------------
# CONFIG — fill in real selectors once you've inspected each site.
# These are PLACEHOLDERS and will not work until you update them.
# ---------------------------------------------------------------------------
SITES = {
    "prs": {
        "login_url": "https://www.prsformusic.com/login",
        "username_selector": "input#username",       # <-- update
        "password_selector": "input#password",        # <-- update
        "login_button_selector": "button[type=submit]",  # <-- update
        "statements_url": "https://statements.prsformusic.com/#/",
        "download_link_selector": "a.statement-card__actions-download",
        # Clicking download_link_selector opens a popup listing every file
        # (PDF, CSV, CTL) for that statement; each has its own download button.
        "modal_file_button_selector": "div.modal-main a > button",
        "modal_close_selector": "body > div.ReactModalPortal > div > div > a > svg > circle",
    },
    "ditto": {
        "login_url": "https://my.dittomusic.com/login",  # <-- confirm
        "username_selector": "input#email",            # <-- update
        "password_selector": "input#password",          # <-- update
        "login_button_selector": "button[type=submit]",  # <-- update
        "statements_url": "https://my.dittomusic.com/publishing/statements",  # <-- update
        "download_link_selector": "a.download-statement",  # <-- update
    },
}


def pull_statements(site_key: str):
    config = SITES[site_key]
    username = keyring.get_password(SERVICE_NAME, f"{site_key}_username")
    password = keyring.get_password(SERVICE_NAME, f"{site_key}_password")

    if not username or not password:
        print(f"No stored credentials for {site_key}. Run the keyring setup steps first.")
        return

    out_dir = DOWNLOAD_ROOT / site_key / datetime.now().strftime("%Y-%m")
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # visible on purpose
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        page.goto(config["login_url"])
        print(f"\n[{site_key}] Browser window opened.")
        print("Please log in and complete any 2FA/CAPTCHA now.")
        input("Press ENTER here once you're logged in and see your dashboard...")

        # Navigate to statements page
        page.goto(config["statements_url"])
        page.wait_for_load_state("networkidle")

        links = page.locator(config["download_link_selector"])
        count = links.count()
        print(f"Found {count} statement(s).")

        for i in range(count):
            if "modal_file_button_selector" in config:
                # This site opens a popup with one download button per file
                # (PDF, CSV, CTL, ...) instead of downloading directly.
                links.nth(i).click()
                file_buttons = page.locator(config["modal_file_button_selector"])
                file_buttons.first.wait_for()
                file_count = file_buttons.count()
                print(f"  Statement {i + 1}: {file_count} file(s) to download.")

                for j in range(file_count):
                    with page.expect_download() as download_info:
                        file_buttons.nth(j).click()
                    download = download_info.value
                    dest = out_dir / download.suggested_filename
                    download.save_as(dest)
                    print(f"  Saved: {dest}")

                page.locator(config["modal_close_selector"]).click()
                page.locator(config["modal_file_button_selector"]).wait_for(state="detached")
            else:
                with page.expect_download() as download_info:
                    links.nth(i).click()
                download = download_info.value
                dest = out_dir / download.suggested_filename
                download.save_as(dest)
                print(f"Saved: {dest}")

        browser.close()

    print(f"\nDone. Files saved to: {out_dir}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    if target == "all":
        for key in SITES:
            pull_statements(key)
    elif target in SITES:
        pull_statements(target)
    else:
        print(f"Unknown target '{target}'. Choose from: {', '.join(SITES)} or 'all'.")

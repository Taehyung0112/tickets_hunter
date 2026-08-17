"""Open the mock page in real Chrome, drive it, print the verdict.

Needs Chrome and zendriver, so it is not part of the pytest suite. Run
gen_checkout_fill_mock.py first, then this, from the repo root.
"""
import asyncio
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, "src")
import chrome_downloader
import zendriver as uc

PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "checkout_fill_mock.html")


async def main():
    chrome = chrome_downloader.ensure_chrome_available(download_dir=os.path.join("src", "webdriver"))
    browser = await uc.start(uc.Config(headless=True, browser_executable_path=chrome, sandbox=False))
    tab = await browser.get("file:///" + PAGE.replace("\\", "/"))
    await asyncio.sleep(1.0)

    await tab.evaluate("document.getElementById('install').click(); 'ok'")
    await asyncio.sleep(0.4)
    print("install:", await tab.evaluate("document.getElementById('out').textContent"))

    await tab.evaluate("document.getElementById('render').click(); 'ok'")
    await asyncio.sleep(2.5)

    verdict = await tab.evaluate("document.getElementById('verdict').innerHTML") or ""
    print(re.sub(r"<[^>]+>", "", verdict.replace("<br>", "\n")))
    print("stats:", await tab.evaluate("JSON.stringify(window.__thFillStats)"))
    await browser.stop()


asyncio.run(main())

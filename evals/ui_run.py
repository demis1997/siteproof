"""Browser assertions against the trusted dashboard in a separate test container."""
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto("http://web:3000")
        page.get_by_label("Tenant access key").fill("integration-key")
        page.get_by_role("button", name="Connect workspace").click()
        page.get_by_role("button").filter(has_text="http://fixture.siteproof.test/overflow").click()
        page.locator(".evidence img").first.wait_for()
        assert page.locator(".fixture").is_visible()
        page.wait_for_function("()=>{const imgs=[...document.querySelectorAll('.evidence img')];return imgs.length===2&&imgs.every(i=>i.complete&&i.naturalWidth>0)}")
        page.get_by_role("tab", name="Findings", exact=True).click()
        page.locator(".evidence-links button").first.click()
        assert page.get_by_role("tabpanel", name="Evidence", exact=True).is_visible()
        page.screenshot(path="/tmp/dashboard.png", full_page=True)
        Path("/tmp/ui-result.txt").write_text("PASS: actual dashboard login, fixture label, loaded PNGs and evidence navigation")
        browser.close()


if __name__ == "__main__":
    main()

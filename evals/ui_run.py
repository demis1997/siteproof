"""Browser assertions against the trusted dashboard in a separate test container."""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto("http://web:3000")
        page.get_by_label("Tenant access key").fill("integration-key")
        page.get_by_role("button", name="Connect workspace").click()
        try:
            page.get_by_role("heading", name="Start an audit", exact=True).wait_for(timeout=10000)
        except Exception:
            Path("/tmp/ui-failure.txt").write_text(page.locator("body").inner_text()[:12000])
            page.screenshot(path="/tmp/ui-failure.png", full_page=True)
            raise
        page.get_by_label("Public website URL", exact=True).fill("http://fixture.siteproof.test/overflow")
        with page.expect_response(lambda response: response.url.endswith("/api/jobs") and response.request.method == "POST") as created:
            page.get_by_role("button", name="Audit website").click()
        response = created.value
        assert response.status == 201, response.text()
        job_id = response.json()["id"]
        page.locator(".evidence img").first.wait_for(timeout=180000)
        assert page.locator(".fixture").is_visible()
        page.wait_for_function("()=>{const imgs=[...document.querySelectorAll('.evidence img')];return imgs.length===2&&imgs.every(i=>i.complete&&i.naturalWidth>0)}")
        page.get_by_role("tab", name="Findings", exact=True).click()
        page.locator(".evidence-links button").first.click()
        assert page.get_by_role("tabpanel", name="Evidence", exact=True).is_visible()
        page.screenshot(path="/tmp/dashboard.png", full_page=True)
        Path("/tmp/ui-result.json").write_text(json.dumps({"job_id": job_id, "status": "PASS", "checks": ["login", "URL submission", "background progress", "fixture label", "loaded PNGs", "grounded evidence navigation"]}))
        browser.close()


if __name__ == "__main__":
    main()

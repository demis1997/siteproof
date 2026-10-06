"""Capture service runs on a network with only the validating egress proxy."""

import base64
import json
import os
import signal
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

from .security import valid_phone, validate_url

VIEWPORTS = {"desktop": {"width": 1440, "height": 1000}, "mobile": {"width": 390, "height": 844}}
EXTRACT = """() => { const selector = e => { let parts=[]; while(e&&e.nodeType===1){let tag=e.tagName.toLowerCase();let siblings=e.parentElement?[...e.parentElement.children].filter(n=>n.tagName===e.tagName):[e];parts.unshift(tag+':nth-of-type('+(siblings.indexOf(e)+1)+')');e=e.parentElement;} return parts.join(' > '); }; const pick = s => [...document.querySelectorAll(s)].slice(0,100).map((e,i)=>({selector:selector(e),tag:e.tagName,text:(e.innerText||e.alt||'').slice(0,500),href:e.getAttribute('href'),src:e.getAttribute('src'),label:e.getAttribute('aria-label'),geometry:{x:e.getBoundingClientRect().x,y:e.getBoundingClientRect().y,width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height}})); return {title:document.title,headings:pick('h1,h2,h3'),navigation:pick('nav a'),links:pick('a'),buttons:pick('button,input'),images:pick('img'),text:document.body.innerText.slice(0,16000),overflow:document.documentElement.scrollWidth>innerWidth}; }"""


def capture(url=None, html=None, *, proxy="http://proxy:8080", executable_path=None, axe_path=None, source_url=None):
    if url is not None and proxy is None:
        raise ValueError("Live URL capture requires isolated egress proxy")
    evidence, screenshots, facts = [], [], []
    stamp = datetime.now(UTC).isoformat()
    source_url = source_url or url or "private-preview"
    canonical_url = source_url
    with sync_playwright() as p:
        browser = p.chromium.launch(
            args=["--disable-dev-shm-usage"],
            executable_path=executable_path,
            proxy={"server": proxy, "bypass": ""} if proxy else None,
        )
        for viewport, size in VIEWPORTS.items():
            context = browser.new_context(
                viewport=size, service_workers="block", accept_downloads=False, locale="en-US", timezone_id="UTC"
            )
            requests = [0]

            def guard(route, request, counter=requests):
                counter[0] += 1
                if route.request.url.startswith(("http:", "https:")):
                    try:
                        validate_url(route.request.url, resolve=False)
                    except ValueError:
                        route.abort()
                        return
                if (
                    urlsplit(route.request.url).scheme not in ("http", "https", "data")
                    or route.request.method not in ("GET", "HEAD")
                    or counter[0] > 100
                    or route.request.resource_type in ("media", "websocket")
                ):
                    route.abort()
                else:
                    route.continue_()

            context.route("**/*", guard)
            context.route_web_socket("**/*", lambda ws: ws.close())
            page = context.new_page()
            context.on("page", lambda popup: popup.close())
            try:
                navigation_status = None
                if html is not None:
                    page.set_content(html, timeout=15000)
                else:
                    response = page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    navigation_status = response.status if response else None
                    source_url = validate_url(page.url, resolve=False)
                    if viewport == "desktop":
                        canonical_url = source_url
                page.wait_for_timeout(500)
                dom = page.evaluate(EXTRACT)
                eid = "dom-" + viewport
                evidence.append(
                    {
                        "id": eid,
                        "kind": "dom",
                        "viewport": viewport,
                        "data": dom,
                        "source_url": source_url,
                        "captured_at": stamp,
                    }
                )
                screenshots.append(
                    {
                        "id": "screenshot-" + viewport,
                        "viewport": viewport,
                        "png": base64.b64encode(page.screenshot(full_page=False)).decode(),
                    }
                )
                checks = [
                    ("horizontal_overflow", not dom["overflow"]),
                    ("render", navigation_status is None or navigation_status < 400),
                ]
                contacts = [a for a in dom["links"] if (a.get("href") or "").startswith(("mailto:", "tel:"))]
                import re

                valid = bool(contacts) and all(
                    bool(re.fullmatch(r"mailto:[^@\s?]+@[^@\s?]+\.[^@\s?]+", a["href"]))
                    if a["href"].startswith("mailto:")
                    else valid_phone(a["href"].split(":", 1)[1])
                    for a in contacts
                )
                checks.append(("contact_links", valid))
                checks.append(
                    (
                        "contact_visible",
                        any(
                            a["geometry"]["y"] >= 0
                            and a["geometry"]["y"] < size["height"]
                            and a["geometry"]["width"] > 0
                            for a in contacts
                        ),
                    )
                )
                # Scope is fragment links on this captured homepage only.
                anchors = [
                    a["href"][1:] for a in dom["links"] if (a.get("href") or "").startswith("#") and len(a["href"]) > 1
                ]
                internal_ok = all(page.evaluate("(id)=>!!document.getElementById(id)", anchor) for anchor in anchors)
                checks.append(("internal_links", internal_ok))
                axe_file = Path(axe_path or "/opt/audit/node_modules/axe-core/axe.min.js")
                if axe_file.exists():
                    page.add_script_tag(path=str(axe_file))
                    axe = page.evaluate(
                        'async()=>await axe.run(document,{runOnly:{type:"tag",values:["wcag2a","wcag2aa","wcag21aa"]}})'
                    )
                    for violation in axe["violations"]:
                        evidence.append(
                            {
                                **violation,
                                "audit_id": violation["id"],
                                "id": "axe-" + viewport + "-" + violation["id"],
                                "kind": "axe",
                                "viewport": viewport,
                            }
                        )
                    checks.append(("axe", not any(v["impact"] in ("critical", "serious") for v in axe["violations"])))
                    checks.append(
                        (
                            "accessible_labels",
                            not any(v["id"] in ("button-name", "link-name", "label") for v in axe["violations"]),
                        )
                    )
                else:
                    evidence.append(
                        {
                            "id": "axe-unavailable-" + viewport,
                            "kind": "unavailable",
                            "name": "axe",
                            "reason": "axe-core runtime missing",
                        }
                    )
                for name, passed in checks:
                    evidence.append(
                        {
                            "id": name + "-" + viewport,
                            "kind": "check",
                            "name": name,
                            "viewport": viewport,
                            "passed": passed,
                        }
                    )
                if viewport == "desktop":
                    for i, a in enumerate(contacts):
                        href = a["href"]
                        kind = "email" if href.startswith("mailto:") else "phone"
                        displayed = a["text"].strip()
                        pattern = r"[^@\s]+@[^@\s]+\.[^@\s]+" if kind == "email" else r"\+?[0-9(). \-]{7,}"
                        match = re.search(pattern, displayed)
                        value = match.group(0).strip() if match else href.split(":", 1)[1]
                        destination = ("mailto:" if kind == "email" else "tel:") + value
                        facts.append(
                            {
                                "id": "fact-" + str(i),
                                "kind": kind,
                                "value": value,
                                "href": destination,
                                "original_href": href,
                                "source_url": source_url,
                                "evidence_id": eid,
                                "captured_at": stamp,
                                "approved": False,
                            }
                        )
                    existing_contacts = {(f["kind"], re.sub(r"[(). \-]", "", f["value"])) for f in facts}
                    for i, line in enumerate(dom["text"].splitlines()):
                        # Retain conflicting visible contact candidates, including those outside links.
                        candidates = [("email", m.group(0)) for m in re.finditer(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>.,]+", line)]
                        candidates += [("phone", m.group(1).strip(" .")) for m in re.finditer(
                            r"(?:call|phone|tel)\s*:?\s*(\+?[0-9][0-9(). \-]{6,}[0-9.])", line, re.IGNORECASE)]
                        for kind, value in candidates:
                            key = (kind, re.sub(r"[(). \-]", "", value))
                            if key in existing_contacts or (kind == "phone" and not valid_phone(value)):
                                continue
                            existing_contacts.add(key)
                            facts.append({"id": f"fact-visible-{i}-{kind}", "kind": kind, "value": value,
                                          "href": ("mailto:" if kind == "email" else "tel:") + value,
                                          "source_url": source_url, "evidence_id": eid, "captured_at": stamp,
                                          "approved": False, "uncertainty": "Visible contact candidate; review multiple values for conflicts"})
                        line = line.strip()
                        kind = (
                            "price"
                            if re.search(r"(?:[$£€]\s*\d|\d\s*(?:USD|EUR|GBP))", line)
                            else (
                                "hours"
                                if re.search(
                                    r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b.*\d",
                                    line,
                                    re.IGNORECASE,
                                )
                                else None
                            )
                        )
                        if kind and 0 < len(line) < 250:
                            facts.append(
                                {
                                    "id": "fact-text-" + str(i),
                                    "kind": kind,
                                    "value": line,
                                    "source_url": source_url,
                                    "evidence_id": eid,
                                    "captured_at": stamp,
                                    "approved": False,
                                }
                            )
                    for i, heading in enumerate(dom["headings"]):
                        if heading["tag"] == "H2" and heading["text"].strip():
                            facts.append(
                                {
                                    "id": "fact-service-" + str(i),
                                    "kind": "service",
                                    "value": heading["text"].strip(),
                                    "source_url": source_url,
                                    "evidence_id": eid,
                                    "captured_at": stamp,
                                    "approved": False,
                                    "uncertainty": "Heading treated as candidate service; human approval required",
                                }
                            )
            except Exception as exc:
                evidence.append(
                    {
                        "id": "capture-error-" + viewport,
                        "kind": "unavailable",
                        "name": "capture",
                        "reason": str(exc)[:500],
                    }
                )
            finally:
                context.close()
        browser.close()
        chrome_path = executable_path or p.chromium.executable_path
    # Stop the Playwright driver too: its threads count against the same fixed PID limit.
    for viewport in VIEWPORTS:
        evidence.append(lighthouse_evidence(url, viewport, chrome_path, proxy))
    return {
        "evidence": evidence,
        "screenshots": screenshots,
        "facts": facts,
        "partial": any(e["kind"] == "unavailable" for e in evidence),
        "canonical_url": canonical_url,
    }


def lighthouse_evidence(url, viewport, executable_path, proxy):
    evidence = []
    if url:
        try:
            with tempfile.TemporaryDirectory() as folder:
                report = str(Path(folder) / "lighthouse.json")
                profile = str(Path(folder) / "chrome-profile")
                try:
                    subprocess.run(
                            [
                            "/opt/audit/node_modules/.bin/lighthouse",
                            url,
                            "--output=json",
                            "--output-path=" + report,
                            f"--chrome-flags=--headless --no-sandbox --disable-dev-shm-usage --renderer-process-limit=2 --user-data-dir={profile} --proxy-server={proxy} --proxy-bypass-list=<-loopback>",
                            "--only-categories=performance,accessibility,best-practices,seo",
                            "--quiet",
                            *(
                                [
                                    "--preset=desktop",
                                    "--screenEmulation.mobile=false",
                                    "--screenEmulation.width=1440",
                                    "--screenEmulation.height=1000",
                                    "--screenEmulation.deviceScaleFactor=1",
                                ]
                                if viewport == "desktop"
                                else [
                                    "--screenEmulation.mobile=true",
                                    "--screenEmulation.width=390",
                                    "--screenEmulation.height=844",
                                    "--screenEmulation.deviceScaleFactor=1",
                                ]
                            ),
                        ],
                        env=dict(os.environ, CHROME_PATH=executable_path, NODE_OPTIONS="--v8-pool-size=1", UV_THREADPOOL_SIZE="1"),
                        timeout=45,
                        check=True,
                        capture_output=True,
                        start_new_session=True,
                    )
                finally:
                    cleanup_chrome_profile(profile)
                lighthouse = json.loads(Path(report).read_text())
                if lighthouse.get("runtimeError"):
                    raise ValueError("Lighthouse runtime error: " + str(lighthouse["runtimeError"])[:500])
                evidence.append(
                    {
                        "id": "lighthouse-" + viewport,
                        "kind": "lighthouse",
                        "viewport": viewport,
                        "tool_version": lighthouse.get("lighthouseVersion"),
                        "categories": lighthouse.get("categories"),
                        "audits": lighthouse.get("audits"),
                    }
                )
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            diagnostic = getattr(exc, "stderr", b"") or b""
            if isinstance(diagnostic, bytes):
                diagnostic = diagnostic.decode(errors="replace")
            evidence.append(
                {
                    "id": "lighthouse-" + viewport,
                    "kind": "unavailable",
                    "name": "lighthouse",
                    "viewport": viewport,
                    "reason": "Measurement failed or timed out",
                    "error_type": type(exc).__name__,
                    "return_code": getattr(exc, "returncode", None),
                    "detail": diagnostic[-1200:] or str(exc)[:500],
                }
            )
    else:
        evidence.append(
            {
                "id": "lighthouse-" + viewport,
                "kind": "unavailable",
                "name": "lighthouse",
                "reason": "HTML preview has no public URL; Lighthouse unavailable",
            }
        )
    return evidence[0]


def cleanup_chrome_profile(profile):
    """Stop only Chromium processes bearing this operation's unique profile marker."""
    proc = Path("/proc")
    if not proc.exists():
        return
    marker = ("--user-data-dir=" + profile).encode()
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if marker in (entry / "cmdline").read_bytes().split(b"\0"):
                os.kill(int(entry.name), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass

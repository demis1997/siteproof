from html import escape

from .contracts import PageSpec


def render(spec: dict) -> str:
    page = PageSpec.model_validate(spec)
    contacts = "".join(
        '<a class="contact" href="' + escape(c["href"], quote=True) + '">' + escape(c["value"]) + "</a>"
        for c in page.contacts
    )
    services = "".join("<li>" + escape(s) + "</li>" for s in page.services)
    return (
        """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>"""
        + escape(page.title)
        + """</title><style>*{box-sizing:border-box}body{margin:0;color:#182b2a;background:#f8f7f2;font:18px/1.6 system-ui}header,main,footer{max-width:1100px;margin:auto;padding:24px}nav{display:flex;flex-wrap:wrap;gap:20px}a{color:#145d50}h1{font-size:clamp(32px,6vw,72px);line-height:1.1;max-width:850px}.contact{display:inline-block;padding:12px 20px;margin:8px 8px 8px 0;background:#145d50;color:white;border-radius:4px;overflow-wrap:anywhere}section{padding:32px 0}a:focus-visible{outline:3px solid #d27f22;outline-offset:4px}</style></head><body><header><nav aria-label="Main navigation"><a href="#services">Services</a><a href="#about">About</a><a href="#contact">Contact</a></nav></header><main><h1>"""
        + escape(page.headline)
        + """</h1>"""
        + contacts
        + """<section id="services"><h2>Services</h2><ul>"""
        + services
        + """</ul></section><section id="about"><h2>About</h2><p>"""
        + escape(page.about)
        + """</p></section><section id="contact"><h2>Contact</h2>"""
        + contacts
        + """</section></main><footer>Private SiteProof preview"""
        + (" · Fixture data" if page.fixture else "")
        + """</footer></body></html>"""
    )

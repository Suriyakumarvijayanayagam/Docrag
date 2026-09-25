"""
Records the Datum walkthrough video from the running app, with captions and a
visible cursor. Runs in the Playwright image, so nothing is installed locally:

    docker run --rm --add-host=host.docker.internal:host-gateway \
        -e DATUM_URL=http://host.docker.internal:3000 \
        -e DATUM_EMAIL=you@example.com -e DATUM_PASSWORD=... \
        -v "$PWD/docs/demo:/demo" -w /demo mcr.microsoft.com/playwright/python:v1.49.0-noble \
        sh -c "pip install -q --break-system-packages playwright==1.49.0 imageio-ffmpeg && python record_demo.py"

Expects the account to have a library with the sample job file
(sample-docs/job-2025-118) and a job created from it. Writes datum-demo.mp4.
"""
import os
import shutil
import subprocess
import time
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

URL = os.environ.get("DATUM_URL", "http://host.docker.internal:3000")
EMAIL, PASSWORD = os.environ["DATUM_EMAIL"], os.environ["DATUM_PASSWORD"]
OUT = Path(os.environ.get("DEMO_OUT", "datum-demo.mp4"))
SIZE = {"width": 1440, "height": 900}

OVERLAY = """
(() => {
  if (document.getElementById('demo-caption')) return;
  const style = document.createElement('style');
  style.textContent = `
    #demo-caption { position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%); z-index: 99999;
      max-width: 900px; padding: 12px 20px; border-radius: 10px; background: rgba(15,16,18,.88); color: #fff;
      font: 500 17px/1.45 -apple-system, "Segoe UI", sans-serif; text-align: center; box-shadow: 0 8px 30px rgba(0,0,0,.35);
      transition: opacity .25s; pointer-events: none; }
    #demo-caption small { display: block; margin-top: 3px; color: #b9bcc3; font-size: 13.5px; font-weight: 400; }
    #demo-cursor { position: fixed; z-index: 100000; width: 22px; height: 22px; margin: -11px 0 0 -11px; border-radius: 50%;
      background: rgba(47,95,208,.35); border: 2px solid #2f5fd0; pointer-events: none;
      transition: left .45s ease, top .45s ease, transform .15s; }
    #demo-cursor.down { transform: scale(.7); background: rgba(47,95,208,.6); }
    #demo-card { position: fixed; inset: 0; z-index: 99998; display: grid; place-items: center; background: #111214; color: #fff;
      font-family: -apple-system, "Segoe UI", sans-serif; text-align: center; }
    #demo-card h1 { margin: 0 0 10px; font-size: 44px; font-weight: 650; letter-spacing: -.02em; }
    #demo-card p { margin: 6px 0; color: #b9bcc3; font-size: 19px; }`;
  document.head.appendChild(style);
  const caption = document.createElement('div'); caption.id = 'demo-caption'; caption.style.opacity = 0;
  const cursor = document.createElement('div'); cursor.id = 'demo-cursor'; cursor.style.left = '720px'; cursor.style.top = '450px';
  document.body.append(caption, cursor);
})()
"""


class Demo:
    def __init__(self, page):
        self.page = page

    def overlay(self):
        self.page.evaluate(OVERLAY)

    def say(self, text: str, sub: str = "", hold: float = 2.5):
        self.overlay()
        self.page.evaluate("([t, s]) => { const c = document.getElementById('demo-caption'); c.innerHTML = t + (s ? '<small>' + s + '</small>' : ''); c.style.opacity = 1 }", [text, sub])
        time.sleep(hold)

    def hide(self):
        self.page.evaluate("() => { const c = document.getElementById('demo-caption'); if (c) c.style.opacity = 0 }")

    def card(self, title: str, lines: list[str], hold: float = 4):
        self.overlay()
        self.page.evaluate("([t, ls]) => { const d = document.createElement('div'); d.id = 'demo-card'; d.innerHTML = '<div><h1>' + t + '</h1>' + ls.map(l => '<p>' + l + '</p>').join('') + '</div>'; document.body.appendChild(d) }", [title, lines])
        time.sleep(hold)
        self.page.evaluate("() => document.getElementById('demo-card')?.remove()")

    def point(self, locator):
        self.overlay()
        locator.scroll_into_view_if_needed()
        box = locator.bounding_box()
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        self.page.evaluate("([x, y]) => { const c = document.getElementById('demo-cursor'); c.style.left = x + 'px'; c.style.top = y + 'px' }", [x, y])
        time.sleep(0.6)

    def click(self, locator, pause: float = 1.0):
        self.point(locator)
        self.page.evaluate("() => document.getElementById('demo-cursor').classList.add('down')")
        locator.click()
        time.sleep(0.15)
        self.page.evaluate("() => document.getElementById('demo-cursor')?.classList.remove('down')")
        time.sleep(pause)

    def type(self, locator, text: str):
        self.click(locator, pause=0.3)
        locator.press_sequentially(text, delay=38)
        time.sleep(0.6)

    def scroll(self, selector: str, to: str = "bottom", steps: int = 6):
        for _ in range(steps):
            self.page.evaluate("([s, to]) => { const e = document.querySelector(s); if (e) e.scrollBy({ top: to === 'bottom' ? 220 : -220, behavior: 'smooth' }) }", [selector, to])
            time.sleep(0.45)


def main():
    video_dir = Path("/tmp/demo-video")
    shutil.rmtree(video_dir, ignore_errors=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport=SIZE, record_video_dir=str(video_dir), record_video_size=SIZE,
                                      color_scheme="light", device_scale_factor=1)
        page = context.new_page()
        demo = Demo(page)

        page.goto(URL)
        page.wait_for_selector(".auth-card")
        demo.card("Datum", ["Document intelligence for welding and fabrication QA",
                            "Runs entirely on this machine · qwen2.5:3b via Ollama · Apple M1, 8 GB"], hold=4.5)
        demo.say("Local accounts. Documents and the model never leave the machine.", hold=3)

        response = context.request.post(f"{URL}/api/auth/login", data={"email": EMAIL, "password": PASSWORD})
        assert response.ok, response.text()
        page.goto(URL)
        page.wait_for_selector(".sidebar")
        time.sleep(1)

        # Library
        demo.click(page.locator(".nav button", has_text="Library"))
        page.wait_for_selector(".table tbody tr")
        demo.say("A library holds a project's documents.",
                 "Each is read, split into passages, embedded, and mined for table values and figures.", hold=4)
        demo.hide()

        # Ask
        demo.click(page.locator(".nav button", has_text="Ask"))
        demo.click(page.locator(".new-thread"))
        demo.say("Ask a question in plain language", "Hybrid search → the model reranks the passages → a cited answer", hold=2.5)
        demo.type(page.locator(".composer textarea"), "What coupon thickness and test date does PQR-017 record?")
        demo.click(page.locator(".composer .btn-primary"), pause=0.5)
        demo.say("Answering on the local 3B model", "Sources arrive first, then the answer streams in", hold=1)
        page.wait_for_selector(".answer .answer-foot", timeout=240_000)
        demo.hide()
        time.sleep(1.5)
        demo.say("Every claim is cited. The model's own reasoning is kept separate,",
                 "and the grounding label says how well the sources support the answer.", hold=5)
        cite = page.locator(".answer .cite").first
        if cite.count():
            demo.click(cite, pause=3)
            demo.say("A citation opens the PDF at that page with the passage highlighted.", hold=4.5)
            close = page.locator(".viewer-header button[title='Close viewer']")
            if close.count():
                demo.click(close, pause=0.5)
        demo.hide()

        # Jobs
        demo.click(page.locator(".nav button", has_text="Jobs"))
        page.wait_for_selector("tr.clickable")
        demo.say("Job files: the WPS, PQR, welder qualifications, consumable certificate and weld log for one job",
                 "Fictional sample job JOB-2025-118", hold=4)
        demo.click(page.locator("tr.clickable td").first, pause=1.5)
        demo.click(page.locator("button", has_text="Run checks"), pause=0.5)
        page.wait_for_selector(".finding", timeout=120_000)
        time.sleep(1)
        demo.say("Datum reads the key fields from each document and cross-checks them in code, not with the model.",
                 "Seven problems planted in the sample job, all found: none of these are hallucinations.", hold=5)
        demo.scroll(".job-body", steps=4)
        demo.say("Code rules name their clause and ask you to verify against your edition.", hold=3.5)
        demo.scroll(".job-body", to="top", steps=4)
        evidence = page.locator(".evidence", has_text="Sample_PQR-017.pdf").first
        if evidence.count():
            demo.click(evidence, pause=3)
            demo.say("Evidence lines open the source page with the value highlighted.", hold=4)
            close = page.locator(".viewer-header button[title='Close viewer']")
            if close.count():
                demo.click(close, pause=0.5)
        demo.click(page.locator(".segmented button", has_text="Errors"), pause=1.5)
        demo.scroll(".job-body", steps=10)
        row = page.locator(".job-doc-row", has_text="Sample_PQR-017.pdf")
        demo.click(row.locator("button").first, pause=1)
        demo.say("Every extracted field shows where it came from, and can be corrected by hand.",
                 "The model may only propose a field, and its value is dropped unless it appears verbatim in the document.", hold=5)
        demo.hide()

        # Calculators
        demo.click(page.locator(".nav button", has_text="Calculators"), pause=1)
        demo.say("Welding calculations are done in code, with the formula and reference shown.", hold=3)
        current = page.locator(".calc").first.locator("input").nth(1)
        current.fill("")
        demo.type(current, "180")
        demo.click(page.locator("button", has_text="Use in preheat"), pause=1)
        demo.click(page.locator("button", has_text="Use CET in preheat"), pause=1.5)
        demo.say("Heat input and CET feed straight into the EN 1011-2 preheat estimate.",
                 "Out-of-range inputs are flagged against the method's validity limits.", hold=5)
        demo.hide()

        demo.card("Datum", ["Cited answers · cross-checked job files · welding calculations",
                            "Self-hosted: FastAPI, PostgreSQL + pgvector, Ollama, React"], hold=4)
        video_path = page.video.path()
        context.close()
        browser.close()

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", video_path, "-c:v", "libx264", "-preset", "slow",
                    "-crf", "26", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUT)], check=True)
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()

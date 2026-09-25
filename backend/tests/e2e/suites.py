"""
End-to-end suites against a running stack. Each takes (base_url, results, project).

  core     auth, libraries, upload + indexing, answers, citations, figures,
           diagrams, memory, access control, deletion cleanup
  welding  reference libraries (loader, read-only, scope switch), calculators
  jobs     job files: type guessing, extraction, checks, corrections, access
  real     answer quality with a real model: facts, citations, format,
           refusal, calculation deflection, timing (not for the fake model)
"""
import re
import time

from client import JOB_SAMPLES, OWNER, REVIEWER, SAMPLES, Client, compose

CORE_SAMPLES = ["Orion_requirements.docx", "PC-42_datasheet.pdf", "VE-9_datasheet.pdf"]


def core(base, r, project):
    owner, reviewer = Client(base), Client(base)
    r.check("owner signs in", owner.signin(OWNER) == 200)
    reviewer.signin(REVIEWER)
    _, health, _ = owner.req("GET", "/api/health")
    r.check("model backend reachable", health.get("ollama_available") is True, health)

    _, kb, _ = owner.req("POST", "/api/knowledge-bases", {"name": "Orion review (e2e)"})
    kb_id = kb["knowledge_base"]["id"]
    status, up, _ = owner.upload(f"/api/knowledge-bases/{kb_id}/documents", [SAMPLES / n for n in CORE_SAMPLES])
    r.check("upload accepted", status == 202 and len(up["documents"]) == 3, up)
    _, dup, _ = owner.upload(f"/api/knowledge-bases/{kb_id}/documents", [SAMPLES / "PC-42_datasheet.pdf"])
    r.check("re-upload is a duplicate", dup["documents"][0]["status"] == "duplicate", dup)
    docs = {d["filename"]: d for d in owner.wait_ready(f"/api/knowledge-bases/{kb_id}/documents")}
    r.check("documents indexed", all(d["status"] == "ready" for d in docs.values()), [(n, d["status"]) for n, d in docs.items()])
    pdf = docs["PC-42_datasheet.pdf"]
    r.check("tables and figure extracted", pdf["fact_count"] > 0 and pdf["figure_count"] > 0, pdf)

    _, chat, _ = owner.req("POST", "/api/chats", {"knowledge_base_id": kb_id})
    chat_id = chat["chat"]["id"]
    events = owner.ask(chat_id, "What is the thermal shutdown temperature of the PC-42?")
    names = [n for n, _ in events]
    r.check("answer streams sources, text, done", names[0] == "sources" and "delta" in names and names[-1] == "done", names[:2] + names[-1:])
    sources = events[0][1]["sources"]
    r.check("sources hide full chunk text", all("content" not in s for s in sources))
    r.check("grounding label", events[0][1]["confidence"] in ("high", "medium", "low", "none"))
    r.check("exact table values offered", any(s.get("exact") for s in sources), [s["location"] for s in sources])

    events = owner.ask(chat_id, "Compare the PC-42 and VE-9 dropout and ripple")
    r.check("comparison spans both datasheets", {"PC-42_datasheet.pdf", "VE-9_datasheet.pdf"} <= {s["filename"] for s in events[0][1]["sources"]})
    events = owner.ask(chat_id, "diagram: PC-42 block diagram")
    diagram = next((d["diagram"] for n, d in events if n == "diagram"), None)
    r.check("existing figure returned for diagram request", diagram and diagram["kind"] == "figure", diagram)
    if diagram and diagram["kind"] == "figure":
        status, _, headers = owner.req("GET", diagram["url"], raw=True)
        r.check("figure served to member", status == 200 and headers.get("Content-Type", "").startswith("image/"))
        status, _, _ = reviewer.req("GET", diagram["url"], raw=True)
        r.check("figure hidden from non-member", status == 404, status)

    status, body, headers = owner.req("GET", f"/api/documents/{pdf['id']}/file", raw=True)
    r.check("PDF served inline", status == 200 and body[:4] == b"%PDF" and "inline" in headers.get("Content-Disposition", ""))
    status, _, _ = reviewer.req("GET", f"/api/documents/{pdf['id']}/file", raw=True)
    r.check("document hidden from non-member", status == 404, status)
    time.sleep(5)
    _, memory, _ = owner.req("GET", f"/api/knowledge-bases/{kb_id}/memory")
    r.check("memory endpoint readable", isinstance(memory.get("entries"), list))
    status, _, _ = reviewer.req("GET", f"/api/knowledge-bases/{kb_id}/memory")
    r.check("memory hidden from non-member", status == 404, status)

    owner.req("POST", f"/api/knowledge-bases/{kb_id}/members", {"email": REVIEWER[0]})
    status, _, _ = reviewer.req("GET", f"/api/documents/{pdf['id']}/file", raw=True)
    r.check("invited member can read", status == 200, status)
    status, _, _ = reviewer.req("DELETE", f"/api/documents/{pdf['id']}")
    r.check("member can't delete owner's upload", status == 403, status)
    status, _, _ = owner.req("DELETE", f"/api/documents/{pdf['id']}")
    r.check("owner deletes document", status == 200, status)
    events = owner.ask(chat_id, "diagram: PC-42 block diagram")
    diagram = next((d["diagram"] for n, d in events if n == "diagram"), None)
    r.check("deleted document's figure gone", diagram and diagram["kind"] != "figure", diagram)
    status, schema, _ = owner.req("GET", "/api/openapi.json")
    r.check("API schema served under /api", status == 200 and "/api/jobs/{job_id}/check" in schema.get("paths", {}))
    status, html, _ = owner.req("GET", "/", raw=True)
    r.check("web app served", status == 200 and b'id="root"' in html)
    owner.req("DELETE", f"/api/knowledge-bases/{kb_id}")


def welding(base, r, project):
    wps = SAMPLES / "Sample_WPS-SMAW-017.docx"
    compose(project, "cp", str(wps), "api:/tmp/Sample_WPS-SMAW-017.docx")
    load = compose(project, "exec", "-T", "api", "python", "-m", "scripts.load_reference",
                   "--name", "Welding reference (e2e)", "/tmp/Sample_WPS-SMAW-017.docx")
    r.check("loader queues reference document", "queued" in load.stdout, load.stdout + load.stderr)
    again = compose(project, "exec", "-T", "api", "python", "-m", "scripts.load_reference",
                    "--name", "Welding reference (e2e)", "/tmp/Sample_WPS-SMAW-017.docx")
    r.check("loader skips a loaded file", "1 already loaded" in again.stdout, again.stdout)

    owner, reviewer = Client(base), Client(base)
    owner.signin(OWNER)
    reviewer.signin(REVIEWER)
    _, kbs, _ = reviewer.req("GET", "/api/knowledge-bases")
    ref = next((k for k in kbs["knowledge_bases"] if k["is_reference"]), None)
    r.check("reference library visible to everyone", ref is not None and ref["role"] == "reader", kbs)
    docs = reviewer.wait_ready(f"/api/knowledge-bases/{ref['id']}/documents")
    r.check("reference document indexed", docs[0]["status"] == "ready" and docs[0]["fact_count"] > 0, docs)
    status, _, _ = reviewer.upload(f"/api/knowledge-bases/{ref['id']}/documents", [SAMPLES / "VE-9_datasheet.pdf"])
    r.check("reader can't upload to reference", status == 403, status)
    status, _, _ = reviewer.req("DELETE", f"/api/documents/{docs[0]['id']}")
    r.check("reader can't delete reference document", status == 403, status)

    _, kb, _ = owner.req("POST", "/api/knowledge-bases", {"name": "Own library (e2e)"})
    kb_id = kb["knowledge_base"]["id"]
    owner.upload(f"/api/knowledge-bases/{kb_id}/documents", [SAMPLES / "VE-9_datasheet.pdf"])
    owner.wait_ready(f"/api/knowledge-bases/{kb_id}/documents")
    _, chat, _ = owner.req("POST", "/api/chats", {"knowledge_base_id": kb_id})
    chat_id = chat["chat"]["id"]
    question = "What is the maximum interpass temperature on WPS-SMAW-017?"
    files = {s["filename"] for s in owner.ask(chat_id, question)[0][1]["sources"]}
    r.check("thread searches reference alongside own library", "Sample_WPS-SMAW-017.docx" in files, files)
    owner.req("PATCH", f"/api/chats/{chat_id}", {"use_reference": False})
    files = {s["filename"] for s in owner.ask(chat_id, question)[0][1]["sources"]}
    r.check("reference excluded when switched off", "Sample_WPS-SMAW-017.docx" not in files, files)
    _, ref_chat, _ = reviewer.req("POST", "/api/chats", {"knowledge_base_id": ref["id"]})
    reviewer.ask(ref_chat["chat"]["id"], "Which electrode does WPS-SMAW-017 use?")
    time.sleep(8)
    _, memory, _ = reviewer.req("GET", f"/api/knowledge-bases/{ref['id']}/memory")
    r.check("no memory written into reference library", memory["entries"] == [], memory)

    status, hi, _ = owner.req("POST", "/api/calc/heat-input", {"voltage": 24, "current": 180, "travel_speed_mm_min": 150, "process": "SMAW"})
    r.check("heat input 24 V 180 A 150 mm/min SMAW = 1.382 kJ/mm", status == 200 and hi["heat_input_kj_mm"] == 1.382, hi)
    status, ce, _ = owner.req("POST", "/api/calc/carbon-equivalent", {"C": 0.2, "Mn": 1.2})
    r.check("CE(IIW) C 0.20 Mn 1.20 = 0.40", status == 200 and ce["ce_iiw"] == 0.4, ce)
    status, ph, _ = owner.req("POST", "/api/calc/preheat", {"cet": 0.35, "thickness_mm": 30, "hydrogen_ml_100g": 5, "heat_input_kj_mm": 1.5})
    r.check("EN 1011-2 preheat example = 116 °C", status == 200 and ph["preheat_c"] == 116, ph)
    status, _, _ = owner.req("POST", "/api/calc/heat-input", {"voltage": 24, "current": 180, "travel_speed_mm_min": 150, "process": "OXY"})
    r.check("unknown process rejected", status == 422, status)
    status, _, _ = Client(base).req("POST", "/api/calc/preheat", {"cet": 0.35, "thickness_mm": 30, "hydrogen_ml_100g": 5, "heat_input_kj_mm": 1.5})
    r.check("calculators need sign-in", status == 401, status)

    removed = compose(project, "exec", "-T", "api", "python", "-m", "scripts.load_reference", "--name", "Welding reference (e2e)", "--remove")
    _, kbs, _ = owner.req("GET", "/api/knowledge-bases")
    r.check("operator removes reference library", not any(k["is_reference"] for k in kbs["knowledge_bases"]), removed.stdout + removed.stderr)
    owner.req("DELETE", f"/api/knowledge-bases/{kb_id}")


def jobs(base, r, project):
    owner, reviewer = Client(base), Client(base)
    owner.signin(OWNER)
    reviewer.signin(REVIEWER)
    _, kb, _ = owner.req("POST", "/api/knowledge-bases", {"name": "Pipe rack project (e2e)"})
    kb_id = kb["knowledge_base"]["id"]
    status, job, _ = owner.req("POST", f"/api/knowledge-bases/{kb_id}/jobs", {"name": "JOB-2025-118 pipe rack"})
    r.check("create job", status == 201, job)
    job_id = job["job"]["id"]
    status, up, _ = owner.upload(f"/api/jobs/{job_id}/upload", sorted(JOB_SAMPLES.iterdir()))
    r.check("upload six job documents", status == 202 and len(up["documents"]) == 6, up)
    owner.wait_ready(f"/api/jobs/{job_id}")
    _, detail, _ = owner.req("GET", f"/api/jobs/{job_id}")
    docs = {d["filename"]: d for d in detail["documents"]}
    r.check("document types guessed", {n: d["doc_type"] for n, d in docs.items()} == {
        "Sample_PQR-017.pdf": "pqr", "Sample_TC-4471.pdf": "consumable", "Sample_WPQ-W14.pdf": "wpq", "Sample_WPQ-W22.pdf": "wpq",
        "Sample_WPS-SMAW-017.docx": "wps", "Sample_WeldLog_JOB-2025-118.xlsx": "weld_log"})

    def fields(name):
        return {f["key"]: f["display"] for f in docs[name]["fields"]}
    wps, pqr, w14, tc = (fields(n) for n in ("Sample_WPS-SMAW-017.docx", "Sample_PQR-017.pdf", "Sample_WPQ-W14.pdf", "Sample_TC-4471.pdf"))
    r.check("WPS fields", (wps["number"], wps["process"], wps["filler"], wps["thickness_range"], wps["pqr_refs"])
            == ("WPS-SMAW-017", "SMAW", "E7018", "10–25 mm", "PQR-017"), wps)
    r.check("PQR fields", (pqr["number"], pqr["test_thickness"], pqr["test_date"]) == ("PQR-017", "10 mm", "2025-03-12"), pqr)
    r.check("welder fields", (w14["welder_id"], w14["positions"], w14["test_date"]) == ("W-14", "1G, 2G", "2025-01-20"), w14)
    r.check("certificate fields", (tc["classification"], tc["batch"]) == ("E7016", "4471"), tc)
    r.check("weld log read", docs["Sample_WeldLog_JOB-2025-118.xlsx"]["log"]["rows"] == 7)

    _, result, _ = owner.req("POST", f"/api/jobs/{job_id}/check")
    checks = {f["check"] for f in result["check"]["findings"]}
    r.check("all seven planted problems found", {"thickness_over_2t", "consumable_mismatch", "log_welder_wrong_process",
            "log_welder_unqualified", "log_wps_missing", "log_thickness", "continuity_lapse"} <= checks, sorted(checks))
    r.check("no false WPS/PQR mismatches", not {"process_mismatch", "filler_mismatch_pqr", "base_metal_differs"} & checks)
    r.check("7 errors, 3 warnings", result["check"]["counts"] == {"error": 7, "warning": 3, "note": 0}, result["check"]["counts"])
    two_t = next(f for f in result["check"]["findings"] if f["check"] == "thickness_over_2t")
    r.check("2T finding cites WPS and PQR", {e["filename"] for e in two_t["evidence"]} == {"Sample_WPS-SMAW-017.docx", "Sample_PQR-017.pdf"})

    tc_id = docs["Sample_TC-4471.pdf"]["document_id"]
    status, _, _ = owner.req("PATCH", f"/api/jobs/{job_id}/documents/{tc_id}", {"overrides": {"classification": "not a class"}})
    r.check("unreadable correction rejected", status == 422, status)
    owner.req("PATCH", f"/api/jobs/{job_id}/documents/{tc_id}", {"overrides": {"classification": "E7018"}})
    _, fixed, _ = owner.req("POST", f"/api/jobs/{job_id}/check")
    r.check("correction clears the certificate finding", "consumable_mismatch" not in {f["check"] for f in fixed["check"]["findings"]})
    owner.req("PATCH", f"/api/jobs/{job_id}/documents/{tc_id}", {"overrides": {"classification": ""}})
    _, back, _ = owner.req("POST", f"/api/jobs/{job_id}/check")
    r.check("reverting brings it back", "consumable_mismatch" in {f["check"] for f in back["check"]["findings"]})

    status, _, _ = reviewer.req("GET", f"/api/jobs/{job_id}")
    r.check("job hidden from non-member", status == 404, status)
    owner.req("POST", f"/api/knowledge-bases/{kb_id}/members", {"email": REVIEWER[0]})
    status, seen, _ = reviewer.req("GET", f"/api/jobs/{job_id}")
    r.check("member sees job and last check", status == 200 and seen["check"]["counts"]["error"] == 7, status)
    log_id = docs["Sample_WeldLog_JOB-2025-118.xlsx"]["document_id"]
    owner.req("DELETE", f"/api/jobs/{job_id}/documents/{log_id}")
    _, without, _ = owner.req("POST", f"/api/jobs/{job_id}/check")
    left = {f["check"] for f in without["check"]["findings"]}
    r.check("detaching the log removes its findings", "continuity_lapse" not in left and "no_log" in left, sorted(left))
    r.check("delete job", owner.req("DELETE", f"/api/jobs/{job_id}")[0] == 200)
    owner.req("DELETE", f"/api/knowledge-bases/{kb_id}")


def real(base, r, project):
    """Answer quality on a real model, over the sample job documents."""
    owner = Client(base)
    owner.signin(OWNER)
    _, kb, _ = owner.req("POST", "/api/knowledge-bases", {"name": "Real model check (e2e)"})
    kb_id = kb["knowledge_base"]["id"]
    owner.upload(f"/api/knowledge-bases/{kb_id}/documents", sorted(JOB_SAMPLES.iterdir()))
    owner.wait_ready(f"/api/knowledge-bases/{kb_id}/documents")
    _, chat, _ = owner.req("POST", "/api/chats", {"knowledge_base_id": kb_id, "use_reference": False})
    chat_id = chat["chat"]["id"]
    cases = [
        ("What is the maximum interpass temperature on WPS-SMAW-017?", ["250"], "Sample_WPS-SMAW-017.docx"),
        ("What coupon thickness was used for PQR-017?", ["10"], "Sample_PQR-017.pdf"),
        ("Which positions is welder W-14 qualified for?", ["1G", "2G"], "Sample_WPQ-W14.pdf"),
        ("What electrode classification does test certificate TC-4471 cover?", ["E7016"], "Sample_TC-4471.pdf"),
    ]
    for question, facts, source in cases:
        start = time.time()
        events = owner.ask(chat_id, question)
        took = time.time() - start
        done = next((d["message"] for n, d in events if n == "done"), None)
        if not r.check(f"answered: {question}", done is not None, [n for n, _ in events][-1:]):
            continue
        answer, sources = done["content"], events[0][1]["sources"]
        print(f"     {took:.0f}s · grounding {events[0][1]['confidence']} · {answer[:220]!r}")
        r.check("  states the facts " + "/".join(facts), all(f.lower() in answer.lower() for f in facts), answer[:400])
        r.check(f"  cites {source}", source in {s["filename"] for s in sources[:4]}, [s["filename"] for s in sources[:4]])
        r.check("  uses [n] citations", bool(re.search(r"\[\d+\]", answer)), answer[:300])
        r.check("  keeps the two-part format", bool(re.search(r"from the documents", answer, re.I)), answer[:200])
        r.check("  writes an answer instead of pasting excerpts",
                not re.search(r"\[\d+\] \S+\.(pdf|docx|xlsx) \(|Exact table value -|value read from a table", answer), answer[:300])
    events = owner.ask(chat_id, "What minimum yield strength does IS 2062 E350 require?")
    done = next((d["message"] for n, d in events if n == "done"), {"content": ""})
    r.check("explains when the documents don't say", len(re.sub(r"(?i)from the documents:|additional insight:|none\.?", "", done["content"]).strip()) > 20
            and bool(re.search(r"not (found|stated|mention|provide|contain|specif|includ|cover)|none of the|no information|does not|doesn't|do not|missing", done["content"], re.I)), done["content"][:400])
    events = owner.ask(chat_id, "What is the heat input for 24 V, 160 A at 150 mm/min with SMAW?")
    done = next((d["message"] for n, d in events if n == "done"), {"content": ""})
    r.check("calculation done by the calculator, not the model: 1.229 kJ/mm", "1.229 kJ/mm" in done["content"]
            and "calculator" in done["content"].lower(), done["content"][:400])
    owner.req("DELETE", f"/api/knowledge-bases/{kb_id}")


SUITES = {"core": core, "welding": welding, "jobs": jobs, "real": real}

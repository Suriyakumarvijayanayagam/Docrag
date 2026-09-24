from app import job_fields
from app.job_checks import run_checks
from app.job_fields import (
    _from_facts, _from_model, _from_text, guess_doc_type, parse_classifications, parse_date, parse_positions,
    parse_processes, parse_range_mm, parse_refs, parse_temperature_c, positions_match,
)


def test_parsers_read_welding_notation():
    assert parse_processes("GTAW root + SMAW fill") == ["GTAW", "SMAW"]
    assert parse_processes("Process 135 (MAG)") == ["GMAW"]
    assert parse_classifications("AWS A5.1 E7018-1 H4R, 3.15 mm") == ["E7018-1"]
    assert parse_classifications("ER70S-6 wire with E71T-1C and E308L-16") == ["ER70S-6", "E71T-1C", "E308L-16"]
    assert parse_classifications("IS 2062 E250 BR") == []
    assert parse_positions("1G (PA) and 2G (PC)") == ["1G", "PA", "2G", "PC"]
    assert positions_match("PC", ["2G"]) and not positions_match("3G", ["1G", "2G"])
    assert parse_range_mm("10 mm to 25 mm") == {"min": 10, "max": 25}
    assert parse_range_mm("3/16 in - 1 in")["max"] == 25.4
    assert parse_temperature_c("Min 50 °C") == 50
    assert parse_temperature_c("200 °F") == 93.3
    assert parse_date("12/03/2025") == "2025-03-12"
    assert parse_date("12 Mar 2025") == "2025-03-12"
    assert parse_date("31/02/2025") is None
    assert parse_refs("Supported by PQR-017 and PQR 021") == ["PQR-017", "PQR-021"]


def test_table_label_wins_over_generic_match():
    field = next(f for f in job_fields.FIELDS["wpq"] if f.key == "positions")
    facts = [
        {"label": "Test position", "value": "2G", "page": 1, "locator": "p. 1 table 1 row 5"},
        {"label": "Positions qualified", "value": "1G, 2G", "page": 1, "locator": "p. 1 table 1 row 6"},
    ]

    assert _from_facts(field, facts)["value"] == ["1G", "2G"]


def test_text_lines_are_a_fallback():
    field = next(f for f in job_fields.FIELDS["wpq"] if f.key == "welder_id")
    chunks = [{"content": "Welder name: R. Kumar\nWelder ID: W-14\nProcess: SMAW", "page_start": 1}]

    record = _from_text(field, chunks)

    assert record["value"] == "W-14" and record["method"] == "text" and record["page"] == 1


def test_model_values_are_kept_only_when_in_the_document(monkeypatch):
    fields = [f for f in job_fields.FIELDS["wpq"] if f.key in ("welder_id", "test_date")]
    chunks = [{"content": "Certificate for welder W-14, tested 20/01/2025.", "page_start": 2}]
    monkeypatch.setattr(job_fields.llm, "chat", lambda *args, **kwargs: '{"welder_id": "W-14", "test_date": "2025-01-20"}')

    records = _from_model(fields, "wpq", chunks)

    assert records["welder_id"]["value"] == "W-14" and records["welder_id"]["method"] == "model"
    assert "test_date" not in records  # reformatted by the model, so not verifiable in the text


def test_doc_type_guess():
    assert guess_doc_type("Sample_PQR-017.pdf", "") == "pqr"
    assert guess_doc_type("WeldLog_JOB-118.xlsx", "") == "weld_log"
    assert guess_doc_type("scan_0042.pdf", "WELDER PERFORMANCE QUALIFICATION RECORD") == "wpq"
    assert guess_doc_type("cert.pdf", "Inspection certificate EN 10204 3.1") == "consumable"


def _rec(value, page=1):
    return {"value": value, "raw": str(value), "page": page, "locator": f"p. {page}", "snippet": str(value), "method": "table"}


def _doc(doc_id, doc_type, **fields):
    return {"document_id": doc_id, "filename": f"{doc_id}.pdf", "doc_type": doc_type, "fields": {k: _rec(v) for k, v in fields.items()}}


def _row(row, joint, welder, wps, day, position, thickness=12.0):
    return {"row": row, "joint": joint, "welder": welder, "wps": wps, "date": day, "position": [position],
            "process": [], "thickness": thickness, "snippet": f"{joint} {welder} {wps} {day} {position}"}


def _job():
    wps = _doc("wps", "wps", number="WPS-017", process=["SMAW"], filler=["E7018"], positions=["1G", "2G"],
               thickness_range={"min": 10, "max": 25}, pqr_refs=["PQR-017"], base_metal="IS 2062 E250 BR")
    pqr = _doc("pqr", "pqr", number="PQR-017", process=["SMAW"], filler=["E7018"], test_thickness=10.0,
               base_metal="IS 2062 E250 BR", test_date="2025-03-12")
    w14 = _doc("w14", "wpq", welder_id="W-14", process=["SMAW"], positions=["1G", "2G"], test_date="2025-01-20")
    w22 = _doc("w22", "wpq", welder_id="W-22", process=["GMAW"], positions=["1G", "2G", "3G", "4G"], test_date="2025-02-01")
    cert = _doc("tc", "consumable", classification=["E7016"])
    log = {"document_id": "log", "filename": "log.xlsx", "doc_type": "weld_log", "fields": {}, "log": {"rows": [
        _row(2, "J1", "W-14", "WPS-017", "2025-04-02", "1G"),
        _row(3, "J2", "W-14", "WPS-017", "2025-04-20", "3G"),
        _row(4, "J3", "W-22", "WPS-017", "2025-04-21", "1G"),
        _row(5, "J4", "W-14", "WPS-017", "2025-11-15", "2G"),
        _row(6, "J5", "W-31", "WPS-017", "2025-05-01", "1G"),
        _row(7, "J6", "W-14", "WPS-021", "2025-05-02", "1G"),
        _row(8, "J7", "W-14", "WPS-017", "2025-05-03", "1G", thickness=32.0),
    ]}}
    return [wps, pqr, w14, w22, cert, log]


def test_checks_find_each_planted_problem():
    result = run_checks(_job())
    checks = {finding["check"] for finding in result["findings"]}

    assert {"thickness_over_2t", "consumable_mismatch", "log_position", "log_welder_wrong_process",
            "continuity_lapse", "log_welder_unqualified", "log_wps_missing", "log_thickness"} <= checks
    assert "process_mismatch" not in checks and "filler_mismatch_pqr" not in checks
    assert result["counts"]["error"] >= 6


def test_findings_cite_both_sides():
    findings = {f["check"]: f for f in run_checks(_job())["findings"]}

    thickness = findings["thickness_over_2t"]
    assert {e["document_id"] for e in thickness["evidence"]} == {"wps", "pqr"}
    assert thickness["kind"] == "code_rule" and "QW-451.1" in thickness["rule"]
    continuity = findings["continuity_lapse"]
    assert "J4" in continuity["title"] and continuity["evidence"][0]["locator"] == "row 5"


def test_clean_job_has_no_errors():
    documents = [d for d in _job() if d["doc_type"] != "weld_log"]
    documents[1]["fields"]["test_thickness"] = _rec(15.0)
    documents[4]["fields"]["classification"] = _rec(["E7018"])

    result = run_checks(documents)

    assert result["counts"]["error"] == 0
    assert any(f["check"] == "no_log" for f in result["findings"])


def test_heading_with_dash_is_not_a_label_line():
    field = next(f for f in job_fields.FIELDS["wps"] if f.key == "number")
    chunks = [{"content": "WPS-SMAW-017 - Welding Procedure Specification\nScope: butt welds", "page_start": None}]

    assert _from_text(field, chunks) is None
    assert job_fields._from_whole_text(field, "wps", chunks)["value"] == "WPS-SMAW-017"

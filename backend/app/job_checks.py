"""
Cross-checks a job's documents against each other and against the weld log.

Two kinds of finding, kept apart on purpose:
  consistency - two documents in the job disagree. Needs no code knowledge.
  code_rule   - a limit from a welding code. Each names its clause and says to
                verify against the edition the job is built to; these are the
                only places code requirements are encoded, and there are few.

Every finding carries evidence from each side (document, page or row, the
text) so a reviewer can check it rather than trust it. Checks are plain code:
the same documents always give the same findings.
"""
from __future__ import annotations

from datetime import date

from app.job_fields import DOC_TYPES, FIELDS, canon_id, display, positions_match

SEVERITY_ORDER = {"error": 0, "warning": 1, "note": 2}
CONTINUITY_MONTHS = 6
FIELD_KINDS = {doc_type: {field.key: field for field in fields} for doc_type, fields in FIELDS.items()}


def _add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    for candidate in (day.day, 30, 29, 28):
        try:
            return date(year, month, min(day.day, candidate))
        except ValueError:
            continue
    return date(year, month, 28)


class Job:
    def __init__(self, documents: list[dict]):
        """documents: [{document_id, filename, doc_type, fields: {key: record}, log: {...} | None}]"""
        self.documents = documents
        self.findings: list[dict] = []

    def of(self, doc_type: str) -> list[dict]:
        return [document for document in self.documents if document["doc_type"] == doc_type]

    @staticmethod
    def value(document: dict, key: str):
        record = document["fields"].get(key)
        return record["value"] if record else None

    @staticmethod
    def evidence(document: dict, key: str | None = None, row: dict | None = None) -> dict:
        base = {"document_id": document["document_id"], "filename": document["filename"], "doc_type": document["doc_type"]}
        if row is not None:
            return {**base, "label": "Weld", "value": row["snippet"], "page": None,
                    "locator": f"row {row['row']}", "snippet": row["snippet"]}
        record = document["fields"].get(key) if key else None
        if not record:
            return {**base, "label": None, "value": None, "page": None, "locator": None, "snippet": None}
        field = FIELD_KINDS[document["doc_type"]][key]
        return {**base, "label": field.label, "value": display(field.kind, record["value"]), "page": record.get("page"),
                "locator": record.get("locator"), "snippet": record.get("snippet"), "method": record.get("method")}

    def add(self, check: str, severity: str, kind: str, title: str, detail: str, evidence: list[dict], rule: str | None = None) -> None:
        key = f"{check}:" + ":".join(sorted(f"{e['document_id']}:{e.get('locator') or e.get('label') or ''}" for e in evidence))
        self.findings.append({"id": key, "check": check, "severity": severity, "kind": kind, "title": title,
                              "detail": detail, "rule": rule, "evidence": evidence})

    # -- lookups ---------------------------------------------------------------

    def wps_by_number(self) -> dict[str, dict]:
        return {canon_id(self.value(doc, "number")): doc for doc in self.of("wps") if self.value(doc, "number")}

    def pqr_by_number(self) -> dict[str, dict]:
        return {canon_id(self.value(doc, "number")): doc for doc in self.of("pqr") if self.value(doc, "number")}

    def wpq_by_welder(self) -> dict[str, list[dict]]:
        found: dict[str, list[dict]] = {}
        for doc in self.of("wpq"):
            if self.value(doc, "welder_id"):
                found.setdefault(canon_id(self.value(doc, "welder_id")), []).append(doc)
        return found

    # -- checks ----------------------------------------------------------------

    def missing_fields(self) -> None:
        for doc in self.documents:
            for field in FIELDS.get(doc["doc_type"], ()):
                if field.required and not doc["fields"].get(field.key):
                    self.add("missing_field", "note", "missing", f"{field.label} not found in {doc['filename']}",
                             f"Checks that need the {field.label.lower()} skip this document. Enter it by hand on the document's fields.",
                             [self.evidence(doc)])

    def wps_against_pqr(self) -> None:
        pqrs = self.pqr_by_number()
        for wps in self.of("wps"):
            refs = self.value(wps, "pqr_refs") or []
            if not refs:
                if self.of("pqr"):
                    self.add("wps_no_pqr_ref", "note", "missing", f"{wps['filename']} doesn't name its supporting PQR",
                             "It can't be matched to a PQR in this job, so the WPS-to-PQR checks were skipped.", [self.evidence(wps)])
                continue
            for ref in refs:
                pqr = pqrs.get(canon_id(ref))
                if not pqr:
                    self.add("pqr_missing", "warning", "missing", f"Supporting {ref} is not in this job",
                             f"{wps['filename']} cites {ref}, but no PQR with that number has been added, so the procedure's qualification can't be checked.",
                             [self.evidence(wps, "pqr_refs")])
                    continue
                self._compare_wps_pqr(wps, pqr)

    def _compare_wps_pqr(self, wps: dict, pqr: dict) -> None:
        wps_process, pqr_process = set(self.value(wps, "process") or []), set(self.value(pqr, "process") or [])
        if wps_process and pqr_process and not wps_process <= pqr_process:
            self.add("process_mismatch", "error", "consistency", "WPS process isn't the process qualified by its PQR",
                     f"{wps['filename']} specifies {', '.join(sorted(wps_process))}; {pqr['filename']} qualifies {', '.join(sorted(pqr_process))}. "
                     "A change of process needs a new PQR.",
                     [self.evidence(wps, "process"), self.evidence(pqr, "process")])
        wps_filler, pqr_filler = set(self.value(wps, "filler") or []), set(self.value(pqr, "filler") or [])
        if wps_filler and pqr_filler and not wps_filler & pqr_filler:
            self.add("filler_mismatch_pqr", "warning", "consistency", "Filler classification differs between WPS and PQR",
                     f"WPS: {', '.join(sorted(wps_filler))}; PQR: {', '.join(sorted(pqr_filler))}. "
                     "Check that the change stays within the filler grouping the code allows without requalification.",
                     [self.evidence(wps, "filler"), self.evidence(pqr, "filler")])
        wps_metal, pqr_metal = self.value(wps, "base_metal"), self.value(pqr, "base_metal")
        if wps_metal and pqr_metal and canon_id(wps_metal) != canon_id(pqr_metal):
            self.add("base_metal_differs", "warning", "consistency", "Base metal differs between WPS and PQR",
                     f"WPS: {wps_metal}; PQR: {pqr_metal}. Confirm both fall in the same material group.",
                     [self.evidence(wps, "base_metal"), self.evidence(pqr, "base_metal")])
        thickness_range, coupon = self.value(wps, "thickness_range"), self.value(pqr, "test_thickness")
        if thickness_range and coupon and thickness_range.get("max") is not None and coupon < 38 and thickness_range["max"] > 2 * coupon:
            self.add("thickness_over_2t", "error", "code_rule", "WPS thickness range exceeds what the PQR coupon qualifies",
                     f"The PQR coupon is {coupon:g} mm, which qualifies up to {2 * coupon:g} mm; the WPS claims up to {thickness_range['max']:g} mm.",
                     [self.evidence(wps, "thickness_range"), self.evidence(pqr, "test_thickness")],
                     rule="ASME IX QW-451.1 (groove welds): maximum qualified thickness 2T for coupons under 38 mm (1½ in). "
                          "Verify against the code and edition this job is built to.")

    def consumables_against_wps(self) -> None:
        wps_fillers = {c: wps for wps in self.of("wps") for c in (self.value(wps, "filler") or [])}
        for cert in self.of("consumable"):
            classes = self.value(cert, "classification") or []
            if not classes or not wps_fillers:
                continue
            if not set(classes) & set(wps_fillers):
                wps = next(iter(wps_fillers.values()))
                self.add("consumable_mismatch", "error", "consistency", "Consumable certificate is for a different electrode than the WPS",
                         f"{cert['filename']} certifies {', '.join(classes)}; the WPS specifies {', '.join(sorted(wps_fillers))}. "
                         "Either the wrong batch was issued or the wrong certificate was filed.",
                         [self.evidence(cert, "classification"), self.evidence(wps, "filler")])

    def welders_against_wps(self) -> None:
        processes = {p for wps in self.of("wps") for p in (self.value(wps, "process") or [])}
        if not processes:
            return
        for wpq in self.of("wpq"):
            qualified = set(self.value(wpq, "process") or [])
            if qualified and not qualified & processes:
                self.add("welder_process_unused", "warning", "consistency", f"{self.value(wpq, 'welder_id') or wpq['filename']} isn't qualified for this job's processes",
                         f"Qualified for {', '.join(sorted(qualified))}; the job's WPSs use {', '.join(sorted(processes))}.",
                         [self.evidence(wpq, "process")] + [self.evidence(wps, "process") for wps in self.of("wps")[:1]])

    def weld_log(self) -> None:
        wps_index, welders = self.wps_by_number(), self.wpq_by_welder()
        for log in self.of("weld_log"):
            if log.get("log_error"):
                self.add("log_unreadable", "warning", "missing", f"Couldn't read {log['filename']} as a weld log", log["log_error"], [self.evidence(log)])
                continue
            rows = (log.get("log") or {}).get("rows", [])
            history: dict[tuple[str, str], list[tuple[date, dict]]] = {}
            for row in rows:
                wps = wps_index.get(canon_id(row["wps"])) if row["wps"] else None
                row_evidence = self.evidence(log, row=row)
                if row["wps"] and not wps:
                    self.add("log_wps_missing", "error", "consistency", f"Joint {row['joint']} was welded to {row['wps']}, which isn't in this job",
                             "Add that WPS to the job, or correct the log.", [row_evidence])
                qualifications = welders.get(canon_id(row["welder"]), [])
                if not qualifications:
                    self.add("log_welder_unqualified", "error", "consistency", f"No qualification on file for welder {row['welder']} (joint {row['joint']})",
                             "Add the welder's qualification record to the job, or correct the welder ID.", [row_evidence])
                    continue
                # the log's own process column wins; otherwise the process of the WPS it names
                row_process = set(row["process"])
                if not row_process and wps:
                    row_process = set(self.value(wps, "process") or [])
                qualified_process = [q for q in qualifications if not row_process or set(self.value(q, "process") or []) & row_process]
                if row_process and not qualified_process:
                    self.add("log_welder_wrong_process", "error", "consistency",
                             f"Welder {row['welder']} isn't qualified for {', '.join(sorted(row_process))} (joint {row['joint']})",
                             f"Their qualification covers {', '.join(sorted({p for q in qualifications for p in (self.value(q, 'process') or [])}))}.",
                             [row_evidence] + [self.evidence(q, "process") for q in qualifications])
                    continue
                relevant = qualified_process or qualifications
                for position in row["position"]:
                    if not any(positions_match(position, self.value(q, "positions") or []) for q in relevant if self.value(q, "positions")):
                        if any(self.value(q, "positions") for q in relevant):
                            self.add("log_position", "warning", "consistency", f"Joint {row['joint']} welded in {position}, not listed on welder {row['welder']}'s qualification",
                                     "Codes let some test positions cover others, so this may still be acceptable; check the position coverage rules "
                                     "(e.g. ASME IX QW-461.9) against the qualification.",
                                     [row_evidence] + [self.evidence(q, "positions") for q in relevant])
                    if wps and self.value(wps, "positions") and not positions_match(position, self.value(wps, "positions")):
                        self.add("log_position_wps", "warning", "consistency", f"Joint {row['joint']} welded in {position}, which {self.value(wps, 'number')} doesn't list",
                                 "Confirm the WPS covers this position.", [row_evidence, self.evidence(wps, "positions")])
                thickness_range = self.value(wps, "thickness_range") if wps else None
                if row["thickness"] is not None and thickness_range:
                    low, high = thickness_range.get("min"), thickness_range.get("max")
                    if (low is not None and row["thickness"] < low) or (high is not None and row["thickness"] > high):
                        self.add("log_thickness", "error", "consistency", f"Joint {row['joint']} is {row['thickness']:g} mm, outside {self.value(wps, 'number')}'s range",
                                 f"The WPS covers {display('range_mm', thickness_range)}.", [row_evidence, self.evidence(wps, "thickness_range")])
                if row["date"]:
                    welded = date.fromisoformat(row["date"])
                    tested = [date.fromisoformat(self.value(q, "test_date")) for q in relevant if self.value(q, "test_date")]
                    if tested and welded < min(tested):
                        self.add("log_before_qualification", "error", "consistency", f"Joint {row['joint']} was welded before welder {row['welder']} qualified",
                                 f"Welded {welded.isoformat()}; qualification test {min(tested).isoformat()}.",
                                 [row_evidence] + [self.evidence(q, "test_date") for q in relevant])
                    for process in row_process or {"?"}:
                        history.setdefault((canon_id(row["welder"]), process), []).append((welded, row))
            self._continuity(log, history, welders)

    def _continuity(self, log: dict, history: dict, welders: dict) -> None:
        for (welder, process), welds in history.items():
            qualifications = [q for q in welders.get(welder, []) if process == "?" or process in (self.value(q, "process") or [])]
            tested = [date.fromisoformat(self.value(q, "test_date")) for q in qualifications if self.value(q, "test_date")]
            if not tested:
                continue
            welds = sorted(welds, key=lambda item: item[0])
            label = process if process != "?" else "welding"
            # count from the latest test before the first logged weld (welding before any
            # test is reported separately as log_before_qualification)
            earlier = [d for d in tested if d <= welds[0][0]]
            last = max(earlier) if earlier else min(tested)
            for welded, row in welds:
                if welded > _add_months(last, CONTINUITY_MONTHS):
                    self.add("continuity_lapse", "error", "code_rule",
                             f"Welder {row['welder']}'s {label} qualification had lapsed when joint {row['joint']} was welded",
                             f"No {label} welding is recorded between {last.isoformat()} and {welded.isoformat()}, more than {CONTINUITY_MONTHS} months. "
                             "The qualification needs renewing before this weld counts.",
                             [self.evidence(log, row=row)] + [self.evidence(q, "test_date") for q in qualifications],
                             rule="ASME IX QW-322.1(a): a welder's qualification expires after 6 months without welding in that process. "
                                  "Check the code this job is built to; the log may also be missing welds from other jobs.")
                    break
                last = max(last, welded)

    def coverage(self) -> None:
        if not self.of("wps"):
            self.add("no_wps", "note", "missing", "No WPS in this job", "Add the welding procedure specification to check everything against it.", [])
        if self.of("wps") and not self.of("pqr"):
            self.add("no_pqr", "note", "missing", "No PQR in this job", "Add the supporting PQR to check the WPS's qualification.", [])
        if self.of("wps") and not self.of("consumable"):
            self.add("no_consumable", "note", "missing", "No consumable certificate", "Add the electrode or wire test certificate to check it matches the WPS.", [])
        if self.of("wps") and not self.of("weld_log"):
            self.add("no_log", "note", "missing", "No weld log", "Add a weld log (joint, welder, WPS, date, position) to check welders against the joints they welded.", [])

    def run(self) -> list[dict]:
        self.missing_fields()
        self.wps_against_pqr()
        self.consumables_against_wps()
        self.welders_against_wps()
        self.weld_log()
        self.coverage()
        unique = list({finding["id"]: finding for finding in self.findings}.values())
        return sorted(unique, key=lambda finding: (SEVERITY_ORDER[finding["severity"]], finding["check"], finding["title"]))


def run_checks(documents: list[dict]) -> dict:
    findings = Job(documents).run()
    counts = {severity: sum(1 for finding in findings if finding["severity"] == severity) for severity in SEVERITY_ORDER}
    return {"findings": findings, "counts": counts, "documents": len(documents),
            "doc_types": {doc_type: sum(1 for d in documents if d["doc_type"] == doc_type) for doc_type in DOC_TYPES}}

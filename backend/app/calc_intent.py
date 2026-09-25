"""
Answers calculation questions with the calculators instead of the model.

"What's the heat input for 24 V, 160 A at 150 mm/min with SMAW?" has one
right answer, and a 3B model gets arithmetic wrong with confidence. So these
questions never reach it: the numbers are parsed here and run through
welding.py, and the reply shows the formula and reference. Missing inputs are
named rather than guessed.
"""
from __future__ import annotations

import re

from app import welding
from app.job_fields import parse_processes

_HEAT_INPUT = re.compile(r"\b(heat[\s-]*input|arc[\s-]*energy)\b", re.I)
_OTHER_CALC = re.compile(r"\b(carbon equivalent|\bCE\b|\bCET\b|\bPcm\b|preheat)\b", re.I)
_ASKS_TO_COMPUTE = re.compile(r"\b(calculate|compute|work out|what(?:'s| is| would be)|how much|find)\b", re.I)
_NUMBER = r"(\d+(?:\.\d+)?)"


def _travel_speed_mm_min(text: str) -> float | None:
    for pattern, factor in ((rf"{_NUMBER}\s*mm\s*/\s*min", 1), (rf"{_NUMBER}\s*mm\s*/\s*s(?:ec)?\b", 60),
                            (rf"{_NUMBER}\s*cm\s*/\s*min", 10), (rf"{_NUMBER}\s*(?:in|ipm|inch(?:es)?)\s*/?\s*(?:min)?\b", 25.4)):
        if match := re.search(pattern, text, re.I):
            return float(match.group(1)) * factor
    return None


def answer(question: str) -> str | None:
    """A markdown reply for a calculation question, or None to let the normal pipeline answer."""
    if not _ASKS_TO_COMPUTE.search(question):
        return None
    if _HEAT_INPUT.search(question):
        voltage = re.search(rf"{_NUMBER}\s*(?:V|volts?)\b", question, re.I)
        current = re.search(rf"{_NUMBER}\s*(?:A|amps?|amperes?)\b", question)
        speed = _travel_speed_mm_min(question)
        processes = parse_processes(question)
        if not (voltage or current or speed):
            return None  # a question about a document's heat-input limits, not a calculation
        missing = [name for name, value in (("arc voltage (V)", voltage), ("welding current (A)", current),
                                            ("travel speed (mm/min)", speed), ("process (SMAW, GMAW, GTAW, SAW…)", processes)) if not value]
        if missing:
            return ("This is a calculation, so Datum does it with its calculator rather than the model. "
                    f"To work out heat input it still needs the {', '.join(missing)}. "
                    "Add them to the question, or use the **Calculators** page.")
        result = welding.heat_input(float(voltage.group(1)), float(current.group(1)), speed, processes[0])
        warnings = "".join(f"\n\n> {warning}" for warning in result["warnings"])
        return (
            f"**Heat input: {result['heat_input_kj_mm']} kJ/mm** for {processes[0]} at {voltage.group(1)} V, "
            f"{current.group(1)} A and {speed:g} mm/min (arc energy {result['arc_energy_kj_mm']} kJ/mm × "
            f"thermal efficiency k = {result['efficiency']}).\n\n"
            f"Worked out by Datum's calculator, not the model: `{result['formula']}`. {result['reference']}"
            f"{warnings}\n\nThe **Calculators** page takes this on to a CET preheat estimate."
        )
    composition = re.search(r"\d\s*%|\b(?:C|Mn|Cr|Mo|Ni|Cu|Si|V)\s*[=:]?\s*0?\.\d", question)
    if _OTHER_CALC.search(question) and composition:
        return ("Carbon equivalent and preheat are calculations, so Datum does them with its calculator rather "
                "than the model. Open the **Calculators** page and enter the composition (weight %), plate "
                "thickness, diffusible hydrogen and heat input; it shows the formula, reference and validity limits.")
    return None

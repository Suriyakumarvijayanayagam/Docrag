"""
Welding calculations done in code, never by the model: a 3B model will get
arithmetic wrong with total confidence, and these numbers decide whether a
joint cracks. Each result carries the formula and the reference it follows,
and warns when inputs fall outside the range the method was validated for.

These are estimates to check against the governing code and the qualified
WPS, not replacements for them.
"""
import math

# Thermal efficiency factor k by process (ISO/TR 17671-1, formerly EN 1011-1).
PROCESS_EFFICIENCY = {
    "SAW": 1.0,
    "SMAW": 0.8,
    "GMAW": 0.8,
    "FCAW": 0.8,
    "MCAW": 0.8,
    "GTAW": 0.6,
    "PAW": 0.6,
}

# Composition limits (wt %) within which the EN 1011-2 CET method applies.
CET_RANGES = {
    "C": (0.05, 0.32), "Si": (0.0, 0.8), "Mn": (0.5, 1.9), "Cr": (0.0, 1.5),
    "Cu": (0.0, 0.7), "Mo": (0.0, 0.75), "Ni": (0.0, 2.5), "V": (0.0, 0.18), "B": (0.0, 0.005),
}


def heat_input(voltage: float, current: float, travel_speed_mm_min: float, process: str) -> dict:
    """Arc energy and heat input in kJ/mm."""
    process = process.upper()
    if process not in PROCESS_EFFICIENCY:
        raise ValueError(f"Unknown process {process}; expected one of {', '.join(PROCESS_EFFICIENCY)}")
    if voltage <= 0 or current <= 0 or travel_speed_mm_min <= 0:
        raise ValueError("Voltage, current and travel speed must be positive")
    arc_energy = voltage * current * 60 / (1000 * travel_speed_mm_min)
    efficiency = PROCESS_EFFICIENCY[process]
    warnings = []
    if not 5 <= voltage <= 60:
        warnings.append(f"{voltage} V is outside the usual 5-60 V range for arc welding; check the units.")
    if travel_speed_mm_min > 3000:
        warnings.append("Travel speed above 3000 mm/min is unusual; check it isn't in mm/s or in/min.")
    return {
        "arc_energy_kj_mm": round(arc_energy, 3),
        "heat_input_kj_mm": round(arc_energy * efficiency, 3),
        "efficiency": efficiency,
        "formula": "arc energy = V × I × 60 / (1000 × travel speed [mm/min]);  heat input = k × arc energy",
        "reference": "Arc energy as in ASME Section IX QW-409.1(a); thermal efficiency k per ISO/TR 17671-1 (EN 1011-1). "
                     "Waveform-controlled power sources need the instantaneous energy method (QW-409.1(c)).",
        "warnings": warnings,
    }


def carbon_equivalent(C: float, Mn: float, Si: float = 0, Cr: float = 0, Mo: float = 0, V: float = 0,
                      Ni: float = 0, Cu: float = 0, B: float = 0) -> dict:
    """IIW CE, CET and Pcm from a composition in weight %."""
    composition = {"C": C, "Mn": Mn, "Si": Si, "Cr": Cr, "Mo": Mo, "V": V, "Ni": Ni, "Cu": Cu, "B": B}
    for element, value in composition.items():
        if value < 0 or value > 30:
            raise ValueError(f"{element} = {value} % is not a plausible weight percentage")
    ce_iiw = C + Mn / 6 + (Cr + Mo + V) / 5 + (Ni + Cu) / 15
    cet = C + (Mn + Mo) / 10 + (Cr + Cu) / 20 + Ni / 40
    pcm = C + Si / 30 + (Mn + Cu + Cr) / 20 + Ni / 60 + Mo / 15 + V / 10 + 5 * B
    warnings = [
        f"{element} = {composition[element]} % is outside the {low}-{high} % range of the EN 1011-2 CET method"
        for element, (low, high) in CET_RANGES.items()
        if not low <= composition[element] <= high
    ]
    if C < 0.18:
        warnings.append("For C below about 0.18 %, Pcm usually predicts cold-cracking risk better than IIW CE.")
    return {
        "ce_iiw": round(ce_iiw, 3),
        "cet": round(cet, 3),
        "pcm": round(pcm, 3),
        "formula": {
            "ce_iiw": "C + Mn/6 + (Cr+Mo+V)/5 + (Ni+Cu)/15",
            "cet": "C + (Mn+Mo)/10 + (Cr+Cu)/20 + Ni/40",
            "pcm": "C + Si/30 + (Mn+Cu+Cr)/20 + Ni/60 + Mo/15 + V/10 + 5B",
        },
        "reference": "IIW CE; CET per EN 1011-2 Annex C; Pcm (Ito-Bessyo).",
        "warnings": warnings,
    }


def preheat_cet(cet: float, thickness_mm: float, hydrogen_ml_100g: float, heat_input_kj_mm: float) -> dict:
    """Minimum preheat estimate by the EN 1011-2 Annex C (CET) method."""
    if thickness_mm <= 0 or hydrogen_ml_100g <= 0 or heat_input_kj_mm <= 0 or cet <= 0:
        raise ValueError("All inputs must be positive")
    temperature = (
        697 * cet
        + 160 * math.tanh(thickness_mm / 35)
        + 62 * hydrogen_ml_100g ** 0.35
        + (53 * cet - 32) * heat_input_kj_mm
        - 328
    )
    warnings = []
    for label, value, low, high, unit in (
        ("CET", cet, 0.2, 0.5, "%"),
        ("Thickness", thickness_mm, 10, 90, "mm"),
        ("Diffusible hydrogen", hydrogen_ml_100g, 1, 20, "ml/100 g"),
        ("Heat input", heat_input_kj_mm, 0.5, 4.0, "kJ/mm"),
    ):
        if not low <= value <= high:
            warnings.append(f"{label} {value} {unit} is outside the method's validated range ({low}-{high} {unit}).")
    return {
        "preheat_c": round(temperature),
        "required": temperature > 0,
        "formula": "Tp = 697·CET + 160·tanh(d/35) + 62·HD^0.35 + (53·CET − 32)·Q − 328  [°C]",
        "reference": "EN 1011-2 Annex C (CET method). Check against the preheat required by the governing code and WPS.",
        "warnings": warnings,
    }

import math

import pytest

from app.welding import carbon_equivalent, heat_input, preheat_cet


def test_heat_input_applies_process_efficiency():
    result = heat_input(24, 180, 150, "smaw")

    assert result["arc_energy_kj_mm"] == pytest.approx(1.728)
    assert result["heat_input_kj_mm"] == pytest.approx(1.382, abs=1e-3)
    assert result["efficiency"] == 0.8
    assert heat_input(30, 500, 400, "SAW")["heat_input_kj_mm"] == pytest.approx(2.25)
    assert heat_input(12, 120, 100, "GTAW")["heat_input_kj_mm"] == pytest.approx(0.518, abs=1e-3)


def test_heat_input_rejects_bad_input_and_flags_suspect_units():
    with pytest.raises(ValueError):
        heat_input(24, 180, 0, "SMAW")
    with pytest.raises(ValueError):
        heat_input(24, 180, 150, "OXY")
    assert heat_input(24, 180, 5000, "GMAW")["warnings"]


def test_carbon_equivalents():
    result = carbon_equivalent(C=0.20, Mn=1.20, Si=0.30, Cr=0.10, Mo=0.05, V=0.01, Ni=0.10, Cu=0.10)

    assert result["ce_iiw"] == pytest.approx(0.20 + 0.20 + 0.16 / 5 + 0.20 / 15, abs=1e-3)
    assert result["cet"] == pytest.approx(0.20 + 1.25 / 10 + 0.20 / 20 + 0.10 / 40, abs=1e-3)
    assert result["pcm"] == pytest.approx(0.20 + 0.01 + 1.40 / 20 + 0.10 / 60 + 0.05 / 15 + 0.001, abs=1e-3)
    assert result["warnings"] == []


def test_carbon_equivalent_warns_outside_cet_range_and_for_low_carbon():
    warnings = carbon_equivalent(C=0.08, Mn=2.2)["warnings"]

    assert any("Mn" in warning for warning in warnings)
    assert any("Pcm" in warning for warning in warnings)
    with pytest.raises(ValueError):
        carbon_equivalent(C=-0.1, Mn=1.0)


def test_preheat_matches_formula_and_flags_range():
    result = preheat_cet(cet=0.35, thickness_mm=30, hydrogen_ml_100g=5, heat_input_kj_mm=1.5)
    expected = 697 * 0.35 + 160 * math.tanh(30 / 35) + 62 * 5 ** 0.35 + (53 * 0.35 - 32) * 1.5 - 328

    assert result["preheat_c"] == round(expected)
    assert result["required"] is True
    assert result["warnings"] == []
    assert preheat_cet(cet=0.25, thickness_mm=12, hydrogen_ml_100g=2, heat_input_kj_mm=2.0)["required"] is False
    assert preheat_cet(cet=0.6, thickness_mm=120, hydrogen_ml_100g=5, heat_input_kj_mm=1.0)["warnings"]

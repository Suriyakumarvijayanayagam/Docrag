from app.calc_intent import answer


def test_heat_input_question_is_calculated_not_generated():
    reply = answer("What is the heat input for 24 V, 160 A at 150 mm/min with SMAW?")

    assert "1.229 kJ/mm" in reply and "1.536" in reply and "QW-409.1" in reply


def test_units_are_converted():
    assert "1.229 kJ/mm" in answer("Calculate heat input: SMAW, 24 volts, 160 amps, 2.5 mm/s")


def test_missing_inputs_are_named_not_guessed():
    reply = answer("What is the heat input at 24 V and 160 A?")

    assert "travel speed" in reply and "process" in reply and "kJ/mm" not in reply


def test_document_questions_go_to_the_model():
    assert answer("What heat input limit does WPS-SMAW-017 set?") is None
    assert answer("What preheat does WPS-SMAW-017 require?") is None
    assert answer("Summarise the PQR-017 test results") is None


def test_composition_questions_point_to_the_calculators():
    assert "Calculators" in answer("What is the carbon equivalent for C 0.18, Mn 1.4?")

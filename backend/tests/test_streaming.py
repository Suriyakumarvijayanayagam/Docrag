from app.streaming import _says_nothing


def test_bare_none_counts_as_no_answer():
    assert _says_nothing("None.")
    assert _says_nothing("FROM THE DOCUMENTS:\nNone.\n\nADDITIONAL INSIGHT:\nNone.")
    assert _says_nothing("**FROM THE DOCUMENTS:** None")


def test_real_answers_are_kept():
    assert not _says_nothing("FROM THE DOCUMENTS: None of the documents state the E350 yield strength [1].")
    assert not _says_nothing("The coupon was 10 mm [2].")

from app.retrieval import ensure_document_diversity, is_comparison_query, is_exhaustive_query, spreadsheet_facts


def test_exhaustive_query_detection():
    assert is_exhaustive_query("List all students")
    assert is_exhaustive_query("How many students are in the workbook?")
    assert not is_exhaustive_query("Summarize the students' attendance")


def test_spreadsheet_facts_count_unique_student_rows_not_excel_row_numbers():
    sources = [
        {
            "document_id": "workbook-1",
            "filename": "Students Due List.xlsx",
            "section": "Roster",
            "document_complete": True,
            "content": (
                "Sheet Roster — Row 4 — Student Name: Alice | Student ID: 1\n"
                "Sheet Roster — Row 5 — Student Name: Bob | Student ID: 2"
            ),
        },
        {
            "document_id": "workbook-1",
            "filename": "Students Due List.xlsx",
            "section": "Roster",
            "document_complete": True,
            "content": (
                "Sheet Roster — Row 5 — Student Name: Bob | Student ID: 2\n"
                "Sheet Roster — Row 6 — Student Name: Total | Student ID: 2"
            ),
        },
    ]

    facts = spreadsheet_facts(sources)

    assert len(facts) == 1
    assert "2 data rows" in facts[0]
    assert "'Student Name' values in sheet order (2): Alice; Bob" in facts[0]


def test_spreadsheet_facts_are_not_claimed_for_partial_documents():
    sources = [{
        "document_id": "workbook-1",
        "filename": "Students Due List.xlsx",
        "section": "Roster",
        "document_complete": False,
        "content": "Sheet Roster — Row 4 — Student Name: Alice",
    }]

    assert spreadsheet_facts(sources) == []


def test_spreadsheet_facts_use_first_column_when_no_name_column():
    sources = [{
        "document_id": "parts", "filename": "BOM.xlsx", "section": "Parts", "document_complete": True,
        "content": "Sheet Parts — Row 2 — Part: R1 | Qty: 4\nSheet Parts — Row 3 — Part: C7 | Qty: 2\n"
                   "Sheet Parts — Row 4 — Part: Total | Qty: 6",
    }]

    facts = spreadsheet_facts(sources)

    assert "2 data rows" in facts[0]
    assert "'Part' values in sheet order (2): R1; C7" in facts[0]


def test_comparison_detection():
    assert is_comparison_query("Compare the PC-42 and VE-9 dropout voltage")
    assert is_comparison_query("PC-42 vs VE-9")
    assert not is_comparison_query("What is the dropout voltage of the PC-42?")


def test_document_diversity_interleaves_documents():
    candidates = [{"id": i, "document_id": doc} for i, doc in enumerate(["a", "a", "a", "b", "b"])]

    ordered = ensure_document_diversity(candidates)

    assert [c["document_id"] for c in ordered] == ["a", "b", "a", "b", "a"]
    assert len(ordered) == len(candidates)

from app.chunking import TextBlock, chunk_blocks
from app.ingestion import extract_document


def test_single_block_is_not_duplicated_at_final_flush():
    chunks = chunk_blocks([TextBlock("A concise paragraph with useful information.", page=3)], max_tokens=80, overlap=12)

    assert len(chunks) == 1
    assert chunks[0].page_start == 3
    assert chunks[0].page_end == 3
    assert "concise paragraph" in chunks[0].content


def test_chunking_preserves_section_and_splits_long_content():
    paragraph = " ".join(f"term{index}" for index in range(260))
    chunks = chunk_blocks([TextBlock(paragraph, page=2, section="Findings")], max_tokens=55, overlap=8)

    assert len(chunks) > 1
    assert all(chunk.section == "Findings" for chunk in chunks)
    assert all(chunk.page_start == 2 and chunk.page_end == 2 for chunk in chunks)
    assert all(chunk.token_count <= 55 for chunk in chunks)


def test_empty_blocks_are_skipped():
    assert chunk_blocks([TextBlock("  "), TextBlock("\n")]) == []


def test_overlap_does_not_create_duplicate_chunks():
    blocks = [TextBlock(" ".join(f"p{block}w{word}" for word in range(36)), page=block) for block in range(8)]

    chunks = chunk_blocks(blocks, max_tokens=84, overlap=30)

    assert len(chunks) > 2
    assert len({chunk.content for chunk in chunks}) == len(chunks)
    assert all(chunk.token_count <= 84 for chunk in chunks)


def test_markdown_keeps_heading_context(tmp_path):
    document = tmp_path / "notes.md"
    document.write_text("# Launch plan\n\nShip the local workspace next month.", encoding="utf-8")

    blocks, page_count = extract_document(str(document), ".md")

    assert page_count == 0
    assert blocks[0].section == "Launch plan"
    assert blocks[1].section == "Launch plan"


def test_spreadsheet_rows_keep_column_labels(tmp_path):
    from openpyxl import Workbook

    document = tmp_path / "metrics.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Quarterly"
    sheet.append(["Metric", "Value"])
    sheet.append(["Revenue", 125])
    workbook.save(document)

    blocks, page_count = extract_document(str(document), ".xlsx")

    assert page_count == 1
    assert blocks[0].section == "Quarterly"
    assert "Metric: Revenue" in blocks[0].text
    assert "Value: 125" in blocks[0].text


def test_spreadsheet_skips_title_and_header_and_keeps_each_record_once(tmp_path):
    import re

    from openpyxl import Workbook
    from app.ingestion import make_chunks

    document = tmp_path / "students.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Roster"
    sheet.append(["Students Due List — May 2026"])
    sheet.append([None])
    sheet.append(["Student Name", "Student ID", "Status"])
    for index in range(60):
        sheet.append([f"Student {index + 1}", index + 1, "Due"])
    workbook.save(document)

    chunks, page_count = make_chunks(str(document))
    row_numbers = [
        int(match.group(1))
        for chunk in chunks
        for match in re.finditer(r"(?m)^Sheet Roster — Row (\d+) —", chunk.content)
    ]

    assert page_count == 1
    assert len(row_numbers) == 60
    assert len(set(row_numbers)) == 60
    assert min(row_numbers) == 4
    assert max(row_numbers) == 63

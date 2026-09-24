"""
Loads documents into a reference library: a read-only library every account
on this server can search, meant for standards, codes and manufacturer
catalogues (for example IS 2062 / IS 814 / IS 816, ASME Section IX, AWS D1.1,
electrode datasheets). The worker indexes them like any upload.

Run inside the API container, with the files mounted or copied in:

    docker compose cp ./standards api:/tmp/standards
    docker compose exec api python -m scripts.load_reference \
        --name "Welding reference" --description "Codes, standards and consumable data" /tmp/standards

Re-running with the same name adds new files and skips ones already loaded.
--list shows reference libraries; --remove deletes one with its documents.

Standards bodies (BIS, ASME, AWS, ISO) license their documents; load only
copies your organisation is licensed to share with everyone on this server.
"""
import argparse
import sys
from pathlib import Path

from app.config import settings
from app.db import connection, initialize_database
from app.ingestion import SUPPORTED_EXTENSIONS
from app.storage import remove_document_files, store_document


def _files(paths: list[str]) -> list[Path]:
    found: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            found.extend(sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS))
        elif path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            found.append(path)
        else:
            print(f"skipped (not found or unsupported type): {path}", file=sys.stderr)
    return found


def _library(name: str, description: str) -> dict:
    with connection() as conn:
        library = conn.execute(
            "SELECT id, name FROM knowledge_bases WHERE is_reference AND name=%s", (name,)
        ).fetchone()
        if library:
            if description:
                conn.execute("UPDATE knowledge_bases SET description=%s WHERE id=%s", (description, library["id"]))
                conn.commit()
            return library
        library = conn.execute(
            """INSERT INTO knowledge_bases(name, description, created_by, is_reference)
               VALUES(%s, %s, NULL, true) RETURNING id, name""",
            (name, description),
        ).fetchone()
        conn.commit()
        return library


def load(name: str, description: str, paths: list[str]) -> None:
    library = _library(name, description)
    limit = settings.max_upload_mb * 1024 * 1024
    added = duplicates = 0
    for path in _files(paths):
        content = path.read_bytes()
        if not content or len(content) > limit:
            print(f"skipped (empty or over {settings.max_upload_mb} MB): {path}", file=sys.stderr)
            continue
        row = store_document(content, path.name, kb_id=library["id"])
        if row.get("status") == "duplicate":
            duplicates += 1
        else:
            added += 1
            print(f"queued: {path.name}")
    print(f"{library['name']}: {added} queued for indexing, {duplicates} already loaded")


def list_libraries() -> None:
    with connection() as conn:
        rows = conn.execute(
            """SELECT kb.name, count(d.id) AS documents,
                      count(d.id) FILTER (WHERE d.status='ready') AS ready
               FROM knowledge_bases kb LEFT JOIN documents d ON d.knowledge_base_id=kb.id
               WHERE kb.is_reference GROUP BY kb.id ORDER BY kb.name"""
        ).fetchall()
    for row in rows:
        print(f"{row['name']}: {row['ready']}/{row['documents']} documents ready")
    if not rows:
        print("No reference libraries.")


def remove(name: str) -> None:
    with connection() as conn:
        library = conn.execute("SELECT id FROM knowledge_bases WHERE is_reference AND name=%s", (name,)).fetchone()
        if not library:
            sys.exit(f"No reference library named {name!r}")
        documents = conn.execute("SELECT id, storage_path FROM documents WHERE knowledge_base_id=%s", (library["id"],)).fetchall()
        conn.execute("DELETE FROM knowledge_bases WHERE id=%s", (library["id"],))
        conn.commit()
    for document in documents:
        remove_document_files(document)
    print(f"Removed {name} and {len(documents)} documents")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage reference libraries readable by every account.")
    parser.add_argument("paths", nargs="*", help="files or directories to load")
    parser.add_argument("--name", help="reference library name")
    parser.add_argument("--description", default="")
    parser.add_argument("--list", action="store_true", help="list reference libraries")
    parser.add_argument("--remove", action="store_true", help="delete the named reference library")
    args = parser.parse_args()

    initialize_database()
    if args.list:
        list_libraries()
    elif args.remove:
        if not args.name:
            parser.error("--remove needs --name")
        remove(args.name)
    else:
        if not args.name or not args.paths:
            parser.error("give --name and at least one file or directory")
        load(args.name, args.description, args.paths)


if __name__ == "__main__":
    main()

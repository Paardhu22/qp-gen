"""Fix SQLite DocumentChunk.pdfSourceId still being NOT NULL.

Migration 0006 dropped the NOT NULL constraint on Postgres via
`ALTER COLUMN ... DROP NOT NULL`, but that statement doesn't exist on
SQLite. The SQLite branch of 0006 only added the `hsatSourceId` column
and never actually relaxed `pdfSourceId`, so the real table still
rejected HSAT chunks (which have `pdf_source=None`) with an
IntegrityError even though the Django model/state already treats the
field as nullable.

SQLite has no ALTER COLUMN, so the fix is the standard rebuild:
create a new table with the correct schema, copy the data over, drop
the old table, and rename. This is idempotent — it checks the current
column's nullability first and does nothing if already fixed, and it
is a no-op entirely on non-SQLite backends.
"""

from django.db import migrations


def fix_pdf_source_nullable(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "sqlite":
        return

    with connection.cursor() as cursor:
        cursor.execute('PRAGMA table_info("DocumentChunk");')
        columns = cursor.fetchall()
        # PRAGMA table_info columns: cid, name, type, notnull, dflt_value, pk
        pdf_col = next((c for c in columns if c[1] == "pdfSourceId"), None)
        if pdf_col is None or pdf_col[3] == 0:
            # Column missing or already nullable — nothing to fix.
            return

        has_metadata = any(c[1] == "metadata" for c in columns)
        has_hsat = any(c[1] == "hsatSourceId" for c in columns)

        cursor.execute("PRAGMA foreign_keys=OFF;")
        cursor.execute("""
            CREATE TABLE "DocumentChunk_new" (
                "id"           VARCHAR(255) NOT NULL PRIMARY KEY,
                "content"      TEXT         NOT NULL,
                "page"         INTEGER,
                "chunkIndex"   INTEGER      NOT NULL,
                "embedding"    text,
                "pdfSourceId"  VARCHAR(255) REFERENCES "pdf_source"("id") ON DELETE CASCADE,
                "metadata"     TEXT         NOT NULL DEFAULT '{}',
                "hsatSourceId" VARCHAR(255) REFERENCES "hsat_source"("id") ON DELETE CASCADE
            );
        """)

        select_cols = ['"id"', '"content"', '"page"', '"chunkIndex"', '"embedding"', '"pdfSourceId"']
        insert_cols = ['"id"', '"content"', '"page"', '"chunkIndex"', '"embedding"', '"pdfSourceId"']

        if has_metadata:
            select_cols.append('"metadata"')
            insert_cols.append('"metadata"')
        if has_hsat:
            select_cols.append('"hsatSourceId"')
            insert_cols.append('"hsatSourceId"')

        cursor.execute(f"""
            INSERT INTO "DocumentChunk_new" ({", ".join(insert_cols)})
            SELECT {", ".join(select_cols)} FROM "DocumentChunk";
        """)

        cursor.execute('DROP TABLE "DocumentChunk";')
        cursor.execute('ALTER TABLE "DocumentChunk_new" RENAME TO "DocumentChunk";')

        cursor.execute(
            'CREATE INDEX IF NOT EXISTS "document_chunk_pdf_source_idx" ON "DocumentChunk" ("pdfSourceId");'
        )
        cursor.execute(
            'CREATE INDEX IF NOT EXISTS "document_chunk_hsat_source_idx" ON "DocumentChunk" ("hsatSourceId");'
        )
        cursor.execute("PRAGMA foreign_keys=ON;")


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0006_hsat_models"),
    ]

    operations = [
        migrations.RunPython(
            fix_pdf_source_nullable,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

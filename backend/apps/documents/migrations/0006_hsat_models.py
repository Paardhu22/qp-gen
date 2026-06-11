"""HSAT shared-textbook tables.

Adds:
  - `hsat_source`           — one record per (grade, subject, book).
  - `paper_hsat_source`     — join table linking Paper ↔ HsatSource.
  - `DocumentChunk.hsatSourceId` (nullable FK)
  - Drops NOT NULL on `DocumentChunk.pdfSourceId` (a chunk now belongs to
    either pdf_source or hsat_source).

The database_operations block is idempotent — safe against environments
where Prisma or a previous run already created some of the tables /
columns.
"""

import django.db.models.deletion
import utils.ids
from django.db import migrations, models

def run_hsat_sql(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("""
            -- hsat_source ------------------------------------------------
            CREATE TABLE IF NOT EXISTS "hsat_source" (
                "createdAt"      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
                "updatedAt"      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
                "id"             VARCHAR(255)  NOT NULL,
                "grade"          VARCHAR(8)    NOT NULL,
                "subject"        VARCHAR(64)   NOT NULL,
                "book"           VARCHAR(128)  NOT NULL,
                "status"         VARCHAR(20)   NOT NULL DEFAULT 'pending',
                "chunk_count"    INTEGER       NOT NULL DEFAULT 0,
                "error"          TEXT,
                "chapter_errors" JSONB         NOT NULL DEFAULT '{}'::jsonb,
                "processed_at"   TIMESTAMPTZ,
                PRIMARY KEY ("id")
            );
            CREATE UNIQUE INDEX IF NOT EXISTS "hsat_source_gsb_uniq"
                ON "hsat_source" ("grade", "subject", "book");
            CREATE INDEX IF NOT EXISTS "hsat_gsb_idx"
                ON "hsat_source" ("grade", "subject", "book");
            CREATE INDEX IF NOT EXISTS "hsat_status_idx"
                ON "hsat_source" ("status");

            -- paper_hsat_source -----------------------------------------
            CREATE TABLE IF NOT EXISTS "paper_hsat_source" (
                "createdAt"     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                "updatedAt"     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                "id"            VARCHAR(255) NOT NULL,
                "paperId"       VARCHAR(32)  NOT NULL
                                    REFERENCES "Paper"("id") ON DELETE CASCADE,
                "hsatSourceId"  VARCHAR(255) NOT NULL
                                    REFERENCES "hsat_source"("id") ON DELETE CASCADE,
                PRIMARY KEY ("id")
            );
            CREATE UNIQUE INDEX IF NOT EXISTS "paper_hsat_source_uniq"
                ON "paper_hsat_source" ("paperId", "hsatSourceId");
            CREATE INDEX IF NOT EXISTS "phs_paper_idx"
                ON "paper_hsat_source" ("paperId");

            -- DocumentChunk: allow NULL pdfSourceId + add hsatSourceId ---
            ALTER TABLE "DocumentChunk"
                ALTER COLUMN "pdfSourceId" DROP NOT NULL;
            ALTER TABLE "DocumentChunk"
                ADD COLUMN IF NOT EXISTS "hsatSourceId" VARCHAR(255);
            """)

            cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'documentchunk_hsatsourceid_fk'
                ) THEN
                    ALTER TABLE "DocumentChunk"
                        ADD CONSTRAINT documentchunk_hsatsourceid_fk
                        FOREIGN KEY ("hsatSourceId")
                        REFERENCES "hsat_source"("id") ON DELETE CASCADE;
                END IF;
            END$$;
            """)

            cursor.execute("""
            CREATE INDEX IF NOT EXISTS "document_chunk_hsat_source_idx"
                ON "DocumentChunk" ("hsatSourceId");
            """)
    else:
        # SQLite
        with connection.cursor() as cursor:
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS "hsat_source" (
                "createdAt"      datetime   NOT NULL DEFAULT CURRENT_TIMESTAMP,
                "updatedAt"      datetime   NOT NULL DEFAULT CURRENT_TIMESTAMP,
                "id"             VARCHAR(255)  NOT NULL,
                "grade"          VARCHAR(8)    NOT NULL,
                "subject"        VARCHAR(64)   NOT NULL,
                "book"           VARCHAR(128)  NOT NULL,
                "status"         VARCHAR(20)   NOT NULL DEFAULT 'pending',
                "chunk_count"    INTEGER       NOT NULL DEFAULT 0,
                "error"          TEXT,
                "chapter_errors" TEXT          NOT NULL DEFAULT '{}',
                "processed_at"   datetime,
                PRIMARY KEY ("id")
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS "paper_hsat_source" (
                "createdAt"     datetime  NOT NULL DEFAULT CURRENT_TIMESTAMP,
                "updatedAt"     datetime  NOT NULL DEFAULT CURRENT_TIMESTAMP,
                "id"            VARCHAR(255) NOT NULL,
                "paperId"       VARCHAR(32)  NOT NULL REFERENCES "Paper"("id") ON DELETE CASCADE,
                "hsatSourceId"  VARCHAR(255) NOT NULL REFERENCES "hsat_source"("id") ON DELETE CASCADE,
                PRIMARY KEY ("id")
            );
            """)
            
            # Introspect to see if we need to add the column hsatSourceId
            introspection = connection.introspection
            columns = {col.name for col in introspection.get_table_description(cursor, "DocumentChunk")}
            if "hsatSourceId" not in columns:
                cursor.execute('ALTER TABLE "DocumentChunk" ADD COLUMN "hsatSourceId" VARCHAR(255);')


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0005_pdfsource_sha256_av_status"),
        ("projects", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            # ── Django ORM state ──────────────────────────────────────────────
            state_operations=[
                migrations.CreateModel(
                    name="HsatSource",
                    fields=[
                        (
                            "created_at",
                            models.DateTimeField(
                                auto_now_add=True, db_column="createdAt"
                            ),
                        ),
                        (
                            "updated_at",
                            models.DateTimeField(auto_now=True, db_column="updatedAt"),
                        ),
                        (
                            "id",
                            models.CharField(
                                default=utils.ids.generate_id,
                                editable=False,
                                max_length=255,
                                primary_key=True,
                                serialize=False,
                            ),
                        ),
                        ("grade", models.CharField(max_length=8)),
                        ("subject", models.CharField(max_length=64)),
                        ("book", models.CharField(max_length=128)),
                        ("status", models.CharField(default="pending", max_length=20)),
                        ("chunk_count", models.IntegerField(default=0)),
                        ("error", models.TextField(blank=True, null=True)),
                        ("chapter_errors", models.JSONField(blank=True, default=dict)),
                        ("processed_at", models.DateTimeField(blank=True, null=True)),
                    ],
                    options={
                        "db_table": "hsat_source",
                        "unique_together": {("grade", "subject", "book")},
                        "indexes": [
                            models.Index(
                                fields=["grade", "subject", "book"],
                                name="hsat_gsb_idx",
                            ),
                            models.Index(
                                fields=["status"], name="hsat_status_idx"
                            ),
                        ],
                    },
                ),
                migrations.CreateModel(
                    name="PaperHsatSource",
                    fields=[
                        (
                            "created_at",
                            models.DateTimeField(
                                auto_now_add=True, db_column="createdAt"
                            ),
                        ),
                        (
                            "updated_at",
                            models.DateTimeField(auto_now=True, db_column="updatedAt"),
                        ),
                        (
                            "id",
                            models.CharField(
                                default=utils.ids.generate_id,
                                editable=False,
                                max_length=255,
                                primary_key=True,
                                serialize=False,
                            ),
                        ),
                        (
                            "paper",
                            models.ForeignKey(
                                db_column="paperId",
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="hsat_sources",
                                to="projects.paper",
                            ),
                        ),
                        (
                            "hsat_source",
                            models.ForeignKey(
                                db_column="hsatSourceId",
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="paper_links",
                                to="documents.hsatsource",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "paper_hsat_source",
                        "unique_together": {("paper", "hsat_source")},
                        "indexes": [
                            models.Index(fields=["paper"], name="phs_paper_idx"),
                        ],
                    },
                ),
                migrations.AlterField(
                    model_name="documentchunk",
                    name="pdf_source",
                    field=models.ForeignKey(
                        blank=True,
                        db_column="pdfSourceId",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chunks",
                        to="documents.pdfsource",
                    ),
                ),
                migrations.AddField(
                    model_name="documentchunk",
                    name="hsat_source",
                    field=models.ForeignKey(
                        blank=True,
                        db_column="hsatSourceId",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chunks",
                        to="documents.hsatsource",
                    ),
                ),
                migrations.AddIndex(
                    model_name="documentchunk",
                    index=models.Index(
                        fields=["hsat_source"], name="document_chunk_hsat_source_idx"
                    ),
                ),
            ],
            # ── Actual SQL — idempotent ───────────────────────────────────────
            database_operations=[
                migrations.RunPython(
                    run_hsat_sql,
                    reverse_code=migrations.RunPython.noop,
                )
            ],
        ),
    ]

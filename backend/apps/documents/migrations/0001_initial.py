# This migration replaces the old Document-based schema with the PdfSource system.
#
# IMPORTANT — for databases already initialised by Prisma:
#   The "pdf_source" and "DocumentChunk" tables were already created by Prisma
#   with the correct column names (pdfSourceId, etc.).  The RunSQL block below
#   uses IF NOT EXISTS / DROP IF EXISTS so it is fully idempotent.
#
#   If Django's migration tracker already recorded the OLD 0001_initial as applied,
#   reset it before migrating:
#
#       python manage.py migrate documents zero --fake
#       python manage.py migrate documents

import django.db.models.deletion
import pgvector.django
import utils.ids
from django.db import migrations, models


def run_initial_sql(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("""
            -- Remove the old legacy Document table if it was ever created
            -- by a previous Django migration. CASCADE also drops any FK
            -- constraints pointing at it (e.g. old DocumentChunk rows).
            DROP TABLE IF EXISTS "Document" CASCADE;

            -- Create pdf_source if Prisma hasn't already done so.
            CREATE TABLE IF NOT EXISTS "pdf_source" (
                "createdAt"  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                "updatedAt"  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                "id"         VARCHAR(255) NOT NULL,
                "name"       VARCHAR(255) NOT NULL,
                "size"       INTEGER      NOT NULL,
                "url"        VARCHAR(2048) NOT NULL DEFAULT '',
                "status"     VARCHAR(50)  NOT NULL DEFAULT 'uploading',
                "error"      TEXT,
                "userId"     VARCHAR(255) NOT NULL
                                 REFERENCES "user"("id") ON DELETE CASCADE,
                PRIMARY KEY ("id")
            );

            -- Create DocumentChunk with the pdfSourceId FK if Prisma
            -- hasn't already done so.
            CREATE TABLE IF NOT EXISTS "DocumentChunk" (
                "id"          VARCHAR(255) NOT NULL,
                "content"     TEXT         NOT NULL,
                "page"        INTEGER,
                "chunkIndex"  INTEGER      NOT NULL,
                "embedding"   vector(1536),
                "pdfSourceId" VARCHAR(255) NOT NULL
                                  REFERENCES "pdf_source"("id") ON DELETE CASCADE,
                PRIMARY KEY ("id")
            );

            CREATE INDEX IF NOT EXISTS "document_chunk_pdf_source_idx"
                ON "DocumentChunk" ("pdfSourceId");
            """)
    else:
        # SQLite
        with connection.cursor() as cursor:
            cursor.execute('DROP TABLE IF EXISTS "Document";')
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS "pdf_source" (
                "createdAt"  datetime  NOT NULL DEFAULT CURRENT_TIMESTAMP,
                "updatedAt"  datetime  NOT NULL DEFAULT CURRENT_TIMESTAMP,
                "id"         VARCHAR(255) NOT NULL,
                "name"       VARCHAR(255) NOT NULL,
                "size"       INTEGER      NOT NULL,
                "url"        VARCHAR(2048) NOT NULL DEFAULT '',
                "status"     VARCHAR(50)  NOT NULL DEFAULT 'uploading',
                "error"      TEXT,
                "userId"     VARCHAR(255) NOT NULL REFERENCES "user"("id") ON DELETE CASCADE,
                PRIMARY KEY ("id")
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS "DocumentChunk" (
                "id"          VARCHAR(255) NOT NULL,
                "content"     TEXT         NOT NULL,
                "page"        INTEGER,
                "chunkIndex"  INTEGER      NOT NULL,
                "embedding"   text,
                "pdfSourceId" VARCHAR(255) NOT NULL REFERENCES "pdf_source"("id") ON DELETE CASCADE,
                PRIMARY KEY ("id")
            );
            """)
            cursor.execute('CREATE INDEX IF NOT EXISTS "document_chunk_pdf_source_idx" ON "DocumentChunk" ("pdfSourceId");')


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        # SeparateDatabaseAndState lets us define the correct Django model state
        # while running idempotent SQL that works whether Prisma already created
        # these tables or not.
        migrations.SeparateDatabaseAndState(
            # ── Django ORM state ──────────────────────────────────────────────
            state_operations=[
                migrations.CreateModel(
                    name="PdfSource",
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
                        ("name", models.CharField(max_length=255)),
                        ("size", models.IntegerField()),
                        (
                            "url",
                            models.CharField(blank=True, default="", max_length=2048),
                        ),
                        (
                            "status",
                            models.CharField(default="uploading", max_length=50),
                        ),
                        ("error", models.TextField(blank=True, null=True)),
                        (
                            "user",
                            models.ForeignKey(
                                db_column="userId",
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="pdf_sources",
                                to="accounts.user",
                            ),
                        ),
                    ],
                    options={"db_table": "pdf_source"},
                ),
                migrations.CreateModel(
                    name="DocumentChunk",
                    fields=[
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
                        ("content", models.TextField()),
                        ("page", models.IntegerField(blank=True, null=True)),
                        (
                            "chunk_index",
                            models.IntegerField(db_column="chunkIndex"),
                        ),
                        (
                            "embedding",
                            pgvector.django.VectorField(
                                blank=True, dimensions=1536, null=True
                            ),
                        ),
                        (
                            "pdf_source",
                            models.ForeignKey(
                                db_column="pdfSourceId",
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="chunks",
                                to="documents.pdfsource",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "DocumentChunk",
                        "indexes": [
                            models.Index(
                                fields=["pdf_source"],
                                name="document_chunk_pdf_source_idx",
                            )
                        ],
                    },
                ),
            ],
            # ── Actual SQL (idempotent) ───────────────────────────────────────
            database_operations=[
                migrations.RunPython(
                    run_initial_sql,
                    reverse_code=migrations.RunPython.noop,
                )
            ],
        )
    ]

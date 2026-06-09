"""End-to-end S3 sanity check for the HSAT shared-content bucket.

Run any time the bucket, credentials, or IAM policy change. Prints
PASS / FAIL per check, exits non-zero if anything failed so it can be
wired into deploy gates.

    python manage.py verify_s3

Checks (in order):
  1. Credentials and bucket name are present in settings.
  2. boto3 client can be built.
  3. head_bucket succeeds (bucket exists + reachable + region OK).
  4. ListBucket works (the IAM key has s3:ListBucket).
  5. GetObject works on the first catalog key (the IAM key has
     s3:GetObject) — downloaded into a BytesIO buffer, never touching
     disk.
"""

from __future__ import annotations

import sys
from io import BytesIO

from botocore.exceptions import ClientError, NoCredentialsError
from django.core.management.base import BaseCommand

from services import hsat_catalog
from services.s3_client import S3NotConfigured, get_bucket, get_client, is_configured


class Command(BaseCommand):
    help = "Verify HSAT S3 bucket access end-to-end."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--probe-key",
            help="Override the S3 key used for the GetObject check.",
            default=None,
        )

    def handle(self, *args, **options):  # noqa: D401
        failed = 0

        def report(name: str, ok: bool, detail: str = "") -> None:
            nonlocal failed
            tag = self.style.SUCCESS("PASS") if ok else self.style.ERROR("FAIL")
            self.stdout.write(f"  [{tag}] {name}" + (f" — {detail}" if detail else ""))
            if not ok:
                failed += 1

        self.stdout.write(self.style.MIGRATE_HEADING("S3 verification\n"))

        # 1. Configuration
        if not is_configured():
            report(
                "settings configured",
                False,
                "AWS_STORAGE_BUCKET_NAME / AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY missing",
            )
            self.stdout.write(self.style.ERROR("\nverify_s3: 1 failed"))
            sys.exit(1)
        report("settings configured", True, f"bucket={get_bucket()}")

        # 2. Client
        try:
            client = get_client()
            report("boto3 client built", True)
        except (S3NotConfigured, NoCredentialsError, Exception) as exc:
            report("boto3 client built", False, str(exc))
            self.stdout.write(self.style.ERROR("\nverify_s3: 1 failed"))
            sys.exit(1)

        bucket = get_bucket()

        # 3. head_bucket — region / existence / network
        try:
            client.head_bucket(Bucket=bucket)
            report("head_bucket", True)
        except ClientError as exc:
            code = (exc.response.get("Error") or {}).get("Code", "")
            report("head_bucket", False, f"{code}: {exc}")
        except Exception as exc:  # noqa: BLE001
            report("head_bucket", False, str(exc))

        # 4. ListBucket
        try:
            response = client.list_objects_v2(Bucket=bucket, MaxKeys=1)
            sample = (response.get("Contents") or [{}])[0].get("Key", "")
            report("s3:ListBucket", True, f"first key: {sample!r}")
        except ClientError as exc:
            code = (exc.response.get("Error") or {}).get("Code", "")
            report(
                "s3:ListBucket",
                False,
                f"{code}: IAM key likely missing s3:ListBucket — {exc}",
            )
        except Exception as exc:  # noqa: BLE001
            report("s3:ListBucket", False, str(exc))

        # 5. GetObject — explicitly check the catalog's first key so we
        # exercise the same path ingestion will use.
        probe_key = options.get("probe_key")
        if not probe_key:
            for _g, _s, _b, keys in hsat_catalog.iter_books():
                if keys:
                    probe_key = keys[0]
                    break
        if not probe_key:
            report("s3:GetObject", False, "no catalog keys available to probe")
        else:
            try:
                buf = BytesIO()
                client.download_fileobj(bucket, probe_key, buf)
                size = buf.tell()
                if size <= 0:
                    report("s3:GetObject", False, f"empty download for {probe_key!r}")
                else:
                    report(
                        "s3:GetObject",
                        True,
                        f"{probe_key!r} ({size} bytes)",
                    )
            except ClientError as exc:
                code = (exc.response.get("Error") or {}).get("Code", "")
                hint = (
                    " — IAM key likely missing s3:GetObject"
                    if code in {"AccessDenied", "403"}
                    else ""
                )
                report("s3:GetObject", False, f"{code}: {exc}{hint}")
            except Exception as exc:  # noqa: BLE001
                report("s3:GetObject", False, str(exc))

        if failed:
            self.stdout.write(self.style.ERROR(f"\nverify_s3: {failed} failed"))
            sys.exit(1)
        self.stdout.write(self.style.SUCCESS("\nverify_s3: all checks passed"))

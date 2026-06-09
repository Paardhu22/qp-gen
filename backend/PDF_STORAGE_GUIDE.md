# PDF Storage & Upload System Documentation

## Overview

The Q-Gen backend now supports secure PDF storage with multiple backends:
- **Local filesystem** (default for development)
- **Amazon S3** (production)
- **MinIO** (local S3-compatible alternative for development)

The system includes:
- **SHA256 deduplication** — avoid reprocessing identical PDFs
- **AV scanning** — optional ClamAV integration for malware detection
- **Presigned uploads** — direct browser-to-S3 uploads without server proxying
- **Storage abstraction** — seamless backend switching via Django configuration

---

## Architecture

### Upload Flow (Presigned)

```
Browser
  ↓ 1. Request presigned POST URL
Server
  ↓ 2. Return S3 credentials + URL
Browser
  ↓ 3. Upload file directly to S3
S3 / MinIO
  ↓ 4. Notify server with storage key
Server
  ↓ 5. Download from storage, process, save metadata
Database
```

### Upload Flow (Legacy)

```
Browser
  ↓ POST /api/documents/upload
Server (multipart upload)
  ↓ Save to storage + process
Database
```

---

## Configuration

### Environment Variables (`.env`)

#### S3 / MinIO Storage (Optional)
```bash
# Leave empty to use local MEDIA_ROOT (default)
AWS_STORAGE_BUCKET_NAME=my-bucket
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_S3_REGION_NAME=us-east-1
AWS_S3_ENDPOINT_URL=          # For MinIO: http://localhost:9000

# Presigned URL expiry (seconds)
AWS_QUERYSTRING_EXPIRE=3600

# Max upload size in bytes (default: 100 MB)
MAX_UPLOAD_SIZE_BYTES=104857600
```

#### AV Scanning (Optional)
```bash
CLAMAV_ENABLED=false          # Set to true to enable
CLAMAV_HOST=localhost
CLAMAV_PORT=3310
```

---

## Quick Start: Local Development with MinIO

### 1. Start MinIO Container

```bash
docker run -p 9000:9000 \
  -e MINIO_ROOT_USER=minio \
  -e MINIO_ROOT_PASSWORD=minio123 \
  -v %cd%/minio-data:/data \
  --name minio -d \
  minio/minio server /data
```

**Access MinIO Console**: http://localhost:9000 (minio / minio123)

### 2. Configure Backend

Update `backend/.env`:
```bash
AWS_STORAGE_BUCKET_NAME=uploads
AWS_ACCESS_KEY_ID=minio
AWS_SECRET_ACCESS_KEY=minio123
AWS_S3_ENDPOINT_URL=http://localhost:9000
AWS_S3_USE_SSL=false
```

### 3. Create MinIO Bucket

```bash
# Inside MinIO console or via CLI:
aws s3 mb s3://uploads --endpoint-url http://localhost:9000
```

### 4. Start Django Server

```bash
cd backend
.venv\Scripts\activate
py manage.py runserver 0.0.0.0:8000
```

---

## API Endpoints

### 1. **POST /api/documents/presign**
Request presigned URL for direct-to-S3 upload.

**Request:**
```json
{
  "name": "textbook.pdf",
  "content_type": "application/pdf",
  "size": 1024000
}
```

**Response:**
```json
{
  "url": "https://s3.amazonaws.com/uploads",
  "fields": {
    "key": "uploads/user-123/abc123_textbook.pdf",
    "policy": "...",
    "signature": "..."
  },
  "key": "uploads/user-123/abc123_textbook.pdf"
}
```

### 2. **POST /api/documents/confirm**
Notify server to process an uploaded object from storage.

**Request:**
```json
{
  "key": "uploads/user-123/abc123_textbook.pdf",
  "name": "textbook.pdf",
  "content_type": "application/pdf"
}
```

**Response:**
```json
{
  "pdfSourceId": "ps_abc123def456",
  "warnings": [
    "PyMuPDF is not installed..."
  ]
}
```

### 3. **POST /api/documents/upload** (Legacy)
Upload file directly (multipart). Falls back if presign unavailable.

**Request:**
```
POST /api/documents/upload
Content-Type: multipart/form-data

file=<binary>
```

**Response:**
```json
{
  "pdfSourceId": "ps_abc123def456",
  "warnings": []
}
```

---

## Database Schema

### PdfSource Model

```python
class PdfSource(TimeStampedModel):
    id                  # UUID (primary key)
    name                # Filename
    size                # Bytes
    url                 # Public URL to stored PDF (if configured)
    content_type        # MIME type (e.g. application/pdf)
    status              # 'uploading' | 'processing' | 'ready' | 'error'
    error               # Error message if status='error'
    sha256              # SHA256 hash for deduplication
    av_status           # 'pending' | 'passed' | 'failed' | null
    user_id             # Owner
    created_at          # Timestamp
    updated_at          # Timestamp
```

### Deduplication

When a PDF with the same **SHA256 hash** and **user** is uploaded again:
- The existing `PdfSource` is returned immediately (no reprocessing)
- Saves processing time and storage space
- Works across both presigned and legacy upload flows

### AV Scanning

Optional ClamAV integration:
- **Disabled by default** (`CLAMAV_ENABLED=false`)
- When enabled, scans file before processing
- Sets `av_status` to `'passed'` or `'failed'`
- Blocks upload if threat detected

---

## Implementation Details

### SHA256 Deduplication

**File:** `backend/services/document_service.py`

```python
def _compute_sha256(buffer: bytes) -> str:
    """Compute SHA256 hash of file content."""
    h = hashlib.sha256()
    h.update(buffer)
    return h.hexdigest()

# In process_pdf_upload():
sha256_hash = _compute_sha256(buffer)
existing = PdfSource.objects.filter(
    user=user, sha256=sha256_hash, status="ready"
).first()
if existing:
    return existing  # Reuse existing
```

### AV Scanning

```python
def _scan_with_av(buffer: bytes, file_name: str) -> tuple[bool, Optional[str]]:
    """Scan file with ClamAV if enabled."""
    av_enabled = os.environ.get("CLAMAV_ENABLED", "").lower() == "true"
    if not av_enabled:
        return True, None  # Not enabled = pass
    
    # Use pyclamd to connect to ClamAV daemon
    # Returns (is_safe, error_message)
```

### Avoiding Double-Saves

**Function:** `process_pdf_from_storage(key, user, name, content_type)`

When confirming a presigned upload:
1. Read file from storage (already uploaded)
2. Compute SHA256 + check for duplicates
3. Run AV scan
4. Process without re-saving (uses existing key)
5. Set `pdf_source.url` to point to the storage key

This avoids the overhead of downloading from S3 and re-uploading.

---

## Storage Paths

### Local Filesystem (Development)
```
backend/media/
├── pdfs/
│   ├── ps_abc123/
│   │   └── textbook.pdf
│   └── ps_def456/
│       └── notes.pdf
└── pdf_images/
    ├── ps_abc123/
    │   └── page-1-image-0.jpg
    └── ps_def456/
        └── page-3-image-1.png
```

### S3 / MinIO
```
s3://uploads/
├── pdfs/
│   ├── ps_abc123/
│   │   └── textbook.pdf
│   └── ps_def456/
│       └── notes.pdf
├── uploads/
│   └── user-123/
│       └── abc123_textbook.pdf    (presigned upload temp)
└── pdf_images/
    ├── ps_abc123/
    │   └── page-1-image-0.jpg
    └── ps_def456/
        └── page-3-image-1.png
```

---

## Frontend Integration

The frontend `FileUpload` component automatically:

1. **Requests presigned URL** from `/api/documents/presign` (if S3 configured)
2. **Uploads directly to S3** (bypasses backend)
3. **Confirms upload** by calling `/api/documents/confirm`
4. **Falls back to legacy upload** if presign unavailable

**File:** `frontend/components/file-upload.tsx`

---

## Monitoring & Debugging

### Check PdfSource Status
```bash
curl -H "Authorization: Bearer <TOKEN>" \
  http://localhost:8000/api/projects/resources/
```

### View Storage (MinIO)
```bash
# List all objects in uploads bucket
aws s3 ls s3://uploads/ --recursive \
  --endpoint-url http://localhost:9000
```

### Check Database
```bash
py manage.py dbshell

-- Find PDFs by user
SELECT id, name, sha256, status, av_status FROM pdf_source 
WHERE user_id = <user_id>;

-- Check for duplicates
SELECT sha256, COUNT(*) as count FROM pdf_source 
WHERE status = 'ready' 
GROUP BY sha256 
HAVING count > 1;
```

### Logs
- **Upload errors**: `backend/upload_error.log`
- **Django logs**: stdout/stderr when running `runserver`
- **MinIO logs**: available in MinIO console

---

## Production Checklist

- [ ] Configure `AWS_STORAGE_BUCKET_NAME` and S3 credentials
- [ ] Enable server-side encryption (S3 bucket settings)
- [ ] Set lifecycle policies (move old files to IA/Glacier)
- [ ] Enable versioning (bucket protection)
- [ ] Restrict bucket access (private ACLs)
- [ ] Monitor storage costs (S3 Pricing Calculator)
- [ ] Set up CloudTrail logging (audit trail)
- [ ] Test presigned URL expiry (`AWS_QUERYSTRING_EXPIRE`)
- [ ] Validate file size limits (`MAX_UPLOAD_SIZE_BYTES`)
- [ ] Optional: Enable ClamAV for virus scanning
- [ ] Optional: Set up CDN (CloudFront) for faster downloads

---

## Troubleshooting

### Issue: "Object not found in storage" on confirm
**Cause:** Presigned upload failed silently on browser.
**Solution:** Check browser console for errors; verify S3 credentials and bucket policy.

### Issue: Duplicate PDFs still being processed
**Cause:** SHA256 mismatch or different user.
**Solution:** Check `pdf_source.sha256` in database; ensure uploads are by same user.

### Issue: AV scan hanging
**Cause:** ClamAV daemon not running or unreachable.
**Solution:** Verify `CLAMAV_HOST:CLAMAV_PORT` or disable (`CLAMAV_ENABLED=false`).

### Issue: Large file upload timeout
**Cause:** Network or server timeout.
**Solution:** Increase `MAX_UPLOAD_SIZE_BYTES`; use chunked/resumable uploads (future enhancement).

---

## Future Enhancements

- [ ] Chunked / resumable uploads for large files
- [ ] Batch upload support
- [ ] File compression (gzip before storage)
- [ ] Parallel AV scanning (multiple files)
- [ ] Automatic text extraction and indexing
- [ ] OCR for scanned PDFs
- [ ] Metadata extraction (title, author, etc.)
- [ ] Version history (keep old versions)
- [ ] Sharing & access control (user-level permissions)

---

## References

- **Django Storages**: https://django-storages.readthedocs.io/
- **Boto3 (AWS SDK)**: https://boto3.amazonaws.com/v1/documentation/api/latest/
- **MinIO**: https://min.io/docs/
- **ClamAV**: https://www.clamav.net/

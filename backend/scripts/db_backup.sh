#!/bin/bash
# Exit immediately if a command exits with a non-zero status
set -e

# Configuration (These can be overridden by environment variables)
DB_NAME="${DB_NAME:-qpgen_db}"
DB_USER="${DB_USER:-qpgen_user}"
PGPASSWORD="${PGPASSWORD:-your_secure_password}"
BUCKET_NAME="${AWS_STORAGE_BUCKET_NAME:-your-s3-bucket-name}"
AWS_DEFAULT_REGION="${AWS_S3_REGION_NAME:-ap-south-1}"

BACKUP_DIR="/tmp/db_backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_backup_${TIMESTAMP}.sql"
S3_KEY="backups/db/${DB_NAME}_backup_${TIMESTAMP}.sql"

# Export region for AWS CLI
export AWS_DEFAULT_REGION

# Create temp directory
mkdir -p "${BACKUP_DIR}"

echo "Starting database backup for ${DB_NAME}..."

# Execute pg_dump (custom directory format backup)
PGPASSWORD="${PGPASSWORD}" pg_dump -h localhost -U "${DB_USER}" -d "${DB_NAME}" -F c -b -v -f "${BACKUP_FILE}"

echo "Uploading backup to S3: s3://${BUCKET_NAME}/${S3_KEY}..."
# Upload backup to AWS S3 using AWS CLI (utilizes EC2 IAM Instance Profile automatically if credentials are not specified)
aws s3 cp "${BACKUP_FILE}" "s3://${BUCKET_NAME}/${S3_KEY}"

# Clean up local backup file
rm -f "${BACKUP_FILE}"

echo "Database backup successfully uploaded to S3: s3://${BUCKET_NAME}/${S3_KEY}"

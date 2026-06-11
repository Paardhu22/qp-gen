# Backend API Endpoints

This document lists the currently registered backend routes and the endpoints currently used by the frontend.

## Overview

- **Base URL:** `http://3.110.176.28:8000`
- **API prefix:** `/api/`
- **Authentication:** Most application endpoints require a Bearer access token, except public health and authentication bootstrap/reset endpoints.
- **Streaming:** Question generation uses Server-Sent Events (SSE).

## Public Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/health/` | Returns a simple backend health status. |
| `POST` | `/api/auth/register` | Creates a new user account and returns access and refresh tokens. |
| `POST` | `/api/auth/login` | Authenticates a user and returns access and refresh tokens. |
| `POST` | `/api/auth/refresh` | Exchanges a valid refresh token for a new token pair. |
| `POST` | `/api/auth/forgot-password` | Starts the password reset flow with a generic success response. |
| `POST` | `/api/auth/reset-password` | Consumes a reset token and updates the user's password. |

## Authenticated Account Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/auth/logout` | Revokes the current access token session. |
| `GET` | `/api/auth/profile` | Returns the authenticated user's profile. |
| `GET` | `/api/auth/dashboard` | Returns the authenticated user's profile for dashboard use. |
| `POST` | `/api/auth/verify-password` | Verifies the current user's password before sensitive account changes. |
| `POST` | `/api/auth/change-password` | Changes the current user's password after validating the old password. |

## Document Upload Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/documents/upload` | Uploads and processes a PDF through the backend. |
| `POST` | `/api/documents/presign` | Creates a presigned S3 upload request for direct browser-to-storage uploads. |
| `POST` | `/api/documents/confirm` | Confirms a direct storage upload and processes the uploaded PDF. |

## HSAT Source Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/hsat/catalog/` | Returns the HSAT book catalog with ingestion status and optional chapters. |
| `GET` | `/api/hsat/chapters/` | Returns chapter metadata and status for a selected HSAT book. |
| `POST` | `/api/hsat/ingest/` | Triggers ingestion of a selected HSAT book or selected chapters. |
| `POST` | `/api/hsat/apply/` | Applies an HSAT source to a paper and starts ingestion if needed. |
| `DELETE` | `/api/hsat/apply/` | Removes an applied HSAT source from a paper. |
| `GET` | `/api/hsat/papers/{paper_id}/sources/` | Lists HSAT sources currently attached to a paper. |

## Generation Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/generation/questions/stream` | Streams generated questions as SSE events from uploaded PDFs, HSAT sources, and prompt settings. |
| `POST` | `/api/generation/answer-key` | Generates an answer key from paper HTML content. |
| `GET` | `/api/generation/history` | Lists the authenticated user's generation history. |
| `DELETE` | `/api/generation/history` | Clears the authenticated user's generation history. |
| `POST` | `/api/generation/test-science-engine` | Runs an authenticated vertical-slice test of the science generation engine. |
| `POST` | `/api/generation/papers/{paper_id}/generate-answer-script/` | Generates and saves a separate answer-script paper for an existing paper. |

## Project, Question, and Paper Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/projects/` | Lists the authenticated user's projects, optionally including nested questions with `?withQuestions=true`. |
| `POST` | `/api/projects/questions/save` | Saves generated questions into a project. |
| `DELETE` | `/api/projects/questions/clear` | Deletes all questions owned by the authenticated user. |
| `DELETE` | `/api/projects/questions/{question_id}/` | Deletes one saved question owned by the authenticated user. |
| `GET` | `/api/projects/papers/` | Lists saved papers owned by the authenticated user. |
| `POST` | `/api/projects/papers/` | Saves a new paper under a project. |
| `GET` | `/api/projects/papers/{paper_id}/` | Returns the full details of one saved paper. |
| `PUT` | `/api/projects/papers/{paper_id}/` | Updates an existing saved paper. |
| `DELETE` | `/api/projects/papers/{paper_id}/` | Deletes one saved paper. |
| `DELETE` | `/api/projects/papers/clear` | Deletes all papers owned by the authenticated user. |

## Utility and Non-API Routes

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/debug/science-engine-health` | Runs a public debug health check for the science generation engine. |
| `GET` | `/media/{path}` | Resolves stable media paths by redirecting to signed storage URLs or serving local media. |
| `ANY` | `/admin/` | Exposes the Django admin site. |

## Frontend-Confirmed Usage

The frontend currently calls the account, document upload, HSAT catalog/chapters/ingest/apply, question generation stream, project, paper, question deletion, answer-script generation, and password-management endpoints listed above.

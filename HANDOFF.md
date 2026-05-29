# AOS (Academic Orchestration System) - Developer Handoff Guide

> **Last Updated**: May 2026
> 
> This document serves as the complete architectural guide for onboarding the next developer. It covers system design, critical workflows, infrastructure decisions, and known limitations.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Tech Stack & Tooling](#tech-stack--tooling)
3. [High-Level Architecture](#high-level-architecture)
4. [Directory Structure](#directory-structure)
5. [Core Logic & Critical Workflows](#core-logic--critical-workflows)
6. [Database Schema](#database-schema)
7. [Environment Setup & Configuration](#environment-setup--configuration)
8. [Known Issues & Technical Debt](#known-issues--technical-debt)

---

## Project Overview

### What Is AOS?

The **Academic Orchestration System (AOS) Question Paper Generator** is an enterprise-grade AI examination builder designed to automate the creation of high-stakes academic assessments. It is specifically engineered to comply with **CBSE (Central Board of Secondary Education), India** guidelines while eliminating hallucinations, structural deviations, and factual errors in AI-generated question papers.

### Primary Purpose

- **Generate CBSE-compliant question papers** automatically for Classes 1-10
- **Extract answer keys** from papers with precise formatting
- **Organize questions** by subject, difficulty, and Bloom's taxonomy levels
- **Retrieve contextual content** from educator-uploaded textbooks using RAG (Retrieval-Augmented Generation)
- **Stream real-time generation** via Server-Sent Events (SSE) for live visualization

### Target Users

- **Educators & Teachers**: Create formatted examination papers without manual work
- **Educational Institutions**: Standardize assessment generation across departments
- **Board Compliance**: Ensure questions follow CBSE structural guidelines

### Core Philosophy: The Decoupled Architecture

AOS enforces **strict separation** between:

- **Pedagogical Blueprint** (`q_instructions`): The structure, layout, stream counts, Bloom's targets, and CBSE rules
- **Content Retrieval** (RAG): Raw factual context extracted exclusively from educator's uploaded textbooks

This decoupling ensures **mathematically exact board replication** while drawing 100% curriculum truth from source documents, avoiding AI hallucination.

---

## Tech Stack & Tooling

### Frontend

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Framework** | Next.js 14+ (App Router) | React-based full-stack framework with SSR |
| **Language** | TypeScript | Type-safe React component development |
| **State Management** | Zustand (`editor-store.ts`) | Lightweight client-side state for editor |
| **Rich Text Editor** | TipTap (v3.23.4) | WYSIWYG editor with markdown/HTML support |
| **Form Handling** | React Hook Form + Zod | Type-safe form validation |
| **UI Components** | Custom + Radix UI | Accessible component library |
| **HTTP Client** | Native Fetch API + custom wrapper | API communication with backend |
| **Authentication** | Better Auth (v1.6.11) | OAuth 2.0 + email/password auth |
| **Database (Frontend)** | Prisma ORM + PostgreSQL | User, session, paper, question models |
| **Styling** | Tailwind CSS (v3) | Utility-first CSS framework |
| **Request Querying** | TanStack React Query | Data fetching & caching |

### Backend

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Framework** | Django 5.0.6 + DRF (v3.15.2) | REST API framework |
| **Language** | Python 3.11+ | Backend logic & services |
| **Database** | PostgreSQL 14+ with pgvector | Primary data store + vector embeddings |
| **ORM** | Django ORM | Relational data mapping |
| **Vector DB** | pgvector (v0.2.5) | Embedding storage & semantic search |
| **LLM Integration** | OpenAI API (v2.36.0+) | GPT-4/GPT-3.5 for generation & embeddings |
| **PDF Processing** | PyPDF (v4.2.0) + PyMuPDF (v1.24.0) | Text & image extraction from PDFs |
| **Document Generation** | python-docx (v1.1.2) | DOCX file export |
| **Auth** | Django Sessions + JWT | Session-based & token auth |
| **CORS** | django-cors-headers | Cross-origin request handling |
| **Environment** | python-dotenv (v1.0.1) | Environment variable management |

### Deployment & Infrastructure

- **Database Hosting**: Neon PostgreSQL (cloud-hosted with pgvector support)
- **Static Files**: Django media storage (local development) or cloud storage
- **API Streaming**: Server-Sent Events (SSE) for real-time generation updates
- **Authentication Flow**: Session cookies + JWT tokens

---

## High-Level Architecture

### System Overview Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                       Next.js Frontend (Port 3000)               │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ generator-form.tsx  │ TipTap Editor │ Sidebar │ Top Navbar │ │
│  └────────────────────────────┬────────────────────────────────┘ │
└─────────────────────────────────┼─────────────────────────────────┘
                                  │ HTTP/SSE
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│              Django REST API (Port 8000)                          │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ Authentication │ Document Upload │ Generation │ Projects   │ │
│  │   (accounts/)  │  (documents/)    │  (generation/)           │ │
│  └────────────────────────────┬────────────────────────────────┘ │
│                               │                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Services Layer                                           │   │
│  │ ┌────────────────┬──────────────┬────────────────────┐  │   │
│  │ │ generation_    │ retrieval_   │ document_service   │  │   │
│  │ │ service.py     │ service.py   │ embedding_service  │  │   │
│  │ │ generation_    │ openai_      │ chunking_service   │  │   │
│  │ │ router.py      │ service.py   │ pdf_service        │  │   │
│  │ └────────────────┴──────────────┴────────────────────┘  │   │
│  └──────────────────────────┬───────────────────────────────┘   │
└─────────────────────────────┼─────────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
    ┌─────────────┐  ┌──────────────────┐  ┌─────────────────┐
    │  PostgreSQL │  │  q_instructions/ │  │  OpenAI API     │
    │  (Neon)     │  │  (Blueprint      │  │  (Generation &  │
    │  + pgvector │  │   Orchestration) │  │  Embeddings)    │
    └─────────────┘  └──────────────────┘  └─────────────────┘
```

### Data Flow: Question Generation Pipeline

```
1. Educator submits form with:
   - Subject, class, difficulty
   - PDF documents (sources)
   - Custom instructions or count (-1 for CBSE defaults)

2. Frontend (generator-form.tsx):
   - Uploads PDFs to /api/documents/upload
   - POSTs generation request to /api/generation/questions/stream

3. Backend (generation/views.py):
   - Validates authentication
   - Passes request to generation_service.stream_generated_questions()

4. generation_router.py:
   - Normalizes & validates input (CBSE + Class 1-10 + Subject)
   - Routes to appropriate engine (new or legacy)
   - For Science/Social Science (Class 1-10): Uses q_instructions blueprint system

5. Blueprint Resolution (q_instructions/):
   - Loads subject-specific orchestrator
   - Resolves stream allocation (e.g., 25% MCQ, 25% Short Answer, etc.)
   - Compiles pedagogical blueprint prompt

6. Retrieval (retrieval_service.py):
   - Embeds educator queries using OpenAI embeddings API
   - Performs vector similarity search on PDF chunks
   - Returns most relevant contextual passages

7. LLM Invocation (generation_service.py):
   - Assembles unified prompt:
     * System rules + pedagogical blueprint
     * Retrieval context from PDFs
     * LLM streaming instructions
   - Streams JSON objects via OpenAI streaming API
   - Each JSON object = 1 question

8. JSON Extraction & Validation:
   - JsonObjectStreamExtractor detects complete JSON objects
   - Validates question structure
   - Streams via SSE to frontend

9. Frontend Real-Time Rendering:
   - Receives SSE events
   - Inserts questions into TipTap editor
   - Updates live preview

10. Answer Key Generation:
    - User requests answer key via /api/generation/answer-key
    - Service calls OpenAI to extract & format answers from paper HTML
```

### Authentication Flow

```
User Registration/Login → Better Auth (frontend/lib/auth.ts)
         ↓
Create Prisma User record + Session
         ↓
Frontend stores token in localStorage (token-storage.ts)
         ↓
Every API request includes Authorization header or session cookie
         ↓
Backend validates via IsAuthenticated permission class
         ↓
request.user populated from session/token
```

---

## Directory Structure

### Backend (`backend/`)

```
backend/
├── config/                     # Django core settings & URLs
│   ├── settings.py             # Database, middleware, installed apps
│   ├── urls.py                 # Root URL dispatcher
│   ├── wsgi.py / asgi.py       # WSGI/ASGI entry points
│   └── debug_views.py          # Health check endpoints
│
├── apps/                       # Django applications (by domain)
│   ├── accounts/               # User authentication & management
│   │   ├── models.py           # User, Session, Account, Verification
│   │   ├── serializers.py      # User serialization
│   │   ├── views.py            # Login, register, profile endpoints
│   │   ├── permissions.py      # Custom permission classes
│   │   └── urls.py
│   │
│   ├── documents/              # PDF upload & chunking
│   │   ├── models.py           # PdfSource, DocumentChunk (with embeddings)
│   │   ├── serializers.py      # Upload response DTOs
│   │   ├── views.py            # Upload endpoint
│   │   └── urls.py
│   │
│   ├── generation/             # Question & answer generation
│   │   ├── models.py           # GenerationHistory, ApiUsage tracking
│   │   ├── serializers.py      # Req/resp for generation API
│   │   ├── views.py            # QuestionGenerationStreamView, AnswerKeyView
│   │   ├── urls.py
│   │   └── permissions.py
│   │
│   ├── projects/               # Paper management & saving
│   │   ├── models.py           # Project, Paper metadata
│   │   └── views.py            # Save/load project endpoints
│   │
│   ├── question_generation/    # New AI engine (Science)
│   │   ├── domain/              # Core domain models
│   │   │   ├── context.py       # GenerationContext, TokenBudget
│   │   │   ├── enums.py         # AcademicClass, EducationBoard
│   │   │   └── exceptions.py
│   │   │
│   │   ├── infrastructure/      # Technical concerns
│   │   │   ├── providers/
│   │   │   │   └── openai_provider.py  # LLM wrapper
│   │   │   ├── observability/
│   │   │   │   └── metrics.py    # Instrumentation
│   │   │   └── token_budget/
│   │   │       └── budgeter.py   # Token allocation algorithm
│   │   │
│   │   ├── services/            # Business logic
│   │   │   └── prompting/
│   │   │       ├── assembler.py  # Prompt construction
│   │   │       └── request_factory.py  # LLM request building
│   │   │
│   │   └── tests/               # Test suite
│   │
│   └── common/                 # Shared utilities
│       ├── models.py           # TimeStampedModel base class
│       └── urls.py
│
├── services/                   # Core service layer
│   ├── generation_service.py    # Main generation orchestrator
│   ├── generation_router.py     # Request routing logic (NEW vs LEGACY engine)
│   ├── retrieval_service.py     # Vector search over PDF chunks
│   ├── embedding_service.py     # OpenAI embedding generation
│   ├── document_service.py      # PDF processing & chunking
│   ├── pdf_service.py           # PyMuPDF text/image extraction
│   ├── openai_service.py        # OpenAI client wrapper & token tracking
│   ├── chunking_service.py      # Text chunking with overlap
│   ├── answer_script_service.py # Answer key generation per question
│   ├── auth_service.py          # User auth helpers
│   ├── export_service.py        # DOCX/PDF export
│   └── semantic_pipeline.py     # Image captioning & semantic chunking
│
├── q_instructions/             # BLUEPRINT SYSTEM (Pedagogical Rules Engine)
│   ├── core/                    # Domain-agnostic interfaces
│   │   ├── interfaces.py        # ISubjectPlugin, IOrchestrator
│   │   ├── enums.py             # AcademicClass, EducationBoard, QuestionType
│   │   ├── datatypes.py         # CompiledPaperBlueprint, QuestionSlot
│   │   └── exceptions.py
│   │
│   ├── subjects/                # Subject-specific plugins
│   │   ├── registry.py          # SubjectRegistry (loader)
│   │   ├── science/             # Science plugin (Class 1-10)
│   │   │   ├── blueprint.py      # Stream structure (MCQ, Short, Long)
│   │   │   ├── orchestrator.py   # Bloom's allocation algorithm
│   │   │   ├── curriculum.py     # Curriculum mappings
│   │   │   ├── streams.py        # Question type definitions
│   │   │   ├── science.py        # Main Science plugin class
│   │   │   └── blooms_engine.py  # Bloom's level targeting
│   │   │
│   │   └── social_science/      # Social Science plugin
│   │       └── [similar structure to science/]
│   │
│   ├── master/                  # Integration layer
│   │   ├── facade.py            # AcademicGenerationFacade (stable boundary)
│   │   ├── orchestrator.py      # MasterAcademicOrchestrator
│   │   └── validators.py        # Blueprint validation
│   │
│   ├── orchestration/           # Orchestration utilities
│   ├── generation/              # Generation rules engine
│   ├── retrieval/               # Retrieval-specific rules
│   ├── analytics/               # Paper diagnostics
│   └── tests/                   # q_instructions test suite
│
├── utils/                       # Utility functions
│   └── ids.py                  # ID generation (ULID-based)
│
├── requirements.txt             # Python dependencies
├── manage.py                   # Django CLI
└── db.sqlite3                  # SQLite (local dev only)
```

### Frontend (`frontend/`)

```
frontend/
├── app/                        # Next.js App Router
│   ├── layout.tsx              # Root layout with providers
│   ├── page.tsx                # Landing page
│   ├── globals.css             # Global Tailwind styles
│   │
│   ├── (auth)/                 # Grouped auth routes
│   │   ├── login/
│   │   │   └── page.tsx        # Login form
│   │   └── register/
│   │       └── page.tsx        # Registration form
│   │
│   ├── (dashboard)/            # Protected dashboard routes
│   │   ├── layout.tsx          # Dashboard layout with sidebar
│   │   ├── page.tsx            # Main dashboard
│   │   └── editor/             # Paper editor
│   │       └── page.tsx
│   │
│   └── api/                    # API route handlers
│       ├── auth/               # Auth endpoints (provided by Better Auth)
│       └── upload/             # File upload handler
│
├── components/                 # React components
│   ├── generator-form.tsx      # Question generation form (CRITICAL)
│   ├── tiptap-editor.tsx       # Rich text editor component
│   ├── file-upload.tsx         # Drag-drop PDF upload
│   ├── top-navbar.tsx          # Navigation bar
│   ├── sidebar.tsx             # Sidebar navigation
│   ├── login-form.tsx          # Login UI
│   ├── register-form.tsx       # Registration UI
│   ├── protected-layout.tsx    # Auth guard wrapper
│   ├── GooeyNav.tsx            # Animated navigation
│   ├── Grainient.tsx           # Animated background
│   │
│   ├── editor/                 # TipTap editor extensions
│   │   └── [custom extensions]
│   │
│   └── ui/                     # Radix UI + shadcn/ui components
│       ├── form.tsx
│       ├── input.tsx
│       ├── select.tsx
│       ├── button.tsx
│       ├── textarea.tsx
│       └── [other base UI]
│
├── lib/                        # Utility functions
│   ├── auth.ts                 # Better Auth setup (CRITICAL)
│   ├── api-client.ts           # Fetch wrapper + streaming
│   ├── auth-client.ts          # Client-side auth helpers
│   ├── db.ts                   # Prisma client instance
│   ├── token-storage.ts        # localStorage token management
│   ├── utils.ts                # Helper functions
│   ├── openai.ts               # OpenAI client (if used frontend-side)
│   ├── retrieval.ts            # Retrieval logic (if any frontend RAG)
│   ├── export-docx.ts          # DOCX export functions
│   ├── export-pdf.ts           # PDF export functions
│   └── embeddings.ts           # If frontend computes embeddings
│
├── actions/                    # Next.js Server Actions
│   ├── generate.ts             # Generate questions (server-side)
│   ├── generateAnswers.ts      # Generate answer keys
│   ├── generateQuestions.ts    # Dedicated question generation
│   ├── savePaper.ts            # Persist paper to DB
│   └── saveQuestions.ts        # Save individual questions to bank
│
├── store/                      # Zustand state management
│   └── editor-store.ts         # TipTap editor state, selected text, etc.
│
├── public/                     # Static assets
│   └── [images, logos, etc]
│
├── prisma/                     # Prisma ORM
│   ├── schema.prisma           # Database schema definition (CRITICAL)
│   └── migrations/             # Prisma migrations
│
├── scripts/                    # Build & setup scripts
│   └── setup-db.ts             # Database initialization
│
├── middleware.ts               # Next.js middleware (auth checks)
├── next.config.ts              # Next.js configuration
├── tsconfig.json               # TypeScript config
├── package.json                # Dependencies
├── postcss.config.mjs          # PostCSS for Tailwind
├── tailwind.config.ts          # Tailwind CSS config
├── components.json             # Shadcn/ui config
├── prisma.config.ts            # Prisma configuration
└── eslint.config.mjs           # ESLint rules
```

---

## Core Logic & Critical Workflows

### Workflow 1: Document Upload & Chunking

**Entry Point**: `frontend/components/file-upload.tsx` → `POST /api/documents/upload`

**Backend Flow** (`services/document_service.py`):

1. **Extract Text from PDF**:
   - `pdf_service.py` uses PyMuPDF to extract pages, text, and images
   - Images are stored separately if size > `PDF_IMAGE_MIN_BYTES` (8KB default)

2. **Semantic Chunking**:
   - Text split using `chunking_service.chunk_text()` with:
     - `chunk_size = 1000` tokens
     - `chunk_overlap = 200` tokens (context preservation)
   - Chunks break at sentence boundaries (`.` or `\n`) when possible

3. **Image Processing**:
   - Extracted images captioned via `caption_image_for_embedding()` using OpenAI Vision API
   - Captions stored alongside image metadata
   - Caption limit: 40 images per PDF (configurable)

4. **Embedding Generation**:
   - `embedding_service.generate_embeddings()` calls OpenAI with embedding model
   - **Default model**: `text-embedding-3-small` (1536 dimensions)
   - Embeddings stored in PostgreSQL `pgvector` column

5. **Metadata Storage**:
   - `PdfSource` record created with upload status
   - `DocumentChunk` records created with:
     - Original text content
     - Page number (if available)
     - Chunk index (for ordering)
     - Embedding vector
     - Metadata JSON (image URLs, captions, etc.)

**Database Indices**:
- `DocumentChunk` indexed on `pdf_source_id` for efficient retrieval

### Workflow 2: Question Generation (Main Pipeline)

**Entry Point**: `frontend/components/generator-form.tsx` → `POST /api/generation/questions/stream`

**Step 1: Request Validation** (`generation_router.py`):

```python
# Normalize inputs
board_norm = normalize_subject(subject)  # "social science" → "social science"
class_num = extract_class_number(class_val)  # "Class 10" → 10

# Eligibility check
is_eligible = (
    board == "CBSE" and 
    subject in ["science", "social science"] and 
    1 <= class_num <= 10
)

# Route decision
if is_eligible:
    use_new_engine = True  # q_instructions system
else:
    use_new_engine = False # legacy pipeline
```

**Step 2: Blueprint Resolution** (for eligible requests):

```
Request → generation_router.py
  ↓
Call: q_instructions.master.facade.AcademicGenerationFacade
  ↓
Load SubjectPlugin (e.g., ScienceSubjectPlugin)
  ↓
SubjectPlugin.get_blueprints_for_class(class_10) → list of BlueprintSpecs
  ↓
ScienceOrchestrator.allocate_streams(count=-1 for CBSE pattern)
  ↓
Returns: struct with:
  - sections: [
      {"section_title": "Part A", "questions": [
        {"question_type": "MCQ", "marks": 1, "count": 10, "blooms": "Knowledge"},
        ...
      ]},
      {"section_title": "Part B", ...}
    ]
  - total_marks
  - total_duration
```

**Step 3: RAG Retrieval** (`retrieval_service.py`):

For each question slot:

```python
# Generate query embedding
query = f"Generate a {topic} question for {subject} Class {class_num}"
query_embedding = generate_single_embedding(query)

# Semantic search
chunks = retrieve_relevant_chunks(
    query=query,
    pdf_source_ids=uploaded_pdf_ids,
    limit=5,
    query_embedding=query_embedding
)
# Returns chunks ranked by cosine similarity
```

**Step 4: Prompt Assembly** (`generation_service.py`):

```
Construct unified LLM prompt:

[SYSTEM RULES]
- You are an expert educator creating CBSE-compliant questions
- Strict JSON output format
- No markdown, no explanations

[PEDAGOGICAL BLUEPRINT]
- Section: "Part A: Multiple Choice"
- Question Type: MCQ
- Marks: 1
- Bloom's Level: Knowledge/Understanding
- Instructions: [exact text from q_instructions blueprint]

[RETRIEVAL CONTEXT]
From textbook chunks (ranked by relevance):
- Chunk 1: [Relevant text from PDF]
- Chunk 2: [More context]

[TOKEN BUDGET]
- Max tokens for question: 150
- Max tokens for options: 80 each

[FINAL INSTRUCTION]
Generate exactly 1 question matching above constraints.
Return as JSON: {"question": "...", "options": [...], "correct": 0, "explanation": "..."}
```

**Step 5: LLM Streaming** (`openai_service.py`):

```python
response = client.chat.completions.create(
    model="gpt-4-turbo",  # or gpt-3.5-turbo
    messages=[...assembled prompt...],
    temperature=0.7,  # Slight randomness for variety
    stream=True,  # CRITICAL for SSE
    max_tokens=500
)

for chunk in response:
    if chunk.choices[0].delta.content:
        yield f"data: {chunk.choices[0].delta.content}\n\n"
```

**Step 6: JSON Object Extraction** (`JsonObjectStreamExtractor`):

```
Raw stream: "{\n\"question\": \"What is...\", \"op"...
                                                    ↓ incomplete JSON
                                                    
Feed character by character into JsonObjectStreamExtractor:
- Track brace depth: { → depth=1, } → depth=0
- Track string escaping to avoid false braces in strings
- On depth=0 after opening {, call json.loads(buffer)

Result: {"question": "What is...", "options": [...], ...}
          ↓ complete object, emit via SSE event
```

**Step 7: Frontend Real-Time Rendering** (`components/generator-form.tsx`):

```typescript
const handleGenerateQuestions = async () => {
  const response = await fetch("/api/generation/questions/stream", {
    method: "POST",
    body: JSON.stringify(payload),
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const event = decoder.decode(value);  // "data: {...}\n\n"
    const question = JSON.parse(event.replace("data: ", ""));
    
    editor.insertContent(`<div>${question.question}</div>`);
  }
};
```

### Workflow 3: Answer Key Generation

**Entry Point**: `frontend/tiptap-editor.tsx` → `POST /api/generation/answer-key`

**Backend Flow** (`answer_script_service.py`):

1. **Extract HTML Content**: Get `paperContentHTML` from request
2. **Construct Prompt**:
   ```
   You are an expert educator. Here is a question paper in HTML:
   [paperContentHTML]
   
   Extract all questions and generate comprehensive answer key.
   Format as HTML with <h1>, <h2>, <p>, <ul>, <li>, <strong>, etc.
   ```
3. **LLM Call**: OpenAI chat completion (NOT streaming, full response)
4. **Return HTML**: Response streamed back to editor

**Token Optimization**:
- `answer_script_service._record_usage()` logs API calls for billing tracking
- Uses `ApiUsage` model to record prompt/completion tokens per user

---

## Database Schema

### Prisma Schema (Frontend ORM) — `frontend/prisma/schema.prisma`

```prisma
// Authentication
model User {
  id          String    @id
  name        String
  email       String    @unique
  image       String?
  createdAt   DateTime
  updatedAt   DateTime
  sessions    Session[]
  accounts    Account[]
  papers      Paper[]
  questions   Question[]
  pdfSources  PdfSource[]
}

model Session {
  id        String   @id @unique
  expiresAt DateTime
  token     String   @unique
  createdAt DateTime
  updatedAt DateTime
  ipAddress String?
  userAgent String?
  userId    String
  user      User     @relation(fields: [userId], references: [id], onDelete: Cascade)
}

model Account {
  id                    String    @id
  accountId             String
  providerId            String    // "google" or "email"
  userId                String
  user                  User      @relation(fields: [userId], references: [id], onDelete: Cascade)
  accessToken           String?
  refreshToken          String?
  idToken               String?
  accessTokenExpiresAt  DateTime?
  refreshTokenExpiresAt DateTime?
  scope                 String?
  password              String?   // For email provider
  createdAt             DateTime
  updatedAt             DateTime
}

// Content Management
model Paper {
  id              String   @id @default(cuid())
  userId          String
  user            User     @relation(fields: [userId], references: [id], onDelete: Cascade)
  class           String
  subject         String
  examName        String
  content         String?  // HTML/Markdown editor content
  metadata        Json?
  layoutSettings  Json?
  questionRefs    String[] // Array of Question IDs
  createdAt       DateTime @default(now())
  updatedAt       DateTime @updatedAt
}

model Question {
  id           String   @id @default(cuid())
  userId       String
  user         User     @relation(fields: [userId], references: [id], onDelete: Cascade)
  class        String
  subject      String
  topic        String
  questionType String   // "mcq", "short_answer", "long_answer"
  marks        Int      @default(1)
  difficulty   String?
  content      String
  options      String[] // For MCQs
  answer       String?
  explanation  String?
  createdAt    DateTime @default(now())
  updatedAt    DateTime @updatedAt
}

// Document Management
model PdfSource {
  id        String   @id @default(cuid())
  userId    String
  user      User     @relation(fields: [userId], references: [id], onDelete: Cascade)
  name      String
  size      Int
  url       String   // Empty for backend uploads
  status    String   @default("uploading") // "uploading" | "processing" | "ready" | "error"
  error     String?
  chunks    DocumentChunk[]
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}

model DocumentChunk {
  id           String                       @id @default(cuid())
  content      String
  page         Int?
  chunkIndex   Int
  embedding    Unsupported("vector(1536)")?
  pdfSourceId  String
  pdfSource    PdfSource                    @relation(fields: [pdfSourceId], references: [id], onDelete: Cascade)
  @@index([pdfSourceId])
}
```

### Django Models (Backend ORM)

#### `apps/accounts/models.py`

```python
class User:
    id: CharField (PK)
    name: CharField(255)
    email: EmailField (UNIQUE)
    image: TextField (nullable)
    created_at: DateTimeField (auto)
    updated_at: DateTimeField (auto)

class Session:
    id: CharField (PK)
    expires_at: DateTimeField
    token: CharField (UNIQUE)
    ip_address: CharField (nullable)
    user_agent: TextField (nullable)
    user: ForeignKey(User) → CASCADE

class Account:
    id: CharField (PK)
    account_id: CharField
    provider_id: CharField ("email" or OAuth provider)
    user: ForeignKey(User) → CASCADE
    access_token: TextField (nullable)
    refresh_token: TextField (nullable)
    password: TextField (hashed, nullable)
```

#### `apps/documents/models.py`

```python
class PdfSource:
    id: CharField (PK)
    name: CharField(255)
    size: IntegerField
    url: CharField(2048)
    status: CharField(50) # "uploading" | "ready" | "error"
    error: TextField (nullable)
    user: ForeignKey(User) → CASCADE
    created_at: DateTimeField (auto)

class DocumentChunk:
    id: CharField (PK)
    content: TextField
    page: IntegerField (nullable)
    chunk_index: IntegerField
    metadata: JSONField
    embedding: VectorField(dimensions=1536) # pgvector
    pdf_source: ForeignKey(PdfSource) → CASCADE
    @@index(pdf_source_id)
```

#### `apps/generation/models.py`

```python
class GenerationHistory:
    id: CharField (PK)
    prompt: TextField
    settings: JSONField
    result: JSONField
    user: ForeignKey(User) → CASCADE

class ApiUsage:
    id: CharField (PK)
    user: ForeignKey(User, nullable, SET_NULL)
    operation: CharField(64) # "embeddings", "generation", "answer_key"
    model: CharField(64)
    prompt_tokens: IntegerField
    completion_tokens: IntegerField
    total_tokens: IntegerField
```

### Database Indices

- **DocumentChunk**: Index on `pdf_source_id` (for fast chunk lookup)
- **GenerationHistory**: Implicit index on `user_id` (for history queries)
- **User**: Primary key `id`, unique on `email`

---

## Environment Setup & Configuration

### Backend Environment Variables (`backend/.env`)

```bash
# ========== REQUIRED ==========

# Django Core
DJANGO_SECRET_KEY=<your-secret-key-min-50-chars>
DJANGO_DEBUG=false  # Set to 'true' only for local development

# Database (Neon PostgreSQL)
DATABASE_URL=postgresql://<user>:<password>@<host>:<port>/<database>?sslmode=require
# Example: postgresql://user:pass@ep-abc123.neon.tech:5432/qpgen?sslmode=require

# OpenAI API
OPENAI_API_KEY=sk-proj-<your-api-key>
OPENAI_MODEL=gpt-4-turbo  # or gpt-3.5-turbo for cost savings
OPENAI_EMBEDDING_MODEL=text-embedding-3-small  # 1536 dimensions

# ========== OPTIONAL ==========

# CORS & Hosts
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,yourdomain.com
CORS_ALLOWED_ORIGINS=http://localhost:3000,https://yourdomain.com

# Features
QG_NEW_ENGINE_ENABLED=true  # Enable new Science engine (q_instructions)

# PDF Processing
PDF_IMAGE_MIN_BYTES=8192      # Skip images smaller than 8KB
PDF_IMAGE_MIN_DIMENSION=96    # Skip images smaller than 96px
PDF_IMAGE_MAX_CAPTIONS=40     # Max images to caption per PDF

# Storage
AOS_PUBLIC_MEDIA_BASE_URL=https://your-cdn.com  # Optional CDN URL

# Chunking
CHUNKING_SIZE=1000
CHUNKING_OVERLAP=200
```

### Frontend Environment Variables (`frontend/.env.local`)

```bash
# ========== REQUIRED ==========

# API Endpoints
NEXT_PUBLIC_API_URL=http://localhost:8000  # Backend API base URL
NEXT_PUBLIC_APP_URL=http://localhost:3000  # Frontend URL (for Better Auth redirects)

# Database (PostgreSQL)
DATABASE_URL=postgresql://<user>:<password>@<host>:5432/qpgen?sslmode=require

# Authentication (Better Auth)
BETTER_AUTH_SECRET=<min-32-chars-random-string>

# ========== OPTIONAL ==========

# Google OAuth (for social login)
GOOGLE_CLIENT_ID=<your-google-client-id>
GOOGLE_CLIENT_SECRET=<your-google-client-secret>

# Analytics (if integrated)
NEXT_PUBLIC_GA_ID=G-XXXXXXXX

# Feature Flags
NEXT_PUBLIC_ENABLE_EXPORT=true
NEXT_PUBLIC_ENABLE_PDF_SOURCES=true
```

### Backend Setup Steps

1. **Create virtual environment**:
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Create `.env` file** (see template above):
   ```bash
   cp .env.example .env
   # Edit .env with your values
   ```

4. **Enable pgvector extension** (if using PostgreSQL locally):
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

5. **Run migrations**:
   ```bash
   python manage.py migrate
   ```

6. **Create superuser** (for Django admin):
   ```bash
   python manage.py createsuperuser
   ```

7. **Start development server**:
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```

### Frontend Setup Steps

1. **Install dependencies**:
   ```bash
   cd frontend
   npm install
   # or
   yarn install
   ```

2. **Create `.env.local` file** (see template above)

3. **Initialize Prisma database** (creates tables):
   ```bash
   npx prisma migrate dev
   # Or if database exists:
   npx prisma db push
   ```

4. **Start development server**:
   ```bash
   npm run dev
   # or
   yarn dev
   ```

5. **Build for production**:
   ```bash
   npm run build
   npm start
   ```

### Testing & Debugging

**Backend Tests**:
```bash
# Test suite for generation service
python test_llm.py
python test_llm_service.py
python test_live.py  # Integration tests

# Run specific app tests
python manage.py test apps.generation
```

**Frontend Linting**:
```bash
npm run lint
```

**Debug Endpoints** (Django):
```
GET /debug/science-engine-health  # Health check for new engine
```

---

## Known Issues & Technical Debt

### Critical Issues

1. **🔴 Package.json Script Naming**
   - **File**: [frontend/package.json](frontend/package.json#L6)
   - **Issue**: Dev script is named `"nigga"` — extremely offensive and requires immediate correction
   - **Fix**: Rename to `"dev": "next dev"`
   - **Impact**: Blocks professional deployment and violates all CoCs

2. **🔴 Hardcoded Parameters in Generation Router**
   - **File**: [backend/services/generation_router.py](backend/services/generation_router.py#L78)
   - **Issue**: Test code with hardcoded eligibility checks left in production code
   - **Fix**: Clean up or move to test fixtures
   - **Impact**: Routing logic may behave unexpectedly

3. **🔴 OpenAI API Key Not Validated at Startup**
   - **File**: [backend/config/settings.py](backend/config/settings.py#L147-151)
   - **Issue**: Missing `OPENAI_API_KEY` raises cryptic error; should validate earlier
   - **Current**: Error raised only when services need it
   - **Fix**: Validate at Django startup with clear error message

### High-Priority Technical Debt

4. **🟡 PDF Image Processing Has No Error Recovery**
   - **File**: [backend/services/document_service.py](backend/services/document_service.py#L50-100)
   - **Issue**: If image captioning fails, entire chunk processing fails
   - **Current**: Catches exception and logs warning, but doesn't retry or gracefully degrade
   - **Impact**: Large PDFs with many images may fail silently
   - **Recommendation**: Implement retry logic or skip failed images gracefully

5. **🟡 Token Budget Algorithm Is Aggressive**
   - **File**: [backend/apps/question_generation/infrastructure/token_budget/budgeter.py](backend/apps/question_generation)
   - **Issue**: Samples max 55 chunks for large PDFs; may lose important context
   - **Current**: Static ceiling; doesn't account for document density
   - **Recommendation**: Make configurable; log warnings when truncating
   - **Impact**: Edge case: very dense or technical PDFs may lose critical content

6. **🟡 No Rate Limiting on Generation Endpoints**
   - **File**: [backend/apps/generation/views.py](backend/apps/generation/views.py)
   - **Issue**: No throttle on `/api/generation/questions/stream`
   - **Current**: Any authenticated user can spam API calls
   - **Recommendation**: Implement per-user rate limiting (e.g., 10 reqs/min)
   - **Impact**: Potential abuse; unbounded API costs

7. **🟡 Embedding Model Is Hard-Coded**
   - **File**: [backend/config/settings.py](backend/config/settings.py#L157)
   - **Issue**: `OPENAI_EMBEDDING_MODEL` set to `text-embedding-3-small`; no fallback
   - **Impact**: If model deprecated, code breaks; no version negotiation
   - **Recommendation**: Add `OPENAI_EMBEDDING_MODEL_FALLBACK`

### Medium-Priority Issues

8. **🟠 Better Auth Secret Uses Fallback in Development**
   - **File**: [frontend/lib/auth.ts](frontend/lib/auth.ts#L6)
   - **Issue**: `secret: process.env.BETTER_AUTH_SECRET || "fallback_secret_for_dev_only"`
   - **Impact**: Production deployments with missing secret silently use insecure default
   - **Fix**: Throw error if secret not provided in non-dev environments

9. **🟠 No Query Deduplication in Retrieval Service**
   - **File**: [backend/services/retrieval_service.py](backend/services/retrieval_service.py)
   - **Issue**: Same query may be embedded multiple times if called in loop
   - **Current**: Each question query generates new embedding
   - **Impact**: Unnecessary API calls; higher token usage
   - **Recommendation**: Cache embeddings per session

10. **🟠 Answer Key Generation Has No Input Sanitization**
    - **File**: [backend/services/answer_script_service.py](backend/services/answer_script_service.py)
    - **Issue**: `paperContentHTML` passed directly to LLM without validation
    - **Current**: Assumes frontend sends valid HTML
    - **Recommendation**: Sanitize/validate HTML structure before sending to LLM

11. **🟠 SSE Event Data Not Validated After Parsing**
    - **File**: [backend/services/generation_service.py](backend/services/generation_service.py#L60-100)
    - **Issue**: JSON objects extracted but not schema-validated before streaming
    - **Current**: Assumes LLM output matches expected structure
    - **Impact**: Invalid JSON objects reach frontend; may crash editor
    - **Recommendation**: Validate against Pydantic schema before yielding

### Low-Priority Improvements

12. **🟢 Add Observability / Structured Logging**
    - **Current**: Basic Python logging
    - **Recommendation**: Integrate structured logging (e.g., `loguru`, OpenTelemetry) for better debugging in production

13. **🟢 Database Connection Pooling Not Optimized**
    - **File**: [backend/config/settings.py](backend/config/settings.py#L78)
    - **Current**: `conn_max_age=600` (10 min)
    - **Recommendation**: Benchmark for your workload; may need connection pooling service

14. **🟢 No Caching Layer for Subject Blueprints**
    - **File**: [backend/q_instructions/subjects/registry.py](backend/q_instructions/subjects/registry.py)
    - **Issue**: Blueprints loaded from disk every request
    - **Recommendation**: Cache in memory or Redis

15. **🟢 Missing Comprehensive Error Handling for LLM Timeouts**
    - **Current**: OpenAI timeouts propagate directly to frontend
    - **Recommendation**: Implement exponential backoff + user-friendly error messages

### Frontend-Specific Issues

16. **🟡 Token Storage Uses localStorage (XSS Vulnerability)**
    - **File**: [frontend/lib/token-storage.ts](frontend/lib/token-storage.ts)
    - **Issue**: Stores auth token in localStorage; vulnerable to XSS
    - **Recommendation**: Migrate to secure HTTP-only cookie (Better Auth supports this)

17. **🟡 Editor State Not Persisted**
    - **File**: [frontend/store/editor-store.ts](frontend/store/editor-store.ts)
    - **Issue**: No auto-save; user loses work if page crashes
    - **Recommendation**: Implement auto-save to local DB or server every 5 seconds

18. **🟡 No User Feedback During Long-Running Generations**
    - **File**: [frontend/components/generator-form.tsx](frontend/components/generator-form.tsx)
    - **Issue**: SSE stream may stall; no heartbeat/progress indicator
    - **Recommendation**: Emit progress events; show loading state per section

### Architectural Concerns

19. **🟠 Database Schema Mismatch Between Prisma & Django**
    - **Issue**: Prisma schema (frontend) and Django models (backend) must stay in sync manually
    - **Current**: Both define User, PdfSource, DocumentChunk
    - **Recommendation**: Single source of truth (generate from one schema tool) or strict testing

20. **🟠 No Versioning of Blueprint Specifications**
    - **Issue**: q_instructions blueprints have no version tracking
    - **Current**: If subject plugin changes, old generations may not reproduce
    - **Recommendation**: Add `blueprint_version` field to `GenerationHistory`

---

## Conclusion

The AOS system is a sophisticated, architecture-aware question paper generator. The **key innovation** is the **decoupled architecture**: separating pedagogical rules (q_instructions) from content retrieval (RAG). This design eliminates hallucination and ensures CBSE compliance.

**For the next developer**:
- Start with [what_am_i.md](what_am_i.md) for conceptual grounding
- Understand the **routing decision** in `generation_router.py` (NEW vs LEGACY engine)
- The **q_instructions** system is the most complex; study `subjects/science/` as a reference
- Streaming via SSE is critical; don't remove or change without testing
- **Address critical issues immediately** (script naming, hardcoded params, API validation)
- Set up proper monitoring & error tracking early

Good luck! 🚀

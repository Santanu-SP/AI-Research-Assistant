# Research Assistant Web Application (Frontend)

A scholarly evidence-backed research workspace designed for active investigation synthesis, source citation mapping, and document management. Built in React 19, TypeScript, Tailwind CSS, and Vite.

---

## 🚀 Quickstart & Development

### 1. Install Dependencies
```bash
npm install
```

### 2. Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Default configuration points to the future FastAPI backend:
```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

### 3. Run Development Server
```bash
npm run dev
```
The application will launch on `http://localhost:3000`.

### 4. Production Build & Type Check
```bash
npm run typecheck
npm run build
```

---

## 🏛 Architecture & Project Layout

The codebase strictly decouples the user interface from backend communication, allowing seamless local mock operation or direct connection to a FastAPI service:

```
src/
├── app/
│   ├── App.tsx                     # Main app root & BrowserRouter provider
│   └── router.tsx                  # Declarative client-side routing
├── components/
│   ├── common/
│   │   ├── EmptyState.tsx          # Consistent archival empty state
│   │   ├── PrimaryButton.tsx       # Standard action button with hover motion
│   │   └── StatusBadge.tsx         # Completed, Researching, Draft, Failed badges
│   ├── documents/
│   │   ├── DocumentRow.tsx         # Document metadata row with status and actions
│   │   └── UploadDocumentModal.tsx # Drag-and-drop & manual upload dialog
│   ├── layout/
│   │   ├── AppLayout.tsx           # Layout container with responsive mobile drawer
│   │   ├── AppSidebar.tsx          # 232px fixed left navigation & profile
│   │   └── TopBar.tsx              # Breadcrumbs, quick search, and action bar
│   ├── research/
│   │   ├── CitationChip.tsx        # [n] inline citation with hover preview & click-to-scroll
│   │   ├── ProgressStepper.tsx     # 5-stage progress indicator with live counters
│   │   └── ResearchComposer.tsx    # Research query textarea with depth selector
│   └── sources/
│       ├── ExpandedSource.tsx      # High-contrast expanded evidence card
│       ├── SourceRow.tsx           # Compact source row
│       └── SourcesPanel.tsx        # Desktop panel & mobile drawer with filter/notes
├── data/
│   ├── mockDocuments.ts            # Realistic document files dataset
│   └── mockResearch.ts             # Synthesized research reports & progress data
├── pages/
│   ├── Documents.tsx               # Document knowledge base (/documents)
│   ├── MyResearch.tsx              # Research archive & filter table (/research)
│   ├── NewResearch.tsx             # New research inquiry (/research/new)
│   ├── ResearchProgress.tsx        # Real-time investigation tracking (/research/:id/progress)
│   └── ResearchReport.tsx          # Synthesis memo with bidirectional citations (/research/:id)
├── services/
│   ├── api.ts                      # Central fetch client configured with VITE_API_BASE_URL
│   ├── documents.service.ts        # Document API service (upload, list, retry, delete)
│   └── research.service.ts         # Research API service (start, status, report)
└── types/
    ├── document.ts                 # TypeScript interfaces for documents
    ├── research.ts                 # Research progress, report, and project models
    └── source.ts                   # Scholarly citation & reference types
```

---

## 🔌 FastAPI Backend Integration Guide

The frontend communicates exclusively through `src/services/api.ts` and the domain services (`research.service.ts` and `documents.service.ts`).

To connect the application to your FastAPI backend:
1. Ensure your FastAPI backend enables CORS for `http://localhost:3000`.
2. Configure `VITE_API_BASE_URL` in your `.env` file (e.g. `http://localhost:8000/api/v1`).
3. Replace the mock resolution promises in `src/services/research.service.ts` and `src/services/documents.service.ts` with direct calls to `apiRequest<T>()`.

### Planned API Endpoints

#### 1. Research Endpoints
- `GET /api/v1/research`
  - Returns `Research[]` for the archive list.
- `GET /api/v1/research/{id}`
  - Returns single `Research` project metadata.
- `POST /api/v1/research`
  - Payload: `{ question: string, depth: 'quick' | 'standard' | 'deep', includeWeb: boolean, includeDocs: boolean }`
  - Returns: `{ id: string }`
- Progress and report screens continue to use frontend mock data until their backend APIs are implemented.

#### 2. Document Endpoints
- `GET /api/v1/documents`
  - Returns `Document[]`.
- `POST /api/v1/documents`
  - `multipart/form-data` with `file: UploadFile`.
  - Returns `Document` with status `'processing'`.
- `DELETE /api/v1/documents/{id}`
  - Removes document from workspace.
- Retry behavior remains a frontend-only demonstration until document processing is implemented.

---

## 🎨 Visual System & Typography

- **UI Sans:** Geist (`font-sans`) for toolbars, inputs, status tags, citations, and navigation.
- **Report Serif:** EB Garamond (`font-serif`) for synthesis titles, pull quotes, and narrative prose.
- **Color Palette:**
  - Deep Forest Primary: `#163328`
  - Forest Hover: `#214f40`
  - Forest Tint: `#F1F6F3`
  - Off-White Canvas: `#FAFAF8`
  - Subtle Surface: `#F5F5F2`
  - Subtle Border: `#E5E7E4`
  - Primary Text: `#181A18`
  - Secondary Text: `#6B706C`

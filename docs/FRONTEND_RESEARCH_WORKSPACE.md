# Frontend Research Workspace — Architecture Guide

## Overview

The Research Workspace Experience adds **project-scoped document and research management** to the existing AI Research Assistant frontend. It is built using the same stack as the rest of the app: **React 19, TypeScript, TailwindCSS v4, react-router-dom v7**.

---

## New Directory Layout

```
frontend/src/
├── app/
│   ├── App.tsx            # Root: wires AuthProvider → ProjectProvider → ToastProvider
│   ├── AuthContext.tsx    # (existing) session auth state
│   ├── ProjectContext.tsx # NEW: selected project state + sessionStorage persistence
│   ├── ToastContext.tsx   # NEW: toast notification system
│   └── router.tsx         # UPDATED: /projects + /projects/:projectId routes
│
├── components/
│   ├── common/
│   │   ├── IngestionStatus.tsx    # NEW: document lifecycle badge (animated spinner)
│   │   ├── SafeMarkdown.tsx       # NEW: markdown renderer (no dangerouslySetInnerHTML)
│   │   └── SourceTypeLabel.tsx    # NEW: SourceType + ContentLevel labels
│   │
│   ├── layout/
│   │   └── AppSidebar.tsx         # UPDATED: Projects nav + recent projects list
│   │
│   └── projects/
│       ├── ArchiveProjectDialog.tsx   # Confirms + calls DELETE /projects/{id}
│       ├── CreateProjectDialog.tsx    # Creates via POST /projects
│       ├── EditProjectDialog.tsx      # Updates via PATCH /projects/{id}
│       ├── ProjectCard.tsx            # Project grid card with actions menu
│       ├── ProjectHeader.tsx          # Name, description, dates, archived banner
│       ├── ProjectResearchPanel.tsx   # Project-scoped research composer + result view
│       ├── ProjectSourcesPanel.tsx    # Document list + upload + search + filter
│       └── SourceCard.tsx             # Single document card with ingestion state
│       └── ProjectUploadModal.tsx     # Multi-file upload queue with duplicate detection
│
├── hooks/
│   └── useProjectDocuments.ts   # NEW: AbortController fetch + polling hook
│
├── pages/
│   ├── Projects.tsx            # NEW: /projects — project list page
│   └── ProjectWorkspace.tsx    # NEW: /projects/:projectId — tabbed workspace
│
├── services/
│   ├── documents.service.ts    # UPDATED: added project-scoped endpoints
│   └── projects.service.ts     # NEW: CRUD for /api/v1/projects
│
├── test/
│   ├── fixtures.ts                     # Shared test fixtures (real backend shapes)
│   ├── CreateProjectDialog.test.tsx
│   ├── documents.service.test.ts
│   ├── IngestionStatus.test.tsx
│   ├── ProjectContext.test.tsx
│   ├── ProjectUploadModal.test.tsx
│   ├── projects.service.test.ts
│   ├── SafeMarkdown.test.tsx
│   ├── setup.ts                        # Vitest setup (jest-dom matchers)
│   └── SourceCard.test.tsx
│
└── types/
    └── project.ts   # NEW: ResearchProject, CreateProjectInput, UpdateProjectInput
```

---

## Provider Hierarchy

```
<BrowserRouter>
  <AuthProvider>            ← session state (pre-existing)
    <ProjectProvider>       ← selected project + sessionStorage persistence
      <ToastProvider>       ← transient notifications
        <AppRouter />       ← routes
      </ToastProvider>
    </ProjectProvider>
  </AuthProvider>
</BrowserRouter>
```

---

## API Contract Compliance

All endpoints map directly to `backend/app/api/routes/`:

| Frontend method | Backend route | File |
|---|---|---|
| `projectsService.listProjects()` | `GET /api/v1/projects` | routes/projects.py |
| `projectsService.getProject(id)` | `GET /api/v1/projects/{id}` | routes/projects.py |
| `projectsService.createProject()` | `POST /api/v1/projects` | routes/projects.py |
| `projectsService.updateProject()` | `PATCH /api/v1/projects/{id}` | routes/projects.py |
| `projectsService.archiveProject()` | `DELETE /api/v1/projects/{id}` | routes/projects.py |
| `documentsService.getProjectDocuments()` | `GET /api/v1/projects/{id}/documents` | routes/project_documents.py |
| `documentsService.uploadProjectDocument()` | `POST /api/v1/projects/{id}/documents` | routes/project_documents.py |

No backend routes were added or modified.

---

## Key Design Decisions

### Stale-result guards

`ProjectResearchPanel` captures the `projectId` in a `useRef` at submit time and discards any response if the ref no longer matches the prop. This prevents a slow response from Project A appearing in Project B's UI when the user switches projects mid-flight.

### AbortController in `useProjectDocuments`

Every time `projectId` changes, the previous in-flight fetch is aborted. This avoids stale data from appearing when switching projects quickly.

### Duplicate detection (HTTP 409)

The backend raises HTTP 409 when a file with identical content is uploaded to the same project. `ProjectUploadModal` catches this per-file and shows "Already exists" without failing the entire batch.

### Ingestion polling

`useProjectDocuments` detects when any document has `status: 'uploaded' | 'processing'` and polls every 4 seconds. Polling stops automatically when all documents reach a terminal state (`indexed | failed`).

### SafeMarkdown

The backend answer field contains lightly-formatted Markdown (bold, bullets, headers). `SafeMarkdown` renders it without using `dangerouslySetInnerHTML`. It parses a safe subset of Markdown tokens in-process using pure React rendering — no eval, no HTML injection risk.

### Archive vs Delete

`projectsService.archiveProject()` calls `DELETE /projects/{id}` which the backend treats as a **soft archive**, not a hard delete. Archived projects can be viewed with `includeArchived=true` on the list endpoint.

### sessionStorage for project selection

The selected project ID is stored in `sessionStorage` (not `localStorage`). This means:
- Refreshing within the same session preserves the selection
- Opening a new browser tab starts fresh
- An expired/deleted project auto-clears the stored ID on 404

---

## Backend Capabilities: Known Gaps

The following capabilities were **not implemented** because no backend endpoint supports them:

| Desired feature | Backend status | Documented workaround |
|---|---|---|
| Restore archived project | No `PATCH` to restore `archived_at` | Not implemented; user must contact API |
| Per-project research history list | No `GET /projects/{id}/research` | Use `GET /research?project_id=...` if added |
| Document reprocessing retry | No retry endpoint | User must re-upload after deletion |

These are documented here rather than implemented with fake behavior.

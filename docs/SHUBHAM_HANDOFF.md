# Shubham — Research Workspace Experience: Handoff Notes

## What was built

This PR delivers the complete **Research Workspace Experience** — a major productization lift that adds project-scoped document management and research directly into the existing AI Research Assistant frontend.

### Scope summary

| Area | Files changed / created |
|---|---|
| **Types** | `types/project.ts` (new) |
| **Services** | `services/projects.service.ts` (new), `services/documents.service.ts` (updated) |
| **State** | `app/ProjectContext.tsx` (new), `app/ToastContext.tsx` (new), `app/App.tsx` (updated) |
| **Routing** | `app/router.tsx` (added `/projects`, `/projects/:projectId`) |
| **Navigation** | `components/layout/AppSidebar.tsx` (added Projects link + recent projects) |
| **Pages** | `pages/Projects.tsx` (new), `pages/ProjectWorkspace.tsx` (new) |
| **Project UI** | 9 new components under `components/projects/` |
| **Common UI** | `IngestionStatus.tsx`, `SafeMarkdown.tsx`, `SourceTypeLabel.tsx` |
| **Hooks** | `hooks/useProjectDocuments.ts` (AbortController + polling) |
| **Tests** | 8 new test files, shared fixtures, vitest config |
| **Docs** | `docs/FRONTEND_RESEARCH_WORKSPACE.md` |

---

## How to use

### Starting a dev server

```powershell
# In frontend/
npm install   # if not already done
npm run dev   # starts on http://localhost:3000
```

### Running production type-check

```powershell
npx tsc --noEmit
```

### Running tests

```powershell
node node_modules/vitest/dist/node/cli.mjs run
```

---

## Navigation flow

```
/ (Landing)
└── /login → /projects
    ├── /projects                       ← NEW: Project list with search
    │   ├── Create project dialog       ← inline modal
    │   └── /projects/:projectId        ← NEW: Project workspace
    │       ├── Sources tab             ← document list + upload
    │       └── Research tab            ← composer + citation view
    ├── /research/new                   ← existing
    ├── /research                       ← existing (all research)
    ├── /research/:id/progress          ← existing
    ├── /research/:id                   ← existing (report)
    └── /documents                      ← existing (global docs)
```

---

## Key behaviors to verify manually

### 1. Project creation
1. Go to `/projects`
2. Click "New Project"
3. Enter a name, optional description
4. Should redirect to `/projects/:id` workspace

### 2. Document upload
1. Inside a project workspace → Sources tab
2. Click Upload
3. Drag a PDF or DOCX
4. After upload, document should appear in the list
5. While status is `processing`, a spinner animates
6. Uploading the same file twice should show "Already exists"

### 3. Archived project restrictions
1. Archive a project (three-dot menu → Archive)
2. Navigate back to the workspace
3. Upload button should be gone; an archived banner should be visible
4. Research composer should show "Research is disabled for archived projects"

### 4. Project switching
1. Open Project A workspace
2. Type a question in the Research tab
3. Navigate to Project B workspace (use sidebar)
4. Previous results should be cleared; composer should be empty

### 5. Session persistence
1. Open Project A workspace
2. Refresh the page
3. Project A workspace should restore (sessionStorage)

---

## Backend constraints this PR works within

- **No new backend routes** were added. All endpoints pre-exist in the backend codebase.
- The archive action (`archiveProject`) calls `DELETE /projects/{id}` which the backend treats as a soft-delete (not permanent).
- Research query always submits the `project_id` to scope it. If the user has no documents in the project, the backend returns `insufficient_evidence: true` — the UI displays a warning banner.
- Duplicate uploads: the backend returns HTTP 409. The upload modal detects this per-file and shows "Already exists" without failing the entire batch.

## Known gaps (documented, not faked)

| Feature | Status |
|---|---|
| Restore archived project | Not supported by current backend API |
| Per-project research history | No `GET /projects/{id}/research` endpoint yet |
| Document retry after failure | User must re-upload |

These are documented in `docs/FRONTEND_RESEARCH_WORKSPACE.md` rather than faked.

---

## Files intentionally NOT changed

- `backend/` — zero backend changes
- `frontend/src/pages/MyResearch.tsx` — global research list preserved as-is
- `frontend/src/pages/Documents.tsx` — global docs page preserved as-is
- `frontend/src/services/research.service.ts` — existing service reused, not modified

---

## Test coverage overview

| Test file | What's covered |
|---|---|
| `projects.service.test.ts` | listProjects (params), getProject (404), create (POST body), update (PATCH), archive (DELETE), error mapping |
| `documents.service.test.ts` | project-scoped GET, upload (FormData), 409 duplicate, error mapping |
| `ProjectContext.test.tsx` | initial state, selectProject, clearProject, error state, sessionStorage |
| `SafeMarkdown.test.tsx` | paragraphs, bold, code, headings, lists, blockquotes, XSS prevention |
| `IngestionStatus.test.tsx` | all states, error summary visibility, unknown status fallback, aria-label |
| `SourceCard.test.tsx` | title/fallback, status badges, delete button, DOI links, archived hiding |
| `CreateProjectDialog.test.tsx` | render, validation, API call, error display, close |
| `ProjectUploadModal.test.tsx` | file queuing, success, duplicate, invalid type, cancel |

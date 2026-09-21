# Auth and core UI action audit

| Component | Action before this change | Result now |
| --- | --- | --- |
| AppRouter | Open workspace without a session | Protected routes redirect to Login; session restores on reload |
| Login and Register | No account screens | Validated forms use the auth API and show errors/loading |
| AppSidebar | Placeholder Settings and static profile | Profile shows the signed-in user and opens Logout |
| TopBar | Search control had no handler | Hidden until search exists |
| ResearchComposer | Web/document toggles did not affect requests | Removed; research depth and draft creation remain functional |
| NewResearch | Create persisted draft | Creates draft; entering New Research resets composer state |
| MyResearch and recent links | Draft links returned to the list | Open the draft progress/detail screen |
| ResearchProgress | Cancel only navigated away; report link used wrong path | Cancel removed; report link uses the existing route |
| Documents | Upload/delete calls did not send sessions; Use in research only navigated | Authenticated upload/delete; View details opens metadata and the owned PDF |
| UploadDocumentModal | Generic upload failure | Shows safe API error message; Cancel and Confirm work |
| ResearchReport | Share label implied public access | Copies the private report link; export remains functional |
| SourcesPanel | Hard-coded note text and false save claim | Starts empty and saves per user/report in this browser |

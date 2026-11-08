# Deviations from the plan

This file lists where the project differs from the SRS, SAD and Test Plan, and why. It was written at the end of Sprint 2 (7 Nov 2026).

## Process

| # | Planned | What happened | Reason / effect |
|---|---|---|---|
| 1 | Six sprints (Sprint 0 to Sprint 5), as in the SRS RTM | Two sprints: Sprint 1 (27–31 Oct) and Sprint 2 (5–7 Nov) | The course schedule allows two sprints. Work from the planned Sprints 3–5 was moved into Sprint 2 or left for later (see the RTM status) |
| 2 | Task tracking in GitHub Projects | Jira Cloud (DFS project) | The course asks for a Jira dashboard with a burndown chart |
| 3 | Project setup in a separate Sprint 0 | Setup (DFS-5, repo skeleton and CI) was done inside Sprint 1 | No time for a separate sprint |
| 4 | Jira stories created before Sprint 1 started | Stories were created on 30 Oct, during Sprint 1 | The Sprint 1 burndown therefore starts late. Dates were **not** changed afterwards to make the chart look better |
| 5 | Sprint 2 from 2 Nov | Sprint 2 was started in Jira on 5 Nov | Sprint 1 work and reviews ran over. The sprint end date (7 Nov) did not change |
| 6 | SARIMAX in the first forecasting story | SARIMAX moved to Sprint 2 (DFS-15, PR #18) | Sprint 1 shipped moving average and Holt-Winters first |
| 7 | Every PR reviewed and approved before merge | PR #4 (DFS-9) was merged by merge order before its review was finished; it was reviewed by comment afterwards | Since then, branch protection on `main` requires one approval from someone other than the author and three passing CI checks |
| 8 | DFS-15 and DFS-19 marked Done only when their code was merged | Both cards were moved to Done in Jira before their code existed. This was noticed and corrected: DFS-15 was built in PR #18 and DFS-19 in PR #16 | Card status now follows merged PRs |
| 9 | Demo videos with narration | The Sprint 1 and Sprint 2 videos are scripted browser recordings with on-screen captions and no voice | Recorded with Playwright so the steps can be repeated exactly. Files: `videos/Sprint1_demo.webm`, `videos/Sprint2_demo.webm` |
| 10 | — | Most of the code and documents were written with an AI assistant (Claude Code), then reviewed, tested and merged by team members through PRs | Allowed by the course. Every change still went through review and CI |

## Product

| # | Planned | What happened | Reason / effect |
|---|---|---|---|
| 11 | Hosted on a public server with HTTPS (DFS-SR-001), 99.5% availability (DFS-NF-004) | No public hosting. The CI/CD **deploy** stage builds the images and publishes them to GitHub Container Registry (GHCR) on every push to `main`; the app is run with Docker Compose | No budget or time for a server. The app is ready for HTTPS: it sends HSTS and uses secure cookies when `COOKIE_SECURE=true`. DFS-SR-001 and DFS-NF-004 are **not met** |
| 12 | Database changes through Alembic migrations (SAD) | Tables are created when the app starts (`create_all`) | Simpler for a two-sprint project. Changing an existing table needs a database reset until migrations are added |
| 13 | Rate limits shared by all API servers (SAD suggests Redis) | The rate limiter keeps its counts in memory, per API process | One API process is used, so the limits are exact. With several processes, each would count separately |
| 14 | Purchase recommendations and PO approval (DFS-F-017, DFS-F-018) | Only the database tables and schemas were built (PR #16). Supplier allocation, endpoints and approval are not built | Out of time in Sprint 2 |
| 15 | Screens for every feature | Inventory, market indicators, forecast approval/override, alerts, dashboard KPIs and export are available through the API (Swagger at `/docs`) but have no screens yet | Back-end work was prioritised. The Sprint 2 video shows these through the API docs page |
| 16 | Audit log of logins, data changes, approvals and overrides (DFS-SR-005) | Only forecast overrides and approvals are audited | Partly done |
| 17 | Performance, scalability, accessibility and accuracy tests (TC-Perf-01..03, TC-UX-01, TC-Fc-06, TC-Rel-01) | Not run | Need a hosted environment and a full reference data set. Listed as **N** or **P** in [RTM_STATUS.md](RTM_STATUS.md) |
| 18 | Dashboard and export covered by automated tests | No tests for `/api/reports/*` | Checked by hand only |
| 19 | SARIMAX working from DFS-15 (PR #18) | SARIMAX failed on every run because SciPy was not pinned; runs fell back to the other models without any error shown. Found and fixed in DFS-23 | SciPy is now pinned and SARIMAX has regression tests. See [TEST_RESULTS.md](TEST_RESULTS.md) |

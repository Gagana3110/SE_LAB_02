# Requirements Traceability Matrix: status at the end of Sprint 2

This is the RTM from section 8 of the SRS, updated on 7 Nov 2026. The SRS PDF still shows every requirement as **N**, because it was written before any code existed. This file records where each requirement stands now.

**Status:** **A** = Accepted (built, and its test case passes) · **P** = Partly done · **N** = Not started

Test results are in [TEST_RESULTS.md](TEST_RESULTS.md). Known gaps and changes to the plan are in [DEVIATIONS.md](DEVIATIONS.md).

## Functional requirements

| Req ID | Requirement | Test case | Status | Where it was built | Notes |
|---|---|---|---|---|---|
| DFS-F-001 | Login and session timeout | TC-Auth-01 | **A** | DFS-6, PR #2 | 30-minute idle timeout, renewed on each request |
| DFS-F-002 | Role-based access | TC-Auth-02 | **A** | DFS-6, PR #2 | Four roles, checked on the server for every request |
| DFS-F-003 | Password reset | TC-Auth-03 | **A** | DFS-20, PR #15 | Single-use link valid for 30 minutes, sent by email (Mailpit locally) |
| DFS-F-004 | Products, materials and BOM | TC-MD-01 | **A** | DFS-7, PR #3; screens in DFS-12, PR #7 | |
| DFS-F-005 | Supplier management | TC-MD-02 | **A** | DFS-8, PR #5 | |
| DFS-F-006 | Material-supplier mapping | TC-MD-03 | **A** | DFS-8, PR #5 | Warns about materials with no supplier |
| DFS-F-007 | Import sales history | TC-Data-01 | **A** | DFS-9, PR #4; screen in DFS-12, PR #7 | CSV/XLSX import with a downloadable error report |
| DFS-F-008 | Inventory and stock movements | TC-Data-02 | **A** | DFS-17, PR #12 | API only: there is no inventory screen yet |
| DFS-F-009 | Market indicators | TC-Data-03 | **A** | DFS-17, PR #12 | API only |
| DFS-F-010 | Generate forecast | TC-Fc-01 | **A** | DFS-10, PR #6; SARIMAX in DFS-15, PR #18 | Moving average, Holt-Winters and SARIMAX, run in the background by Celery |
| DFS-F-011 | Back-test and best-model selection | TC-Fc-02 | **A** | DFS-10, PR #6; DFS-15, PR #18 | Holds out recent periods and picks the model with the lowest MAPE. SARIMAX was silently failing until SciPy was pinned in DFS-23 (see TEST_RESULTS.md) |
| DFS-F-012 | Forecast chart and intervals | TC-Fc-03 | **A** | DFS-11, PR #8 | |
| DFS-F-013 | Forecast override and approval | TC-Fc-04 | **A** | DFS-16, PR #11 | API only. Override needs a reason; approval locks the forecast; both are audited |
| DFS-F-014 | Short-history fallback | TC-Fc-05 | **A** | DFS-10, PR #6; DFS-15, PR #18 | Products with fewer than 12 periods use the moving average |
| DFS-F-015 | BOM explosion (MRP) | TC-Proc-01 | **A** | DFS-18, PR #13 | Calculation service checked against `docs/DFS18_hand_calculations.xlsx`; no screen |
| DFS-F-016 | Safety stock and reorder point | TC-Inv-01 | **A** | DFS-18, PR #13 | Checked at 90% and 95% service levels for 3 materials |
| DFS-F-017 | Purchase recommendations | TC-Proc-02 | **P** | DFS-19, PR #16 | Only the database tables and schemas exist. Supplier allocation logic, endpoints and tests are not built |
| DFS-F-018 | Approve recommendation / draft PO | TC-Proc-03 | **N** | — | Depends on DFS-F-017 |
| DFS-F-019 | Low-stock and accuracy alerts | TC-Inv-02 | **A** | DFS-20B, PR #19 | Alerts when stock is low or MAPE exceeds 20%, with one email per alert |
| DFS-F-020 | Dashboard KPIs | TC-Rep-01 | **P** | DFS-21, PR #17 | `GET /api/reports/dashboard` works; no automated test and no dashboard screen |
| DFS-F-021 | CSV / PDF export | TC-Rep-02 | **P** | DFS-21, PR #17 | `GET /api/reports/export/{type}?format=csv\|pdf` with a role check per report; no automated test and no export button in the UI |

## Non-functional requirements

| Req ID | Requirement | Test case | Status | Notes |
|---|---|---|---|---|
| DFS-NF-001 | Response time ≤ 2 s (p95, 50 users) | TC-Perf-01 | **N** | No load test was run |
| DFS-NF-002 | Forecast run for 500 products ≤ 5 min | TC-Perf-02 | **P** | Runs happen in the background (Celery), so browsing is not blocked. The 500-product timing was not measured |
| DFS-NF-003 | Forecast accuracy (mean MAPE ≤ 20%) | TC-Fc-06 | **P** | MAPE, MAE and bias are calculated and shown for each forecast. No accuracy report on a full reference data set yet |
| DFS-NF-004 | 99.5% availability, daily backups | TC-Rel-01 | **N** | Not hosted (see [DEVIATIONS.md](DEVIATIONS.md)) |
| DFS-NF-005 | Usability and WCAG 2.1 AA | TC-UX-01 | **P** | Labelled forms and keyboard-usable pages on desktop. No Lighthouse audit run |
| DFS-NF-006 | Maintainability: ≥ 80% coverage, common model interface | CI coverage report | **A** | CI fails the build below 80% backend coverage; all models share one interface |
| DFS-NF-007 | Scalability: 1 M sales rows, 2,000 products | TC-Perf-03 | **N** | Not tested |

## Security requirements

| Req ID | Requirement | Test case | Status | Notes |
|---|---|---|---|---|
| DFS-SR-001 | TLS 1.2+ everywhere | TC-Sec-01 | **N** | No public HTTPS host. The app sends HSTS and uses secure cookies when `COOKIE_SECURE=true` |
| DFS-SR-002 | Passwords stored as salted Argon2 | TC-Sec-02 | **A** | DFS-6, PR #2 |
| DFS-SR-003 | Server-side authorisation on every API call | TC-Sec-03 | **A** | Role checks on every router; tested per role |
| DFS-SR-004 | Input and upload validation | TC-Sec-03, TC-Sec-04 | **A** | Only .csv/.xlsx up to 10 MB; Pydantic validation on every request |
| DFS-SR-005 | Append-only audit log | TC-Sec-05 | **P** | Forecast overrides and approvals are audited (`GET /api/audit-log`). Logins and master-data changes are not audited yet |
| DFS-SR-006 | Rate limiting (login 10/min, API 100/min) | TC-Sec-06 | **A** | DFS-22, PR #14 |

## Summary

| | A | P | N | Total |
|---|---|---|---|---|
| Functional | 17 | 3 | 1 | 21 |
| Non-functional | 1 | 3 | 3 | 7 |
| Security | 4 | 1 | 1 | 6 |
| **All** | **22** | **7** | **5** | **34** |

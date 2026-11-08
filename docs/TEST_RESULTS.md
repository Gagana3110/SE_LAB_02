# Test results: end of Sprint 2

Run on 7 Nov 2026, on branch `feature/DFS-23-tests-docs-video` (same code as `main` after PR #19).

## Summary

| Suite | Command | Result |
|---|---|---|
| Backend lint | `ruff check .` | All checks passed |
| Backend tests | `pytest` (Python 3.12, SQLite test database) | **269 passed, 0 failed** in 5 min 45 s |
| Backend coverage | `pytest --cov` (gate: 80%) | **90.81%** (2,362 statements, 217 missed) |
| Frontend tests | `npm test` (Vitest) | **48 passed, 0 failed** (2 files) |
| CI on `main` | GitHub Actions `ci-cd.yml` | Backend, frontend and Docker jobs pass; deploy publishes images to GHCR |

The same checks run in CI on every pull request. A pull request cannot be merged unless the backend, frontend and Docker jobs pass.

### Backend tests by file

| File | Test functions | Covers |
|---|---|---|
| `test_auth.py` | 24 | Login, sessions, lockout, roles, Argon2 |
| `test_password_reset.py` | 5 | Password reset |
| `test_masterdata.py` | 18 | Products, materials, BOM |
| `test_suppliers.py` | 19 | Suppliers, material-supplier links |
| `test_sales_import.py` | 34 | Sales import and error report |
| `test_inventory.py` | 12 | Stock movements, balances, market indicators |
| `test_forecasting.py` | 40 | Forecast engine (moving average, Holt-Winters, SARIMAX, back-test), runs, chart data |
| `test_forecast_approval.py` | 5 | Override, approval, audit log |
| `test_procurement.py` | 9 | BOM explosion, net requirement, safety stock, reorder point |
| `test_alerts.py` | 6 | Low-stock and MAPE alerts, alert emails |
| `test_hardening.py` | 14 | Rate limiting, security headers |
| `test_reference_data.py` | 4 | Reference data set |
| `test_health.py` | 2 | Health check |
| **Total** | **192 functions, 269 test runs** (some are parametrised) | |

### Frontend tests

| File | Tests | Covers |
|---|---|---|
| `src/App.test.tsx` | 37 | Login, menus per role, products, materials, BOM, suppliers, import, users |
| `src/ForecastPage.test.tsx` | 11 | Starting a run, progress, chart, table, product switch |

## Results by Test Plan test case

**Pass** = automated tests pass · **Pass (manual)** = checked by hand in the running app · **Partial** = only part of the case is covered · **Not run** = feature or environment not available

| Test case | Requirement | Result | Evidence |
|---|---|---|---|
| TC-Auth-01 | DFS-F-001 Login and session timeout | Pass | `test_auth.py`, e.g. `test_expired_session_is_rejected` |
| TC-Auth-02 | DFS-F-002 Role-based access | Pass | `test_auth.py::test_other_roles_cannot_use_admin_endpoints`, role tests in every module, `App.test.tsx` menus per role |
| TC-Auth-03 | DFS-F-003 Password reset | Pass | `test_password_reset.py`: link works once, expires after 30 min, token stored hashed, unknown email gets the same answer. Also shown in the Sprint 2 video |
| TC-MD-01 | DFS-F-004 Products, materials, BOM | Pass | `test_masterdata.py`, `App.test.tsx` |
| TC-MD-02 | DFS-F-005 Suppliers | Pass | `test_suppliers.py` |
| TC-MD-03 | DFS-F-006 Material-supplier mapping | Pass | `test_suppliers.py` |
| TC-Data-01 | DFS-F-007 Sales import | Pass | `test_sales_import.py` |
| TC-Data-02 | DFS-F-008 Inventory | Pass | `test_inventory.py::test_tc_data_02_*` |
| TC-Data-03 | DFS-F-009 Market indicators | Pass | `test_inventory.py::test_market_indicator_*` |
| TC-Fc-01 | DFS-F-010 Generate forecast | Pass | `test_forecasting.py::test_run_produces_a_forecast_for_the_full_horizon` and others |
| TC-Fc-02 | DFS-F-011 Back-test and best model | Pass | `test_forecasting.py::test_every_model_is_backtested_and_the_lowest_mape_wins`, `test_sarimax_*` (added in this cycle, see the defect below). Also shown in the Sprint 2 video |
| TC-Fc-03 | DFS-F-012 Chart and intervals | Pass | `test_forecasting.py::test_intervals_contain_the_forecast_and_widen_over_time`, `ForecastPage.test.tsx` |
| TC-Fc-04 | DFS-F-013 Override and approval | Pass | `test_forecast_approval.py`: reason required, approval locks the forecast, second approval gets 409, both audited |
| TC-Fc-05 | DFS-F-014 Short-history fallback | Pass | `test_forecasting.py::test_short_history_uses_moving_average` |
| TC-Fc-06 | DFS-NF-003 Forecast accuracy | Not run | No accuracy report on the full reference data set yet |
| TC-Proc-01 | DFS-F-015 BOM explosion | Pass | `test_procurement.py`, matches `docs/DFS18_hand_calculations.xlsx` |
| TC-Inv-01 | DFS-F-016 Safety stock and ROP | Pass | `test_procurement.py::test_safety_stock_for_three_materials_at_both_service_levels`, `test_reorder_point_matches_hand_calculation` |
| TC-Proc-02 | DFS-F-017 Purchase recommendations | Not run | Feature not built (only database tables) |
| TC-Proc-03 | DFS-F-018 Approve recommendation / draft PO | Not run | Feature not built |
| TC-Inv-02 | DFS-F-019 Alerts | Pass | `test_alerts.py`: low-stock and lead-time alerts, no duplicates, MAPE alert with email |
| TC-Rep-01 | DFS-F-020 Dashboard KPIs | Pass (manual) | `GET /api/reports/dashboard` returned the KPIs in the running app (Sprint 2 video). No automated test |
| TC-Rep-02 | DFS-F-021 CSV / PDF export | Pass (manual) | CSV and PDF downloaded as Administrator; Inventory Manager refused with 403 (manual checks below). No automated test |
| TC-Perf-01 | DFS-NF-001 Response time | Not run | No load test |
| TC-Perf-02 | DFS-NF-002 Forecast run time | Not run | Not measured for 500 products. A run for the 50 reference products finished in the video recording |
| TC-Perf-03 | DFS-NF-007 Scalability | Not run | |
| TC-Rel-01 | DFS-NF-004 Availability | Not run | Not hosted |
| TC-UX-01 | DFS-NF-005 Usability | Not run | No Lighthouse audit |
| CI coverage report | DFS-NF-006 Maintainability | Pass | 90.81% ≥ 80%, checked by CI on every build |
| TC-Sec-01 | DFS-SR-001 TLS | Not run | No HTTPS host. `test_hardening.py::test_https_deployments_send_strict_transport_security` checks HSTS when `COOKIE_SECURE=true` |
| TC-Sec-02 | DFS-SR-002 Argon2 | Pass | `test_auth.py::test_passwords_are_stored_only_as_argon2_hashes` |
| TC-Sec-03 | DFS-SR-003 / SR-004 Server-side checks | Pass | Tests marked TC-Sec-03 in `test_auth.py` and `test_sales_import.py`; role tests in every module |
| TC-Sec-04 | DFS-SR-004 Input validation | Pass | Tests marked TC-Sec-04 in `test_sales_import.py` (file type, size, bad content) |
| TC-Sec-05 | DFS-SR-005 Audit log | Partial | Override and approval entries tested in `test_forecast_approval.py`. Logins and master-data changes are not audited |
| TC-Sec-06 | DFS-SR-006 Rate limiting | Pass | `test_hardening.py`: 11th login in a minute gets 429, per-user API limit, health checks exempt. Also shown in the Sprint 2 video |

**Totals:** 24 Pass (2 of them manual), 1 Partial, 9 Not run, out of 34 rows.

## Defect found during this test cycle

| | |
|---|---|
| **Defect** | SARIMAX never ran. Every SARIMAX fit failed with `TypeError: fmin_l_bfgs_b() got an unexpected keyword argument 'disp'`. The back-test caught the error and dropped SARIMAX, so runs silently used Holt-Winters or moving average instead |
| **Found by** | Manual check while recording the Sprint 2 video: a run with only SARIMAX allowed came back as moving average |
| **Cause** | SciPy was not pinned, so installs picked SciPy 1.18, which statsmodels 0.14.4 does not support |
| **Fix** | Pinned `scipy==1.14.1` in `backend/requirements.txt` |
| **Regression tests** | Added to `test_forecasting.py`: `test_sarimax_backtest_gives_metrics`, `test_sarimax_only_run_uses_sarimax`, `test_every_model_is_backtested_and_the_lowest_mape_wins`. They fail without the pin and pass with it |
| **Lesson** | The broad `except Exception` in the back-test hid the failure, and there was no SARIMAX test. Every model now has a test that checks it really runs |

## Manual checks in the running app

Done with `docker compose up` and the reference data set on 7 Nov 2026. Most are shown in [videos/Sprint2_demo.webm](../videos/Sprint2_demo.webm).

| Check | Result |
|---|---|
| Password reset email arrives in Mailpit, link works once, second use is refused | Pass |
| Forecast run for all 50 products with all three models; each product shows its chosen model, MAPE, MAE, bias and confidence | Pass |
| Override without a reason is rejected; override after approval is rejected (409) | Pass |
| Stock receipt and issue update the balance; an issue larger than the stock is rejected | Pass |
| `POST /api/alerts/evaluate` creates low-stock and MAPE alerts | Pass |
| `GET /api/reports/dashboard` returns the KPIs | Pass |
| `GET /api/reports/export/forecasts?format=csv` and `?format=pdf` as Administrator: 200, a CSV with a header row (24 KB) and a valid PDF (22 KB) | Pass |
| The same export as an Inventory Manager is refused with 403 | Pass |
| 11 wrong logins in a minute: the 11th gets HTTP 429 | Pass |

## How to repeat

```bash
docker run --rm -v "$PWD:/repo" -w /repo/backend python:3.12-slim \
  sh -c "pip install -q -r requirements-dev.txt && ruff check . && pytest"
cd frontend && npm ci && npm test
```

# Demand Forecasting System (DFS)

A web application that forecasts product demand from sales history, inventory and market indicators, then recommends which raw materials to buy, from which supplier and by when.

Software Engineering mini project. Requirements and design are in [docs/](docs/).

## Team

| Name | SRN |
|---|---|
| Bandugula Sai Rithesh Reddy | PES1UG24AM064 |
| Dhyeya Aneesh | PES1UG24AM091 |
| G Ganikhasri | PES1UG24AM098 |
| Gagana C | PES1UG24AM099 |

## Tech stack

React + TypeScript, Python FastAPI, PostgreSQL, Redis + Celery, statsmodels, Docker Compose, GitHub Actions.

## What it does

**Sprint 1**
- Login with four roles (Administrator, Demand Planner, Inventory Manager, Procurement Manager) and a 30-minute idle timeout
- Products, raw materials and bills of materials (BOM)
- Suppliers and material-supplier links, with a warning for materials that have no supplier
- Sales history import from CSV/XLSX, with a downloadable error report
- Forecasts with moving average and Holt-Winters, shown as a chart with intervals

**Sprint 2**
- Password reset by email: a single-use link, valid for 30 minutes
- SARIMAX model and back-testing: each forecast shows its model, MAPE, MAE and bias, and the best model is chosen automatically
- Forecast override (a reason is required) and approval, recorded in an audit log
- Inventory: receipts, issues, adjustments and stock balances; market indicators
- MRP calculations: BOM explosion, net requirements, safety stock and reorder point
- Alerts for low stock and for forecasts with MAPE above 20%, with an email per alert
- Dashboard KPIs and CSV/PDF export
- Rate limiting, security headers and a deploy stage in CI/CD

Some Sprint 2 features have no screen yet and are used through the API docs page. See [docs/RTM_STATUS.md](docs/RTM_STATUS.md) for what is done.

## Documents and videos

| | |
|---|---|
| Requirements (SRS), design (SAD), Test Plan | [docs/](docs/) |
| RTM status at the end of Sprint 2 | [docs/RTM_STATUS.md](docs/RTM_STATUS.md) |
| Test results | [docs/TEST_RESULTS.md](docs/TEST_RESULTS.md) |
| Deviations from the plan | [docs/DEVIATIONS.md](docs/DEVIATIONS.md) |
| MRP hand calculations | [docs/DFS18_hand_calculations.xlsx](docs/DFS18_hand_calculations.xlsx) |
| Sprint 1 demo (1 min) | [videos/Sprint1_demo.webm](videos/Sprint1_demo.webm) |
| Sprint 2 demo (2 min) | [videos/Sprint2_demo.webm](videos/Sprint2_demo.webm) |

## Run the app

Requires Docker Desktop. First copy `.env.example` to `.env` and set your own passwords; the first Administrator account is created from `ADMIN_EMAIL` and `ADMIN_PASSWORD`.

```bash
docker compose up --build
```

- Web app: http://localhost:8080
- API docs: http://localhost:8000/docs
- Mailpit (catches password-reset and alert emails locally): http://localhost:8025

### Security settings

| Setting | Default | Meaning |
|---|---|---|
| `COOKIE_SECURE` | `false` | Set to `true` when the app is served over HTTPS. The session cookie is then sent only over HTTPS, and the API sends `Strict-Transport-Security` |
| `TRUST_PROXY_HEADERS` | `true` in Docker Compose, `false` otherwise | Use the client address that nginx forwards (`X-Real-IP`) for rate limits. Only turn this on when the API is reachable through the proxy alone |
| `LOGIN_RATE_PER_MINUTE` | `10` | Login attempts per minute from one address; more get HTTP 429 |
| `API_RATE_PER_MINUTE` | `100` | API calls per minute per user (or per address when not logged in) |
| `MAPE_ALERT_THRESHOLD` | `20` | A forecast with a higher MAPE raises an accuracy alert |

The API also sends `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` and a strict `Content-Security-Policy` on every response.

## CI/CD

`.github/workflows/ci-cd.yml` runs on every pull request and every push to `main`:

1. **Build and test**: backend (ruff, bandit, pytest with an 80% coverage gate) and frontend (Vitest, then a type-checked production build)
2. **Docker image build**: builds both images
3. **Deploy** (push to `main` only): publishes the images to GitHub Container Registry as `ghcr.io/gagana3110/se_lab_02-backend` and `ghcr.io/gagana3110/se_lab_02-frontend`, tagged `latest` and with the commit SHA

`main` is protected: a pull request needs one approval from someone other than its author, and the three build checks must pass.

## Run the tests

```bash
cd backend
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
pytest
```

```bash
cd frontend
npm ci
npm test
```

## Reference data

The synthetic data set from the Test Plan is in `data/reference/`. Regenerate it with:

```bash
cd backend
python scripts/generate_reference_data.py
```

## How we work

- Tasks are tracked on Jira (project key `DFS`).
- Create a branch per task named with the Jira key, e.g. `feature/DFS-6-login`.
- Start commit messages with the key, e.g. `DFS-6 add login API`.
- Open a Pull Request to `main`. CI must pass, and another team member reviews, approves and merges it.

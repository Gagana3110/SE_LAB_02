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

React + TypeScript, Python FastAPI, PostgreSQL, Redis, Docker Compose, GitHub Actions.

## Run the app

Requires Docker Desktop. First copy `.env.example` to `.env` and set your own passwords; the first Administrator account is created from `ADMIN_EMAIL` and `ADMIN_PASSWORD`.

```bash
docker compose up --build
```

- Web app: http://localhost:8080
- API docs: http://localhost:8000/docs

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
- Open a Pull Request to `main`. CI must pass, and the repo owner reviews and merges.

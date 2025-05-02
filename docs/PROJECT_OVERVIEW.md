# Nota AI — End-to-End Invoice Automation for Indonesian Restaurants

> **Purpose of this document**  
> Single source of truth.  
> If the conversation history disappears, feeding this file back to ChatGPT / WindSurf fully restores the project context.

---

## 1 • Vision & Business Context

| Aspect | Details |
|--------|---------|
| **Target market** | Restaurants & cafés in Indonesia (Bali first). |
| **Pain point** | Hand-written, messy invoices; manual entry into Syrve (ex-iiko) wastes hours and causes errors. |
| **Solution** | Telegram bot + GPT-4o Vision → parse → validate → XML to Syrve → continuous self-learning. |
| **Key goals 2025** | Reduce manual invoice work ≥ 80 %, near-real-time food-cost visibility, foundation for multi-location analytics. |

---

## 2 • High-Level Flow (“Gold Path”)

```mermaid
sequenceDiagram
User->>Bot: Sends invoice photo (jpg/png)
Bot->>OCR (GPT-4o Vision): Base64 image
OCR-->>Bot: Parsed JSON (supplier, date, positions[])
Bot->>Matcher: Compare positions vs products.csv + aliases.csv
Matcher-->>Bot: Match + status (ok/unit_mismatch/unknown)
Bot->>User: Markdown report with ✅ & ⚠️ buttons
User->>Bot: (optional) inline corrections
Bot->>Aliases DB: store new alias if confirmed
Bot->>Formatter: Build final XML (later sprint)
Formatter-->>Syrve API: POST /invoice



⸻

3 • Current Status (after Sprint 0)

Module	State	Notes
Skeleton bot (aiogram 3)	Done	
OCR stub (USE_OPENAI_OCR=0)	Done	
Pydantic models (ParsedData, Position)	Done	
Matcher (exact+fuzzy name+unit)	Done	
Formatter (Markdown report RU/EN)	Done	
Data 🤖 base_suppliers.csv, base_products.csv	Done	
aliases.csv (empty)	Done	
CI (GitHub Actions) + tests	Done	
Docs (this file)	Now!	
Deploy to DO / systemd	Planned (Sprint 4)	



⸻

4 • Roadmap

Sprint	Scope & Deliverables
S-01	Inline corrections UI; auto-save aliases into data/aliases.csv.
S-02	Daily pull of fresh suppliers/products from Syrve API; merge logic.
S-03	Generate & push XML invoices + error handling (409, 422).
S-04	Production deploy (systemd, healthcheck, tmp cleanup, logrotate).
S-05	Multi-tenant, i18n, price anomaly alerts, dashboard (Grafana/Metabase).



⸻

5 • Directory Layout

.
├── bot.py                 # entry-point
├── app/
│   ├── config.py          # pydantic-settings
│   ├── ocr.py             # GPT-4o (stub/real)
│   ├── matcher.py
│   ├── formatter.py
│   ├── data_loader.py
│   ├── models.py          # ParsedData, Position
│   └── keyboards.py       # inline UI (future)
├── data/
│   ├── base_suppliers.csv
│   ├── base_products.csv
│   └── aliases.csv        # grows over time
## Sprint 1: Inline corrections & self-learning aliases

### Features
- Inline UI for every invoice line: ✅ OK, ✏️ Edit, 🗑 Remove.
- Alias self-learning: user-confirmed names are saved to `data/aliases.csv` (deduplicated, lowercase).
- Fuzzy matcher: merges aliases on startup, suggests top-5 similar products if unknown.
- Command `/reload` reloads CSVs without restart.
- Unit tests cover alias flow: unknown → edit → alias saved → next run = ok.
- All bot messages in English.

### Alias Flow Diagram

```
unknown → edit → alias saved → повтор → ok
```

### Data & Test Constraints
* Do **NOT** edit `data/base_products.csv` or `data/base_suppliers.csv`.
* All new aliases go ONLY to `data/aliases.csv`.
* For unit-tests use files in `data/sample/`.

**Особенности:**
- Эти файлы не должны изменяться автоматически ботом или в процессе self-learning — только ручное редактирование.
- Все новые алиасы и “обученные” продукты пишутся в отдельные файлы (`aliases.csv`, `learned_products.csv`), чтобы не затронуть базу.

### Acceptance Checklist (DoD)
- [x] Inline buttons for each invoice position.
- [x] Edit flow allows user to correct name/qty/unit/price or remove a row.
- [x] Alias self-learning: confirmed names are saved and recognized next time.
- [x] Fuzzy suggestions: top-5 similar products shown if name is unknown.
- [x] All tests pass, CI green.
- [x] Docs updated (this file, README).

---
├── docs/PROJECT_OVERVIEW.md
├── tests/
│   ├── mock_invoice.json
│   └── test_basic.py
├── Makefile
├── requirements*.txt
└── .github/workflows/ci.yml



⸻

6 • Data Contracts

class Position(BaseModel):
    name: str
    qty: float
    unit: str
    price: float | None = None

class ParsedData(BaseModel):
    supplier: str
    date: date  # ISO-8601
    positions: list[Position]
    total: float | None = None

Stored alias line: alias,product_id

⸻

7 • Environment Variables

Key	Default	Description
BOT_TOKEN	—	Telegram bot token.
OPENAI_API_KEY	—	GPT-4o Vision access.
OPENAI_MODEL	gpt-4o	Model name (future proof).
MATCH_THRESHOLD	0.75	Levenshtein ratio for fuzzy match.
USE_OPENAI_OCR	0	1 = call real OCR, else stub.
SYRVE_API_KEY	—	(Sprint 3) Auth for Syrve.

docs/.env.example holds an up-to-date template.

⸻

8 • Make Targets

Target	Action
run-local	Start polling bot (python bot.py).
test	Run pytest with stub OCR.
lint	black . --check + isort --check.
deploy	(future) ssh do 'git pull && systemctl restart nota'.



⸻

9 • CI Pipeline (GitHub Actions)

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -r requirements.txt
      - run: make lint
      - run: make test



⸻

10 • Coding Conventions
	•	Black + isort (88 chars)
	•	Flake8 (warnings treated as CI failure)
	•	Pre-commit hooks recommended (pre-commit install).
	•	Typing: PEP 604 (str | None) + pydantic models.

⸻

11 • Branch & Release Strategy
	•	main — stable, deployable.
	•	sprint-<n> — dev branch per sprint (merged via PR).
	•	Hotfixes direct to main if prod-critical.
	•	Tags: v0.1.0 (SemVer) on every production deploy; GitHub-release archives.

⸻

12 • Roles / User Journeys

Role	Scenario	Interaction
Cook	Snap photo right after delivery	Gets instant ✅/⚠️, can fix qty/unit inline.
Bookkeeper	Reviews pending invoices	Uses “Send to Syrve” button (future).
Admin	Maintains product DB & thresholds	SSH deploy, views Grafana dashboard (after S-04).



⸻

13 • Self-Learning Logic
	1.	Matcher flags a position status="unknown".
	2.	Bot sends inline-button “Add alias”.
	3.	User picks correct product.
	4.	Bot appends line to data/aliases.csv.
	5.	On bot restart, data_loader merges aliases → product list.

⸻

14 • Deployment & Ops
	•	Server: DigitalOcean droplet, Ubuntu 22.04, systemd service nota-bot.
	•	Log rotation: logrotate.d/nota.conf, keep 7 days.
	•	Tmp cleanup: cron find tmp -mtime +3 -delete.
	•	Back-ups: weekly pg_dump (when we switch to PostgreSQL).

⸻

15 • Future Enhancements
	•	Price variance alerts (> ±10 % vs last 3 deliveries).
	•	Multi-language UI (RU/EN/ID).
	•	OAuth login for web dashboard (FastAPI + Next.js).
	•	Plugin architecture to add new OCR providers (Google Vision, Tesseract).

⸻

Last updated: 2025-05-02 (UTC+08).
Maintainers: Denis @Enthusiasm-c & ChatGPT (assistant).

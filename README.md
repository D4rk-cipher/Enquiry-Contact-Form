# Enquiry Contact Form Bot - Phase 1

Automates finding and filling website contact forms from a list of business emails.

**Phase 1 features**
- Extract unique domains from a CSV of emails
- Discover contact pages (common paths + nav scanning)
- Heuristic form field detection and filling
- Test mode (fill only) and Submit mode
- CAPTCHA / challenge detection then skip + log
- Resumable runs (important for large lists up to ~50k)
- Screenshots + detailed CSV logging
- Configurable profile (name, email, phone, company, messages)

Phase 2 (stealth, LLM form intelligence, CAPTCHA solving) will be added later.

---

## Quick start

```bash
git clone https://github.com/D4rk-cipher/Enquiry-Contact-Form.git
cd Enquiry-Contact-Form
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

Edit `config.yaml` with your real details (name, email, phone, company, message).

Prepare a CSV with emails, e.g. `data/emails.csv`:

```csv
email
info@example.com
contact@anothercompany.com
```

### Test mode (recommended first)

```bash
python main.py --input data/emails.csv --mode test --limit 5
```

This fills forms but **does not submit**. Check `output/screenshots/` and `output/results.csv`.

### Submit mode

```bash
python main.py --input data/emails.csv --mode submit
```

### Resume a large run

```bash
python main.py --input data/emails.csv --mode test --resume
```

### Industry-specific message

```bash
python main.py --input data/emails.csv --mode test --industry real_estate
```

---

## Important notes for large runs (10k-50k)

- Runs are sequential with a configurable delay (default ~10 s + jitter).
- 50k domains will take a long time (days). That is expected.
- Always use `--resume` so you can stop and continue safely.
- Progress is saved after every domain in `output/progress.json`.
- Keep `headless: false` while developing; switch to `true` for long unattended runs if you prefer.
- Start with a small `--limit` and inspect results before full runs.

---

## Output files

| File | Purpose |
|------|---------|
| `output/results.csv` | Every domain + status + notes + screenshot path |
| `output/needs_captcha.csv` | Domains that need manual attention |
| `output/progress.json` | Already processed domains (for resume) |
| `output/screenshots/` | PNG screenshots of each attempt |

Status values: `submitted`, `filled_only`, `captcha`, `no_form`, `error`

---

## Configuration

All personal data and messages live in `config.yaml`.  
Never hard-code secrets in the Python files.

---

## Next (Phase 2 ideas)

- Stealth browser / better anti-detect
- LLM-assisted form field understanding
- Paid CAPTCHA solving
- Optional low concurrency
- Better success-page detection

# Signup Automation - The Authorized Partner (QA Task)

Playwright (Python) script that automates the agency signup on https://authorized-partner.vercel.app/

**Flow covered:** Terms checkbox -> 1. Set up account -> OTP verification -> 2. Agency details -> 3. Professional experience -> 4. Verification & preferences

> The OTP is sent to a real email inbox, so the script pauses on the OTP page and waits (up to 5 min) for the code to be typed in and "Verify Code" clicked. Every other step is fully automated.

## Prerequisites
- [uv](https://docs.astral.sh/uv/) - installs Python and dependencies for you (no manual virtualenv)
  - Windows: `winget install --id=astral-sh.uv -e` or `pip install uv`
  - macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Internet access
- An email inbox you can read (the address is set in `test_data.json`)

## How to run
```bash
git clone <this-repo-url>
cd <repo-folder>

uv sync                              # creates .venv, installs dependencies
uv run playwright install chromium   # one-time browser download
uv run python signup_automation_script.py
```
Optional: `--data other.json` to use a different data file.

Outputs: `test_report.md` and `artifacts/screenshots/*.png`. Exit code is `0` on success and `1` if any step fails.

## Environment
| Item | Version |
|------|---------|
| Language | Python >= 3.10 (uv selects one) |
| Framework | Playwright (sync API), Chromium |
| Dependencies | `playwright` (see `pyproject.toml`) |

## Test data
All values live in `test_data.json`. `{ts}` is replaced with a Unix timestamp on every run so the email/agency name are unique; with Gmail, `name+{ts}@gmail.com` still lands in the same inbox. Edit the email to one you can access.

| Section | Fields |
|---------|--------|
| account | first/last name, email, phone (+977), password |
| agency | name, role, email, website, address, region |
| experience | years, students/year, focus area, success %, services |

## Checks performed
- "Continue" is disabled until the terms box is ticked, then enabled.
- Each step's heading is asserted before interacting.
- Screenshot after every step, and on failure.

## Known limitations
- Step 4 fields are handled generically (tick checkboxes, upload dummy PDF, click submit); adjust `step_verification()` for specific required fields.



## Test Execution Results

### Successful Execution

The signup automation script was previously executed successfully, and the complete registration flow was reached.

The screenshots captured during that execution are available in `artifacts/screenshots/`.

**Screenshots captured:**

| Screenshot | Description |
|---|---|
| `01_terms_checkbox_ticked.png` | Terms and conditions accepted |
| `02_account_details_filled.png` | Account registration details filled |
| `03_otp_page.png` | OTP verification page displayed |
| `04_agency_details_filled.png` | Agency details completed |
| `05_professional_experience_filled.png` | Professional experience completed |
| `06_verification_preferences_filled.png` | Verification and preferences completed |
| `07_account_created.png` | Account creation confirmation |

### Latest Execution Status

During the latest execution, the registration process stopped at **Step 1 – Set up your account**.

The backend API returned:

```text
HTTP 429 - Too Many Requests
```

The API endpoint was:

```text
POST /api/tempuser/
```

This response indicates that the server temporarily rate-limited the registration requests. As a result, the OTP page did not open during this run.

**Important:** This is a server-side rate-limiting issue, not a confirmed automation script failure. The remaining steps were not executed in the latest run.

### Test Coverage

- Terms and conditions acceptance
- Account setup form
- OTP verification (manual OTP entry)
- Agency details
- Professional experience
- Verification and preferences
- Account creation confirmation

### Known Limitations

- OTP verification requires manual interaction because the OTP is sent to a real email inbox.
- The latest execution was blocked by HTTP 429 from the backend.
- A successful end-to-end execution is evidenced by the previously captured screenshots; the latest run could not independently verify all steps.
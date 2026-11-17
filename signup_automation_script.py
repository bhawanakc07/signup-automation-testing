
import base64
import json
import random
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE_URL = "https://authorized-partner.vercel.app"
OTP_WAIT_MS = 5 * 60 * 1000  # we give ourselves 5 minutes to type the OTP

SHOT_DIR = Path("artifacts/screenshots")
SHOT_DIR.mkdir(parents=True, exist_ok=True)


# ----------------------------------------------------------------- helper functions
def make_phone():
    """Make a random 10 digit Nepali mobile number, e.g. 9841234567."""
    prefix = random.choice(["980", "981", "982", "984", "985", "974", "975"])
    rest = "".join(random.choices("0123456789", k=7))
    return prefix + rest


def load_data():
    """Read test_data.json and replace {ts} and {phone} with fresh values."""
    text = Path("test_data.json").read_text(encoding="utf-8")
    text = text.replace("{ts}", str(int(time.time())))
    text = text.replace("{phone}", make_phone())
    return json.loads(text)


def shot(page, name, full=False):
    """Save a screenshot in artifacts/screenshots/."""
    page.screenshot(path=SHOT_DIR / f"{name}.png", full_page=full)
    print("Screenshot saved:", name)


def log_api(response):
    """Print the calls made to the backend, so we can see what the server answered."""
    if "stage.cloudedu.com.au" in response.url:
        print("[API]", response.request.method, response.status, response.url)


def fill_after_label(page, label, value):
    """Find the text box that belongs to a label (like 'First Name') and type into it."""
    box = page.get_by_label(label, exact=True)
    if box.count() != 1:
        # fallback: the first input that comes after the label text
        box = page.locator(
            f"xpath=(//*[normalize-space(text())='{label}'])[1]"
            "/following::*[self::input or self::textarea][1]"
        )
    box = box.first
    box.wait_for()
    if box.is_editable():  # some boxes are already filled and locked
        box.fill(value)


def choose_from_dropdown(page, label, option):
    """Open the dropdown that belongs to a label and click one option."""
    dropdown = page.locator(
        f"xpath=(//*[normalize-space(text())='{label}'])[1]"
        "/following::*[self::select or @role='combobox' or self::button][1]"
    )
    dropdown.wait_for()
    if dropdown.evaluate("e => e.tagName") == "SELECT":
        dropdown.select_option(label=option)  # normal <select> dropdown
        return

    dropdown.click()  # custom dropdown: open it first
    page.wait_for_timeout(500)

    # look for a real, visible option first
    choice = page.get_by_role("option", name=option)
    if choice.count() == 0:
        # only if there is no real option, search by plain text
        choice = page.get_by_text(option, exact=True)
    choice.first.click()


def tick_checkbox(page, text):
    """Tick a checkbox using the text next to it."""
    try:
        page.get_by_role("checkbox", name=text).click(timeout=3000)
    except Exception:
        page.get_by_text(text, exact=True).first.click()


def make_png(path):
    """Create a tiny PNG image that we can upload as a document."""
    path.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    ))
    return path


# ----------------------------------------------------------------- the test steps
def step_terms(page, data):
    page.goto(BASE_URL + "/register", wait_until="networkidle")
    expect(page.get_by_text("Register Your Agency").first).to_be_visible()
    page.wait_for_timeout(1000)

    # tick the "I agree to the Terms of Service and Privacy Policy" box
    checkbox = page.get_by_role("checkbox").first
    try:
        checkbox.click(timeout=3000)
    except Exception:
        checkbox.click(force=True)

    shot(page, "01_terms_checkbox_ticked")
    page.get_by_role("button", name="Continue").click()
    expect(page.get_by_text("Complete Your Agent Profile in Steps").first).to_be_visible()


def step_account(page, data):
    a = data["account"]
    expect(page.get_by_text("Provide your personal details.").first).to_be_visible()

    fill_after_label(page, "First Name", a["first_name"])
    fill_after_label(page, "Last Name", a["last_name"])
    fill_after_label(page, "Email Address", a["email"])
    page.get_by_placeholder("00-00000000").fill(a["phone"])
    fill_after_label(page, "Password", a["password"])
    fill_after_label(page, "Confirm Password", a["password"])
    print("Using email:", a["email"], "| phone:", a["phone"])

    shot(page, "02_account_details_filled")
    page.get_by_role("button", name="Next", exact=True).click()

    # the OTP page should open. If not, something was rejected by the server.
    otp_heading = page.get_by_role("heading", name="Email Verification code", exact=True)
    try:
        expect(otp_heading).to_be_visible(timeout=15000)
    except AssertionError:
        raise AssertionError(
            "OTP page did not open. Check the [API] lines above. "
            "A 429 means too many requests: wait 30-60 minutes and try again."
        )


def step_otp(page, data):
    page.wait_for_timeout(500)
    shot(page, "03_otp_page")
    print("\n>>> OTP page reached. Type the code from your email and click 'Verify Code'.")
    print(">>> Waiting up to 5 minutes...\n")
    # we just wait until the next page (Agency Details) shows up
    expect(page.get_by_text("About your Agency").first).to_be_visible(timeout=OTP_WAIT_MS)


def step_agency(page, data):
    g = data["agency"]
    fill_after_label(page, "Name", g["name"])
    fill_after_label(page, "Role in Agency", g["role"])
    fill_after_label(page, "Email Address", g["email"])
    fill_after_label(page, "Website", g["website"])
    fill_after_label(page, "Address", g["address"])

    # the region (Nepal) is usually already selected, so only pick it if missing
    if page.get_by_text(g["region"], exact=True).count() == 0:
        choose_from_dropdown(page, "Region of Operation", g["region"])

    shot(page, "04_agency_details_filled")
    page.get_by_role("button", name="Next", exact=True).click()


def step_experience(page, data):
    e = data["experience"]
    expect(page.get_by_text("Experience and Performance Metrics").first).to_be_visible()

    choose_from_dropdown(page, "Years of Experience", e["years"])
    fill_after_label(page, "Number of Students Recruited Annually", e["students_recruited_annually"])
    fill_after_label(page, "Focus Area", e["focus_area"])
    fill_after_label(page, "Success Metrics", e["success_metrics"])
    for service in e["services"]:
        tick_checkbox(page, service)

    shot(page, "05_professional_experience_filled")
    page.get_by_role("button", name="Next", exact=True).click()


def step_verification(page, data):
    v = data["verification"]
    expect(page.get_by_text("Provide Business Details and Set Preferences").first).to_be_visible()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)

    # 1) Business Registration Number
    fill_after_label(page, "Business Registration Number", v["business_registration_number"])

    # 2) Preferred Countries: click the button to open the list, then click each country
    trigger = page.locator("button, [role='combobox']").filter(
        has_text=re.compile("preferred countries", re.I)
    ).first
    trigger.scroll_into_view_if_needed()
    popup = page.locator(
        "[role='listbox'], [cmdk-list], [role='menu'], [role='dialog'], "
        "[data-radix-popper-content-wrapper]"
    ).last

    for country in v["preferred_countries"]:
        if not popup.is_visible():  # open the list if it is closed
            trigger.click()
            page.wait_for_timeout(700)
        search_box = popup.locator("input")
        if search_box.count() > 0:  # if the list has a search box, type the country
            search_box.first.fill(country)
            page.wait_for_timeout(600)
        popup.get_by_text(re.compile(re.escape(country), re.I)).first.click()
        page.wait_for_timeout(500)
    page.keyboard.press("Escape")  # close the list

    # 3) Documents: "Add Documents" shows 3 upload boxes, then we put a file in each
    add_button = page.locator("button").filter(has_text=re.compile("add documents", re.I))
    file_inputs = page.locator("input[type='file']")
    for _ in range(3):
        if file_inputs.count() >= 3 or add_button.count() == 0:
            break
        add_button.first.click()
        page.wait_for_timeout(1000)

    image = str(make_png(Path("artifacts/business_document.png")))
    print("Upload boxes found:", file_inputs.count())
    for i in range(file_inputs.count()):
        file_inputs.nth(i).set_input_files(image)
        page.wait_for_timeout(1000)

    # 4) Preferred Institution Types
    for name in v["institution_types"]:
        box = page.get_by_role("checkbox", name=name, exact=True)
        try:
            if not box.is_checked():  # some are already ticked, do not untick them
                box.click(timeout=2000)
        except Exception:
            page.get_by_text(name, exact=True).first.click()

    shot(page, "06_verification_preferences_filled", full=True)
    page.locator("button").filter(has_text=re.compile(r"^\s*submit\s*$", re.I)).first.click()


def step_confirmation(page, data):
    # after Submit the site should move away from the register page
    try:
        page.wait_for_url(lambda url: "/register" not in url, timeout=20000)
    except Exception:
        print("Still on the register page after Submit")
    page.wait_for_timeout(3000)
    print("Final page:", page.url)
    shot(page, "07_account_created", full=True)


# ----------------------------------------------------------------- report + main
def write_report(results):
    lines = [
        "# Signup Automation - Test Report",
        "",
        f"Run at: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "| Step | Result | Time (s) |",
        "|------|--------|----------|",
    ]
    for name, status, seconds in results:
        lines.append(f"| {name} | {status} | {seconds:.1f} |")
    Path("test_report.md").write_text("\n".join(lines), encoding="utf-8")


def main():
  
    for old in SHOT_DIR.glob("*.png"):
        old.unlink()

    data = load_data()
    steps = [
        ("Accept terms", step_terms),
        ("1. Set up your account", step_account),
        ("OTP verification (typed by hand)", step_otp),
        ("2. Agency details", step_agency),
        ("3. Professional experience", step_experience),
        ("4. Verification and preferences", step_verification),
        ("5. Account created", step_confirmation),
    ]
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=100)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.set_default_timeout(15000)
        page.on("response", log_api)

        for number, (name, step) in enumerate(steps, 1):
            start = time.time()
            try:
                step(page, data)
                results.append((name, "PASS", time.time() - start))
                print("PASS:", name)
            except Exception as error:
                shot(page, f"FAILED_{number:02d}")
                results.append((name, "FAIL", time.time() - start))
                print("FAIL:", name)
                print("Reason:", str(error).splitlines()[0])
                break

        write_report(results)
        print("\nReport written to test_report.md")

        # keep the browser open so we can look at the last page
        if "--close" not in sys.argv:
            input("\nPress Enter to close the browser... ")
        browser.close()

    failed = any(status == "FAIL" for _, status, _ in results)
    sys.exit(1 if failed else 0)


main()
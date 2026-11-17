# Signup automation for https://authorized-partner.vercel.app/
import json
import os
import random
import re
import time

from playwright.sync_api import sync_playwright, expect

URL = os.getenv("BASE_URL", "https://authorized-partner.vercel.app")
HEADLESS = os.getenv("HEADLESS", "no") == "yes"
CHANNEL = os.getenv("BROWSER_CHANNEL") or None

ts = str(int(time.time()))
with open("test_data.json", encoding="utf-8") as f:
    data = json.loads(f.read().replace("{ts}", ts))

phone_used = ""          # filled in later, the phone is made by this script
api = {"sent": 0, "limit": False, "seen_limit": False, "retry": None}


def new_phone():
    # real Nepali mobile prefix + 7 digits
    return random.choice(["980", "981", "982", "984", "985", "986"]) + str(random.randint(1000000, 9999999))



def on_request(req):
    if req.method == "POST":
        api["sent"] += 1


def on_response(resp):
    if resp.request.method != "POST":
        return
    try:
        body = " ".join(resp.text().split())[:150]
    except Exception:
        body = ""
    print("[API]", resp.status, resp.url, body)
    if resp.status == 429:
        api["limit"] = True
        api["seen_limit"] = True
        api["retry"] = resp.headers.get("retry-after")



def fill(page, label, value):
    # the label is not always linked to the input, so try a few ways
    ways = [
        page.get_by_label(label, exact=True),
        page.get_by_label(re.compile(label, re.I)),
        page.get_by_placeholder(re.compile(label, re.I)),
        page.locator(f"xpath=(//*[starts-with(normalize-space(text()),'{label}')])[1]/following::input[1]"),
    ]
    for way in ways:
        if way.count() > 0:
            way.first.fill(value)
            return
    raise Exception(f"Field '{label}' not found")


def fill_passwords(page, value):
    # password boxes have no label, find them by type
    boxes = page.locator("input[type='password']")
    boxes.first.wait_for()
    for i in range(boxes.count()):
        boxes.nth(i).fill(value)


def choose(page, label, option):
    # open the dropdown below the label and click the option
    page.locator(f"xpath=(//*[normalize-space(text())='{label}'])[1]"
                 "/following::*[@role='combobox' or self::select or self::button][1]").click()
    page.get_by_role("option", name=re.compile(option, re.I)).first.click()


def click_next(page):
    # click Next, and click again only if the page did not send anything
    otp_title = page.get_by_text("Email Verification code").first
    button = page.get_by_role("button", name="Next", exact=True)
    for attempt in range(4):
        before = api["sent"]
        button.scroll_into_view_if_needed()
        expect(button).to_be_enabled()
        if attempt == 0:
            button.click()
        elif attempt == 1:
            button.click(force=True)
        elif attempt == 2:
            button.focus()
            page.keyboard.press("Enter")
        else:
            button.dispatch_event("click")
        for _ in range(8):
            page.wait_for_timeout(400)
            if api["sent"] > before or otp_title.is_visible() or page.get_by_text("valid phone").count() > 0:
                return
        print(f"Next click {attempt + 1} did nothing, trying another way")


def page_errors(page):
    # red messages under fields, alerts and toasts (helps to see why Next does nothing)
    found = []
    for t in page.locator("[role='alert'], [data-sonner-toast], [id$='-form-item-message'], "
                          "p.text-destructive, p[class*='text-red']").all_inner_texts():
        t = " ".join(t.split())
        if t and t not in found:
            found.append(t)
    return found


def go_next(page, target):
    # click Next and wait until the next page (target) shows. If the click was lost, click again.
    button = page.get_by_role("button", name="Next", exact=True)
    page.keyboard.press("Tab")
    page.wait_for_timeout(1000)
    for attempt in range(4):
        before = api["sent"]
        api["limit"] = False
        button.scroll_into_view_if_needed()
        expect(button).to_be_enabled()
        if attempt == 0:
            button.click()
        elif attempt == 1:
            button.click(force=True)
        elif attempt == 2:
            button.focus()
            page.keyboard.press("Enter")
        else:
            button.dispatch_event("click")
        page.wait_for_timeout(1500)
        if api["sent"] > before:                 # a request went out, so wait for the answer
            for _ in range(60):
                if target.is_visible():
                    return
                if api["limit"]:
                    raise Exception("Server blocked this step with HTTP 429 (too many requests)")
                page.wait_for_timeout(500)
        elif target.is_visible():
            return
        print(f"Next click {attempt + 1} did not open the next page. Page errors: {page_errors(page)}")
    raise Exception(f"Next did not open the next page. Page errors: {page_errors(page)}")


def wait_with_countdown(page, otp_title, seconds):
    # the site may let us in by itself, so stop early if the OTP page shows up
    end = time.time() + seconds
    last = 0
    while time.time() < end:
        if otp_title.is_visible():
            return True
        if time.time() - last >= 15:
            print(f"   {int(end - time.time())} seconds left")
            last = time.time()
        page.wait_for_timeout(1000)
    return otp_title.is_visible()


# ---------- the steps ----------
def step_terms(page):
    page.goto(URL + "/register")
    page.get_by_role("checkbox").first.click()
    page.get_by_role("button", name="Continue").click()
    expect(page.get_by_text("Provide your personal details.").first).to_be_visible()


def step_account(page):
    global phone_used
    a = data["account"]
    otp_title = page.get_by_text("Email Verification code").first

    fill(page, "First Name", a["first_name"])
    fill(page, "Last Name", a["last_name"])
    fill(page, "Email Address", a["email"])
    fill_passwords(page, a["password"])

    for attempt in range(4):
        phone_used = new_phone()
        page.get_by_placeholder("00-00000000").fill(phone_used)
        page.keyboard.press("Tab")              # leave the box so the site checks the phone
        page.wait_for_timeout(1500)
        if page.get_by_text("valid phone").count() > 0:
            print("Phone rejected, trying another number")
            continue

        api["limit"] = False
        click_next(page)

        for _ in range(150):                    # wait up to 60 seconds
            page.wait_for_timeout(400)
            if otp_title.is_visible():
                return
            if api["limit"] or page.get_by_text("valid phone").count() > 0:
                break

        if api["limit"]:
            try:
                wait = int(api["retry"])
            except (TypeError, ValueError):
                wait = int(os.getenv("RATE_LIMIT_WAIT", "300")) * (attempt + 1)
            if wait > int(os.getenv("MAX_WAIT", "900")):    # longer than 15 minutes: do not sit and wait
                until = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() + wait))
                raise Exception(f"Server blocked the signup with HTTP 429. It asks to wait {wait // 60} minutes "
                                f"(about {wait / 3600:.1f} hours). Try again after {until}.")
            print(f"Server says too many requests (429). Waiting {wait} seconds, keep the window open")
            if wait_with_countdown(page, otp_title, wait):
                return
        elif page.get_by_text("valid phone").count() == 0:
            break

    if api["seen_limit"]:
        raise Exception("Server blocked the signup with HTTP 429 (too many requests)")
    raise Exception("OTP page did not open")


def step_otp(page):
    expect(page.get_by_text("Email Verification code").first).to_be_visible()
    code = os.getenv("SIGNUP_OTP") or input("Enter the OTP from your email: ").strip()
    page.locator("input:visible").first.click()
    page.keyboard.type(code, delay=150)
    page.get_by_role("button", name=re.compile("verify", re.I)).click()
    expect(page.get_by_text("About your Agency").first).to_be_visible(timeout=30000)


def step_agency(page):
    g = data["agency"]
    fill(page, "Name", g["name"])
    fill(page, "Role in Agency", g["role"])
    fill(page, "Email Address", g["email"])
    fill(page, "Website", g["website"])
    fill(page, "Address", g["address"])
    choose(page, "Region of Operation", g["region"])
    page.keyboard.press("Escape")
    go_next(page, page.get_by_text("Experience and Performance Metrics").first)


def step_experience(page):
    e = data["experience"]
    choose(page, "Years of Experience", e["years"])
    fill(page, "Number of Students Recruited Annually", e["students_recruited_annually"])
    fill(page, "Focus Area", e["focus_area"])
    fill(page, "Success Metrics", e["success_metrics"])
    for service in e["services"]:
        page.get_by_role("checkbox", name=service).first.click()
    go_next(page, page.get_by_label(re.compile("business registration", re.I)).first)


def step_verification(page):
    v = data["verification"]
    page.get_by_label(re.compile("business registration", re.I)).fill(v["business_registration_number"])
    for country in v["preferred_countries"]:
        choose(page, "Preferred Countries", country)
    page.keyboard.press("Escape")
    page.get_by_role("button", name=re.compile("submit|finish|complete|save", re.I)).last.click()
    page.wait_for_timeout(4000)


STEPS = [
    ("Open register page and accept terms", step_terms),
    ("1. Set up account (with phone number)", step_account),
    ("Email OTP verification", step_otp),
    ("2. Agency details", step_agency),
    ("3. Professional experience", step_experience),
    ("4. Verification and preferences", step_verification),
]


# ---------- report ----------
def write_report(results, video_file):
    passed = [r for r in results if r["status"] == "PASS"]
    failed = [r for r in results if r["status"] == "FAIL"]
    lines = ["# Signup Automation - Test Report", ""]
    lines.append(f"Run at: {time.strftime('%Y-%m-%d %H:%M:%S')}  ")
    lines.append(f"Site: {URL}", )
    lines.append("")
    if not failed and len(passed) == len(STEPS):
        lines.append("**Result: PASS** - all 6 steps finished and the form was submitted.")
    elif failed:
        lines.append(f"**Result: FAIL** - {len(passed)} of {len(STEPS)} steps passed. "
                     f"Stopped at: {failed[0]['name']}.")
        lines.append(f"Reason: {failed[0]['note']}")
    lines.append("")
    lines.append("| # | Step | Result | Time (s) | Screenshot |")
    lines.append("|---|------|--------|----------|------------|")
    for i, r in enumerate(results, 1):
        lines.append(f"| {i} | {r['name']} | {r['status']} | {r['secs']:.1f} | {r['shot']} |")
    for name, _ in STEPS[len(results):]:
        lines.append(f"| - | {name} | NOT RUN | - | - |")
    lines.append("")
    if api["seen_limit"]:
        lines.append("Note: the site's server answered HTTP 429 (too many requests) to the signup request. "
                     "This is a server rate limit, not a problem in the form filling.")
        lines.append("")
    lines.append("## Test data used")
    lines.append(f"- Email: {data['account']['email']}")
    lines.append(f"- Phone: {phone_used or '(not reached)'}")
    lines.append(f"- Agency: {data['agency']['name']}")
    lines.append("")
    lines.append("## Files")
    lines.append("- Screenshots: `screenshots/`")
    lines.append(f"- Video: `{video_file or 'not recorded'}`")
    with open("test_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ---------- main ----------
os.makedirs("screenshots", exist_ok=True)
results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=HEADLESS, slow_mo=0 if HEADLESS else 300, channel=CHANNEL)
    context = browser.new_context(viewport={"width": 1300, "height": 850}, record_video_dir="videos")
    page = context.new_page()
    page.on("request", on_request)
    page.on("response", on_response)
    expect.set_options(timeout=20000)

    for number, (name, func) in enumerate(STEPS, 1):
        start = time.time()
        short = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:30]
        try:
            func(page)
            shot = f"screenshots/{number:02d}_{short}.png"
            page.screenshot(path=shot)
            results.append({"name": name, "status": "PASS", "secs": time.time() - start, "note": "", "shot": shot})
            print("PASS:", name)
        except Exception as error:
            shot = f"screenshots/{number:02d}_{short}_FAILED.png"
            try:
                page.screenshot(path=shot)
            except Exception:
                shot = "-"
            note = str(error).strip().splitlines()[0][:200] if str(error).strip() else type(error).__name__
            results.append({"name": name, "status": "FAIL", "secs": time.time() - start, "note": note, "shot": shot})
            print("FAIL:", name, "-", note)
            break

    video_path = page.video.path() if page.video else None
    context.close()          # the video file is finished only after this
    browser.close()

video_file = None
if video_path and os.path.exists(video_path):
    video_file = "videos/demo_video.webm"
    os.replace(video_path, video_file)

write_report(results, video_file)
print("Report saved: test_report.md")

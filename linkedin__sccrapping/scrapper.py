import time, random, os, json, re
import sys
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
from camoufox.sync_api import Camoufox
from proxy_manager import rotate_ip, get_current_ip, is_tor_running, PROXY_CONFIG

# Fix Windows console encoding for emojis
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


#              CONFIG

EMAIL       = "urmila.utkarsh123@gmail.com"
PASSWORD    = "Sahil@492004"
OUTPUT       = "esports_leads.csv"
COOKIES_F    = "linkedin_cookies.json"
# ── TIME BARRIER (currently OFF — scraper runs 24/7 including night) ──────────
# To re-enable a time window, uncomment the two lines below and set TEST_MODE = False
# START_HOUR   = 8    # Scraping allowed from this hour (8 = 8 AM)
# END_HOUR     = 23   # Scraping allowed until this hour (23 = 11 PM)
# ─────────────────────────────────────────────────────────────────────────────

# ── IP ROTATION ───────────────────────────────────────────────────────────────
# Tor proxy is ALWAYS ON — IP rotates after every keyword.
# Make sure Tor Browser is running before starting the scraper.
# See proxy_manager.py to adjust TOR_SOCKS_PORT / TOR_CONTROL_PORT.
# ─────────────────────────────────────────────────────────────────────────────

MAX_PER_DAY  = 70
MAX_PER_HOUR = 10
MIN_GAP_SEC  = 120

KEYWORDS = [
    "seeking sponsorship esports",
    "sponsorship acquisition esports",
    "looking for sponsorship gaming",
    "brand partnerships esports",
    "esports team owner sponsorship",
    "strategic partnerships esports",
    "gaming sponsor seeking",
    "sponsorship manager esports",
    "creator partnerships gaming",
    "head of partnerships esports",
    "esports investor partnership",
    "sports sponsorship esports",
    "business development esports",
    "VP sponsorship gaming",
    "global partnerships esports",
]

_hourly_count  = 0
_daily_count   = 0
_hour_reset_at = time.time()
_last_visit_at = None

# ── Daytime guard (currently DISABLED — uncomment body to re-enable) ──────────
# This function makes the scraper sleep outside START_HOUR–END_HOUR.
# To re-enable the time window:
#   1. Uncomment START_HOUR and END_HOUR in the CONFIG block above
#   2. Set TEST_MODE = False
#   3. Uncomment the while-loop body inside this function
def is_daytime():
    # return START_HOUR <= datetime.now().hour < END_HOUR
    return True  # Always "daytime" — time barrier is OFF

def wait_for_daytime():
    # ── To re-enable, uncomment the block below and set TEST_MODE = False ──
    # if not TEST_MODE:
    #     while not is_daytime():
    #         print(f"🌙 [{datetime.now().strftime('%H:%M')}] Sleeping 30 min...")
    #         time.sleep(1800)
    #     print(f"☀️  Resuming at {datetime.now().strftime('%H:%M')}")
    pass  # No time restriction — scraper runs 24/7

# Delays 
def short():  time.sleep(random.uniform(3, 6))
def medium(): time.sleep(random.uniform(10, 20))
def long():   time.sleep(random.uniform(30, 50))

def maybe_break():
    if random.random() < 0.08:
        mins = random.uniform(1, 3)
        print(f"☕ Break {mins:.1f} min...")
        time.sleep(mins * 60)

# Rate guard
def rate_guard():
    global _hourly_count, _daily_count, _hour_reset_at, _last_visit_at
    now = time.time()

    if now - _hour_reset_at >= 3600:
        _hourly_count = 0
        _hour_reset_at = now

    if _last_visit_at and (now - _last_visit_at) < MIN_GAP_SEC:
        wait = MIN_GAP_SEC - (now - _last_visit_at)
        print(f"  ⏳ Waiting {wait:.0f}s...")
        time.sleep(wait)

    if _hourly_count >= MAX_PER_HOUR:
        wait = 3600 - (now - _hour_reset_at)
        print(f"  ⏳ Hourly limit — waiting {wait:.0f}s...")
        time.sleep(wait)
        _hourly_count = 0
        _hour_reset_at = time.time()

    if _daily_count >= MAX_PER_DAY:
        print("🛑 Daily limit — resuming tomorrow at 9 AM...")
        wait_for_daytime()
        _daily_count = 0

    _last_visit_at = time.time()
    _hourly_count += 1
    _daily_count  += 1

#  Human behavior 
def human_scroll(page):
    for _ in range(random.randint(3, 6)):
        page.mouse.wheel(0, random.randint(200, 600))
        time.sleep(random.uniform(0.4, 1.2))

def human_move(page):
    page.mouse.move(
        random.randint(100, 900),
        random.randint(100, 600)
    )
    time.sleep(random.uniform(0.2, 0.6))

# Data
def load_existing():
    if os.path.exists(OUTPUT):
        df = pd.read_csv(OUTPUT)
        return set(df["Profile URL"].dropna().tolist())
    return set()

def save_batch(batch):
    if not batch: return
    df_new = pd.DataFrame(batch)
    if os.path.exists(OUTPUT):
        df_old = pd.read_csv(OUTPUT)
        df = pd.concat([df_old, df_new]).drop_duplicates(subset="Profile URL")
    else:
        df = df_new
    df.to_csv(OUTPUT, index=False)
    print(f"💾 Saved — Total: {len(df)} profiles")

# Cookies 
def save_cookies(context):
    with open(COOKIES_F, "w") as f:
        json.dump(context.cookies(), f)
    print("🍪 Cookies saved")

def load_cookies(context):
    if not os.path.exists(COOKIES_F):
        return False
    try:
        with open(COOKIES_F) as f:
            cookies = json.load(f)
        context.add_cookies(cookies)
        print("🍪 Cookies loaded")
        return True
    except:
        return False

# Block detection
def is_blocked(page):
    url     = page.url.lower()
    content = page.content().lower()
    return any(k in url for k in ["checkpoint", "challenge", "authwall"]) or \
           any(k in content for k in ["we're looking into it", "this one's our fault",
                                       "unusual activity", "verify you're human"])

def handle_block(page, context):
    print("🚨 Block detected — cooling down 15 min...")
    save_cookies(context)
    try:
        page.screenshot(path=f"blocked_{datetime.now().strftime('%H%M%S')}.png")
    except: pass
    time.sleep(900)
    page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
    time.sleep(random.uniform(30, 60))
    human_scroll(page)

# Login
def login(page):
    print("🔐 Logging in...")
    page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=60000)
    time.sleep(5)

    # Screenshot to see what loaded
    page.screenshot(path="login_check.png")

    # Try multiple selectors
    for selector in ["#username", "input[name='session_key']", "input[type='email']"]:
        try:
            page.wait_for_selector(selector, timeout=10000)
            page.type(selector, EMAIL, delay=random.randint(60, 140))
            break
        except:
            continue

    time.sleep(2)

    for selector in ["#password", "input[name='session_password']", "input[type='password']"]:
        try:
            page.wait_for_selector(selector, timeout=5000)
            page.type(selector, PASSWORD, delay=random.randint(60, 140))
            break
        except:
            continue

    time.sleep(2)
    page.keyboard.press("Enter")
    time.sleep(8)
    print("✅ Login attempted!")

# Warmup
def warmup(page):
    print("🔥 Warming up...")
    # Wait for proper login first
    time.sleep(3)
    if "feed" not in page.url and "linkedin.com" not in page.url:
        return
    urls = [
        "https://www.linkedin.com/mynetwork/",
        "https://www.linkedin.com/notifications/",
    ]
    for url in random.sample(urls, 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            medium()
        except:
            pass
    print("✅ Warmup done!")

# Scrape page
def scrape_page(page, existing_urls, keyword):
    time.sleep(random.uniform(3, 6))
    soup    = BeautifulSoup(page.content(), "html.parser")
    results = []

    # Debug: Check if we're on search results page
    profile_links_count = len(soup.find_all("a", {"data-test-app-aware-link": ""}, href=re.compile(r"/in/")))
    print(f"     Debug: Found {profile_links_count} potential profile links in HTML")

    # Find all profile links - LinkedIn uses data-test-app-aware-link with /in/ in href
    # Filter to only links that contain a name (have aria-hidden="true" span with text inside)
    all_links = soup.find_all("a", {"data-test-app-aware-link": ""}, href=re.compile(r"/in/"))
    profile_links = []
    for link in all_links:
        name_span = link.find("span", {"aria-hidden": "true"})
        if name_span and name_span.get_text(strip=True):
            profile_links.append(link)

    print(f"     Debug: Found {len(profile_links)} links with actual names")

    seen = set()
    for idx, link in enumerate(profile_links):
        try:
            url = link["href"].split("?")[0]
            if not url or url in seen: continue
            seen.add(url)

            full_url = f"https://www.linkedin.com{url}" if url.startswith("/") else url
            if full_url in existing_urls: continue

            # ── Name: Find span with aria-hidden="true" inside the link ──
            name_span = link.find("span", {"aria-hidden": "true"})
            name = name_span.get_text(strip=True) if name_span else "N/A"

            if not name or name in ["N/A", ""]:
                continue

            # ── Bio & Location: Find the card container and extract text ──
            # LinkedIn cards have the structure: link -> parent card -> other spans with info
            bio      = "N/A"
            location = "N/A"

            # Find the card container - look for the main card div
            card = link.find_parent("div", {"data-view-name": "search-entity-result-universal-template"})
            if not card:
                card = link.find_parent(["li", "div"], {"role": "listitem"})
            if not card:
                card = link.find_parent("div", class_=re.compile("entity-result|search-result"))

            if card:
                # Bio is usually in a div with t-14 class (subtitle/occupation)
                bio_el = card.find("div", class_=re.compile(r"t-14.*t-normal"))
                if bio_el:
                    bio_text = bio_el.get_text(separator=" ", strip=True)
                    if bio_text and bio_text != name:
                        bio = bio_text

                # Location is often in a separate div or span with location-related classes
                loc_el = card.find("div", class_=re.compile(r"t-14.*t-normal.*black--light"))
                if not loc_el:
                    # Try finding text that looks like a location (city, country patterns)
                    all_text = card.get_text(separator=" ", strip=True)
                    # Simple heuristic: if bio contains comma or location words, split it
                    if bio != "N/A" and ("," in bio or "region" in bio.lower()):
                        parts = bio.split(",")
                        if len(parts) > 1:
                            bio = parts[0].strip()
                            location = ",".join(parts[1:]).strip()

            existing_urls.add(full_url)
            results.append({
                "Name": name, "Bio": bio, "Location": location,
                "Profile URL": full_url, "Keyword": keyword,
                "Scraped On": datetime.now().strftime("%Y-%m-%d")
            })
            print(f"     [{idx}] SUCCESS: {name} - {bio[:30] if bio != 'N/A' else 'N/A'}")

        except Exception as e:
            print(f"    Error scraping profile: {e}")
            continue

    print(f"  🃏 {len(results)} profiles found")
    if results:
        print(f"     Sample: {results[0]['Name']} - {results[0]['Profile URL']}")
    return results

def go_next(page):
    try:
        btn = page.locator("button[aria-label='Next']")
        if btn.is_visible():
            human_move(page)
            btn.click()
            medium()
            return True
    except: pass
    return False


#                MAIN

def main():
    existing_urls = load_existing()
    print(f"📂 Already have {len(existing_urls)} profiles\n")

    # ── Tor check 
    print("🔌 Checking Tor connection...")
    if not is_tor_running():
        print("❌ Tor is NOT running! Please open Tor Browser and try again.")
        print("   (Tor Browser → Connect → leave it open in the background)")
        sys.exit(1)
    current_ip = get_current_ip()
    print(f"✅ Tor is running. Starting IP: {current_ip}\n")


    buffer = []
    keywords = KEYWORDS.copy()
    random.shuffle(keywords)

    # Camoufox launch — always through Tor
    with Camoufox(
        headless=False,       # visible browser
        humanize=True,        # built-in human mouse movements
        os="windows",         # spoof Windows OS
        persistent_context=True,
        user_data_dir="./camoufox_profile",
        geoip=True,           # auto timezone/locale from IP
        proxy=PROXY_CONFIG,   # always Tor — IP rotates per keyword
        timeout=60000
    ) as browser:

        context = browser
        page    = browser.new_page()

        # Login or load cookies
        cookies_loaded = load_cookies(context)
        if cookies_loaded:
            page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
            medium()
            # Check if we're actually logged in (redirected to login means cookies are stale)
            if "login" in page.url.lower():
                print("  Cookies expired - re-logging in...")
                cookies_loaded = False

        if not cookies_loaded:
            login(page)
            save_cookies(context)
            warmup(page)
        # After page loads, save HTML to check
        
        for keyword in keywords:
            print(f"\n🔍 {keyword}")
            url = f"https://www.linkedin.com/search/results/people/?keywords={keyword.replace(' ', '%20')}"
            page.goto(url, wait_until="domcontentloaded")
            medium()
            with open("debug.html", "w", encoding="utf-8") as f:
                f.write(page.content())
            if is_blocked(page):
                handle_block(page, context)
                if is_blocked(page):
                    print("  ❌ Still blocked — skipping keyword")
                    continue

            for pg in range(1, 11):
                # wait_for_daytime()  # ← Uncomment to pause between pages if outside allowed hours
                rate_guard()

                print(f"  📄 Page {pg} [{datetime.now().strftime('%H:%M')}] | Today: {_daily_count}/{MAX_PER_DAY}")
                found = scrape_page(page, existing_urls, keyword)
                buffer.extend(found)
                print(f"  ✅ {len(found)} new profiles")

                if len(buffer) >= 10:
                    save_batch(buffer)
                    buffer = []

                maybe_break()

                if not go_next(page):
                    print("  ⚠️ No more pages")
                    break

            # Natural break + IP rotation between keywords 
            page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
            medium()
            human_scroll(page)
            long()
            rotate_ip(wait=8)  # Get a fresh Tor exit node for the next keyword

        save_batch(buffer)

    print(f"\n🎉 Done! Check {OUTPUT}")

if __name__ == "__main__":
    main()
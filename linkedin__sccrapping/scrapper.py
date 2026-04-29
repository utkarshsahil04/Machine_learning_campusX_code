# -*- coding: utf-8 -*-
import time, random, os, json, re
import sys
import pandas as pd
from datetime import datetime
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from camoufox.sync_api import Camoufox
from proxy_manager import rotate_ip, get_current_ip, is_tor_running, PROXY_CONFIG

# Fix Windows console encoding for emojis
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

#              CONFIG

EMAIL       = "your_email"
PASSWORD    = "passwo"
OUTPUT       = "esports_leads.csv"
COOKIES_F    = "linkedin_cookies.json"
# -- TIME BARRIER (currently OFF -- scraper runs 24/7 including night) ------------
# To re-enable a time window, uncomment the two lines below and set TEST_MODE = False
# START_HOUR   = 8    # Scraping allowed from this hour (8 = 8 AM)
# END_HOUR     = 23   # Scraping allowed until this hour (23 = 11 PM)
# ---------------------------------------------------------------------------------

# -- IP ROTATION ------------------------------------------------------------------
# Tor proxy is ALWAYS ON -- IP rotates after every keyword.
# Make sure Tor Browser is running before starting the scraper.
# ---------------------------------------------------------------------------------

MAX_PER_DAY  = 200
MAX_PER_HOUR = 50
MIN_GAP_SEC  = 5    # seconds between page visits (was 10 -- halved for speed)

KEYWORDS = [
    # Esports teams & orgs seeking sponsors
    "esports team seeking sponsorship",
    "esports org seeking sponsor",
    "gaming team looking for sponsor",
    "esports team sponsorship deal",
    "indie esports team sponsorship",
    "semi-pro esports sponsorship",
    "esports team owner sponsorship",
    "esports founder sponsorship",

    # Players & athletes
    "esports player seeking sponsorship",
    "esports athlete sponsorship",
    "competitive gamer looking for sponsor",
    "pro gamer sponsorship",
    "esports player brand deal",

    # Content creators & streamers
    "streamer looking for sponsor",
    "streamer seeking brand deal",
    "gaming streamer sponsorship",
    "gaming YouTuber sponsorship",
    "gaming influencer sponsorship",
    "gaming content creator sponsorship",
    "gaming content creator brand deal",

    # Coaches & organizers
    "esports coach sponsorship",
    "tournament organizer sponsorship",
    "LAN event sponsorship seeking",
    "gaming event sponsorship",

    # Business roles in esports
    "sponsorship acquisition esports",
    "partnership development esports",
    "business development gaming",
    "revenue partnerships esports",
    "esports sponsorship manager",
    "head of partnerships esports",
    "VP sponsorship gaming",
    "global partnerships esports",
    "strategic partnerships esports",

    # Brand ambassador roles
    "gaming brand ambassador",
    "esports brand ambassador",

    # Specific verticals
    "mobile gaming sponsorship",
    "gaming podcast sponsorship",
    "gaming community sponsorship",
]

_hourly_count        = 0
_daily_count         = 0
_session_leads_count = 0  # Tracks actual profiles found
_hour_reset_at       = time.time()
_last_visit_at       = None

# -- Daytime guard (currently DISABLED) -------------------------------------------
def is_daytime():
    return True  # Always "daytime" -- time barrier is OFF

def wait_for_daytime():
    pass  # No time restriction -- scraper runs 24/7


# Countdown Sleep Utility -- skips countdown display for very short waits
def countdown_sleep(seconds, reason="Waiting"):
    seconds = int(seconds)
    if seconds <= 3:
        time.sleep(seconds)
        return
    for i in range(seconds, 0, -1):
        sys.stdout.write(f"\r  ⏳ {reason}: {i}s remaining...   ")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write(f"\r  ✅ {reason} complete!              \n")
    sys.stdout.flush()


# Delays -- reduced from original for faster scraping
def short():  time.sleep(random.uniform(0.8, 1.5))   # was 1-2s
def medium(): time.sleep(random.uniform(1.5, 2.5))   # was 2-3s
def long():   time.sleep(random.uniform(2.5, 4.0))   # was 3-5s

def maybe_break():
    if random.random() < 0.01:   # 1% chance (was 2%)
        countdown_sleep(random.uniform(10, 20), "Coffee break")


# Rate guard
def rate_guard():
    global _hourly_count, _daily_count, _hour_reset_at, _last_visit_at
    now = time.time()

    if now - _hour_reset_at >= 3600:
        _hourly_count = 0
        _hour_reset_at = now

    if _last_visit_at and (now - _last_visit_at) < MIN_GAP_SEC:
        wait = MIN_GAP_SEC - (now - _last_visit_at)
        countdown_sleep(int(wait), "Wait gap")

    if _hourly_count >= MAX_PER_HOUR:
        wait = 3600 - (now - _hour_reset_at)
        countdown_sleep(int(wait), "Hourly PAGE limit reached")
        _hourly_count = 0
        _hour_reset_at = time.time()

    if _daily_count >= MAX_PER_DAY:
        print(f"🛑 Daily PAGE limit ({MAX_PER_DAY}) reached!")
        countdown_sleep(3600, "Daily cooldown")
        _daily_count = 0

    _last_visit_at = time.time()
    _hourly_count += 1
    _daily_count  += 1


# Human behavior
def human_scroll(page):
    try:
        for _ in range(random.randint(2, 3)):
            page.mouse.wheel(0, random.randint(200, 400))
            time.sleep(random.uniform(0.2, 0.5))
    except Exception:
        pass  # browser may have closed -- skip silently

def human_move(page):
    try:
        page.mouse.move(
            random.randint(100, 900),
            random.randint(100, 600)
        )
        time.sleep(random.uniform(0.1, 0.2))
    except Exception:
        pass  # browser may have closed -- skip silently


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
    print(f"💾 Saved -- Total: {len(df)} profiles")


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
    except Exception:
        return False


# Block detection
def is_blocked(page):
    url     = page.url.lower()
    content = page.content().lower()
    return any(k in url for k in ["checkpoint", "challenge", "authwall"]) or \
           any(k in content for k in ["we're looking into it", "this one's our fault",
                                       "unusual activity", "verify you're human"])

def handle_block(page, context):
    print("🚨 Block detected!")
    save_cookies(context)
    try:
        page.screenshot(path=f"blocked_{datetime.now().strftime('%H%M%S')}.png")
    except Exception:
        pass
    countdown_sleep(600, "Cooling down")   # was 900s -- reduced to 10 min
    page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
    countdown_sleep(random.randint(20, 40), "Returning to feed")  # was 30-60s
    human_scroll(page)


# Login
def login(page):
    print("🔐 Logging in...")
    page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=60000)
    time.sleep(4)  # was 5s

    page.screenshot(path="login_check.png")

    for selector in ["#username", "input[name='session_key']", "input[type='email']"]:
        try:
            page.wait_for_selector(selector, timeout=8000)
            page.type(selector, EMAIL, delay=random.randint(60, 130))
            break
        except Exception:
            continue

    time.sleep(1.5)  # was 2s

    for selector in ["#password", "input[name='session_password']", "input[type='password']"]:
        try:
            page.wait_for_selector(selector, timeout=5000)
            page.type(selector, PASSWORD, delay=random.randint(60, 130))
            break
        except Exception:
            continue

    time.sleep(1.5)  # was 2s
    page.keyboard.press("Enter")
    time.sleep(6)    # was 8s
    print("✅ Login attempted!")


# Warmup
def warmup(page):
    print("🔥 Warming up...")
    time.sleep(2)
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
        except Exception:
            pass
    print("✅ Warmup done!")


# Scrape page
def scrape_page(page, existing_urls, keyword):
    time.sleep(random.uniform(1.5, 3.0))   # was 3-6s -- halved
    soup    = BeautifulSoup(page.content(), "html.parser")
    results = []

    profile_links_count = len(soup.find_all("a", {"data-test-app-aware-link": ""}, href=re.compile(r"/in/")))
    print(f"     Debug: Found {profile_links_count} potential profile links in HTML")

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

            name_span = link.find("span", {"aria-hidden": "true"})
            name = name_span.get_text(strip=True) if name_span else "N/A"

            if not name or name in ["N/A", ""]:
                continue

            bio      = "N/A"
            location = "N/A"

            card = link.find_parent("div", {"data-view-name": "search-entity-result-universal-template"})
            if not card:
                card = link.find_parent(["li", "div"], {"role": "listitem"})
            if not card:
                card = link.find_parent("div", class_=re.compile("entity-result|search-result"))

            if card:
                bio_el = card.find("div", class_=re.compile(r"t-14.*t-normal"))
                if bio_el:
                    bio_text = bio_el.get_text(separator=" ", strip=True)
                    if bio_text and bio_text != name:
                        bio = bio_text

                loc_el = card.find("div", class_=re.compile(r"t-14.*t-normal.*black--light"))
                if not loc_el:
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
    """Click the Next pagination button and wait for navigation.
    KEY FIX: wraps click inside expect_navigation() so Playwright handles
    the page-transition atomically -- previously the click succeeded but
    the mid-navigation state caused an exception that returned False.
    """
    url_before = page.url
    try:
        btn = page.locator("button[aria-label='Next']")
        if not btn.is_visible(timeout=3000):
            print(f"    [{datetime.now().strftime('%H:%M:%S')}] go_next: no Next button visible")
            return False

        print(f"    [{datetime.now().strftime('%H:%M:%S')}] go_next: clicking Next...")
        human_move(page)
        # expect_navigation() tells Playwright to EXPECT a page change after the click
        # This prevents the "navigation interrupted click" exception
        with page.expect_navigation(wait_until="domcontentloaded", timeout=20000):
            btn.click(timeout=5000)

        time.sleep(random.uniform(2, 4))

        # Confirm we actually moved to a new page
        if page.url != url_before:
            print(f"    [{datetime.now().strftime('%H:%M:%S')}] go_next: navigated OK")
            return True
        else:
            print(f"    [{datetime.now().strftime('%H:%M:%S')}] go_next: URL unchanged after click")
            return False

    except Exception as e:
        err = e.__class__.__name__
        print(f"    [{datetime.now().strftime('%H:%M:%S')}] go_next error ({err}): {e}")
        # If the URL changed despite the error the navigation still happened
        if page.url != url_before:
            print(f"    [{datetime.now().strftime('%H:%M:%S')}] go_next: URL changed -- treating as success")
            time.sleep(random.uniform(2, 3))
            return True
        return False
    return False


#                MAIN

def main():
    global _session_leads_count
    existing_urls = load_existing()
    print(f"📂 Already have {len(existing_urls)} profiles\n")

    # -- Tor check
    print("🔌 Checking Tor connection...")
    if not is_tor_running():
        print("❌ Tor is NOT running! Please open Tor Browser and try again.")
        print("   (Tor Browser → Connect → leave it open in the background)")
        sys.exit(1)
    current_ip = get_current_ip()
    print(f"✅ Tor is running. Starting IP: {current_ip}\n")

    buffer   = []
    keywords = KEYWORDS.copy()
    random.shuffle(keywords)

    # Camoufox launch -- always through Tor
    with Camoufox(
        headless=False,
        humanize=True,
        os="windows",
        persistent_context=True,
        user_data_dir="./camoufox_profile",
        geoip=True,
        proxy=PROXY_CONFIG,
        timeout=60000
    ) as browser:

        context = browser
        page    = browser.new_page()

        # Login or load cookies
        cookies_loaded = load_cookies(context)
        if not cookies_loaded:
            login(page)
        warmup(page)

        for keyword in keywords:
            print(f"\n🔍 {keyword}")
            t = datetime.now().strftime('%H:%M:%S')
            print(f"  [{t}] ▶ Loading search page...")

            # Use quote_plus for proper URL encoding
            url = f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(keyword)}"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print(f"  ⚠️ Page load failed ({e.__class__.__name__}) -- skipping keyword")
                continue

            print(f"  [{datetime.now().strftime('%H:%M:%S')}] ▶ page.goto done")
            medium()

            # Write debug snapshot once per keyword (not twice)
            with open("debug.html", "w", encoding="utf-8") as f:
                f.write(page.content())

            if is_blocked(page):
                handle_block(page, context)
                if is_blocked(page):
                    print("  ❌ Still blocked -- skipping keyword")
                    continue

            for pg in range(1, 11):
                rate_guard()
                print(f"  📄 Page {pg} [{datetime.now().strftime('%H:%M')}] | Pages Today: {_daily_count}/{MAX_PER_DAY} | Leads Session: {_session_leads_count}")

                found = scrape_page(page, existing_urls, keyword)
                _session_leads_count += len(found)
                buffer.extend(found)

                print(f"  ✅ {len(found)} new profiles")

                if len(buffer) >= 10:
                    save_batch(buffer)
                    buffer = []

                maybe_break()

                if not go_next(page):
                    print("  ⚠️ No more pages")
                    countdown_sleep(10, "Moving to next keyword")
                    break

            # Brief break + IP rotation between keywords
            try:
                page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=10000)
                human_scroll(page)
            except Exception:
                pass

            rotate_ip(wait=5)
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] ▶ keyword done -- moving to next")

        save_batch(buffer)

    print(f"\n🎉 Done! Check {OUTPUT}")


if __name__ == "__main__":
    main()
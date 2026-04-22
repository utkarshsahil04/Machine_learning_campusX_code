# 🔍 LinkedIn Esports Lead Scraper

A stealth LinkedIn people scraper built with **Camoufox** (anti-detect browser), **BeautifulSoup**, and **Tor-based IP rotation** via `stem`. Designed to find esports professionals looking for sponsorships and brand partnerships — safely and anonymously.

---

## 📁 Project Files

| File | Description |
|---|---|
| `scrapper.py` | Main scraper script |
| `proxy_manager.py` | Tor IP rotation module (`stem` + SOCKS5) |
| `esports_leads.csv` | Output file with scraped profiles |
| `linkedin_cookies.json` | Saved login cookies for session reuse |
| `requirements.txt` | Python dependencies |

---

## ⚙️ Features

- 🧠 **Anti-Detection** — Camoufox with humanized mouse, OS spoofing, and GeoIP auto-locale
- 🌍 **Automatic IP Rotation** — New Tor exit node (fresh IP) after every search keyword
- 🔌 **Tor Startup Check** — Scraper exits immediately if Tor is not running
- 🍪 **Cookie Persistence** — Saves and reloads login session to avoid repeated logins
- 🚦 **Rate Limiting** — Hourly/daily caps with minimum gaps between requests
- 🔄 **Pagination** — Scrapes up to 10 pages per keyword
- 💾 **Incremental Saves** — Appends every 10 profiles; skips already-scraped URLs
- 🚨 **Block Detection** — Detects LinkedIn checkpoints and auto-cools down 15 minutes
- ☕ **Random Breaks** — Occasional random pauses to mimic human browsing
- ⏰ **No Time Restrictions** — Runs 24/7 including nights (time window can be re-enabled, see below)

---

## 🛠️ Installation

```bash
# 1. Clone or download the project
cd linkedin__sccrapping

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt
```

---

## 🌍 IP Rotation Setup (Required)

The scraper **always routes through Tor** and rotates to a fresh IP after every keyword. This protects your LinkedIn account from looking like a bot from a single IP.

### Step 1 — Install Tor Browser
Download from [https://www.torproject.org/](https://www.torproject.org/)

### Step 2 — Open Tor Browser and Connect
- Click **Connect**
- Leave the Tor Browser window **open in the background** (do not close it)
- It must be running before you start the scraper

### Step 3 — Run the scraper
```bash
python scrapper.py
```

On startup you'll see:
```
🔌 Checking Tor connection...
✅ Tor is running. Starting IP: 185.220.xx.xx
```

And after each keyword:
```
🔄 Tor circuit rotated — waiting 8s for new route...
🌍 New IP: 91.108.xx.xx
```

> **If you see:** `❌ Tor is NOT running!` — make sure Tor Browser is open and connected before running.

### Tor Port Reference

| Setting | Tor Browser (default) | Standalone Tor daemon |
|---|---|---|
| SOCKS5 proxy | `9150` | `9050` |
| Control port | `9151` | `9051` |

You can change these in `proxy_manager.py`:
```python
TOR_SOCKS_PORT   = 9150   # change if using standalone Tor
TOR_CONTROL_PORT = 9151
```

---

## 🔧 Configuration

Edit the **CONFIG** block at the top of `scrapper.py`:

```python
EMAIL        = "your_email@example.com"
PASSWORD     = "your_password"
OUTPUT       = "esports_leads.csv"      # Output CSV file
COOKIES_F    = "linkedin_cookies.json"  # Cookie file

MAX_PER_DAY  = 70     # Max profiles scraped per day
MAX_PER_HOUR = 10     # Max profiles scraped per hour
MIN_GAP_SEC  = 120    # Min seconds between page visits
```

> ⚠️ **Never commit your credentials to a public repository.**  
> Consider using a `.env` file and `python-dotenv` to manage secrets safely.

### ⏰ Re-enabling the Time Window (optional)

By default the scraper runs 24/7. To restrict it to business hours only:

1. In the CONFIG block, uncomment:
   ```python
   START_HOUR = 8    # allowed from 8 AM
   END_HOUR   = 23   # allowed until 11 PM
   ```
2. In `wait_for_daytime()`, uncomment the `while not is_daytime()` block
3. In `main()`, uncomment the two `wait_for_daytime()` call lines

---

## ▶️ Usage

```bash
python scrapper.py
```

The scraper will:
1. Check that Tor Browser is running and show the current IP
2. Load existing cookies (or log in fresh and save cookies)
3. Warm up by visiting your network/notifications page
4. Iterate through all keywords (randomized order)
5. Scrape up to 10 pages of people results per keyword
6. **Rotate to a new Tor IP** after finishing each keyword
7. Save results incrementally to `esports_leads.csv`

---

## 📊 Output Format (`esports_leads.csv`)

| Column | Description |
|---|---|
| `Name` | Full name of the LinkedIn profile |
| `Bio` | Headline / occupation |
| `Location` | City or region |
| `Profile URL` | Direct LinkedIn profile link |
| `Keyword` | Search keyword that found this profile |
| `Scraped On` | Date of scraping |

---

## 🔎 Default Keywords

```
seeking sponsorship esports, sponsorship acquisition esports,
looking for sponsorship gaming, brand partnerships esports,
esports team owner sponsorship, head of partnerships esports,
business development esports, VP sponsorship gaming ...
```

Customize the `KEYWORDS` list inside `scrapper.py`.

---

## 🤝 Dependencies

| Package | Purpose |
|---|---|
| `camoufox` | Anti-detect Playwright-based browser |
| `beautifulsoup4` | HTML parsing |
| `pandas` | CSV data management |
| `stem` | Tor control — sends NEWNYM signal to rotate IP |
| `requests` | Verify current IP through Tor |

---

## ⚠️ Disclaimer

This tool is intended for **educational and research purposes only**.  
Scraping LinkedIn may violate their [Terms of Service](https://www.linkedin.com/legal/user-agreement).  
Use responsibly and at your own risk.

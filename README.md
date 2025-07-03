# SMART URL CRAWLER

A robust, crash-resilient crawler that:

- Discovers every **internal** link exactly once  
- Records every **external** link’s HTTP status only  
- Supports modes: `desktop`, `mobile`, `bot` (`--mode`)  
- Persists in MySQL:
  - **urls** (URL, category, status, last attempt)  
  - **crawl_runs** (mode, start/end timestamps)  
  - **snapshots**
    - **internal**: full HTML + SHA-256 hash + TTFB, DOMContentLoaded, LoadEventEnd  
    - **external**: HTTP status or error only  
  - **links**: directed edges (source → target) per snapshot  
- Transactional frontier: `pending` → `in_progress` → `done`/`error`  
- Configurable concurrency (`--concurrency`) & SPA-friendly wait logic  

---

## Table of Contents

1. [Prerequisites](#prerequisites)  
2. [Installation](#installation)  
3. [Configuration](#configuration)  
4. [Database Setup](#database-setup)  
   - [Option A: ORM (`db_manager.py`)](#option-a-orm-db_managerpy)  
   - [Option B: Raw DDL (`schema.sql`)](#option-b-raw-ddl-schemasql)  
5. [Usage](#usage)  
6. [Inspecting Data](#inspecting-data)  
7. [Schema Overview](#schema-overview)  
8. [Troubleshooting](#troubleshooting)  
9. [Extensions & Tuning](#extensions--tuning)  
10. [License](#license)  

---

## Prerequisites

- Python 3.9+  
- MySQL 5.7+ (or compatible)  
- Playwright for Python  

Install dependencies:

```bash
pip install -r requirements.txt
playwright install
```

---

## Installation

```bash
git clone https://your.repo/smart-url-crawler.git
cd smart-url-crawler
pip install -r requirements.txt
playwright install
cp .env.example .env
```

---

## Configuration

Copy `.env.example` → `.env` and edit:

```dotenv
# DATABASE_URL or individual settings:

# DATABASE_URL=mysql+asyncmy://user:pass@host:3306/url_crawler

DB_USER=root
DB_PASSWORD=secret
DB_HOST=localhost
DB_PORT=3306
DB_NAME=url_crawler
```

---

## Database Setup

### Option A: ORM (db_manager.py)

```bash
python db_manager.py drop
python db_manager.py init
```

### Option B: Raw DDL (schema.sql)

```bash
mysql -u $DB_USER -p $DB_NAME < schema.sql
```

---

## Usage

Run the crawler:

```bash
python crawler.py crawl <start_url> --mode desktop --concurrency 5
```

- `<start_url>`: e.g. `https://example.com`  
- `--mode`: `desktop`, `mobile`, or `bot` (default `desktop`)  
- `--concurrency`: number of parallel workers (default 5)  

Example:

```bash
python crawler.py crawl https://example.com --mode mobile --concurrency 10
```

---

## Inspecting Data

```sql
-- URL statuses
SELECT status, COUNT(*) FROM urls GROUP BY status;

-- Recent crawl runs
SELECT id, mode, start_time, end_time FROM crawl_runs ORDER BY id DESC LIMIT 5;

-- Internal snapshots + metrics
SELECT u.url, s.status_code, s.ttfb_ms, s.dom_content_loaded_ms,
       s.load_event_end_ms, s.timestamp
FROM snapshots s JOIN urls u ON u.id = s.url_id
WHERE u.category = 'internal'
ORDER BY s.timestamp DESC LIMIT 10;

-- External statuses/errors
SELECT u.url, s.status_code, s.error_message, s.timestamp
FROM snapshots s JOIN urls u ON u.id = s.url_id
WHERE u.category = 'external'
ORDER BY s.timestamp DESC LIMIT 10;

-- Link graph: outgoing edges
SELECT u1.url AS source, u2.url AS target
FROM links l
JOIN urls u1 ON l.source_id = u1.id
JOIN urls u2 ON l.target_id = u2.id
ORDER BY u1.url;
```

---

## Schema Overview

See `schema.sql` for exact DDL. Key tables:

- **urls**  
- **crawl_runs**  
- **snapshots**  
- **links**  

---

## Troubleshooting

- **MissingGreenlet**: Ensure all async DB calls run inside `asyncio.run()`  
- **DB errors**: Check `.env` for correct values  
- **Playwright timeouts**: Increase or add retries  

---

## Extensions & Tuning

- Asset blocking  
- Retry logic  
- Change detection  
- Visualization  
- Docker  

---

## License

MIT

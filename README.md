# SMART URL CRAWLER is a Playwright Link Crawler with MySQL, PageSpeed Metrics & Link Graph

A robust, crash-resilient crawler that:

- ðŸ” **Discovers** every **internal** link exactly once  
- ðŸš« **Records** every **external** linkâ€™s HTTP status only  
- ðŸŒ Supports **modes**: `desktop`, `mobile`, `bot` (`--mode`)  
- ðŸ—„ï¸ Persists in MySQL:
  - **urls** (URL, category, status, last attempt)  
  - **crawl_runs** (mode, start/end timestamps)  
  - **snapshots**  
    - **internal**: full HTML + SHA-256 hash + TTFB, DOMContentLoaded, LoadEventEnd  
    - **external**: HTTP status or error only  
  - **links**: directed edges (source â†’ target) per snapshot  
- ðŸ”„ Transactional frontier: `pending` â†’ `in_progress` â†’ `done`/`error`  
- âš™ï¸ Configurable **concurrency** (`--concurrency`) & SPA-friendly wait logic  

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

- **Python** 3.9+  
- **MySQL** 5.7+ (or compatible)  
- **Playwright** for Python  

Install dependencies:

\`\`\`bash
pip install -r requirements.txt
playwright install
\`\`\`

---

## Installation

\`\`\`bash
git clone https://your.repo/url-crawler.git
cd url-crawler
pip install -r requirements.txt
playwright install
cp .env.example .env
\`\`\`

---

## Configuration

Copy \`.env.example\` â†’ \`.env\` and fill in:

\`\`\`dotenv
# Either a full URL:
# DATABASE_URL=mysql+asyncmy://user:pass@host:3306/url_crawler

# Or individual:
DB_USER=root
DB_PASSWORD=secret
DB_HOST=localhost
DB_PORT=3306
DB_NAME=url_crawler
\`\`\`

---

## Database Setup

### Option A: ORM (\`db_manager.py\`)

\`\`\`bash
python db_manager.py drop   # âš ï¸ wipes all data
python db_manager.py init   # creates tables via SQLAlchemy models
\`\`\`

### Option B: Raw DDL (\`schema.sql\`)

\`\`\`bash
mysql -u $DB_USER -p $DB_NAME < schema.sql
\`\`\`

---

## Usage

Run the crawler:

\`\`\`bash
python crawler.py crawl <start_url> \
  --mode <desktop|mobile|bot> \
  --concurrency <N>
\`\`\`

- \`<start_url>\`: e.g. \`https://example.com\`  
- \`--mode\`: user-agent mode (default \`desktop\`)  
- \`--concurrency\`: number of parallel workers (default 5)  

**Example**:

\`\`\`bash
python crawler.py crawl https://example.com --mode mobile --concurrency 10
\`\`\`

**Sample Output**:

\`\`\`
ðŸš€ Starting crawl run 1 (mode=mobile) at 2025-07-02T12:00:00Z
[Worker 0] Crawling: https://example.com (internal)
[Worker 0] Detected 12 outgoing links
[Worker 0] Saving snapshot for: https://example.com (status 200)
[Worker 1] Crawling: https://external.com/page (external)
[Worker 1] External URL status: 404
...
ðŸ Finished crawl run 1 at 2025-07-02T12:01:30Z
\`\`\`

---

## Inspecting Data

Connect with your MySQL client and run:

\`\`\`sql
-- 1. URL statuses
SELECT status, COUNT(*) FROM urls GROUP BY status;

-- 2. Recent crawl runs
SELECT id, mode, start_time, end_time
FROM crawl_runs
ORDER BY id DESC
LIMIT 5;

-- 3. Internal snapshots + metrics
SELECT u.url,
       s.status_code,
       s.ttfb_ms,
       s.dom_content_loaded_ms,
       s.load_event_end_ms,
       s.timestamp
FROM snapshots s
JOIN urls u ON u.id = s.url_id
WHERE u.category = 'internal'
ORDER BY s.timestamp DESC
LIMIT 10;

-- 4. External statuses/errors
SELECT u.url,
       s.status_code,
       s.error_message,
       s.timestamp
FROM snapshots s
JOIN urls u ON u.id = s.url_id
WHERE u.category = 'external'
ORDER BY s.timestamp DESC
LIMIT 10;

-- 5. Link graph: outgoing edges
SELECT u1.url AS source,
       u2.url AS target
FROM links l
JOIN urls u1 ON l.source_id = u1.id
JOIN urls u2 ON l.target_id = u2.id
ORDER BY u1.url;
\`\`\`

---

## Schema Overview

See [schema.sql](schema.sql) for exact DDL. Key tables:

- **urls**: URL records & statuses  
- **crawl_runs**: run metadata  
- **snapshots**: full internals or externals-only  
- **links**: directed edges per snapshot  

---

## Troubleshooting

- **MissingGreenlet**: Ensure all AsyncSession calls are inside async functions driven by asyncio.run().  
- **DB connection errors**: Verify `.env` variables.  
- **Playwright issues**: Increase timeouts or add retries.  

---

## Extensions & Tuning

- **Asset blocking**: Intercept images/fonts.  
- **Retry logic**: Requeue errors with backoff.  
- **Change detection**: Diff content_hash.  
- **Visualization**: Use NetworkX or D3.js for link graph.  
- **Docker**: Containerize for CI/CD.  

---

## License

MIT


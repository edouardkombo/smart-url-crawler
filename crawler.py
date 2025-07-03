#!/usr/bin/env python3
"""
Playwright-based crawler: full snapshots for internal URLs
and HTTP status-only for external URLs, plus link graph.

Usage:
    python crawler.py crawl <start_url> [--mode desktop] [--concurrency N]
"""
import os
import sys
import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import urlparse

from dotenv import load_dotenv
load_dotenv()

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

from db_manager import URL, Snapshot, CrawlRun, Link, Base

USER_AGENTS = {
    'desktop': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'mobile':  'Mozilla/5.0 (iPhone; CPU iPhone OS 13_5 like Mac OS X)',
    'bot':     'Googlebot/2.1 (+http://www.google.com/bot.html)'
}

async def wait_for_full_load(page, timeout=15000):
    try:    await page.wait_for_load_state('load', timeout=timeout)
    except PWTimeout: pass
    try:    await page.wait_for_load_state('networkidle', timeout=timeout)
    except PWTimeout: pass
    await page.wait_for_timeout(250)

async def crawl(start_url, mode, concurrency, Session):
    # Create a crawl run record
    async with Session() as session:
        run = CrawlRun(mode=mode, start_time=datetime.now(timezone.utc))
        session.add(run); await session.commit()
        run_id = run.id
    print(f"ðŸš€ Starting crawl run {run_id} (mode={mode}) at {datetime.now(timezone.utc)} UTC")

    base_host = urlparse(start_url).netloc

    # Seed/reset start URL
    async with Session() as session:
        exists = await session.scalar(sa.select(URL).filter_by(url=start_url))
        if exists:
            exists.status = 'pending'; exists.last_attempt = None
        else:
            session.add(URL(url=start_url, category='internal', status='pending'))
        await session.commit()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENTS[mode])

        async def worker(idx):
            async with Session() as session:
                while True:
                    # Claim one pending URL
                    res = await session.execute(
                        sa.select(URL)
                          .where(URL.status=='pending')
                          .order_by(URL.id)
                          .with_for_update(skip_locked=True)
                          .limit(1)
                    )
                    url_obj = res.scalars().first()
                    if not url_obj:
                        return

                    # Classify
                    parsed = urlparse(url_obj.url)
                    url_obj.category = 'internal' if parsed.netloc==base_host else 'external'
                    url_obj.status = 'in_progress'
                    url_obj.last_attempt = datetime.now(timezone.utc)
                    await session.commit()

                    print(f"[Worker {idx}] Crawling: {url_obj.url} ({url_obj.category})")
                    if url_obj.category == 'external':
                        # HTTP status-only
                        try:
                            resp = await context.request.get(url_obj.url, timeout=30000)
                            status = resp.status
                            err = None
                        except Exception as e:
                            status = None
                            err = str(e)
                        snap = Snapshot(
                            url_id=url_obj.id,
                            run_id=run_id,
                            mode=mode,
                            status_code=status,
                            error_message=err,
                            timestamp=datetime.now(timezone.utc)
                        )
                        session.add(snap)
                        url_obj.status = 'done'
                        await session.commit()
                        print(f"[Worker {idx}] External status: {status}")
                        continue

                    # Internal: full page + metrics + link graph
                    page = await context.new_page()
                    try:
                        resp = await page.goto(url_obj.url, timeout=30000, wait_until='domcontentloaded')
                        status_code = resp.status if resp else None
                        await wait_for_full_load(page)

                        perf_json = await page.evaluate("() => JSON.stringify(window.performance.timing)")
                        perf      = json.loads(perf_json)
                        nav       = perf.get('navigationStart',0)
                        ttfb      = perf.get('responseStart',0) - nav
                        domc      = perf.get('domContentLoadedEventEnd',0) - nav
                        loade     = perf.get('loadEventEnd',0) - nav

                        # Discover links
                        hrefs = await page.eval_on_selector_all('a[href]', 'els=>els.map(e=>e.href)')
                        new_links = []
                        for href in set(hrefs):
                            if href == url_obj.url: continue
                            p = urlparse(href)
                            if p.scheme in ('http','https'):
                                target = await session.scalar(sa.select(URL).filter_by(url=href))
                                if not target:
                                    cat = 'internal' if p.netloc==base_host else 'external'
                                    new_url = URL(url=href, category=cat, status='pending')
                                    session.add(new_url); await session.commit()
                                    tgt_id = new_url.id
                                else:
                                    tgt_id = target.id
                                new_links.append((url_obj.id, tgt_id))
                        print(f"[Worker {idx}] Detected {len(new_links)} outgoing links")

                        # Snapshot content
                        content = await page.content()
                        digest  = hashlib.sha256(content.encode()).hexdigest()
                        snap = Snapshot(
                            url_id=url_obj.id,
                            run_id=run_id,
                            mode=mode,
                            status_code=status_code,
                            content_hash=digest,
                            content=content,
                            ttfb_ms=ttfb,
                            dom_content_loaded_ms=domc,
                            load_event_end_ms=loade,
                            timestamp=datetime.now(timezone.utc)
                        )
                        session.add(snap); await session.flush()

                        # Persist link edges
                        for src, tgt in new_links:
                            session.add(Link(source_id=src, target_id=tgt, snapshot_id=snap.id))

                        url_obj.status = 'done'
                        await session.commit()

                    except Exception as e:
                        await session.rollback()
                        snap = Snapshot(
                            url_id=url_obj.id,
                            run_id=run_id,
                            mode=mode,
                            status_code=None,
                            error_message=str(e),
                            timestamp=datetime.now(timezone.utc)
                        )
                        session.add(snap)
                        url_obj.status = 'error'
                        await session.commit()
                        print(f"[Worker {idx}] Error on {url_obj.url}: {e}", file=sys.stderr)
                    finally:
                        await page.close()

        tasks = [asyncio.create_task(worker(i)) for i in range(concurrency)]
        await asyncio.gather(*tasks)
        await browser.close()

    # Finish run
    async with Session() as session:
        await session.execute(
            sa.update(CrawlRun)
              .where(CrawlRun.id==run_id)
              .values(end_time=datetime.now(timezone.utc))
        )
        await session.commit()
    print(f"ðŸ Finished crawl run {run_id} at {datetime.now(timezone.utc)} UTC")

def get_database_url():
    url = os.getenv('DATABASE_URL')
    if url:
        return url
    user, pwd = os.getenv('DB_USER'), os.getenv('DB_PASSWORD')
    host, port, db = os.getenv('DB_HOST'), os.getenv('DB_PORT'), os.getenv('DB_NAME')
    if not all([user,pwd,host,port,db]):
        print("Error: set DB_* or DATABASE_URL", file=sys.stderr)
        sys.exit(1)
    return f"mysql+asyncmy://{user}:{pwd}@{host}:{port}/{db}"

async def main():
    parser = argparse.ArgumentParser(description='Crawler with DB persistence & metrics')
    parser.add_argument('command', choices=['crawl'])
    parser.add_argument('start_url', nargs='?')
    parser.add_argument('--mode', choices=['desktop','mobile','bot'], default='desktop')
    parser.add_argument('--concurrency', type=int, default=5)
    args = parser.parse_args()

    if args.command == 'crawl':
        if not args.start_url:
            parser.error('start_url is required')
        engine = create_async_engine(get_database_url(), echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        Session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        await crawl(args.start_url, args.mode, args.concurrency, Session)

if __name__ == '__main__':
    asyncio.run(main())


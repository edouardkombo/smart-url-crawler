#!/usr/bin/env python3
"""
Database manager CLI for creating and dropping schema (MySQL + asyncmy).

Usage:
    python db_manager.py init   # create DB if needed + tables
    python db_manager.py drop   # drop tables (but not the database)

Reads DATABASE_URL or DB_* env vars for connection.
"""
import os
import sys
import argparse
import asyncio
from dotenv import load_dotenv
load_dotenv()

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.mysql import LONGTEXT

# ORM Base and Models
Base = declarative_base()

class URL(Base):
    __tablename__ = 'urls'
    id           = sa.Column(sa.Integer, primary_key=True)
    url          = sa.Column(sa.String(2048), nullable=False)
    category     = sa.Column(sa.String(16), nullable=False)
    status       = sa.Column(
        sa.Enum('pending','in_progress','done','error', name='url_status'),
        nullable=False, server_default='pending'
    )
    last_attempt = sa.Column(sa.DateTime(timezone=True), nullable=True)

    outgoing = relationship(
        "Link", foreign_keys="[Link.source_id]",
        back_populates="source", cascade="all, delete-orphan"
    )
    incoming = relationship(
        "Link", foreign_keys="[Link.target_id]",
        back_populates="target", cascade="all, delete-orphan"
    )
    snapshots = relationship(
        "Snapshot", back_populates="url", cascade="all, delete-orphan"
    )

    __table_args__ = (
        sa.Index('uq_urls_url', 'url', unique=True, mysql_length=191),
    )

class CrawlRun(Base):
    __tablename__ = 'crawl_runs'
    id         = sa.Column(sa.Integer, primary_key=True)
    mode       = sa.Column(
        sa.Enum('desktop','mobile','bot', name='crawl_mode'),
        nullable=False, server_default='desktop'
    )
    start_time = sa.Column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    end_time   = sa.Column(sa.DateTime(timezone=True), nullable=True)

    snapshots  = relationship("Snapshot", back_populates="run", cascade="all, delete-orphan")

class Snapshot(Base):
    __tablename__ = 'snapshots'
    id                    = sa.Column(sa.Integer, primary_key=True)
    url_id                = sa.Column(sa.Integer, sa.ForeignKey('urls.id', ondelete='CASCADE'), nullable=False)
    run_id                = sa.Column(sa.Integer, sa.ForeignKey('crawl_runs.id', ondelete='CASCADE'), nullable=False)
    mode                  = sa.Column(
        sa.Enum('desktop','mobile','bot', name='crawl_mode'),
        nullable=False
    )
    status_code           = sa.Column(sa.Integer, nullable=True)
    content_hash          = sa.Column(sa.String(64), nullable=True)
    content               = sa.Column(LONGTEXT, nullable=True)
    error_message         = sa.Column(sa.Text, nullable=True)
    ttfb_ms               = sa.Column(sa.Integer, nullable=True)
    dom_content_loaded_ms = sa.Column(sa.Integer, nullable=True)
    load_event_end_ms     = sa.Column(sa.Integer, nullable=True)
    timestamp             = sa.Column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)

    url = relationship("URL", back_populates="snapshots")
    run = relationship("CrawlRun", back_populates="snapshots")

class Link(Base):
    __tablename__ = 'links'
    id          = sa.Column(sa.Integer, primary_key=True)
    source_id   = sa.Column(sa.Integer, sa.ForeignKey('urls.id', ondelete='CASCADE'), nullable=False)
    target_id   = sa.Column(sa.Integer, sa.ForeignKey('urls.id', ondelete='CASCADE'), nullable=False)
    snapshot_id = sa.Column(sa.Integer, sa.ForeignKey('snapshots.id', ondelete='CASCADE'), nullable=False)

    source   = relationship("URL", foreign_keys=[source_id], back_populates="outgoing")
    target   = relationship("URL", foreign_keys=[target_id], back_populates="incoming")
    snapshot = relationship("Snapshot")

# Utilities
def get_database_url():
    url = os.getenv('DATABASE_URL')
    if url:
        return url
    user = os.getenv('DB_USER')
    pwd  = os.getenv('DB_PASSWORD')
    host = os.getenv('DB_HOST','').strip().rstrip('/')
    if host.startswith('http://') or host.startswith('https://'):
        host = host.split('://',1)[1]
    port = os.getenv('DB_PORT') or '3306'
    db   = os.getenv('DB_NAME')
    if not all([user, pwd, host, db]):
        print("Error: set DATABASE_URL or DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME", file=sys.stderr)
        sys.exit(1)
    return f"mysql+asyncmy://{user}:{pwd}@{host}:{port}/{db}"

async def init_db(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("âœ… Database initialized.")

async def drop_db(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    print("ðŸ—‘ï¸  Database dropped.")

def ensure_database_exists():
    """
    Connect to MySQL server (w/o DB) and create the target DB if missing.
    """
    raw_user = os.getenv('DB_USER')
    raw_pwd  = os.getenv('DB_PASSWORD')
    raw_host = os.getenv('DB_HOST','').strip().rstrip('/')
    if raw_host.startswith('http://') or raw_host.startswith('https://'):
        raw_host = raw_host.split('://',1)[1]
    raw_port = os.getenv('DB_PORT') or '3306'
    raw_db   = os.getenv('DB_NAME')
    if not all([raw_user, raw_pwd, raw_host, raw_db]):
        print("Error: set DATABASE_URL or DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME", file=sys.stderr)
        sys.exit(1)

    from sqlalchemy import create_engine, text
    # use a sync driver to manage database creation
    sync_url = f"mysql+mysqlconnector://{raw_user}:{raw_pwd}@{raw_host}:{raw_port}/"
    engine = create_engine(sync_url)
    with engine.connect() as conn:
        conn.execute(text(
            f"CREATE DATABASE IF NOT EXISTS `{raw_db}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        ))
    engine.dispose()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='DB schema manager')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init', help='Create database & tables')
    sub.add_parser('drop', help='Drop tables only')
    args = parser.parse_args()

    if args.command == 'init':
        ensure_database_exists()

    db_url = get_database_url()
    engine = create_async_engine(db_url, echo=False)

    if args.command == 'init':
        asyncio.run(init_db(engine))
    elif args.command == 'drop':
        asyncio.run(drop_db(engine))


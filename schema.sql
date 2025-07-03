-- schema.sql

DROP TABLE IF EXISTS links;
DROP TABLE IF EXISTS snapshots;
DROP TABLE IF EXISTS crawl_runs;
DROP TABLE IF EXISTS urls;

CREATE TABLE urls (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  url           VARCHAR(2048) NOT NULL,
  category      VARCHAR(16) NOT NULL,
  status        ENUM('pending','in_progress','done','error') NOT NULL DEFAULT 'pending',
  last_attempt  DATETIME NULL,
  UNIQUE KEY uq_urls_url (url(191))
);

CREATE TABLE crawl_runs (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  mode        ENUM('desktop','mobile','bot') NOT NULL DEFAULT 'desktop',
  start_time  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  end_time    DATETIME NULL
);

CREATE TABLE snapshots (
  id                        INT AUTO_INCREMENT PRIMARY KEY,
  url_id                    INT NOT NULL,
  run_id                    INT NOT NULL,
  mode                      ENUM('desktop','mobile','bot') NOT NULL,
  status_code               INT NULL,
  content_hash              CHAR(64) NULL,
  content                   LONGTEXT NULL,
  error_message             TEXT NULL,
  ttfb_ms                   INT NULL,
  dom_content_loaded_ms     INT NULL,
  load_event_end_ms         INT NULL,
  timestamp                 DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (url_id) REFERENCES urls(id) ON DELETE CASCADE,
  FOREIGN KEY (run_id) REFERENCES crawl_runs(id) ON DELETE CASCADE
);

CREATE TABLE links (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  source_id      INT NOT NULL,
  target_id      INT NOT NULL,
  snapshot_id    INT NOT NULL,
  FOREIGN KEY (source_id)   REFERENCES urls(id)      ON DELETE CASCADE,
  FOREIGN KEY (target_id)   REFERENCES urls(id)      ON DELETE CASCADE,
  FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
);


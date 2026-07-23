CREATE DATABASE IF NOT EXISTS astocks_qfq
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE astocks_qfq;

CREATE TABLE IF NOT EXISTS stocks (
  ts_code VARCHAR(12) NOT NULL PRIMARY KEY,
  name    VARCHAR(64) NOT NULL DEFAULT ''
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS daily_qfq (
  ts_code     VARCHAR(12) NOT NULL,
  trade_date  CHAR(8)     NOT NULL COMMENT 'YYYYMMDD',
  `open`      DECIMAL(12,4) NULL,
  high        DECIMAL(12,4) NULL,
  low         DECIMAL(12,4) NULL,
  close_qfq   DECIMAL(12,4) NULL,
  volume      BIGINT NULL,
  amount      DECIMAL(20,2) NULL,
  PRIMARY KEY (ts_code, trade_date),
  KEY idx_trade_date (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

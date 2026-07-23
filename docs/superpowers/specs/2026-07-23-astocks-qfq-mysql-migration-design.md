# A 股前复权日线：SQLite → MySQL 迁移设计

日期：2026-07-23  
状态：已确认；实现见 `docs/superpowers/plans/2026-07-23-astocks-qfq-mysql-migration.md`  
范围：研究/回测用单机 MySQL；仅行情表；不改现有 SQLite 脚本

## 背景

`database/astocks_qfq.db`（约 1.8GB）存放 baostock 前复权日线，核心表为 `stocks` 与 `daily_qfq`。同库另有 `app_*` 表，本方案不迁移。

现有脚本（`update_daily.py`、`backfill_qfq_to_yesterday.py`、`bs_qfq_downloader.py`）继续服务 SQLite，保持不动。MySQL 能力通过**新增脚本**提供。

## 目标

1. 将 `stocks`、`daily_qfq` 一次性迁入 MySQL。
2. 提供 MySQL 版日更脚本，行为对齐现有 `update_daily.py`。
3. 连接信息由环境变量/本地 env 文件提供（后续再填），不把密码写入仓库。

## 非目标

- 不迁移任何 `app_*` 表。
- 不修改现有 SQLite 脚本。
- 不新增 MySQL 版 `backfill_qfq_to_yesterday.py`（缺口补齐仍用 SQLite 脚本；若以后需要再开任务）。
- 不做高可用、权限体系、读写分离。
- 不改造 `quant_signal.py` 等上层读取逻辑（可继续读 SQLite，或后续单独接 MySQL）。

## 交付物

| 文件 | 作用 |
| --- | --- |
| `database/schema_mysql.sql` | MySQL DDL（stocks + daily_qfq） |
| `database/migrate_sqlite_to_mysql.py` | **新脚本 1**：SQLite → MySQL 全量迁移与校验 |
| `database/update_daily_mysql.py` | **新脚本 2**：baostock 增量更新写入 MySQL |
| `database/requirements.txt` | 增加 `pymysql` |
| `database/README.md` | 补充 MySQL 用法小节 |

不改动：`update_daily.py`、`backfill_qfq_to_yesterday.py`、`bs_qfq_downloader.py`。

## 目标 Schema

```sql
CREATE DATABASE IF NOT EXISTS astocks_qfq
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE astocks_qfq;

CREATE TABLE stocks (
  ts_code VARCHAR(12) NOT NULL PRIMARY KEY,
  name    VARCHAR(64) NOT NULL DEFAULT ''
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE daily_qfq (
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
```

相对 SQLite 的刻意差异：

- 去掉自增 `id`，以 `(ts_code, trade_date)` 为主键。
- `open` 使用反引号（MySQL 保留字）。
- 价格用 `DECIMAL`；`volume` 用 `BIGINT` 且可空。
- 不建与主键重复的 `ts_code` 单列索引。

库名默认 `astocks_qfq`，可通过环境变量覆盖。

## 连接配置

统一通过环境变量读取（两脚本共用同一约定）：

| 变量 | 含义 | 默认 |
| --- | --- | --- |
| `MYSQL_HOST` | 主机 | `127.0.0.1` |
| `MYSQL_PORT` | 端口 | `3306` |
| `MYSQL_USER` | 用户 | 无默认，必填 |
| `MYSQL_PASSWORD` | 密码 | 空字符串允许 |
| `MYSQL_DATABASE` | 库名 | `astocks_qfq` |

可选：若存在 `database/mysql.env`（或项目约定路径），脚本启动时加载；该文件加入 `.gitignore`，不提交。连接信息由用户稍后提供；实现时用占位说明即可。

依赖：`pymysql`。

## 脚本 1：`migrate_sqlite_to_mysql.py`

### 行为

1. 只读打开本地 SQLite（默认 `database/astocks_qfq.db`，可 CLI 覆盖）。
2. 连接 MySQL；若表不存在则执行 `schema_mysql.sql`（或内嵌等价 DDL）。
3. 清空或要求目标表为空（默认：目标非空则报错退出，提供 `--force` 先 `TRUNCATE`）。
4. 导入 `stocks` 全量。
5. 导入 `daily_qfq`：按年分批或按 `ts_code` 分批 `INSERT`（每批数千行），避免一次载入 1.8GB。
6. 校验并打印：
   - 两边 `COUNT(*)`
   - `COUNT(DISTINCT ts_code)`、`MIN/MAX(trade_date)`
   - 抽样 N 只股票的行数与收盘价校验和（如 `SUM(close_qfq)`）

### CLI（示例）

```bash
python migrate_sqlite_to_mysql.py [--sqlite PATH] [--force] [--batch-size N]
```

### 前置条件

- 迁移前停止对 SQLite 的写入（如正在跑的 backfill），避免导到一半数据变化。
- 不导入 `app_*`。

## 脚本 2：`update_daily_mysql.py`

### 行为

对齐现有 `update_daily.py`：

1. 登录 baostock，拉取 A 股列表（60/00/30/68）。
2. 与 MySQL `stocks` 同步：删除退市代码及其 `daily_qfq`；插入新股。
3. 逐只查本地最新 `trade_date`；若已 ≥ 今天则跳过。
4. 下载当天前复权日线（`adjustflag="2"`），写入 MySQL。
5. 打印更新/跳过/失败统计。

### SQL 映射

| SQLite | MySQL |
| --- | --- |
| `INSERT OR IGNORE INTO stocks` | `INSERT IGNORE INTO stocks` |
| `INSERT OR REPLACE INTO daily_qfq` | `INSERT INTO daily_qfq (...) VALUES (...) ON DUPLICATE KEY UPDATE open=VALUES(open), ...` |
| `?` | `%s`（PyMySQL） |

字段集合与现脚本一致：`ts_code, trade_date, open, high, low, close_qfq, volume, amount`。

### CLI（示例）

```bash
python update_daily_mysql.py [--dry-run]
```

不接受 `.db` 路径参数；连接只来自环境变量 / `mysql.env`。

## 数据口径（不变）

- 前复权：baostock `adjustflag="2"`
- 日期：`YYYYMMDD` 字符串
- 代码：`000001.SZ` / `600000.SH`
- 不写入 `trade_date='SKIP'` 哨兵行

## 验收标准

1. `schema_mysql.sql` 可在空实例建库建表成功。
2. 全量迁移后，SQLite 与 MySQL 的 `daily_qfq` 行数、股票数、日期范围一致；抽样校验无差异。
3. `update_daily_mysql.py` 在交易日可对已迁库增量写入；重复运行不产生重复行。
4. 原有 SQLite 三个脚本未经修改（diff 为空）。
5. `app_*` 在 MySQL 中不存在。

## 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| 迁移中 SQLite 仍在写入 | 文档要求停写；只读打开；迁移后再次比对行数 |
| `open` 保留字 | DDL 与 SQL 一律反引号 |
| 大批量插入超时 | 分批 commit；可调 `--batch-size` |
| 连接信息未就绪 | 脚本先实现；提供后做联调验收 |
| 近期覆盖不全（backfill 进行中） | 建议 backfill 结束后再全量迁；也可先迁再靠日更补当天 |

## 实现顺序

1. `schema_mysql.sql` + `requirements.txt`（pymysql）
2. `migrate_sqlite_to_mysql.py`（含校验）
3. `update_daily_mysql.py`
4. README MySQL 小节

连接信息到位后：建库 → 全量迁移 → 跑一次日更 → 对照 SQLite 抽样验收。

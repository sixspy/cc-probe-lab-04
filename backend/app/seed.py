import sqlite3
from datetime import datetime, timezone
from app.db import 连接

建表 = """
CREATE TABLE IF NOT EXISTS 栏规 (
  键 TEXT PRIMARY KEY,
  值 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 站点源 (
  源键 TEXT PRIMARY KEY,
  名称 TEXT NOT NULL,
  介质 TEXT NOT NULL DEFAULT '大气',
  区域 TEXT NOT NULL DEFAULT '',
  说明 TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS 观测报文 (
  报文编号 TEXT PRIMARY KEY,
  站点键 TEXT NOT NULL,
  指标键 TEXT NOT NULL,
  读数 REAL NOT NULL,
  观测时 TEXT NOT NULL,
  处理时 TEXT NOT NULL,
  命运 TEXT NOT NULL DEFAULT '已装载',
  批次编号 TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS 入栏缓冲 (
  报文编号 TEXT PRIMARY KEY,
  站点键 TEXT NOT NULL,
  指标键 TEXT NOT NULL,
  读数 REAL NOT NULL,
  观测时 TEXT NOT NULL,
  栏号 TEXT NOT NULL,
  命运 TEXT NOT NULL DEFAULT '在栏',
  入栏时 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 站点汇总账 (
  汇总编号 TEXT PRIMARY KEY,
  栏号 TEXT NOT NULL,
  站点键 TEXT NOT NULL,
  指标键 TEXT NOT NULL,
  报文数 INTEGER NOT NULL,
  均值 REAL NOT NULL,
  物化时 TEXT NOT NULL,
  命运 TEXT NOT NULL DEFAULT '已汇总'
);
CREATE TABLE IF NOT EXISTS 坏点匣 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  报文编号 TEXT NOT NULL,
  站点键 TEXT NOT NULL,
  原因 TEXT NOT NULL,
  读数 REAL,
  观测时 TEXT NOT NULL,
  入匣时 TEXT NOT NULL,
  旁路凭证 TEXT NOT NULL DEFAULT '',
  保留形态 TEXT NOT NULL DEFAULT '旁路凭证冻结',
  原观测可回读 INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS 栏贯验 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  时刻 TEXT NOT NULL,
  在栏笔数 INTEGER NOT NULL,
  汇总报文数 INTEGER NOT NULL,
  坏点笔数 INTEGER NOT NULL,
  是否对齐 INTEGER NOT NULL,
  说明 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 装载批次 (
  编号 TEXT PRIMARY KEY,
  时刻 TEXT NOT NULL,
  入流 INTEGER NOT NULL DEFAULT 0,
  入栏 INTEGER NOT NULL DEFAULT 0,
  坏点 INTEGER NOT NULL DEFAULT 0,
  报告 TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS 结栏批次 (
  编号 TEXT PRIMARY KEY,
  栏号 TEXT NOT NULL,
  时刻 TEXT NOT NULL,
  汇总数 INTEGER NOT NULL DEFAULT 0,
  报告 TEXT NOT NULL DEFAULT '{}'
);
"""


def 此刻() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _迁移坏点旁路(conn: sqlite3.Connection) -> None:
    """既有库补凭证列与报文编号唯一互斥；历史匣行补凭证、判齐套。

    早期表 读数 为 NOT NULL，无法表达“原读数丢失”，须按新定义重建。
    旧库若有同号重复匣行，建唯一索引前先去重（保留编号最小的最早行）。
    """
    列信息 = {r["name"]: dict(r) for r in conn.execute("PRAGMA table_info(坏点匣)").fetchall()}
    读数非空 = 列信息.get("读数", {}).get("notnull") == 1
    if 读数非空:
        # 事务写在脚本内：executescript 会先提交悬挂事务，故由脚本自身 BEGIN/COMMIT 包住重建。
        conn.executescript(
            """
            BEGIN;
            CREATE TABLE 坏点匣_新 (
              编号 INTEGER PRIMARY KEY AUTOINCREMENT,
              报文编号 TEXT NOT NULL,
              站点键 TEXT NOT NULL,
              原因 TEXT NOT NULL,
              读数 REAL,
              观测时 TEXT NOT NULL,
              入匣时 TEXT NOT NULL,
              旁路凭证 TEXT NOT NULL DEFAULT '',
              保留形态 TEXT NOT NULL DEFAULT '旁路凭证冻结',
              原观测可回读 INTEGER NOT NULL DEFAULT 1
            );
            INSERT INTO 坏点匣_新(编号,报文编号,站点键,原因,读数,观测时,入匣时)
            SELECT 编号,报文编号,站点键,原因,读数,观测时,入匣时 FROM 坏点匣;
            DROP TABLE 坏点匣;
            ALTER TABLE 坏点匣_新 RENAME TO 坏点匣;
            COMMIT;
            """
        )
        列信息 = {r["name"]: dict(r) for r in conn.execute("PRAGMA table_info(坏点匣)").fetchall()}
    列 = set(列信息)
    if "旁路凭证" not in 列:
        conn.execute("ALTER TABLE 坏点匣 ADD COLUMN 旁路凭证 TEXT NOT NULL DEFAULT ''")
    if "保留形态" not in 列:
        conn.execute(
            "ALTER TABLE 坏点匣 ADD COLUMN 保留形态 TEXT NOT NULL DEFAULT '旁路凭证冻结'"
        )
    if "原观测可回读" not in 列:
        conn.execute(
            "ALTER TABLE 坏点匣 ADD COLUMN 原观测可回读 INTEGER NOT NULL DEFAULT 1"
        )
    conn.execute(
        """UPDATE 坏点匣
           SET 原观测可回读 = CASE
                 WHEN 观测时 IS NOT NULL AND TRIM(观测时) <> '' AND 读数 IS NOT NULL THEN 1
                 ELSE 0 END
           WHERE 旁路凭证 = ''"""
    )
    conn.execute(
        """UPDATE 坏点匣 SET 旁路凭证 = 'BP-' || 编号
           WHERE 旁路凭证 = '' OR 旁路凭证 IS NULL"""
    )
    # 建唯一索引前去重：同号保留最早一行，其余删除，避免历史脏数据阻塞迁移。
    conn.execute(
        """DELETE FROM 坏点匣
           WHERE 编号 NOT IN (SELECT MIN(编号) FROM 坏点匣 GROUP BY 报文编号)"""
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS 坏点匣报文编号唯一 ON 坏点匣(报文编号)"
    )
    conn.commit()


def 初始化库() -> None:
    conn = 连接()
    conn.executescript(建表)
    _迁移坏点旁路(conn)
    if conn.execute("SELECT COUNT(*) AS c FROM 栏规").fetchone()["c"] == 0:
        for k, v in {
            "当前栏号": "B-demo",
            "PM25上限": "75",
            "PM25下限": "0",
            "标定偏移上限": "5",
            "栏策略": "按站点指标汇总均值",
        }.items():
            conn.execute("INSERT INTO 栏规(键,值) VALUES (?,?)", (k, v))
    if conn.execute("SELECT COUNT(*) AS c FROM 站点源").fetchone()["c"] == 0:
        for row in [
            ("站-河东", "河东大气站", "大气", "城区", "示范站"),
            ("站-湖西", "湖西水质站", "水质", "湖区", "示范站"),
            ("站-北岭", "北岭大气站", "大气", "近郊", "示范站"),
            ("站-江口", "江口大气站", "大气", "河口", "示范站"),
            ("站-林场", "林场微站", "大气", "林区", "示范站"),
        ]:
            conn.execute(
                "INSERT INTO 站点源(源键,名称,介质,区域,说明) VALUES (?,?,?,?,?)",
                row,
            )
    conn.commit()
    conn.close()

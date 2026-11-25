"""栏贯验：已汇总缓冲报文数 == 汇总账报文数之和；坏点匣行须原观测齐套。"""
from __future__ import annotations
from app.db import 连接
from app.seed import 此刻


def _坏点齐套(conn) -> tuple[int, int, list[str]]:
    """返回(坏点总数, 缺原观测行数, 缺票报文编号)。齐套要求冻结观测时非空且读数非空。"""
    rows = conn.execute(
        """SELECT 报文编号, 观测时, 读数 FROM 坏点匣
           WHERE 观测时 IS NULL OR TRIM(观测时) = '' OR 读数 IS NULL"""
    ).fetchall()
    总 = conn.execute("SELECT COUNT(*) AS c FROM 坏点匣").fetchone()["c"]
    return int(总), len(rows), [r["报文编号"] for r in rows]


def 跑一次() -> dict:
    conn = 连接()
    try:
        在栏 = conn.execute(
            "SELECT COUNT(*) AS c FROM 入栏缓冲 WHERE 命运='在栏'"
        ).fetchone()["c"]
        已汇总缓冲 = conn.execute(
            "SELECT COUNT(*) AS c FROM 入栏缓冲 WHERE 命运='已汇总'"
        ).fetchone()["c"]
        汇总报文 = conn.execute(
            "SELECT COALESCE(SUM(报文数),0) AS c FROM 站点汇总账"
        ).fetchone()["c"]
        坏点, 缺原观测, 缺票 = _坏点齐套(conn)
        汇总对齐 = int(已汇总缓冲) == int(汇总报文)
        坏点齐套 = 缺原观测 == 0
        对齐 = 1 if (汇总对齐 and 坏点齐套) else 0
        片段 = []
        if not 汇总对齐:
            片段.append(f"撕裂：已汇总缓冲={已汇总缓冲} 汇总报文={汇总报文}")
        if not 坏点齐套:
            片段.append(f"坏点缺原观测{缺原观测}行：{','.join(缺票[:5])}")
        说明 = "入栏已汇总与站点汇总报文数一致；坏点匣原观测齐套" if 对齐 else "；".join(片段)
        时刻 = 此刻()
        conn.execute("BEGIN")
        conn.execute(
            """INSERT INTO 栏贯验(时刻,在栏笔数,汇总报文数,坏点笔数,是否对齐,说明)
               VALUES (?,?,?,?,?,?)""",
            (时刻, 在栏, int(汇总报文), 坏点, 对齐, 说明),
        )
        conn.commit()
        return {
            "时刻": 时刻,
            "在栏": 在栏,
            "已汇总缓冲": int(已汇总缓冲),
            "汇总报文": int(汇总报文),
            "坏点": 坏点,
            "坏点齐套": 坏点齐套,
            "坏点缺原观测": 缺原观测,
            "是否对齐": bool(对齐),
            "说明": 说明,
        }
    finally:
        conn.close()


def 只读快照() -> dict:
    """不落库的贯验快照，供页面预览。"""
    conn = 连接()
    try:
        在栏 = conn.execute(
            "SELECT COUNT(*) AS c FROM 入栏缓冲 WHERE 命运='在栏'"
        ).fetchone()["c"]
        已汇总缓冲 = conn.execute(
            "SELECT COUNT(*) AS c FROM 入栏缓冲 WHERE 命运='已汇总'"
        ).fetchone()["c"]
        汇总报文 = conn.execute(
            "SELECT COALESCE(SUM(报文数),0) AS c FROM 站点汇总账"
        ).fetchone()["c"]
        坏点, 缺原观测, _ = _坏点齐套(conn)
        汇总对齐 = int(已汇总缓冲) == int(汇总报文)
        return {
            "在栏": 在栏,
            "已汇总缓冲": int(已汇总缓冲),
            "汇总报文": int(汇总报文),
            "坏点": 坏点,
            "坏点齐套": 缺原观测 == 0,
            "坏点缺原观测": 缺原观测,
            "是否对齐": 汇总对齐 and 缺原观测 == 0,
        }
    finally:
        conn.close()

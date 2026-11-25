"""列表与栏规。"""
from __future__ import annotations
from app.db import 连接
from app.services import 校验


def 栏规() -> dict:
    conn = 连接()
    try:
        return {r["键"]: r["值"] for r in conn.execute("SELECT 键,值 FROM 栏规").fetchall()}
    finally:
        conn.close()


def 改栏规(体: dict) -> dict:
    错 = 校验.校验栏规补丁(体 or {})
    if 错:
        return {"错误": 校验.摘要错误(错), "栏规": 栏规()}
    conn = 连接()
    try:
        conn.execute("BEGIN")
        for k, v in (体 or {}).items():
            conn.execute(
                "INSERT INTO 栏规(键,值) VALUES (?,?) ON CONFLICT(键) DO UPDATE SET 值=excluded.值",
                (str(k), str(v)),
            )
        conn.commit()
        return 栏规()
    finally:
        conn.close()


def 站点列表() -> list[dict]:
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 站点源 ORDER BY 源键").fetchall()]
    finally:
        conn.close()


def 报文列表(限制: int = 200) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 观测报文 ORDER BY 观测时 DESC LIMIT ?", (限制,)
            ).fetchall()
        ]
    finally:
        conn.close()


def 缓冲列表(命运: str | None = None) -> list[dict]:
    conn = 连接()
    try:
        if 命运:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM 入栏缓冲 WHERE 命运=? ORDER BY 观测时", (命运,)
                ).fetchall()
            ]
        return [dict(r) for r in conn.execute("SELECT * FROM 入栏缓冲 ORDER BY 观测时").fetchall()]
    finally:
        conn.close()


def 汇总列表(限制: int = 200) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 站点汇总账 ORDER BY 物化时 DESC LIMIT ?", (限制,)
            ).fetchall()
        ]
    finally:
        conn.close()


def 坏点列表(限制: int = 200) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 坏点匣 ORDER BY 编号 DESC LIMIT ?", (限制,)
            ).fetchall()
        ]
    finally:
        conn.close()


def 坏点旁路保留列表(限制: int = 200) -> list[dict]:
    """只读：坏点匣行与观测报文同票联查，凭旁路凭证回读冻结的原观测。

    原观测可回读由匣行冻结字段实际状态判定，缺观测时或缺读数即为 False，
    调用方可据此区分“拿得到原观测”与“只剩原因”。
    """
    conn = 连接()
    try:
        rows = conn.execute(
            """
            SELECT b.编号, b.报文编号, b.站点键, b.原因, b.入匣时,
                   b.旁路凭证, b.保留形态, b.原观测可回读,
                   b.观测时 AS 原观测时, b.读数 AS 原读数,
                   o.指标键 AS 原指标键, o.处理时 AS 原处理时,
                   o.命运 AS 观测命运, o.批次编号 AS 观测批次编号,
                   o.观测时 AS 报文观测时, o.读数 AS 报文读数
              FROM 坏点匣 b
              LEFT JOIN 观测报文 o ON o.报文编号 = b.报文编号
             ORDER BY b.编号 DESC
             LIMIT ?
            """,
            (限制,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            可回读 = bool(d.get("原观测可回读")) and bool(
                d.get("原观测时") not in (None, "")
            ) and d.get("原读数") is not None
            # 同票互证：观测流若仍在，冻结值须与观测报文一字不差。
            d["同票一致"] = (
                d.get("报文观测时") is None
                or (
                    d.get("报文观测时") == d.get("原观测时")
                    and d.get("报文读数") == d.get("原读数")
                )
            )
            d["原观测可回读"] = 可回读
            d.pop("报文观测时", None)
            d.pop("报文读数", None)
            out.append(d)
        return out
    finally:
        conn.close()


def 贯验列表(限制: int = 50) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 栏贯验 ORDER BY 编号 DESC LIMIT ?", (限制,)
            ).fetchall()
        ]
    finally:
        conn.close()


def 概览() -> dict:
    conn = 连接()
    try:
        return {
            "观测报文": conn.execute("SELECT COUNT(*) AS c FROM 观测报文").fetchone()["c"],
            "在栏": conn.execute("SELECT COUNT(*) AS c FROM 入栏缓冲 WHERE 命运='在栏'").fetchone()["c"],
            "站点汇总": conn.execute("SELECT COUNT(*) AS c FROM 站点汇总账").fetchone()["c"],
            "坏点": conn.execute("SELECT COUNT(*) AS c FROM 坏点匣").fetchone()["c"],
            "栏规": 栏规(),
        }
    finally:
        conn.close()


def 装载批次列表(限制: int = 50) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT 编号,时刻,入流,入栏,坏点 FROM 装载批次 ORDER BY 时刻 DESC LIMIT ?",
                (限制,),
            ).fetchall()
        ]
    finally:
        conn.close()


def 结栏批次列表(限制: int = 50) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT 编号,栏号,时刻,汇总数 FROM 结栏批次 ORDER BY 时刻 DESC LIMIT ?",
                (限制,),
            ).fetchall()
        ]
    finally:
        conn.close()


def 站点查(源键: str) -> dict | None:
    conn = 连接()
    try:
        r = conn.execute("SELECT * FROM 站点源 WHERE 源键=?", (源键,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()

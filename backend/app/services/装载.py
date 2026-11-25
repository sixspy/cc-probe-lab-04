"""报文装载 → 入栏或坏点。

坏点旁路保留（probe-04）：
- 坏点写入与观测报文命运同票，同处一个事务、同成同败；
- 坏点匣行带旁路凭证，冻结原观测时与原读数，禁止回刷抹字段；
- 同号再进匣由库级唯一互斥 + 进程内串行闸双重挡住，冲突干净驳回，不抛穿。
"""
from __future__ import annotations
import json
import sqlite3
import threading
import uuid
from app.db import 连接
from app.seed import 此刻
from app.services import 校验, 目录, 时间

# 进程内串行闸：把同号竞态在应用层收敛成“先成后驳”，库级唯一索引是最后互斥。
_装载闸 = threading.RLock()


def _批次号(体: dict) -> str:
    前 = str(体.get("批次编号") or "探批").strip() or "探批"
    return f"{前}-{uuid.uuid4().hex[:8]}"


def 装一批(体: dict) -> dict:
    批次 = _批次号(体 or {})
    报文 = (体 or {}).get("报文") or []
    报告 = {"批次编号": 批次, "入流": 0, "入栏": 0, "坏点": 0, "驳回": 0, "明细": []}
    预检 = 校验.校验批次(体 or {})
    if 预检:
        报告["明细"].append({"命运": "批次预检", "说明": 校验.摘要错误(预检)})
    规 = 目录.栏规()
    栏号 = 规.get("当前栏号", "B-demo")
    站集合 = {s["源键"] for s in 目录.站点列表()}
    仓时 = 此刻()
    with _装载闸:
        conn = 连接()
        try:
            conn.execute("BEGIN")
            for ev in 报文:
                行错 = 校验.校验报文(ev)
                if 行错:
                    报告["驳回"] += 1
                    报告["明细"].append({"命运": "驳回-校验", "说明": 校验.摘要错误(行错)})
                    continue
                try:
                    时间.解析时(ev["观测时"])
                except Exception:
                    报告["驳回"] += 1
                    报告["明细"].append({"命运": "驳回-观测时", "说明": ev.get("观测时")})
                    continue
                编号 = ev["报文编号"]
                if conn.execute("SELECT 1 FROM 观测报文 WHERE 报文编号=?", (编号,)).fetchone():
                    报告["驳回"] += 1
                    报告["明细"].append({"命运": "驳回-幂等", "说明": 编号})
                    continue
                if ev["站点键"] not in 站集合:
                    报告["驳回"] += 1
                    报告["明细"].append({"命运": "驳回-未知站点", "说明": ev["站点键"]})
                    continue
                读数 = float(ev["读数"])
                处理 = 仓时
                漂 = 时间.漂移秒(ev["观测时"], 仓时)
                conn.execute("SAVEPOINT 报文入流")
                try:
                    conn.execute(
                        """INSERT INTO 观测报文(报文编号,站点键,指标键,读数,观测时,处理时,命运,批次编号)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (编号, ev["站点键"], ev["指标键"], 读数, ev["观测时"], 处理, "已装载", 批次),
                    )
                except sqlite3.IntegrityError:
                    # 同号并发已在另一路入流：仅回滚本笔，前序报文不动，干净驳回。
                    conn.execute("ROLLBACK TO SAVEPOINT 报文入流")
                    conn.execute("RELEASE SAVEPOINT 报文入流")
                    报告["驳回"] += 1
                    报告["明细"].append({"命运": "驳回-幂等", "说明": 编号})
                    continue
                except Exception:
                    # 非互斥类故障（如匣/库写入失败）：不得释放保存点，冒泡后整笔回滚，同成同败。
                    raise
                conn.execute("RELEASE SAVEPOINT 报文入流")
                报告["入流"] += 1
                ok, 原因 = 校验.过门槛(读数, 规, ev["指标键"])
                if ok:
                    conn.execute(
                        """INSERT INTO 入栏缓冲(报文编号,站点键,指标键,读数,观测时,栏号,命运,入栏时)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (编号, ev["站点键"], ev["指标键"], 读数, ev["观测时"], 栏号, "在栏", 处理),
                    )
                    conn.execute("UPDATE 观测报文 SET 命运=? WHERE 报文编号=?", ("已入栏", 编号))
                    报告["入栏"] += 1
                    报告["明细"].append({
                        "命运": "入栏",
                        "报文编号": 编号,
                        "栏号": 栏号,
                        "漂移秒": 漂,
                        "受控": 校验.指标是否受控(ev["指标键"]),
                    })
                else:
                    # 坏点旁路：凭证冻结原观测时与读数，与观测命运同票提交。
                    凭证 = f"BP-{uuid.uuid4().hex[:12]}"
                    conn.execute("SAVEPOINT 坏点入匣")
                    try:
                        conn.execute(
                            """INSERT INTO 坏点匣
                                 (报文编号,站点键,原因,读数,观测时,入匣时,旁路凭证,保留形态,原观测可回读)
                               VALUES (?,?,?,?,?,?,?,?,?)""",
                            (编号, ev["站点键"], 原因, 读数, ev["观测时"], 处理,
                             凭证, "旁路凭证冻结", 1),
                        )
                    except sqlite3.IntegrityError:
                        # 同号已在另一路进匣：只回滚本笔（含观测插入），不双匣不留半行。
                        conn.execute("ROLLBACK TO SAVEPOINT 坏点入匣")
                        conn.execute("RELEASE SAVEPOINT 坏点入匣")
                        报告["驳回"] += 1
                        报告["明细"].append({"命运": "驳回-幂等", "说明": 编号})
                        continue
                    except Exception:
                        # 匣写入其他故障：保存点不释放，冒泡触发整笔回滚，观测命运同败。
                        raise
                    conn.execute("RELEASE SAVEPOINT 坏点入匣")
                    conn.execute("UPDATE 观测报文 SET 命运=? WHERE 报文编号=?", ("已坏点", 编号))
                    报告["坏点"] += 1
                    报告["明细"].append({
                        "命运": "坏点",
                        "报文编号": 编号,
                        "原因": 原因,
                        "旁路凭证": 凭证,
                        "原观测可回读": True,
                    })
            conn.execute(
                """INSERT INTO 装载批次(编号,时刻,入流,入栏,坏点,报告) VALUES (?,?,?,?,?,?)""",
                (批次, 仓时, 报告["入流"], 报告["入栏"], 报告["坏点"], json.dumps(报告, ensure_ascii=False)),
            )
            conn.commit()
        except Exception:
            # 任何未在保存点内消化的故障：整笔回滚，坏点与观测命运同败，不留半行。
            conn.rollback()
            raise
        finally:
            conn.close()
    return 报告

"""争用失败测：同号两路坏点并发，双请求不得双匣。

红的条件：
- 同号两路并发装载出现双匣行，或一路炸成未捕获异常（500 式失败）；
- 坏点匣报文编号没有库级唯一互斥，裸插两行能双成功；
- 串行再进匣不幂等。
"""
import sqlite3
import threading

import pytest

from app.db import 连接
from app.services import 装载, 目录


坏点体 = {
    "批次编号": "keepobs-3",
    "报文": [{
        "报文编号": "K-race-1",
        "站点键": "站-河东",
        "指标键": "PM25",
        "读数": 120.0,
        "观测时": "2026-11-24T09:10:00Z",
    }],
}


def test_同号两路并发只成一匣一观测():
    果 = []

    def 跑():
        try:
            果.append(装载.装一批(坏点体))
        except Exception as e:  # 并发争用须干净驳回，不许抛穿
            果.append(e)

    t1 = threading.Thread(target=跑)
    t2 = threading.Thread(target=跑)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert len(果) == 2
    assert all(not isinstance(e, Exception) for e in 果), 果
    成功 = [r for r in 果 if r.get("坏点") == 1]
    驳回 = [r for r in 果 if r.get("驳回") == 1]
    assert len(成功) == 1
    assert len(驳回) == 1
    assert any("幂等" in "".join(str(m) for m in r["明细"]) for r in 驳回)
    assert len(目录.坏点列表()) == 1
    assert len(目录.报文列表()) == 1


def test_同号串行再装幂等驳回不双匣():
    assert 装载.装一批(坏点体)["坏点"] == 1
    再 = 装载.装一批(坏点体)
    assert 再["驳回"] == 1
    assert 再["坏点"] == 0
    assert len(目录.坏点列表()) == 1
    assert len(目录.报文列表()) == 1


def test_坏点匣报文编号库级唯一互斥():
    conn = 连接()
    try:
        conn.execute(
            """INSERT INTO 坏点匣(报文编号,站点键,原因,读数,观测时,入匣时)
               VALUES ('K-uniq-1','站-河东','r1',1.0,'2026-11-24T09:00:00Z','t')"""
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO 坏点匣(报文编号,站点键,原因,读数,观测时,入匣时)
                   VALUES ('K-uniq-1','站-北岭','r2',2.0,'2026-11-24T09:01:00Z','t')"""
            )
            conn.commit()
    finally:
        conn.close()
    assert len([r for r in 目录.坏点列表() if r["报文编号"] == "K-uniq-1"]) == 1

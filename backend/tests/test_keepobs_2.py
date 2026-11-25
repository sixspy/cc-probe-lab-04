"""失败测乙：对账灯不得把缺原观测时的匣行误标齐套。

红的条件：
- 匣行原观测时被抹空后，栏贯验仍亮“对齐/齐套”灯；
- 只读旁路保留接口不能区分该行原观测是否还拿得到。
"""
from app.db import 连接
from app.services import 装载, 贯验, 目录


坏点体 = {
    "批次编号": "keepobs-2",
    "报文": [{
        "报文编号": "K-bad-2",
        "站点键": "站-河东",
        "指标键": "PM25",
        "读数": 120.0,
        "观测时": "2026-11-24T09:05:00Z",
    }],
}


def test_齐套匣行对账灯绿():
    装载.装一批(坏点体)
    果 = 贯验.跑一次()
    assert 果["是否对齐"] is True
    assert 果["坏点齐套"] is True
    assert 果["坏点缺原观测"] == 0
    快照 = 贯验.只读快照()
    assert 快照["坏点齐套"] is True
    assert 快照["坏点缺原观测"] == 0


def test_缺原观测时匣行对账灯必须红且回读可区分():
    装载.装一批(坏点体)
    conn = 连接()
    try:
        conn.execute(
            "UPDATE 坏点匣 SET 观测时='' WHERE 报文编号=?", ("K-bad-2",)
        )
        conn.commit()
    finally:
        conn.close()

    快照 = 贯验.只读快照()
    assert 快照["坏点齐套"] is False
    assert 快照["坏点缺原观测"] == 1

    果 = 贯验.跑一次()
    assert 果["是否对齐"] is False
    assert 果["坏点齐套"] is False
    assert 果["坏点缺原观测"] == 1
    assert "原观测" in 果["说明"]

    行 = [r for r in 目录.坏点旁路保留列表() if r["报文编号"] == "K-bad-2"][0]
    assert 行["原观测可回读"] is False
    assert 行["原观测时"] == ""


def test_缺原读数匣行同样不得算齐套():
    装载.装一批(坏点体)
    conn = 连接()
    try:
        conn.execute(
            "UPDATE 坏点匣 SET 读数=NULL WHERE 报文编号=?", ("K-bad-2",)
        )
        conn.commit()
    finally:
        conn.close()
    快照 = 贯验.只读快照()
    assert 快照["坏点齐套"] is False
    assert 快照["坏点缺原观测"] == 1

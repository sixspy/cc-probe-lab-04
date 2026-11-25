"""失败测甲：坏点旁路保留——原观测字段。

红的条件：
- 坏点入库后，正式观测报文的读数/观测时/指标/站点被抹空仍算成功；
- 没有只读旁路保留接口可回读原观测时与读数；
- 坏点写入失败时观测命运没有同败回滚（半行留库）。
另串主链 happy path，防止为救本测改坏装载/结栏/贯验。
"""
import sqlite3

import pytest

from app.db import 连接
from app.services import 装载, 目录, 夹具, 结栏, 贯验


坏点体 = {
    "批次编号": "keepobs-1",
    "报文": [{
        "报文编号": "K-bad-1",
        "站点键": "站-河东",
        "指标键": "PM25",
        "读数": 120.0,
        "观测时": "2026-11-24T09:00:00Z",
    }],
}


def test_坏点入库后正式观测字段不得抹空():
    报告 = 装载.装一批(坏点体)
    assert 报告["坏点"] == 1
    报文 = {r["报文编号"]: r for r in 目录.报文列表()}["K-bad-1"]
    assert 报文["命运"] == "已坏点"
    assert 报文["读数"] == pytest.approx(120.0)
    assert 报文["观测时"] == "2026-11-24T09:00:00Z"
    assert 报文["指标键"] == "PM25"
    assert 报文["站点键"] == "站-河东"
    assert 报文["处理时"]
    匣 = {r["报文编号"]: r for r in 目录.坏点列表()}["K-bad-1"]
    assert 匣["读数"] == pytest.approx(120.0)
    assert 匣["观测时"] == "2026-11-24T09:00:00Z"


def test_只读旁路保留接口可回读原观测且可区分():
    装载.装一批(坏点体)
    行 = 目录.坏点旁路保留列表()
    assert len(行) == 1
    凭证行 = 行[0]
    assert 凭证行["报文编号"] == "K-bad-1"
    assert 凭证行["旁路凭证"]  # 凭证号非空
    assert 凭证行["保留形态"] == "旁路凭证冻结"
    assert 凭证行["原观测时"] == "2026-11-24T09:00:00Z"
    assert 凭证行["原读数"] == pytest.approx(120.0)
    assert 凭证行["原观测可回读"] is True
    # 匣行与观测流同票：凭证回读到的命运须与观测报文一致
    assert 凭证行["观测命运"] == "已坏点"
    assert 凭证行["观测批次编号"]


def test_坏点写入失败则观测命运同败回滚(monkeypatch):
    from app.services import 装载 as 装载模

    真连接 = 连接

    class 坏匣炸连接:
        def __init__(self):
            self._c = 真连接()

        def execute(self, sql, params=()):
            if "INSERT INTO 坏点匣" in str(sql):
                raise sqlite3.OperationalError("模拟坏点匣写入失败")
            return self._c.execute(sql, params)

        def commit(self):
            return self._c.commit()

        def close(self):
            return self._c.close()

        def __getattr__(self, name):
            return getattr(self._c, name)

    monkeypatch.setattr(装载模, "连接", 坏匣炸连接)
    with pytest.raises(sqlite3.OperationalError):
        装载.装一批(坏点体)
    # 同败：观测流不留半行，匣中无行，批次账不落
    assert 目录.报文列表() == []
    assert 目录.坏点列表() == []
    assert 目录.装载批次列表() == []


def test_主链happy_path不被旁路改坏():
    assert 装载.装一批(夹具.读取("入栏成汇总样例"))["入栏"] == 3
    assert 结栏.结当前栏()["汇总数"] == 2
    assert 贯验.跑一次()["是否对齐"] is True

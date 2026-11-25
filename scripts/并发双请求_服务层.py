#!/usr/bin/env python3
"""争用收工脚本（服务层版）：同号两路坏点并发，断言只成一匣一观测。

不依赖 HTTP 服务，直接在独立临时库上并发调用装载服务。
用法：python3 scripts/并发双请求_服务层.py
"""
import os
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(ROOT))

os.environ["数据目录"] = tempfile.mkdtemp(prefix="probe-race-")
os.environ["夹具目录"] = str(Path(__file__).resolve().parents[1] / "fixtures")

from app import seed  # noqa: E402
from app.services import 装载, 目录  # noqa: E402

seed.初始化库()

编号 = "K-race-script"
体 = {
    "批次编号": "并发双请求",
    "报文": [{
        "报文编号": 编号,
        "站点键": "站-河东",
        "指标键": "PM25",
        "读数": 120.0,
        "观测时": "2026-11-24T09:10:00Z",
    }],
}

果 = []


def 一路() -> None:
    try:
        果.append(装载.装一批(体))
    except Exception as e:  # 争用须干净驳回，不许抛穿
        果.append(e)


t1 = threading.Thread(target=一路)
t2 = threading.Thread(target=一路)
t1.start(); t2.start(); t1.join(); t2.join()

for i, r in enumerate(果, 1):
    if isinstance(r, Exception):
        print(f"响应{i}: 抛穿 {type(r).__name__}: {r}")
    else:
        print(f"响应{i}: 坏点={r['坏点']} 驳回={r['驳回']} 明细={r['明细']}")

匣 = [r for r in 目录.坏点列表() if r["报文编号"] == 编号]
观测 = [r for r in 目录.报文列表() if r["报文编号"] == 编号]
凭证 = [r for r in 目录.坏点旁路保留列表() if r["报文编号"] == 编号]
print(f"匣行={len(匣)}（须1） 观测流={len(观测)}（须1）")
print(f"凭证回读={凭证}")

成功 = [r for r in 果 if not isinstance(r, Exception) and r.get("坏点") == 1]
驳回 = [r for r in 果 if not isinstance(r, Exception) and r.get("驳回") == 1]
ok = (
    len(果) == 2
    and len(成功) == 1
    and len(驳回) == 1
    and len(匣) == 1
    and len(观测) == 1
    and 凭证
    and 凭证[0]["原观测可回读"] is True
    and 凭证[0]["同票一致"] is True
)
print("绿：同号并发只成一匣一观测，原观测凭证可回读。" if ok else "红：争用互斥或旁路保留失效。")
sys.exit(0 if ok else 1)

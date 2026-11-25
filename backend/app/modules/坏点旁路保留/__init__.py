"""模块：坏点旁路保留（probe-04 已落地）

选定工程形态：**旁路凭证冻结**（未采用“匣内摘要 + 只读归档包”双写两轨）。
- 坏点落下即生成旁路凭证（BP- 前缀），坏点匣行冻结原观测时与原读数；
- 匣行与观测报文同票：同库事务、同成同败，正式观测字段禁止回刷抹空；
- 同号再进匣：坏点匣报文编号唯一索引 + 装载进程内串行闸，并发只成一匣，另一路幂等驳回；
- 回读可区分：只读接口 GET /api/坏点旁路保留 联查匣行与观测流，逐行给“原观测可回读/已丢失”；
- 栏贯验对账灯并入坏点齐套：缺原观测时或缺读数的匣行判撕裂。

实现落点：app/services/装载.py（事务/凭证/互斥）、app/services/目录.py（只读联查）、
app/services/贯验.py（齐套对账）、app/seed.py（表结构与迁移）。
"""
NAME = "坏点旁路保留"
CONTRACT = "坏点匣凭旁路凭证冻结原读数与观测时，与观测报文同票同成败，供升格回放"
HOOKS = ("before_load", "after_load", "decide_gate", "before_close", "after_close", "extra_verify_checks")
形态 = "旁路凭证冻结"


def describe() -> dict:
    return {"空桩": NAME, "契约": CONTRACT, "钩子": list(HOOKS), "默认启用": True, "工程形态": 形态}


def before_load(batch: dict) -> dict:
    return batch


def after_load(report: dict) -> dict:
    return report


def decide_gate(event: dict, rules: dict) -> str:
    return "入栏"


def before_close(pen_id: str) -> None:
    return None


def after_close(report: dict) -> dict:
    return report


def extra_verify_checks(snapshot: dict) -> list[str]:
    缺 = int((snapshot or {}).get("坏点缺原观测", 0))
    return [f"坏点匣{缺}行缺原观测，旁路保留不齐套"] if 缺 else []

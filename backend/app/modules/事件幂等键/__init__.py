"""事件幂等键：独立凭证按业务键占坑，拒重复回刷。

骨签 hook-14-事件幂等占坑。

形态择定（二选一，禁止并存）：独立凭证按业务键占坑并拒重复回刷。
不采用双写归档轨——正式集合只读事件表（首票集），不存在第二读集合。

约束：
- 占坑与事件写入同一事务，同成败；业务键主键即锁，并发双会话只成一票。
- 对账是影子读，绝不混进正式集合（事件列表/事件详情只读事件表）。
"""
from __future__ import annotations
import sqlite3
from app.db import 连接
from app.services.时间 import 此刻

NAME = "事件幂等键"
骨签 = "hook-14-事件幂等占坑"

建表 = """
CREATE TABLE IF NOT EXISTS 幂等凭证 (
  业务键 TEXT PRIMARY KEY,
  事件号 TEXT NOT NULL,
  占坑态 TEXT NOT NULL DEFAULT '已占坑',
  重复回刷数 INTEGER NOT NULL DEFAULT 0,
  说明 TEXT NOT NULL DEFAULT '',
  占坑时 TEXT NOT NULL
);
"""


def 初始化(conn) -> None:
    """建幂等凭证表（独立凭证，按业务键占坑）。"""
    conn.executescript(建表)


def 占坑(conn, 业务键: str, 事件号: str) -> None:
    """在调用方同一连接（同一事务）里按业务键占坑。

    成功：凭证插入与随后的事件写入同生共死（同事务提交/回滚）。
    已占坑：整个被拒事务回滚，拒痕（重复回刷数+1、留痕）独立落库，再拒。
    """
    try:
        conn.execute(
            "INSERT INTO 幂等凭证(业务键,事件号,占坑态,重复回刷数,说明,占坑时) VALUES (?,?,?,?,?,?)",
            (业务键, 事件号, "已占坑", 0, "首票占坑", 此刻()),
        )
    except sqlite3.IntegrityError:
        conn.rollback()  # 占坑与写入同成败：被拒事务整体作废
        首 = conn.execute("SELECT 事件号 FROM 幂等凭证 WHERE 业务键=?", (业务键,)).fetchone()
        t = 此刻()
        conn.execute("UPDATE 幂等凭证 SET 重复回刷数=重复回刷数+1 WHERE 业务键=?", (业务键,))
        conn.execute(
            "INSERT INTO 操作留痕(时刻,操作,事件号,详情) VALUES (?,?,?,?)",
            (t, "重复回刷被拒", 事件号, f"业务键{业务键}已占坑"),
        )
        conn.commit()  # 拒痕独立落库，不随被拒事务回滚
        首票号 = 首["事件号"] if 首 else "?"
        raise ValueError(f"业务键{业务键}已占坑（首票{首票号}），拒绝重复回刷")


def 凭证列表() -> list:
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM 幂等凭证 ORDER BY 占坑时 DESC"
        ).fetchall()]
    finally:
        conn.close()


def 对账() -> dict:
    """事件队列对账（影子读）：按业务键核对首票与重复票。

    正式集合只认事件表首票集；重复票必须标「已拒」，不得标「已入」。
    """
    conn = 连接()
    try:
        凭证 = [dict(r) for r in conn.execute("SELECT * FROM 幂等凭证 ORDER BY 占坑时").fetchall()]
        明细 = []
        撕裂 = 0
        for z in 凭证:
            票 = [dict(r) for r in conn.execute(
                "SELECT 事件号,状态 FROM 事件 WHERE 业务键=? ORDER BY 入队时", (z["业务键"],)
            ).fetchall()]
            正式票数 = len(票)
            对齐 = 正式票数 == 1 and 票[0]["事件号"] == z["事件号"]
            if not 对齐:
                撕裂 += 1
            明细.append({
                "业务键": z["业务键"],
                "首票事件号": z["事件号"],
                "占坑态": z["占坑态"],
                "正式票数": 正式票数,
                "重复回刷数": z["重复回刷数"],
                "重复票标记": "已拒" if z["重复回刷数"] > 0 else "无",
                "判定": "对齐" if 对齐 else "撕裂",
            })
        无凭证 = conn.execute(
            "SELECT COUNT(*) AS c FROM 事件 WHERE 业务键 NOT IN (SELECT 业务键 FROM 幂等凭证)"
        ).fetchone()["c"]
        已拒 = sum(z["重复回刷数"] for z in 凭证)
        对齐全部 = 撕裂 == 0 and 无凭证 == 0
        return {
            "时刻": 此刻(),
            "凭证数": len(凭证),
            "正式事件数": conn.execute("SELECT COUNT(*) AS c FROM 事件").fetchone()["c"],
            "重复回刷已拒数": 已拒,
            "无凭证事件数": 无凭证,
            "撕裂数": 撕裂,
            "是否对齐": 对齐全部,
            "说明": ("同业务键仅首票入队，重复回刷已拒；正式集合只读事件表首票集"
                    if 对齐全部 else f"存在撕裂{撕裂}处或无凭证事件{无凭证}行，需核查"),
            "明细": 明细,
        }
    finally:
        conn.close()

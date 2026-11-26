from datetime import datetime, timezone
from app.db import 连接
from app.modules import 事件幂等键

建表 = """
CREATE TABLE IF NOT EXISTS 用户 (
  账号 TEXT PRIMARY KEY,
  密码哈希 TEXT NOT NULL,
  角色 TEXT NOT NULL DEFAULT '管理员'
);
CREATE TABLE IF NOT EXISTS 签名规 (
  键 TEXT PRIMARY KEY,
  值 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 投递端点 (
  端点键 TEXT PRIMARY KEY,
  名称 TEXT NOT NULL,
  回调URL TEXT NOT NULL,
  密钥版本 TEXT NOT NULL DEFAULT 'v1',
  启用 INTEGER NOT NULL DEFAULT 1,
  说明 TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS 事件 (
  事件号 TEXT PRIMARY KEY,
  业务键 TEXT NOT NULL DEFAULT '',
  事件类型 TEXT NOT NULL,
  端点键 TEXT NOT NULL DEFAULT '',
  载荷摘要 TEXT NOT NULL DEFAULT '',
  优先级 TEXT NOT NULL DEFAULT '普通',
  状态 TEXT NOT NULL DEFAULT '待投',
  入队时 TEXT NOT NULL,
  更新时 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 投递尝试 (
  尝试号 TEXT PRIMARY KEY,
  事件号 TEXT NOT NULL,
  端点键 TEXT NOT NULL,
  签名摘要 TEXT NOT NULL DEFAULT '',
  状态 TEXT NOT NULL DEFAULT '失败',
  响应码 INTEGER NOT NULL DEFAULT 0,
  说明 TEXT NOT NULL DEFAULT '',
  投递时 TEXT NOT NULL,
  FOREIGN KEY (事件号) REFERENCES 事件(事件号),
  FOREIGN KEY (端点键) REFERENCES 投递端点(端点键)
);
CREATE TABLE IF NOT EXISTS 死信 (
  死信号 TEXT PRIMARY KEY,
  事件号 TEXT NOT NULL UNIQUE,
  端点键 TEXT NOT NULL,
  失败次数 INTEGER NOT NULL DEFAULT 0,
  末次原因 TEXT NOT NULL DEFAULT '',
  状态 TEXT NOT NULL DEFAULT '待处置',
  入匣时 TEXT NOT NULL,
  FOREIGN KEY (事件号) REFERENCES 事件(事件号)
);
CREATE TABLE IF NOT EXISTS 互证批次 (
  批次号 INTEGER PRIMARY KEY AUTOINCREMENT,
  时刻 TEXT NOT NULL,
  事件总数 INTEGER NOT NULL,
  已投递数 INTEGER NOT NULL,
  死信数 INTEGER NOT NULL,
  待投数 INTEGER NOT NULL,
  是否对齐 INTEGER NOT NULL,
  说明 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 操作留痕 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  时刻 TEXT NOT NULL,
  操作 TEXT NOT NULL,
  事件号 TEXT NOT NULL DEFAULT '',
  详情 TEXT NOT NULL DEFAULT ''
);
"""


def 此刻() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def 初始化库() -> None:
    conn = 连接()
    conn.executescript(建表)
    事件幂等键.初始化(conn)  # 独立凭证表：按业务键占坑
    # 存量库迁移：事件表补业务键列
    列 = [r["name"] for r in conn.execute("PRAGMA table_info(事件)").fetchall()]
    if "业务键" not in 列:
        conn.execute("ALTER TABLE 事件 ADD COLUMN 业务键 TEXT NOT NULL DEFAULT ''")
    conn.execute("UPDATE 事件 SET 业务键=事件号 WHERE 业务键=''")
    if conn.execute("SELECT COUNT(*) AS c FROM 用户").fetchone()["c"] == 0:
        conn.execute("INSERT INTO 用户(账号,密码哈希,角色) VALUES (?,?,?)", ("admin", "123456", "管理员"))
    if conn.execute("SELECT COUNT(*) AS c FROM 签名规").fetchone()["c"] == 0:
        for k, v in {
            "最大重试": "3",
            "产品名": "投递台",
            "主链": "端点登记→事件入队→签名投递→失败重试与死信→投递账互证",
            "签名算法": "HMAC-SHA256",
            "超时秒": "5",
            "幂等口径": "同业务键仅首票入队，重复回刷已拒；占坑与写入同成败",
        }.items():
            conn.execute("INSERT INTO 签名规(键,值) VALUES (?,?)", (k, v))
    conn.execute(
        "INSERT OR IGNORE INTO 签名规(键,值) VALUES ('幂等口径','同业务键仅首票入队，重复回刷已拒；占坑与写入同成败')"
    )
    if conn.execute("SELECT COUNT(*) AS c FROM 投递端点").fetchone()["c"] == 0:
        for row in [
            ("ep-billing", "账单回调", "https://example.local/hooks/billing", "v1", 1, "账务"),
            ("ep-notify", "通知回调", "https://example.local/hooks/notify", "v1", 1, "通知"),
            ("ep-audit", "审计回调", "https://example.local/hooks/audit", "v2", 1, "审计"),
            ("ep-legacy", "旧版回调", "https://example.local/hooks/legacy", "v1", 0, "停用"),
            ("ep-partner", "合作方回调", "https://partner.local/ingest", "v1", 1, "外部"),
        ]:
            conn.execute(
                "INSERT INTO 投递端点(端点键,名称,回调URL,密钥版本,启用,说明) VALUES (?,?,?,?,?,?)",
                row,
            )
    if conn.execute("SELECT COUNT(*) AS c FROM 事件").fetchone()["c"] == 0:
        t = 此刻()
        for row in [
            ("EVT-demo-01", "invoice.paid", "ep-billing", "invoice=1001", "普通", "待投"),
            ("EVT-demo-02", "user.created", "ep-notify", "user=u42", "普通", "投递中"),
            ("EVT-demo-03", "order.refund", "ep-audit", "order=908", "紧急", "待投"),
            ("EVT-demo-04", "user.updated", "ep-notify", "user=u7", "低", "已投递"),
            ("EVT-demo-05", "invoice.failed", "ep-billing", "invoice=1002", "普通", "死信"),
        ]:
            conn.execute(
                "INSERT INTO 事件(事件号,事件类型,端点键,载荷摘要,优先级,状态,入队时,更新时) VALUES (?,?,?,?,?,?,?,?)",
                (*row, t, t),
            )
        conn.execute(
            "INSERT INTO 投递尝试(尝试号,事件号,端点键,签名摘要,状态,响应码,说明,投递时) VALUES (?,?,?,?,?,?,?,?)",
            ("TRY-demo-01", "EVT-demo-04", "ep-notify", "sig-demo", "成功", 200, "ok", t),
        )
        conn.execute(
            "INSERT INTO 死信(死信号,事件号,端点键,失败次数,末次原因,状态,入匣时) VALUES (?,?,?,?,?,?,?)",
            ("DL-demo-01", "EVT-demo-05", "ep-billing", 3, "连接超时", "待处置", t),
        )
        conn.execute(
            "INSERT INTO 操作留痕(时刻,操作,事件号,详情) VALUES (?,?,?,?)",
            (t, "种子", "", "初始化投递台样例"),
        )
    # 存量事件回填占坑凭证：业务键=事件号，一事件一凭证
    conn.execute("UPDATE 事件 SET 业务键=事件号 WHERE 业务键=''")
    conn.execute(
        "INSERT OR IGNORE INTO 幂等凭证(业务键,事件号,占坑态,重复回刷数,说明,占坑时) "
        "SELECT 业务键,事件号,'已占坑',0,'存量回填',入队时 FROM 事件"
    )
    conn.commit()
    conn.close()

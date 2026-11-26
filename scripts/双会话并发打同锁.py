"""双会话并发打同锁：两个登录会话同业务键并发入队，只准一路成。

用法：python3 scripts/双会话并发打同锁.py [端口]
依赖：仅需标准库；目标服务已在 端口 上运行。
"""
import json
import sys
import threading
import urllib.parse
import urllib.request
import http.cookiejar

端口 = sys.argv[1] if len(sys.argv) > 1 else "8514"
基址 = f"http://127.0.0.1:{端口}"
业务键 = "BIZ-HOOK14-并发打锁"


def 开(路径: str) -> str:
    return 基址 + urllib.parse.quote(路径)


def 开会话() -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    req = urllib.request.Request(
        开("/api/登录"),
        data=json.dumps({"账号": "admin", "密码": "123456"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with op.open(req) as r:
        assert json.load(r)["ok"], "登录失败"
    return op


def 入队(op, 事件号):
    req = urllib.request.Request(
        开("/api/事件/入队"),
        data=json.dumps({
            "事件号": 事件号,
            "业务键": 业务键,
            "事件类型": "invoice.paid",
            "端点键": "ep-billing",
            "载荷摘要": "并发打锁",
        }).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with op.open(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def main() -> int:
    甲会话, 乙会话 = 开会话(), 开会话()  # 双会话
    闸 = threading.Barrier(2)
    结果 = {}

    def 打(名, op, 事件号):
        闸.wait()
        结果[名] = 入队(op, 事件号)

    ts = [
        threading.Thread(target=打, args=("甲", 甲会话, "EVT-HOOK14-并发甲")),
        threading.Thread(target=打, args=("乙", 乙会话, "EVT-HOOK14-并发乙")),
    ]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    状态 = sorted(v[0] for v in 结果.values())
    for 名, (码, 体) in sorted(结果.items()):
        摘要 = 体.get("错误") or f"已入队:{体.get('事件号', '?')}"
        print(f"会话{名}: HTTP {码} · {摘要}")
    assert 状态 == [200, 400], f"必须一成一拒，实际 {状态}"
    print(f"通过：同业务键「{业务键}」双会话并发，一成一拒，同锁生效")
    return 0


if __name__ == "__main__":
    sys.exit(main())

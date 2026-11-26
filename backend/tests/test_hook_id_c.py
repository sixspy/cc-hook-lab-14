"""争用失败测：同业务键双会话并发入队，只准一路成。

两路并发各开各的库连接（双会话），同业务键、两展示号同时打同一把占坑锁。
缺锁时两路双成功、正式待投双行 —— 本测必须红。
"""
import os, tempfile, threading
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ['数据目录'] = _tmp
os.environ['夹具目录'] = str(Path(__file__).resolve().parents[2] / 'fixtures')

from app import seed
from app.services import 入队, 夹具, 签名目录


def setup_module():
    seed.初始化库()


def test_同业务键双会话并发只成一票():
    体 = 夹具.读取('同业务键两展示号夹具连灌')
    甲, 乙 = 体['事件'][0], 体['事件'][1]
    键 = 甲['业务键'] + '-测丙'
    甲 = {**甲, '业务键': 键, '事件号': 甲['事件号'] + '-测丙'}
    乙 = {**乙, '业务键': 键, '事件号': 乙['事件号'] + '-测丙'}

    结果 = []
    闸 = threading.Barrier(2)

    def 打(item):
        闸.wait()
        try:
            入队.建事件(dict(item))
            结果.append('成')
        except ValueError:
            结果.append('拒')

    ts = [threading.Thread(target=打, args=(x,)) for x in (甲, 乙)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    assert 结果.count('成') == 1, '同业务键并发只准一路占坑成功'
    assert 结果.count('拒') == 1, '另一路必须被拒，不得双成功'
    正式 = [r for r in 签名目录.事件列表() if r.get('业务键') == 键]
    assert len(正式) == 1, '正式集合不得出现同业务键双行'

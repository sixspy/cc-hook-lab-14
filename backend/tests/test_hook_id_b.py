"""失败测乙（校验/对账侧）：事件队列对账不得把重复票标成已入。

夹具「同业务键两展示号夹具连灌」连灌后：
- 正式集合（事件表）对该业务键只留首票；
- 幂等对账必须把第二票标成「已拒」，而不是标成「已入」。
未挂「事件幂等键」占坑与对账前，本测必须红。
"""
import os, tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ['数据目录'] = _tmp
os.environ['夹具目录'] = str(Path(__file__).resolve().parents[2] / 'fixtures')

from app import seed
from app.modules import 事件幂等键
from app.services import 入队, 夹具, 签名目录


def setup_module():
    seed.初始化库()


def test_事件队列对账不得把重复票标成已入():
    体 = 夹具.读取('同业务键两展示号夹具连灌')
    甲, 乙 = 体['事件'][0], 体['事件'][1]
    键 = 甲['业务键'] + '-测乙'
    甲 = {**甲, '业务键': 键, '事件号': 甲['事件号'] + '-测乙'}
    乙 = {**乙, '业务键': 键, '事件号': 乙['事件号'] + '-测乙'}

    入队.建事件(甲)
    try:
        入队.建事件(乙)  # 挂上占坑后这一票必须被拒
    except ValueError:
        pass

    正式 = [r for r in 签名目录.事件列表() if r.get('业务键') == 键]
    assert len(正式) == 1, '正式集合对该业务键只留首票，重复票不得混入'
    assert 正式[0]['事件号'] == 甲['事件号'], '留下的必须是首票'

    rep = 事件幂等键.对账()
    行 = [x for x in rep['明细'] if x['业务键'] == 键]
    assert len(行) == 1, '对账必须按业务键出一行'
    assert 行[0]['重复回刷数'] == 1, '第二票是一次重复回刷'
    assert 行[0]['重复票标记'] == '已拒', '重复票必须标已拒，不得标已入'
    assert 行[0]['判定'] == '对齐', '首票占坑、重复已拒，对账必须对齐'

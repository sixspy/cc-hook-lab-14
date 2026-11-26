"""失败测甲（入队侧）：同业务键第二票连入队，现行待投不得再增。

夹具「同业务键两展示号夹具连灌」造事故：同一业务键、两个展示号（事件号）连灌。
未挂「事件幂等键」占坑前，第二票会再占一行待投 —— 本测必须红。
"""
import os, tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ['数据目录'] = _tmp
os.environ['夹具目录'] = str(Path(__file__).resolve().parents[2] / 'fixtures')

import pytest

from app import seed
from app.services import 入队, 夹具, 签名目录


def setup_module():
    seed.初始化库()


def _待投数() -> int:
    return 签名目录.概览()['待投']


def test_同业务键第二票现行待投仍增_必须拒():
    体 = 夹具.读取('同业务键两展示号夹具连灌')
    甲, 乙 = 体['事件'][0], 体['事件'][1]
    assert 甲['业务键'] == 乙['业务键'], '夹具必须同业务键'
    assert 甲['事件号'] != 乙['事件号'], '夹具必须两展示号'
    键 = 甲['业务键'] + '-测甲'
    甲 = {**甲, '业务键': 键, '事件号': 甲['事件号'] + '-测甲'}
    乙 = {**乙, '业务键': 键, '事件号': 乙['事件号'] + '-测甲'}

    n0 = _待投数()
    首票 = 入队.建事件(甲)
    assert 首票['状态'] == '待投'
    assert _待投数() == n0 + 1, '首票入队，待投 +1'

    with pytest.raises(ValueError):
        入队.建事件(乙)  # 同业务键第二票：必须被拒，不得再占待投行
    assert _待投数() == n0 + 1, '重复票被拒后，现行待投行数不得再增'

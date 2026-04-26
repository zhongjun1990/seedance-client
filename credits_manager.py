"""
HermeQuant 积分账户管理系统
- 本地存储积分余额、交易流水
- 支持充值码兑换、消费预扣、失败退款
- 数据路径: ~/.hermequant/credits/
"""

import os
import json
import hashlib
import uuid
import time
from datetime import datetime, timezone
from pathlib import Path

# ============== 配置 ==============

DATA_DIR = Path.home() / ".hermequant" / "credits"
DATA_DIR.mkdir(parents=True, exist_ok=True)

BALANCE_FILE = DATA_DIR / "balance.json"
TRANSACTIONS_FILE = DATA_DIR / "transactions.json"
USERS_FILE = DATA_DIR / "users.json"

# ============== 费率表（10积分=1元）==============

RATE_TABLE = {
    "t2v_6s":   {"name": "文字→视频 6秒",  "cost": 120, "duration": 6,  "type": "text2video"},
    "t2v_11s":  {"name": "文字→视频 11秒", "cost": 200, "duration": 11, "type": "text2video"},
    "i2v_6s":   {"name": "图片→视频 6秒",  "cost": 150, "duration": 6,  "type": "image2video"},
    "i2v_11s":  {"name": "图片→视频 11秒", "cost": 250, "duration": 11, "type": "image2video"},
    "audio":    {"name": "音频参考",         "cost": 50,  "duration": 0,  "type": "addon"},
}

# ============== 工具函数 ==============

def _load_json(path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def _save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _tz():
    return datetime.now(timezone.utc).astimezone()

def _gen_tx_id():
    return f"TX{uuid.uuid4().hex[:12].upper()}"

# ============== 用户账户 ==============

def init_user():
    """初始化当前用户账户"""
    user_data = _load_json(USERS_FILE, {})
    uid = "default"  # 单机单用户，后续可扩展多用户

    if uid not in user_data:
        user_data[uid] = {
            "id": uid,
            "created_at": _tz().isoformat(),
            "bonus_received": False,
        }
        _save_json(USERS_FILE, user_data)

    balance_data = _load_json(BALANCE_FILE, {})
    if uid not in balance_data:
        balance_data[uid] = {
            "balance": 0,
            "last_updated": _tz().isoformat(),
        }
        _save_json(BALANCE_FILE, balance_data)

    trans_data = _load_json(TRANSACTIONS_FILE, {})
    if uid not in trans_data:
        trans_data[uid] = []
        _save_json(TRANSACTIONS_FILE, trans_data)

    return uid

def get_balance(uid="default"):
    """查询积分余额"""
    balance_data = _load_json(BALANCE_FILE, {})
    return balance_data.get(uid, {}).get("balance", 0)

def get_transactions(uid="default", limit=50):
    """查询交易流水"""
    trans_data = _load_json(TRANSACTIONS_FILE, {})
    txs = trans_data.get(uid, [])
    return sorted(txs, key=lambda x: x["time"], reverse=True)[:limit]

def _add_transaction(uid, tx_type, amount, desc, ref_id=None):
    """添加交易流水"""
    trans_data = _load_json(TRANSACTIONS_FILE, {})
    tx = {
        "id": _gen_tx_id(),
        "type": tx_type,       # recharge / consume / refund / bonus
        "amount": amount,
        "desc": desc,
        "ref_id": ref_id,     # 充值码ID / 任务ID
        "balance_after": get_balance(uid) + amount,
        "time": _tz().isoformat(),
    }
    trans_data.setdefault(uid, []).append(tx)
    _save_json(TRANSACTIONS_FILE, trans_data)

    # 更新余额
    balance_data = _load_json(BALANCE_FILE, {})
    balance_data[uid] = {
        "balance": get_balance(uid) + amount,
        "last_updated": _tz().isoformat(),
    }
    _save_json(BALANCE_FILE, balance_data)

def deduct_balance(amount, task_id, task_desc, uid="default"):
    """
    预扣积分（任务提交时）
    返回 (success, message)
    """
    current = get_balance(uid)
    if current < amount:
        return False, f"余额不足：当前 {current}积分，需要 {amount}积分"

    balance_data = _load_json(BALANCE_FILE, {})
    balance_data[uid] = {
        "balance": current - amount,
        "last_updated": _tz().isoformat(),
    }
    _save_json(BALANCE_FILE, balance_data)

    _add_transaction(uid, "consume", -amount, task_desc, ref_id=task_id)
    return True, f"已扣 {amount}积分，剩余 {current - amount}积分"

def refund_balance(amount, task_id, reason, uid="default"):
    """退款（任务失败时）"""
    current = get_balance(uid)
    balance_data = _load_json(BALANCE_FILE, {})
    balance_data[uid] = {
        "balance": current + amount,
        "last_updated": _tz().isoformat(),
    }
    _save_json(BALANCE_FILE, balance_data)
    _add_transaction(uid, "refund", amount, f"{reason}，退款 {amount}积分", ref_id=task_id)
    return True, f"已退款 {amount}积分"

def apply_bonus(uid="default"):
    """发放新用户赠送积分（仅一次）"""
    user_data = _load_json(USERS_FILE, {})
    if user_data.get(uid, {}).get("bonus_received"):
        return False, "已领取过赠送积分"

    BONUS = 30  # 30积分 = 3元
    current = get_balance(uid)
    balance_data = _load_json(BALANCE_FILE, {})
    balance_data[uid] = {
        "balance": current + BONUS,
        "last_updated": _tz().isoformat(),
    }
    _save_json(BALANCE_FILE, balance_data)

    user_data[uid]["bonus_received"] = True
    _save_json(USERS_FILE, user_data)

    _add_transaction(uid, "bonus", BONUS, "新用户赠送 3元体验积分")
    return True, f"已赠送 {BONUS}积分（3元）"

# ============== 充值码 ==============

def generate_recharge_code(amount_points, code_len=16):
    """
    生成充值码（管理员工具）
    amount_points: 积分数量（10积分=1元）
    """
    raw = f"{uuid.uuid4().hex}{time.time_ns()}"
    code = hashlib.sha256(raw.encode()).hexdigest()[:code_len].upper()

    codes_file = DATA_DIR / "codes.json"
    codes = _load_json(codes_file, {})

    codes[code] = {
        "amount": amount_points,
        "created_at": _tz().isoformat(),
        "used": False,
        "used_at": None,
        "used_by": None,
    }
    _save_json(codes_file, codes)
    return code

def redeem_code(code, uid="default"):
    """兑换充值码"""
    code = code.strip().upper()
    codes_file = DATA_DIR / "codes.json"
    codes = _load_json(codes_file, {})

    if code not in codes:
        return False, "充值码无效"

    entry = codes[code]
    if entry["used"]:
        return False, "充值码已使用"

    # 充值
    amount = entry["amount"]
    current = get_balance(uid)
    balance_data = _load_json(BALANCE_FILE, {})
    balance_data[uid] = {
        "balance": current + amount,
        "last_updated": _tz().isoformat(),
    }
    _save_json(BALANCE_FILE, balance_data)

    # 标记已用
    entry["used"] = True
    entry["used_at"] = _tz().isoformat()
    entry["used_by"] = uid
    _save_json(codes_file, codes)

    _add_transaction(uid, "recharge", amount, f"充值码兑换 {amount}积分（等价 {amount//10}元）", ref_id=code)
    return True, f"充值成功：+{amount}积分，剩余 {current + amount}积分"

def list_codes():
    """列出所有充值码（管理员用）"""
    codes_file = DATA_DIR / "codes.json"
    return _load_json(codes_file, {})

def get_rate_key(video_type, duration, has_audio=False):
    """获取费率key"""
    duration = int(duration)
    if video_type == "text":
        key = "t2v_6s" if duration <= 6 else "t2v_11s"
    else:
        key = "i2v_6s" if duration <= 6 else "i2v_11s"
    return key

# ============== 初始化 ==============

def init():
    uid = init_user()
    return uid

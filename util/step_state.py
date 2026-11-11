# -*- coding: utf-8 -*-
"""
"只增不减"状态文件。GitHub Actions 每次都是全新容器,
所以把今日已提交的最高值落盘到仓库根目录的 step_state.json,
由 workflow 里已有的 `git add .` 一起提交回去,下次运行读取。

没有这个守卫时,按时间递增的区间在多账号/宽区间下可能重叠,
导致后一次提交的步数比前一次小 —— 微信运动会显示步数倒退。
"""
import json
import os
from datetime import datetime, timedelta, timezone

STATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "step_state.json"
)

BEIJING = timezone(timedelta(hours=8))


def _today():
    return datetime.now(BEIJING).strftime("%Y-%m-%d")


def _read():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _write(data):
    try:
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_PATH)
    except Exception:
        pass


def today_max(user=None):
    """今日已提交的最高步数,跨天自动失效"""
    data = _read()
    entry = data.get(user) if user else data.get("_default")
    if not isinstance(entry, dict) or entry.get("date") != _today():
        return 0
    try:
        return int(entry.get("max") or 0)
    except Exception:
        return 0


def raise_floor(lo, user=None):
    """把区间下限抬到不低于今日已提交值"""
    floor = today_max(user)
    return max(int(lo), floor) if floor else int(lo)


def record(step, user=None):
    """提交成功后记录,只增不减"""
    key = user or "_default"
    data = _read()
    entry = data.get(key)
    if not isinstance(entry, dict) or entry.get("date") != _today():
        entry = {"date": _today(), "max": 0}
    try:
        entry["max"] = max(int(entry.get("max") or 0), int(step))
    except Exception:
        entry["max"] = int(step)
    data[key] = entry
    _write(data)

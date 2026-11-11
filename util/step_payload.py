# -*- coding: utf-8 -*-
"""
步数报文构造模块 - 只用标准库,可独立测试。

把 mimotion / WeChatStep 原本那份 2021-08-07 的固定模板,
按目标步数重算成一份内部自洽的记录:
  ttl(总步数) / dis(距离) / cal(热量) / stage(分段) 全部一致,
  活动时段也不再固定挤在清晨 3 小时内。

原始模板里 ttl=18272 但 stage 合计 23904 步、dis=10627 但分段合计 20727 米,
上游只替换 ttl 一个字段,所以提交的是一份自相矛盾的记录。这里一并修掉。
"""
import json
import random
import re
import urllib.parse

SUMMARY_HEAD = "%22summary%22%3A%22"
SUMMARY_TAIL = "%22%2C%22source%22"

STRIDE_RANGE = (0.68, 0.75)   # 步幅 米/步
KCAL_PER_METER = 0.048        # 每米消耗 千卡
PURE_WALKING = False          # True 则清零 rn/runDist/runCal(模板里跑步占 72%,偏高)


def _rebuild_summary(summary, total_steps):
    stp = summary["stp"]
    old_total = max(int(stp.get("ttl") or 1), 1)
    ratio = total_steps / old_total
    stride = random.uniform(*STRIDE_RANGE)

    stp["ttl"] = total_steps
    stp["dis"] = int(total_steps * stride)
    stp["cal"] = int(stp["dis"] * KCAL_PER_METER)
    for key in ("runDist", "runCal", "rn", "wk"):
        if key in stp:
            stp[key] = int(round(stp[key] * ratio))

    stages = stp.get("stage") or []
    if stages:
        old_sum = sum(s.get("step") or 0 for s in stages) or 1
        acc = 0
        for idx, seg in enumerate(stages):
            if idx == len(stages) - 1:
                n = total_steps - acc
            else:
                n = int(round(total_steps * (seg.get("step") or 0) / old_sum))
                acc += n
            n = max(n, 0)
            seg["step"] = n
            seg["dis"] = int(n * stride * random.uniform(0.96, 1.04))
            seg["cal"] = int(seg["dis"] * KCAL_PER_METER)
        _spread_stage_time(stages)

    if PURE_WALKING:
        stp["rn"] = 0
        stp["runDist"] = 0
        stp["runCal"] = 0
    return summary


def _spread_stage_time(stages):
    """把原本集中在 05:27~08:42 的 17 段活动铺到一整天"""
    n = len(stages)
    day_start = random.randint(7 * 60, 9 * 60)
    day_end = random.randint(19 * 60, 22 * 60)
    while day_end - day_start < 8 * 60:
        day_end = day_start + 8 * 60

    old_durs = [max(1, int(s.get("stop") or 0) - int(s.get("start") or 0)) for s in stages]
    tot_old = sum(old_durs)
    span = day_end - day_start

    fill = random.uniform(0.45, 0.60)
    durs = [max(3, int(span * fill * d / tot_old)) for d in old_durs]
    if sum(durs) > span - n:
        scale = max((span - n) / max(sum(durs), 1), 0.05)
        durs = [max(2, int(d * scale)) for d in durs]

    slack = max(span - sum(durs), n)
    weights = [random.uniform(0.4, 1.6) for _ in range(n)]
    wsum = sum(weights)

    t = day_start
    for i, seg in enumerate(stages):
        start = min(t, 1439)
        stop = min(start + durs[i], 1440)
        seg["start"], seg["stop"] = start, max(stop, start + 1)
        t = seg["stop"] + int(slack * weights[i] / wsum)


def _legacy_replace(raw, total_steps, date_str):
    """结构变化时的兜底:退回上游做法,只替换日期和 ttl"""
    m = re.search(r"%22date%22%3A%22(\d{4}-\d{2}-\d{2})%22", raw)
    if m:
        raw = raw.replace(m.group(1), date_str, 1)
    m = re.search(r"ttl%5C%22%3A(\d+)%2C", raw)
    if m:
        raw = raw.replace(m.group(1), str(total_steps), 1)
    return raw


def build_payload(raw, total_steps, date_str):
    """raw 为原始的百分号编码报文,返回替换好的新报文"""
    total_steps = int(total_steps)
    head = raw.find(SUMMARY_HEAD)
    tail = raw.find(SUMMARY_TAIL, head + 1) if head >= 0 else -1
    if head < 0 or tail < 0:
        return _legacy_replace(raw, total_steps, date_str)

    try:
        inner = raw[head + len(SUMMARY_HEAD):tail]
        summary = json.loads(json.loads('"' + urllib.parse.unquote(inner) + '"'))
        _rebuild_summary(summary, total_steps)
        rebuilt = json.dumps(summary, separators=(",", ":"), ensure_ascii=True)
        escaped = json.dumps(rebuilt, ensure_ascii=True)[1:-1]
        encoded = urllib.parse.quote(escaped, safe="")
    except Exception:
        return _legacy_replace(raw, total_steps, date_str)

    payload = raw[:head + len(SUMMARY_HEAD)] + encoded + raw[tail:]
    payload = re.sub(r"%22date%22%3A%22\d{4}-\d{2}-\d{2}%22",
                     "%22date%22%3A%22" + date_str + "%22", payload, count=1)
    return payload

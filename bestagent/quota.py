#!/usr/bin/env python3
"""限速模块：采集操作**记账（日志）** + 随机延迟（账号保护）

🔴 **死命令（2026-09-16 老板拍板，以后都遵守）**：**测试阶段不设人为额度**。
   本地不因"每日上限 / 每页配额 / 页数硬顶 / 详情总数保险丝"而少采或停采。
   本模块从此只做两件事：
     1. **记账**（`record()` / `stats()`）—— 让你看得见花了多少；**看得见 ≠ 拦**；
     2. **真人节奏**（`delay()`）—— 账号保护，保留。
   `check()` 默认**恒返回 True（不拦）**。要恢复拦截：`quota_config.json` 里写 `"enforce": true`
   （**上线前再谈限额**，届时才打开）。下面的 `*_daily_limit` 数字现在只是"记账刻度"，不产生阻断。

用法：
  from quota import Quota
  q = Quota()
  if q.check("search"):          # 测试期恒为 True（只记账不拦）
      ...执行搜索...
      q.record("search")         # 记账（当日志看）
  q.delay()                      # 轮间随机延迟（像真人）

限额默认值可改：data/usage/quota_config.json（不存在则用内置默认）
"""
from __future__ import annotations

import json
import random
import sys
import time
from datetime import date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DEFAULT_CONFIG = {
    # 🔴 enforce=False = 死命令：**只记账、不拦**（测试阶段不设人为额度）。
    #    下面这些数字现在只是"记账刻度"（看得见花了多少），**不产生任何阻断行为**。
    #    上线前再谈限额：那时把它设为 true 才恢复拦截。
    "enforce": False,
    "search_daily_limit": 80,    # 记账刻度（enforce=False 时不拦）
    "extract_daily_limit": 500,  # 记账刻度（enforce=False 时不拦）
    "min_delay_sec": 8,          # 轮间最小延迟（秒）（模拟真人节奏的核心，勿调太短）
    "max_delay_sec": 20,         # 轮间最大延迟（秒）
    "detail_daily_limit": 100,   # 记账刻度（enforce=False 时不拦）；平台真正统计的是"查看简历数"
}


class Quota:
    def __init__(self, path: str = "data/usage/quota.json",
                 config_path: str = "data/usage/quota_config.json",
                 config: dict | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.config = dict(DEFAULT_CONFIG)
        cfg_file = Path(config_path)
        if cfg_file.exists():
            try:
                self.config.update(json.loads(cfg_file.read_text(encoding="utf-8")))
            except Exception:
                pass
        if config:
            self.config.update(config)
        self.data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"days": {}}

    def _day(self) -> dict:
        return self.data["days"].setdefault(date.today().isoformat(), {"search": 0, "extract": 0, "last": 0})

    def check(self, action: str) -> bool:
        """action 今日是否还有额度。

        🔴 死命令（测试阶段不设人为额度）：`enforce=False`（默认）时**恒为 True**——只记账不拦。
        """
        if not self.config.get("enforce", False):
            return True
        limit = self.config.get(f"{action}_daily_limit")
        if limit is None:
            return True
        return self._day().get(action, 0) < limit

    def remaining(self, action: str) -> int:
        """距离"记账刻度"还剩多少。**测试期这个数不拦任何事，只作参考**；未设刻度 → -1（不限）。"""
        limit = self.config.get(f"{action}_daily_limit")
        if limit is None or not self.config.get("enforce", False):
            return -1
        return max(0, limit - self._day().get(action, 0))

    def record(self, action: str, count: int = 1) -> None:
        d = self._day()
        d[action] = d.get(action, 0) + count
        d["last"] = time.time()
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def delay(self, min_sec: float | None = None, max_sec: float | None = None) -> None:
        lo = min_sec if min_sec is not None else self.config["min_delay_sec"]
        hi = max_sec if max_sec is not None else self.config["max_delay_sec"]
        wait = random.uniform(lo, hi)
        print(f"  ⏱ 限速等待 {wait:.1f}s…")
        time.sleep(wait)

    def stats(self) -> str:
        """一行账本（**日志口径**：花了多少；测试期后面这些数字不构成上限）。"""
        d = self._day()
        parts = []
        for k, v in self.config.items():
            if k.endswith("_daily_limit"):
                act = k.replace("_daily_limit", "")
                parts.append(f"{act} {d.get(act, 0)}/{v}")
        return f"今日账本: " + " | ".join(parts)


if __name__ == "__main__":
    # 自测：①死命令下 check 恒 True（只记账不拦）②enforce=True 时才恢复拦截
    q = Quota(path="data/usage/_quota_test.json", config={"search_daily_limit": 2,
                                                          "extract_daily_limit": 5})
    print("初始:", q.stats())
    assert q.check("search") is True
    q.record("search")
    q.record("search")
    q.record("search")
    assert q.check("search") is True, "死命令：测试阶段不设人为额度，check 必须恒为 True"
    assert q.remaining("search") == -1, "不拦时 remaining 应为 -1（不限）"
    print("超记账刻度仍不拦:", q.stats())

    q2 = Quota(path="data/usage/_quota_test.json",
               config={"enforce": True, "search_daily_limit": 2, "extract_daily_limit": 5})
    assert q2.check("search") is False, "enforce=True 时应恢复拦截（上线前才用）"
    assert q2.remaining("search") == 0
    print("enforce=True 恢复拦截:", q2.stats())
    print("✅ quota 自测通过")

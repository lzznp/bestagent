#!/usr/bin/env python3
"""限速模块：采集操作记账 + 限额检查 + 随机延迟（防账号风控，对应授权矩阵"自主+限量限速"）

用法：
  from quota import Quota
  q = Quota()
  if q.check("search"):          # 今日搜索次数未超限
      ...执行搜索...
      q.record("search")         # 记账
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
    "search_daily_limit": 80,    # 每天搜索轮数上限（2026-09-05 老板拍板：搜索次数非平台红线，放宽为防失控熔断）
    "extract_daily_limit": 500,  # 每天提取条数上限（列表页读取，随搜索走）
    "min_delay_sec": 8,          # 轮间最小延迟（秒）（模拟真人节奏的核心，勿调太短）
    "max_delay_sec": 20,         # 轮间最大延迟（秒）
    "detail_daily_limit": 100,   # 查看简历数（打开候选人详情页）日上限——平台真正统计的风控点；详情深采接入后生效
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
        """action 今日是否还有额度。"""
        limit = self.config.get(f"{action}_daily_limit")
        if limit is None:
            return True
        return self._day().get(action, 0) < limit

    def remaining(self, action: str) -> int:
        limit = self.config.get(f"{action}_daily_limit")
        if limit is None:
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
        d = self._day()
        parts = []
        for k, v in self.config.items():
            if k.endswith("_daily_limit"):
                act = k.replace("_daily_limit", "")
                parts.append(f"{act} {d.get(act, 0)}/{v}")
        return f"今日账本: " + " | ".join(parts)


if __name__ == "__main__":
    # 自测：记账/检查/剩余额度
    q = Quota(path="data/usage/_quota_test.json", config={"search_daily_limit": 2, "extract_daily_limit": 5})
    print("初始:", q.stats())
    assert q.check("search") is True
    q.record("search")
    q.record("search")
    assert q.check("search") is False, "超限应返回 False"
    assert q.remaining("search") == 0
    print("2 次搜索后:", q.stats())
    print("✅ quota 自测通过")

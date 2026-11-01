# -*- coding: utf-8 -*-
"""llm_client.py — 直连 LLM 的极小客户端（细筛用的"手"；**纯标准库、0 依赖**）

为什么要它（2026-09-17 老板拍板）：采集里的 `local_score` 是**粗筛**（本地规则、0 token），
细筛要**逐人调一次 LLM**（JD + 该人简历）→ 所以需要一个"能稳定调、失败能说人话"的小客户端。

⚠️ 不是凭空写的 —— 细节照抄老板指定的两份参考代码（都读过）：
  · `参考代码/recruitment-streamlit-v2/services/deepseek_service.py`（**蓝图**）：
    `chat()` 失败自动重试 2 次指数退避；错误**分类**（钥匙无效/余额不足/限流/服务端/超时/响应坏）；
    `_load_prompt()` **剥掉以 # 开头的注释行**（模板说明不发模型）；`_parse_json()` 容错 ```json 围栏。
  · `参考代码/recruitment-wails/internal/llm/openai_compatible.go`（**实现**）：
    `response_format={"type":"json_object"}`；**显式关掉 thinking**（思维链会和输出抢 max_tokens，
    长 JSON 被挤断）；宽松类型解析；**失败把 error 塞进结果、不炸整批**。

纪律（本项目的铁律，别踩）：
  1. **只用标准库**（urllib）——少一个"装不上"的风险；
  2. **密钥只从 .env 读**（本项目唯一那把钥匙：`bridge-agent/.env`），**绝不写进日志/报告/异常文本**；
  3. 失败**分类报人话**（钥匙/余额/限流分开）——不许把"余额不足"说成"匹配没结果"；
  4. 拿不准就**如实报错**，不假装成功。
"""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
# 这些错误**重试没用**（钥匙/余额/请求本身坏）→ 立刻抛出，别白等
NON_RETRYABLE = {"INVALID_KEY", "INSUFFICIENT_BALANCE", "BAD_REQUEST", "EMPTY_INPUT", "PROMPT_MISSING"}
RETRYABLE = {"TIMEOUT", "NETWORK", "RATE_LIMITED", "SERVER"}


class LLMError(Exception):
    """带 code 的 LLM 错误（code 用来判"要不要重试"和"怎么跟老板说"）。"""

    def __init__(self, message: str, code: str = "ERROR", status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status

    def human(self) -> str:
        """给老板看的一句话（不暴露密钥）。"""
        m = {"INVALID_KEY": "API Key 无效（401）——检查 .env 里的 DEEPSEEK_API_KEY",
             "INSUFFICIENT_BALANCE": "API 余额不足（402）——充值后再跑，**不是匹配没结果**",
             "RATE_LIMITED": "被限流（429）——等一会儿再跑",
             "SERVER": "服务端错误（5xx）——重试即可",
             "TIMEOUT": "请求超时",
             "NETWORK": "网络连不上",
             "BAD_JSON": "模型返回的不是合法 JSON（已容错 ```json 围栏仍失败）",
             "BAD_REQUEST": "请求被拒（400）——多半是模型名/参数不对",
             "EMPTY_INPUT": "输入为空（没 JD 或没简历）",
             "PROMPT_MISSING": "提示词模板缺失"}
        return f"{m.get(self.code, self.code)}：{self}"


def default_env_path() -> Path:
    """本项目唯一的 `.env`（=`bridge-agent/.env`，与面板侧栏默认值同一个）。"""
    try:
        from framework_config import BROWSER_AGENT
        return Path(BROWSER_AGENT) / ".env"
    except Exception:  # noqa: BLE001
        return Path(__file__).resolve().parent.parent / "bridge-agent" / ".env"


def load_env(path=None) -> dict[str, str]:
    """读 .env 里的 DeepSeek 配置（**不打印值**）。可用 env 覆盖：DEEPSEEK_API_KEY/BASE_URL/MODEL。"""
    import os
    env: dict[str, str] = {}
    p = Path(path) if path else default_env_path()
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            if k.startswith("DEEPSEEK_") and v.strip():
                env[k] = v.strip().strip('"').strip("'")
    for k in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL", "DEEPSEEK_COST_PER_1K"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    env.setdefault("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL)
    env.setdefault("DEEPSEEK_MODEL", DEFAULT_MODEL)
    env["_env_file"] = str(p)
    return env


def _classify(status: int, body: str) -> LLMError:
    """HTTP 状态 → 分类错误（照 streamlit-v2 的分类法）。"""
    msg = (body or "")[:200]
    try:
        err = (json.loads(body or "{}") or {}).get("error") or {}
        if isinstance(err, dict) and err.get("message"):
            msg = str(err["message"])[:200]
    except Exception:  # noqa: BLE001
        pass
    if status == 401:
        return LLMError(msg, "INVALID_KEY", status)
    if status == 402 or "余额" in msg or "insufficient" in msg.lower():
        return LLMError(msg, "INSUFFICIENT_BALANCE", status)
    if status == 429:
        return LLMError(msg, "RATE_LIMITED", status)
    if 500 <= status < 600:
        return LLMError(msg, "SERVER", status)
    if status == 400:
        return LLMError(msg, "BAD_REQUEST", status)
    return LLMError(msg, f"HTTP_{status}", status)


def clean_json(text: str) -> str:
    """去掉 ```json 围栏 / 前后废话，取出最外层 {...}（模型偶尔会加解释）。"""
    s = (text or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else ""
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    i, j = s.find("{"), s.rfind("}")
    if i >= 0 and j > i:
        s = s[i:j + 1]
    return s.strip()


def parse_json(text: str) -> dict:
    """解析模型的 JSON 返回；失败抛 LLMError(BAD_JSON)（附原文前 200 字便于排查）。"""
    try:
        out = json.loads(clean_json(text))
    except Exception as e:  # noqa: BLE001
        raise LLMError(f"{e}｜原文前 200 字：{(text or '')[:200]!r}", "BAD_JSON") from e
    if not isinstance(out, dict):
        raise LLMError(f"返回的不是 JSON 对象：{type(out).__name__}", "BAD_JSON")
    return out


def estimate_tokens(text: str) -> int:
    """**数量级估算**（本机没装 tokenizer）：中文 markdown/文本 ≈ 2.5 字节/词元。

    ⚠️ 只用来给老板一个"这轮大概多少"的量级，**不是精确值**（真实值看接口回的 usage）。
    """
    return int(round(len((text or "").encode("utf-8")) / 2.5))


def chat(env: dict, prompt: str, *, system: str | None = None, temperature: float = 0.3,
         max_tokens: int = 2048, json_mode: bool = True, timeout: float = 180.0,
         retries: int = 2, model: str | None = None, thinking: bool = False,
         opener=None):
    """调一次 chat/completions，返回 {content, tokens, model, elapsed}。

    · 失败**自动重试** `retries` 次（0.5s→1s 指数退避），只重试**可重试**的错；
    · `thinking=False`（默认）会带 `thinking={"type":"disabled"}`——deepseek-v4 系不关思考会
      把思维链和输出一起塞进 max_tokens，长 JSON 被挤断（照 wails 的实测结论）；
      非推理模型/其他兼容服务会忽略这个字段（协议规定未知字段忽略）。
    · `opener` 可注入（单测用假 HTTP，**绝不真联网**）。
    """
    key = (env or {}).get("DEEPSEEK_API_KEY") or ""
    base = ((env or {}).get("DEEPSEEK_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    model = model or (env or {}).get("DEEPSEEK_MODEL") or DEFAULT_MODEL
    if not key:
        raise LLMError("没找到 DEEPSEEK_API_KEY（在 .env 或环境变量里）", "INVALID_KEY")
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": prompt}]
    payload: dict = {"model": model, "messages": msgs, "temperature": temperature,
                     "max_tokens": max_tokens}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if not thinking:
        payload["thinking"] = {"type": "disabled"}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    t0 = time.time()
    last: LLMError | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                base + "/chat/completions", data=data,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
            if opener is not None:                      # 单测注入
                raw = opener(req, timeout)
            else:
                with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
                    raw = r.read().decode("utf-8", "replace")
            got = json.loads(raw)
            content = (((got.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
            usage = got.get("usage") or {}
            if not content.strip():
                raise LLMError("模型返回了空内容", "BAD_JSON")
            return {"content": content, "tokens": int(usage.get("total_tokens") or 0),
                    "model": got.get("model") or model, "elapsed": round(time.time() - t0, 1)}
        except urllib.error.HTTPError as e:
            last = _classify(int(e.code), e.read().decode("utf-8", "replace"))
        except (socket.timeout, TimeoutError) as e:
            last = LLMError(str(e), "TIMEOUT")
        except urllib.error.URLError as e:
            last = LLMError(str(getattr(e, "reason", e)), "TIMEOUT" if "timed out" in str(e) else "NETWORK")
        except LLMError as e:
            last = e
        except Exception as e:  # noqa: BLE001
            last = LLMError(f"{type(e).__name__}: {e}", "BAD_JSON")
        if last.code in NON_RETRYABLE or last.code not in RETRYABLE or attempt >= retries:
            raise last
        time.sleep(0.5 * (2 ** attempt))     # 0.5s → 1s
    raise last or LLMError("未知失败", "ERROR")


def strip_prompt_comments(text: str) -> str:
    """剥掉 prompt 模板里以 `#` 开头的**说明行**（不发给模型）——照 streamlit-v2 的 `_load_prompt`。"""
    return "\n".join(ln for ln in (text or "").splitlines() if not ln.lstrip().startswith("#")).strip()


def load_prompt(path: Path) -> str:
    """读模板 + 剥注释行（缺文件 → LLMError(PROMPT_MISSING)）。"""
    p = Path(path)
    if not p.exists():
        raise LLMError(f"模板不存在：{p}", "PROMPT_MISSING")
    return strip_prompt_comments(p.read_text(encoding="utf-8"))


def fill(template: str, **kw) -> str:
    """把 {占位符} 换掉（**只换认识的键**，模板里别的花括号不动）。"""
    out = template
    for k, v in kw.items():
        out = out.replace("{" + k + "}", str(v if v is not None else ""))
    return out

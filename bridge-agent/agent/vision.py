#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent/vision.py — 视觉模型调用（P4-V-T2 视觉问答验证的测试基建）

调用 DeepSeek-V4-Flash-Vision-Exp（多模态，OpenAI 兼容 Chat Completions）：
- 模型名：deepseek-v4-flash-vision-exp（DeepSeek API Docs news260821 上线）
- 图像走 base64 data URL（PNG/JPEG/GIF/WebP，实际内容识别格式；≤48MiB 请求体）
- 这是**测试基建**（V-T2 定位：纯测试不写业务代码）——业务层是否用视觉由后续结论决定。

用法（被 vision_qa.py 调用，也可单独 import）：
    from agent.vision import vision_chat
    ans = vision_chat("logs/screenshots/xxx.png", "图里有哪些搜索条件？")
"""
import base64
import json
import os
import time
import urllib.request

# 模型名/端点可用环境变量覆盖（默认取 DeepSeek 官方多模态模型）
VISION_MODEL = os.environ.get("VISION_MODEL", "deepseek-v4-flash-vision-exp")
VISION_URL = os.environ.get("VISION_URL", "https://api.deepseek.com/chat/completions")
VISION_TIMEOUT = int(os.environ.get("VISION_TIMEOUT", "120"))


def load_api_key():
    """复用 core.load_api_key（env → .env），不重复实现。"""
    try:
        from agent.core import load_api_key as _load
    except ImportError:  # 从 agent/ 目录直接运行
        from core import load_api_key as _load
    return _load()


def image_to_data_url(image):
    """把 文件路径 或 已是 data: URL 的图像统一转成 data: URL（视觉模型入参）。

    image 传文件路径时按扩展名推断 MIME（缺省 PNG）；官方接口按实际内容识别格式。
    """
    s = str(image)
    if s.startswith("data:image/"):
        return s
    with open(s, "rb") as f:
        raw = f.read()
    ext = os.path.splitext(s)[1].lower().lstrip(".")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/png")
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


def vision_chat(image, question, api_key=None, model=None, system=None, max_tokens=8000,
                retries=2, retry_delay=2.0):
    """单轮视觉问答：image（路径或 data URL）+ question → 模型回答文本。

    Args:
        image: 截图文件路径（logs/screenshots/*.png）、data: URL，或它们的**列表**
               （多图对比场景，如"当前截图 vs 沉淀截图"，图片按列表顺序送入模型）
        question: 对图像的问题（中文/英文均可）
        api_key: DeepSeek API key（None 自动从 .env 读）
        model: 视觉模型名（默认 deepseek-v4-flash-vision-exp）
        system: 可选 system 提示（如"你是页面截图分析助手"）
        max_tokens: 回答最大 token（含推理预算，给足避免推理耗光导致 content 为空）
        retries: content 为空/None 时的重试次数（reasoning 模型偶发空 content）
        retry_delay: 重试间隔（秒）
    Returns:
        模型回答字符串
    Raises:
        RuntimeError: 缺 API key / 调用失败 / 重试后仍为空
    """
    if api_key is None:
        api_key = load_api_key()
    if not api_key:
        raise RuntimeError("未找到 DEEPSEEK_API_KEY（请设置环境变量或确认 browser-agent/.env 存在）")
    images = image if isinstance(image, (list, tuple)) else [image]
    content = [{"type": "text", "text": question}]
    for img in images:
        content.append({"type": "image_url", "image_url": {"url": image_to_data_url(img)}})
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": content})
    payload = {
        "model": model or VISION_MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    last_err = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            VISION_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=VISION_TIMEOUT) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(retry_delay)
                continue
            raise RuntimeError(f"视觉模型调用失败: {e}")
        msg = data.get("choices", [{}])[0].get("message", {})
        ans = msg.get("content")
        if isinstance(ans, list):  # 部分实现返回 content 分块数组
            ans = "".join(part.get("text", "") for part in ans if isinstance(part, dict))
        if ans is None or not str(ans).strip():
            last_err = (f"模型返回空 content（finish_reason="
                        f"{data.get('choices', [{}])[0].get('finish_reason')}, "
                        f"reasoning={str(msg.get('reasoning_content'))[:100]!r}），尝试重试")
            if attempt < retries:
                time.sleep(retry_delay)
                continue
            raise RuntimeError(f"视觉模型连续返回空内容: {last_err}")
        return str(ans)
    raise RuntimeError(f"视觉模型调用失败: {last_err}")


if __name__ == "__main__":
    # 自测：python agent/vision.py <截图路径> <问题>
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 3:
        print("用法: python agent/vision.py <截图路径> <问题>")
        sys.exit(1)
    print(vision_chat(sys.argv[1], sys.argv[2]))

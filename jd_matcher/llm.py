"""OpenAI 兼容多服务商客户端：结构化输出 + 逐家失败降级。

设计要点（与简历里的扩展项目一致）：
1. API Key 只从环境变量或本地 config 读，不写进代码、不打印到日志；
2. 严格 JSON 输出，解析失败即视为该服务商失败，切换下一家；
3. 所有服务商都失败时返回 None，由上层降级为规则结果，绝不阻塞调用方；
4. 支持各家官方通用环境变量名与本地推理端点（Ollama / LM Studio / vLLM 无需 Key）。
"""
import json
import os
import time
import urllib.error
import urllib.request

SYSTEM_PROMPT = """你是「JD 与简历适配助手」。只能依据给定的【证据片段】做判断，遵守三条底线：
1. 有明确要求的匹配点必须能在证据片段里找到原文支撑，evidence 字段必须引用片段原文；
2. 证据里没写的不要推断，放进 gaps（能力缺口）；
3. 不要编造项目名、框架名、指标或工作经历。

只输出一个 JSON 对象，不要 markdown 代码块，字段固定为：
{
  "matched": [{"point": "JD 中的要求", "evidence": "证据片段原文", "project": "项目名", "chunk_id": "片段编号"}],
  "gaps": ["JD 要求但证据里没有的能力"],
  "rewrite": ["针对这份 JD 的简历改写建议，一条一句"],
  "score": 0 到 100 的整数
}
"""

USER_TEMPLATE = """【JD 原文】
{jd}

【证据片段】
{evidence}

请输出 JSON。"""

# 各家官方常见环境变量名，设了就能直接用，不必改 config
ENV_ALIASES = {
    "qwen": ["DASHSCOPE_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "zhipu": ["ZHIPU_API_KEY", "BIGMODEL_API_KEY", "GLM_API_KEY"],
    "siliconflow": ["SILICONFLOW_API_KEY"],
    "moonshot": ["MOONSHOT_API_KEY"],
    "doubao": ["ARK_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
}


def re_name(name):
    return "".join(ch if ch.isalnum() else "_" for ch in str(name)).upper()


def _is_local(url):
    return any(host in url for host in ("127.0.0.1", "localhost", "0.0.0.0", "[::1]"))


def resolve_env_key(name, custom_env=None):
    """返回 (命中的环境变量名, 值)。优先本项目专用变量，再试各家官方变量。"""
    candidates = ["JDMATCH_" + re_name(name) + "_KEY"]
    if custom_env:
        candidates.insert(0, custom_env)
    candidates += ENV_ALIASES.get(str(name).lower(), [])
    seen = set()
    for var in candidates:
        if var in seen:
            continue
        seen.add(var)
        val = os.environ.get(var, "").strip()
        if val:
            return var, val
    return "", ""


class Provider:
    def __init__(self, raw, timeout):
        self.name = raw.get("name", "unnamed")
        self.base_url = raw.get("base_url", "").rstrip("/")
        self.model = raw.get("model", "")
        self.local = bool(raw.get("local")) or _is_local(self.base_url)
        inline_key = (raw.get("api_key") or "").strip()
        env_var, env_key = resolve_env_key(self.name, raw.get("api_key_env"))
        self.key = inline_key or env_key or ("local-no-key" if self.local else "")
        if inline_key:
            self.key_source = "config（明文，建议改环境变量）"
        elif env_key:
            self.key_source = "环境变量 " + env_var
        elif self.local:
            self.key_source = "本地端点，无需 Key"
        else:
            self.key_source = "未配置"
        self.timeout = timeout

    @property
    def ready(self):
        return bool(self.base_url and self.model) and (self.local or bool(self.key) and self.key != "local-no-key")

    def call(self, jd, evidence_text, temperature=0.1, use_json_mode=True):
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_TEMPLATE.format(jd=jd, evidence=evidence_text)},
            ],
            "temperature": temperature,
        }
        if use_json_mode:
            payload["response_format"] = {"type": "json_object"}
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.key,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"]


class ProviderChain:
    def __init__(self, config_path="config.json", timeout=20):
        self.providers = []
        self.timeout = timeout
        self.load_error = ""
        if not os.path.exists(config_path):
            # 仓库里只提供 config.example.json（无密钥），clone 后无需手动复制即可运行。
            # 用户若创建了本地 config.json（已被 .gitignore 忽略），优先使用它。
            fallback = os.path.join(os.path.dirname(os.path.abspath(config_path)), "config.example.json")
            if os.path.exists(fallback):
                config_path = fallback
            else:
                self.load_error = "未找到 config.json / config.example.json，使用离线规则模式"
                return
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.timeout = cfg.get("timeout", timeout)
            for raw in cfg.get("providers", []):
                if raw.get("disabled"):
                    continue
                self.providers.append(Provider(raw, self.timeout))
        except Exception as e:
            self.load_error = f"读取配置失败：{type(e).__name__}: {e}"

    @property
    def available(self):
        return any(p.ready for p in self.providers)

    def status(self):
        return {
            "mode": "api" if self.available else "offline",
            "load_error": self.load_error,
            "providers": [
                {
                    "name": p.name, "model": p.model, "ready": p.ready,
                    "key_source": p.key_source, "local": p.local,
                }
                for p in self.providers
            ],
        }

    @staticmethod
    def _parse(content, evidence_text=""):
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("顶层不是对象")
        for key in ("matched", "gaps", "rewrite", "score"):
            if key not in data:
                raise ValueError("缺少字段 " + key)
        if not isinstance(data["matched"], list) or not isinstance(data["gaps"], list):
            raise ValueError("matched / gaps 类型错误")

        # 证据一致性校验：模型可能把项目名、推断或套话塞进 evidence 字段。
        # 这里要求 evidence 必须能在送进上下文的片段原文里找到，否则剔除该匹配点。
        sources = [ln.split("：", 1)[1].strip()
                   for ln in evidence_text.splitlines() if "：" in ln]
        if not sources:
            return data
        kept, dropped = [], 0
        for item in data["matched"]:
            ev = str(item.get("evidence", "")).strip()
            if ev and any(ev in s or s in ev for s in sources):
                kept.append(item)
            else:
                dropped += 1
        data["matched"] = kept
        data["dropped_invalid_evidence"] = dropped
        if dropped:
            data["gaps"].append(f"有 {dropped} 条匹配点因未引用证据原文被自动剔除")
        if not kept:
            data["score"] = 0
        return data

    def structured(self, jd, evidence_text):
        """返回 (data|None, meta)。全部服务商失败时 data=None，由上层降级。"""
        meta = {"attempts": [], "provider": None, "latency_ms": 0, "json_mode": True}
        for p in self.providers:
            if not p.ready:
                continue
            for json_mode in (True, False):
                t0 = time.perf_counter()
                try:
                    content = p.call(jd, evidence_text, use_json_mode=json_mode)
                    data = self._parse(content, evidence_text)
                    cost = int((time.perf_counter() - t0) * 1000)
                    meta["attempts"].append({"provider": p.name, "ok": True, "json_mode": json_mode, "latency_ms": cost})
                    meta["provider"] = p.name
                    meta["latency_ms"] = cost
                    meta["json_mode"] = json_mode
                    return data, meta
                except Exception as e:
                    cost = int((time.perf_counter() - t0) * 1000)
                    meta["attempts"].append({
                        "provider": p.name, "ok": False, "json_mode": json_mode,
                        "latency_ms": cost, "error": f"{type(e).__name__}: {str(e)[:120]}",
                    })
                    # json_mode 引发的 400 才值得关掉重试；其它错误直接换服务商
                    err = str(e)
                    if not (json_mode and ("400" in err or "response_format" in err)):
                        break
        return None, meta

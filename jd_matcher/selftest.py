"""接入自检：有真实凭证就测真实端点；没有就用本地 mock 验证整条调用链。

mock server 完全在本机 127.0.0.1，不产生任何外部请求、不需要 API Key，
但会真实走完 HTTP 请求 → OpenAI 响应解析 → JSON 校验 → 逐家降级，
所以「接入层是否写对」这件事是可以离线验证的。
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .llm import Provider, ProviderChain

VALID_RESULT = {
    "matched": [{"point": "大模型 API 调用", "evidence": "对接 8 家 OpenAI 兼容大模型服务商", "project": "P1", "chunk_id": "P1-C1"}],
    "gaps": [],
    "rewrite": ["把 JD 里的关键词对齐到项目描述"],
    "score": 88,
}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            body = {}
        model = body.get("model", "")

        if model == "mock-fail":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"error":"injected failure"}')
            return
        if model == "mock-nojsonmode" and "response_format" in body:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error":"response_format not supported"}')
            return

        content = "这不是 JSON" if model == "mock-badjson" else json.dumps(VALID_RESULT, ensure_ascii=False)
        payload = {"choices": [{"message": {"content": content}}]}
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _chain(base_url, models, timeout=3):
    chain = ProviderChain(config_path="__selftest_no_config__")
    chain.providers = [
        Provider({"name": m, "base_url": base_url, "model": m, "api_key": "selftest-placeholder"}, timeout)
        for m in models
    ]
    return chain


def run_mock_selftest():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{port}/v1"
    jd = "熟悉大模型 API 调用与结构化输出，能做失败降级"
    ev = "[P1-C1] 招聘助手：对接 8 家 OpenAI 兼容大模型服务商"
    checks, details = [], []

    def check(name, condition, extra=""):
        checks.append(bool(condition))
        details.append({"case": name, "pass": bool(condition), "detail": extra})

    try:
        data, meta = _chain(base, ["mock-ok"]).structured(jd, ev)
        check("单服务商正常返回并解析 JSON", data is not None and data["score"] == 88,
              f'provider={meta["provider"]}, {meta["latency_ms"]}ms')

        data, meta = _chain(base, ["mock-fail", "mock-ok"]).structured(jd, ev)
        check("首服务商 500 时自动切换下一家", data is not None and len(meta["attempts"]) >= 2,
              f'attempts={len(meta["attempts"])}')

        data, meta = _chain(base, ["mock-fail", "mock-badjson"]).structured(jd, ev)
        check("全部失败返回 None，交由上层降级", data is None,
              f'attempts={len(meta["attempts"])}')

        data, meta = _chain(base, ["mock-nojsonmode"]).structured(jd, ev)
        check("不支持 json_object 时自动关闭重试", data is not None and meta["json_mode"] is False,
              f'json_mode={meta["json_mode"]}')

        check("调用日志不含 API Key", "selftest-placeholder" not in json.dumps(meta, ensure_ascii=False))
    finally:
        server.shutdown()
        server.server_close()

    return {
        "mode": "mock（本地端点，未调用外部模型）",
        "passed": sum(checks), "total": len(checks),
        "all_pass": all(checks), "details": details,
        "note": "验证的是接入链路；真实模型效果请配置 Key 后运行 --selftest 或 --eval。",
    }


def run_real_selftest(chain):
    results = []
    for p in chain.providers:
        item = {"name": p.name, "model": p.model, "ready": p.ready, "key_source": p.key_source}
        if not p.ready:
            item["status"] = "跳过（未配置凭证）"
            results.append(item)
            continue
        t0 = time.perf_counter()
        try:
            p.call("连通性测试", "", use_json_mode=False)
            item["status"] = "可用"
            item["latency_ms"] = int((time.perf_counter() - t0) * 1000)
        except Exception as e:
            item["status"] = "不可用"
            item["error"] = f"{type(e).__name__}: {str(e)[:120]}"
            item["latency_ms"] = int((time.perf_counter() - t0) * 1000)
        results.append(item)
    return {
        "mode": "real（已向配置的服务商发起真实请求）",
        "providers": results,
        "any_available": any(r["status"] == "可用" for r in results),
    }

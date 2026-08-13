from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import requests
import websocket

PORT = 9224
pages = requests.get(f"http://127.0.0.1:{PORT}/json", timeout=10).json()
page = next(item for item in pages if item.get("type") == "page" and item.get("url", "").startswith("http://localhost:3000"))
ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=20)
sequence = 0


def call(method: str, params: dict | None = None):
    global sequence
    sequence += 1
    request_id = sequence
    ws.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
    while True:
        message = json.loads(ws.recv())
        if message.get("id") == request_id:
            if "error" in message:
                raise RuntimeError(message["error"])
            return message.get("result", {})


def evaluate(expression: str):
    return call("Runtime.evaluate", {"expression": expression, "returnByValue": True})["result"].get("value")


call("Runtime.enable")
print(evaluate("(() => { const button = [...document.querySelectorAll('button')].find((x) => x.innerText.trim() === '授信归因监控'); if (!button) return 'NAV_NOT_FOUND'; button.click(); return 'NAV_CLICKED'; })()"))
time.sleep(3)
print(evaluate("(() => { const button = document.querySelector('button[title=\"点击查看该路径近15天授信申请量趋势\"]'); if (!button) return 'PATH_NOT_FOUND'; button.click(); return button.innerText; })()"))
time.sleep(2)
print(evaluate("document.body.innerText.includes('选中路径 · 归因解释与近15天趋势')"))
print(evaluate("document.body.innerText.includes('分窗口归因解释')"))
print(evaluate("document.body.innerText.includes('近15天授信申请量趋势')"))
print(evaluate("(() => { const title = [...document.querySelectorAll('div')].find((el) => el.textContent?.trim() === '选中路径 · 归因解释与近15天趋势'); if (!title) return 'TITLE_NOT_FOUND'; title.scrollIntoView({ block: 'start' }); return 'SCROLLED'; })()"))
time.sleep(1)
shot = call("Page.captureScreenshot", {"format": "png"})
out = Path(r"E:\agent\monitor\merged-path-card-smoke.png")
out.write_bytes(base64.b64decode(shot["data"]))
print(out)
ws.close()

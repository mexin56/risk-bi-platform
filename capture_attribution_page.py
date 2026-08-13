from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import requests
import websocket

pages = requests.get("http://127.0.0.1:9222/json", timeout=10).json()
page = next(item for item in pages if item.get("type") == "page" and item.get("url", "").startswith("http://localhost:3000"))
ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=20)
seq = 0

def call(method: str, params: dict | None = None):
    global seq
    seq += 1
    request_id = seq
    ws.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
    while True:
        message = json.loads(ws.recv())
        if message.get("id") == request_id:
            if "error" in message:
                raise RuntimeError(message["error"])
            return message.get("result", {})

call("Runtime.enable")
result = call("Runtime.evaluate", {"expression": "(() => { const btn = [...document.querySelectorAll('button')].find(x => x.innerText.includes('授信归因监控')); if (!btn) return 'NOT_FOUND'; btn.click(); return 'CLICKED'; })()", "returnByValue": True})
print(result["result"].get("value"))
time.sleep(12)
body = call("Runtime.evaluate", {"expression": "document.body.innerText.slice(0, 500)", "returnByValue": True})
print(str(body["result"].get("value")).encode("ascii", "backslashreplace").decode("ascii"))
shot = call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
out = Path(r"D:\vscode\归因分析\risk-bi-platform\attribution-smoke.png")
out.write_bytes(base64.b64decode(shot["data"]))
print(out)
ws.close()

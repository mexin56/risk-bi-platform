"""Capture login page + light-bg verification via CDP on headless Edge."""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import requests
import websocket

BASE = "http://127.0.0.1:9222"
OUT = Path(r"E:\agent\monitor\dist\login-check")


def find_page():
    pages = requests.get(f"{BASE}/json", timeout=10).json()
    for item in pages:
        if item.get("type") == "page":
            return item
    raise RuntimeError("no page")


page = find_page()
ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=30)
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


def js(expression: str):
    result = call(
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
    )
    return result.get("result", {}).get("value")


def shot(name: str):
    data = call("Page.captureScreenshot", {"format": "png"})["data"]
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    path.write_bytes(base64.b64decode(data))
    print("saved", path)


call("Page.enable")
call("Runtime.enable")
call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})

# clear any stale token so we land on login page
js("localStorage.removeItem('rc-bi-token'); location.reload();")
time.sleep(4)

body = js("document.body.innerText.slice(0, 300)")
print("---- login page text ----")
print(str(body).encode("ascii", "backslashreplace").decode("ascii")[:300])

info = js("""(() => {
  const inputs = [...document.querySelectorAll('input')];
  const inputsVisible = inputs.map(i => { const r = i.getBoundingClientRect(); return {w: Math.round(r.width), h: Math.round(r.height), border: getComputedStyle(i).borderColor, bg: getComputedStyle(i).backgroundColor}; });
  const card = document.querySelector('[class*=rounded-3xl]');
  const cr = card ? card.getBoundingClientRect() : null;
  const bg = getComputedStyle(document.querySelector('[class*=bg-cover]')).backgroundImage;
  const overlay = document.querySelector('.absolute.inset-0:nth-of-type(2)');
  return JSON.stringify({inputsVisible, cardSize: cr ? [Math.round(cr.width), Math.round(cr.height)] : null, bgImg: bg.slice(0, 80)});
})()""")
print("---- layout info ----")
print(info)

shot("login")
ws.close()
print("DONE")

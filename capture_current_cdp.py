from __future__ import annotations
import base64, json, time
from pathlib import Path
import requests, websocket
pages=requests.get('http://127.0.0.1:9224/json', timeout=10).json()
page=next(x for x in pages if x.get('type')=='page' and x.get('url','').startswith('http://localhost:3000'))
ws=websocket.create_connection(page['webSocketDebuggerUrl'], timeout=20)
i=0
def call(m,p=None):
 global i
 i+=1; rid=i
 ws.send(json.dumps({'id':rid,'method':m,'params':p or {}}))
 while True:
  x=json.loads(ws.recv())
  if x.get('id')==rid:return x.get('result',{})
time.sleep(12)
print(call('Runtime.evaluate', {'expression':"document.body.innerText.includes('15天累计')", 'returnByValue':True})['result'].get('value'))
out=Path(r'E:\agent\monitor\merged-path-card-loaded.png')
out.write_bytes(base64.b64decode(call('Page.captureScreenshot',{'format':'png'})['data']))
print(out)
ws.close()

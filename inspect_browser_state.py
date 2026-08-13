from __future__ import annotations
import json
import requests
import websocket
pages=requests.get('http://127.0.0.1:9224/json',timeout=10).json()
page=next(x for x in pages if x.get('type')=='page' and x.get('url','').startswith('http://localhost:3000'))
ws=websocket.create_connection(page['webSocketDebuggerUrl'],timeout=20)
i=0
def call(m,p=None):
 global i
 i+=1; rid=i; ws.send(json.dumps({'id':rid,'method':m,'params':p or {}}))
 while True:
  v=json.loads(ws.recv())
  if v.get('id')==rid:return v.get('result',{})
def ev(s):return call('Runtime.evaluate',{'expression':s,'returnByValue':True})['result'].get('value')
text=ev('document.body.innerText')
print(str(text).encode('ascii','backslashreplace').decode('ascii')[-4000:])
print('resources=',json.dumps(ev("performance.getEntriesByType('resource').filter(x=>x.name.includes('path-trend')||x.name.includes('dashboard')).map(x=>({name:x.name,duration:x.duration,transferSize:x.transferSize}))"),ensure_ascii=True))
print('html=',str(ev("document.documentElement.outerHTML.includes('15\u5929\u7d2f\u8ba1')")).encode('ascii','backslashreplace').decode('ascii'))
ws.close()

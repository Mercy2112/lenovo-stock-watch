import os, json, urllib.request
token=os.environ.get("TELEGRAM_BOT_TOKEN",""); chat=os.environ.get("TELEGRAM_CHAT_ID","")
body=json.dumps({"chat_id":chat,"text":"[GH Actions test] Lenovo watcher node 2 online — connectivity check OK."}).encode()
req=urllib.request.Request("https://api.telegram.org/bot%s/sendMessage"%token,data=body,headers={"Content-Type":"application/json"},method="POST")
try:
    with urllib.request.urlopen(req,timeout=20) as r: print("SENT",r.status,json.loads(r.read())["ok"])
except Exception as e: print("FAIL",str(e)[:200])

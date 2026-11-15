#!/usr/bin/env python3
"""Lenovo 21NS0012US stock monitor — GitHub Actions edition.

Runs on GitHub's runner infrastructure: a DIFFERENT IP and a DIFFERENT ASN
from the primary VPS poller. Two independent nodes = a block on one does
not blind the other.

Stdlib only. No pip install. No browser. Polls Lenovo's OpenAPI over plain
HTTP JSON (same endpoints as the primary watcher).

State lives in state.json, committed back to the repo so consecutive runs
know the last observed status and only alert on change.
"""
import json
import os
import re
import urllib.error
import urllib.request

PN = "21NS0012US"
ZIP = "60654"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/148.0.0.0 Safari/537.36")
API = "https://openapi.lenovo.com/us/en"
HDR = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.lenovo.com",
    "Referer": "https://www.lenovo.com/us/en/",
    "Content-Type": "application/json",
}
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state.json")
URL = ("https://www.lenovo.com/us/en/p/laptops/thinkpad/thinkpadx1/"
       "thinkpad-x1-carbon-gen-13-aura-edition-14-inch-intel/21ns0012us")


def post(path, payload):
    req = urllib.request.Request(API + path, data=json.dumps(payload).encode(),
                                 headers=HDR, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def get(path):
    req = urllib.request.Request(API + path, headers=HDR)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def poll():
    inv_body = {
        "zipCode": ZIP, "inventoryMsgTranslateFlag": True, "viewFlag": False,
        "requestSource": 82, "needLeadtimeFlag": False,
        "checkBestBuyMapping": False,
        "productParams": [{
            "productCode": PN, "productType": "0", "quantity": 1,
            "activityType": "", "isOutlet": False, "maxCvLeadtime": "",
            "isPre": False, "subProductList": None, "desktopBundleFlag": False,
            "skuId": None, "phisicalProduct": False, "originProductCode": "",
            "preConfigFlag": False, "selectedOptions": None,
            "selectedProductCode": "", "btype": "", "newlyAddedProductCode": "",
            "isRealtimeSelectedProduct": False, "isOnlyShowProductCode": False,
            "isBuyNowSelectedProduct": False, "cartProductCode": "",
            "isConfigurableProduct": False, "selectedOptionsWithKey": None,
        }],
    }
    dlv_body = {
        "inventoryCheck": True, "realTimeInventoryCheck": False,
        "productList": [{"guid": PN, "outlet": False, "qty": 1,
                         "productCode": PN, "productTypeCode": "0",
                         "componentItems": [], "preOrderFlag": False}],
        "source": "pdp", "city": "",
    }

    inv_d = post("/inventory/front/query", inv_body)
    inv_r = (inv_d.get("data") or [{}])[0]
    st = inv_r.get("status")
    num = inv_r.get("currentNum")

    dlv_d = post("/api/ups/getDeliveryDate", dlv_body)
    items = (dlv_d.get("data") or {}).get("deliveryDateItemList") or []
    d_st = dlv_i_date = dlv_lead = None
    if items:
        it = items[0]
        d_st = it.get("inventoryStatus")
        sm = it.get("defaultShippingMethod") or {}
        dlv_i_date = sm.get("deliveryDate")
        dlv_lead = it.get("leadTimeMessage")

    prc_d = get("/detail/price/batch/get?preSelect=1&mcode=" + PN
                + "&configId=&enteredCode=")
    row = (prc_d.get("data") or {}).get(PN) or []
    price = float(row[4]) if len(row) > 4 and row[4] else None
    list_price = None
    for cell in row:
        if isinstance(cell, list):
            for v in cell:
                s = str(v)
                # 3-5 digit amount only: the cell also holds a 15-digit UPC
                if re.fullmatch(r"\d{3,5}(\.\d+)?", s) and price and float(s) > price:
                    list_price = float(s)
                    break
        if list_price:
            break

    if st == 1 and (num or 0) > 0:
        status = "in_stock"
    elif st == 2:
        status = "not_yet"
    elif st == 3:
        status = "build_to_order"
    elif st == 5:
        status = "outlet_only"
    else:
        status = "unknown"

    shippable = bool(d_st == 1 and dlv_i_date)
    if shippable and status == "unknown":
        status = "in_stock"

    return {"status": status, "stock_count": num, "price": price,
            "list_price": list_price, "delivery_date": dlv_i_date,
            "lead_time": dlv_lead, "shippable": shippable,
            "raw_status": st}


VPS_STATE_URL = ("https://raw.githubusercontent.com/Mercy2112/"
                 "lenovo-stock-watch/master/vps_state.json")


def fetch_vps_state():
    """Read the primary VPS node's reported state (public repo, plain HTTP).

    If the VPS already sent a Telegram alert for this exact status+price,
    stay quiet -- two nodes, one notification.
    """
    try:
        req = urllib.request.Request(
            VPS_STATE_URL, headers={"User-Agent": "lenovo-watcher/1.0",
                                    "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except Exception:
        return None


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(st):
    with open(STATE, "w") as f:
        json.dump(st, f, indent=2)


def telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        print("no telegram creds; would send:\n" + text)
        return
    body = json.dumps({"chat_id": chat, "text": text,
                       "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(
        "https://api.telegram.org/bot%s/sendMessage" % token,
        data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print("telegram sent:", r.status)
    except Exception as e:  # noqa: BLE001
        print("telegram failed:", str(e)[:200])


def main():
    try:
        cur = poll()
    except Exception as e:  # noqa: BLE001
        prev = load_state()
        fails = int(prev.get("consecutive_failures", 0)) + 1
        prev["consecutive_failures"] = fails
        prev["last_error"] = str(e)[:300]
        save_state(prev)
        if fails >= 3:
            telegram("Lenovo watcher (GitHub Actions) FAILED %d consecutive checks\n"
                     "Last error: %s\n%s" % (fails, str(e)[:200], URL))
        print("poll failed:", str(e)[:200])
        return 1

    prev = load_state()
    prev_status = prev.get("status")
    prev_price = prev.get("price")

    changed = (prev_status != cur["status"]
               or prev_price != cur["price"])

    label = {"in_stock": "IN STOCK", "not_yet": "AVAILABLE SOON",
             "build_to_order": "BUILD TO ORDER",
             "outlet_only": "OUTLET ONLY"}.get(cur["status"], "UNKNOWN")

    cur["consecutive_failures"] = 0
    cur["last_error"] = None
    cur["node"] = "github-actions"
    # "reported" marks that THIS node actually pushed a Telegram alert for
    # the current status+price. The peer node reads this to avoid sending
    # a duplicate notification for the same change.
    cur["reported"] = False
    cur["last_ok"] = __import__("datetime").datetime.utcnow().isoformat(
        timespec="seconds")
    save_state(cur)

    print("status=%s price=%s list=%s stock=%s"
          % (cur["status"], cur["price"], cur["list_price"], cur["stock_count"]))

    vps = fetch_vps_state()
    if changed and prev_status is not None and vps \
            and vps.get("reported") \
            and vps.get("status") == cur["status"] \
            and vps.get("price") == cur["price"]:
        print("deduped: VPS already reported this change")
        changed = False

    if changed and prev_status is not None:
        line = "[GH] Lenovo ThinkPad X1 Carbon Gen 13 (21NS0012US)\n"
        line += "Status: %s" % label
        if cur["price"]:
            line += " — Price: ${:,.2f}".format(cur["price"])
            if cur["list_price"] and cur["list_price"] > cur["price"]:
                line += " (list ${:,.2f})".format(cur["list_price"])
        extra = []
        if cur["delivery_date"]:
            extra.append("ships %s" % cur["delivery_date"])
        elif cur["lead_time"]:
            extra.append(cur["lead_time"])
        if cur["stock_count"]:
            extra.append("%s in stock" % cur["stock_count"])
        if extra:
            line += "\n" + " | ".join(extra)
        line += "\n" + URL
        telegram(line)
        cur["reported"] = True
        cur["reported_at"] = cur.get("last_ok")
        save_state(cur)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

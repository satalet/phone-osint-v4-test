import re
import json
import time
import sqlite3
import webbrowser
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

import phonenumbers
from phonenumbers import geocoder, carrier, timezone, NumberParseException

BASE_DIR    = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"
DB_FILE     = BASE_DIR / "osint_history.db"

BANNER = """
╔══════════════════════════════════════════════════════╗
║     📡 مستكشف الأرقام المتقدم الشامل الميداني       ║
║              Phone OSINT Tool v4.0                   ║
║     [ OSINT | Archive | Social | DB | Countries ]    ║
╚══════════════════════════════════════════════════════╝
"""

COUNTRIES = {
    "1": ("+970", "فلسطين 🇵🇸"),
    "2": ("+972", "إسرائيل 🇮🇱"),
    "3": ("+962", "الأردن 🇯🇴"),
    "4": ("+966", "السعودية 🇸🇦"),
    "5": ("+20",  "مصر 🇪🇬"),
    "6": ("+1",   "أمريكا/كندا 🇺🇸"),
    "7": ("+44",  "بريطانيا 🇬🇧"),
}

PALESTINE_CARRIERS = {
    ("970", ("59",)):      "Jawwal (جوال) 🇵🇸",
    ("970", ("56", "51")): "Ooredoo Palestine 🇵🇸",
    ("972", ("50",)):      "Cellcom 🇮🇱",
    ("972", ("52",)):      "Partner (Orange IL) 🇮🇱",
    ("972", ("54",)):      "HOT Mobile 🇮🇱",
    ("972", ("55",)):      "HOT Mobile 🇮🇱",
    ("972", ("58",)):      "Golan Telecom 🇮🇱",
}

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def setup_api_keys(config):
    changed = False
    if not config.get("numverify_key"):
        print("\n[!] مفتاح Numverify غير موجود.")
        print("    احصل عليه مجاناً من: https://numverify.com/product")
        key = input("    أدخل المفتاح (أو Enter للتخطي): ").strip()
        config["numverify_key"] = key
        changed = True
    if not config.get("ipqs_key"):
        print("\n[!] مفتاح IPQualityScore غير موجود.")
        print("    احصل عليه مجاناً من: https://www.ipqualityscore.com/create-account")
        key = input("    أدخل المفتاح (أو Enter للتخطي): ").strip()
        config["ipqs_key"] = key
        changed = True
    if changed:
        save_config(config)
        print("\n[✔] تم حفظ المفاتيح في config.json")
    return config

def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL, country TEXT, region TEXT,
            carrier TEXT, line_type TEXT, location TEXT,
            timezones TEXT, numverify TEXT, ipqs TEXT,
            archive_hit INTEGER DEFAULT 0, scanned_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def save_scan(data):
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        INSERT INTO scans (phone,country,region,carrier,line_type,
        location,timezones,numverify,ipqs,archive_hit,scanned_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        data.get("phone"), data.get("country"), data.get("region"),
        data.get("carrier"), data.get("line_type"), data.get("location"),
        data.get("timezones"), data.get("numverify"), data.get("ipqs"),
        data.get("archive_hit", 0), datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    ))
    conn.commit()
    conn.close()

def show_history():
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute(
        "SELECT id,phone,location,carrier,scanned_at FROM scans ORDER BY id DESC LIMIT 10"
    ).fetchall()
    conn.close()
    if not rows:
        print("[–] لا يوجد سجل فحص سابق.")
        return
    print("\n┌─────────────────────────────────────────────────────────────┐")
    print("│                  📂 آخر 10 فحوصات سابقة                    │")
    print("├────┬──────────────────┬──────────────┬───────────────────────┤")
    print("│ ID │ الرقم           │ الشركة       │ التاريخ               │")
    print("├────┼──────────────────┼──────────────┼───────────────────────┤")
    for row in rows:
        print(f"│ {str(row[0]):<3}│ {str(row[1]):<17}│ {str(row[3] or 'غير محدد'):<13}│ {str(row[4]):<22}│")
    print("└────┴──────────────────┴──────────────┴───────────────────────┘")

def clean_input(raw):
    return re.sub(r"[^\d+]", "", raw.strip())

def select_default_country():
    print("\n[*] اختر الدولة الافتراضية للرقم:")
    for k, (code, name) in COUNTRIES.items():
        print(f"    {k}. {name}  ({code})")
    print("    M. أدخل كود يدوياً")
    while True:
        choice = input("[?] اختر رقم الدولة: ").strip().upper()
        if choice in COUNTRIES:
            code, name = COUNTRIES[choice]
            print(f"[✔] تم اختيار: {name}")
            return code
        elif choice == "M":
            manual = input("    أدخل كود الدولة: ").strip().lstrip("+")
            return f"+{manual}"
        else:
            print("[!] اختيار غير صالح.")

def normalize_number(raw, default_country=None):
    cleaned = clean_input(raw)
    if cleaned.startswith("00"):
        return "+" + cleaned[2:]
    if cleaned.startswith("+"):
        return cleaned
    if cleaned.startswith("0") and default_country:
        return default_country + cleaned[1:]
    if default_country:
        return default_country + cleaned
    return None

def get_palestine_carrier(country_code, national_number):
    for (code, prefixes), name in PALESTINE_CARRIERS.items():
        if country_code == code:
            for prefix in prefixes:
                if national_number.startswith(prefix):
                    return name
    return "غير محددة"

def get_line_type(number_type):
    type_map = {
        phonenumbers.PhoneNumberType.MOBILE: "موبايل 📱",
        phonenumbers.PhoneNumberType.FIXED_LINE: "أرضي ☎️",
        phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "أرضي أو موبايل",
        phonenumbers.PhoneNumberType.TOLL_FREE: "مجاني",
        phonenumbers.PhoneNumberType.PREMIUM_RATE: "مدفوع",
        phonenumbers.PhoneNumberType.VOIP: "VOIP 🌐",
        phonenumbers.PhoneNumberType.UNKNOWN: "غير محدد",
    }
    return type_map.get(number_type, "غير محدد")

def fetch_json(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PhoneOSINT/4.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None

def check_numverify(phone_e164, api_key):
    if not api_key:
        return None
    url = f"http://apilayer.net/api/validate?access_key={api_key}&number={phone_e164.lstrip('+')}&format=1"
    data = fetch_json(url)
    if data and data.get("valid"):
        return {
            "carrier": data.get("carrier", "—"),
            "line_type": data.get("line_type", "—"),
            "location": data.get("location", "—"),
            "country": data.get("country_name", "—"),
        }
    return None

def check_ipqs(phone_e164, api_key):
    if not api_key:
        return None
    url = f"https://ipqualityscore.com/api/json/phone/{api_key}/{urllib.parse.quote(phone_e164)}"
    data = fetch_json(url)
    if data and data.get("success"):
        return {
            "fraud_score": data.get("fraud_score", 0),
            "spam": data.get("spam", False),
            "carrier": data.get("carrier", "—"),
            "line_type": data.get("line_type", "—"),
            "prepaid": data.get("prepaid", False),
            "recent_abuse": data.get("recent_abuse", False),
        }
    return None

def check_archive(phone_e164, national_number):
    results = {}
    for q in [phone_e164, "0" + national_number]:
        url = f"https://archive.org/search?query={urllib.parse.quote(chr(34)+q+chr(34))}&output=json&rows=3"
        data = fetch_json(url)
        if data and data.get("response", {}).get("numFound", 0) > 0:
            docs = data["response"].get("docs", [])
            results[q] = {
                "count": data["response"]["numFound"],
                "samples": [{"title": d.get("title","—"), "identifier": d.get("identifier","")} for d in docs[:3]]
            }

    return results

def build_osint_links(parsed: phonenumbers.PhoneNumber) -> dict:
    region     = phonenumbers.region_code_for_number(parsed) or "il"
    national   = str(parsed.national_number)
    e164_clean = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164).replace("+", "")
    intl_full  = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

    return {
        # ── التواصل المباشر (بيفتح تطبيق الواتساب فوراً وبوريك إذا الرقم شغال) ──
        "WhatsApp":   f"https://wa.me/{e164_clean}",
        
        # ── محركات البحث والأرشيف ──
        "Truecaller": f"https://www.truecaller.com/search/{region.lower()}/{e164_clean}",
        "Google":     f"https://www.google.com/search?q=%220{national}%22+OR+%22{urllib.parse.quote(intl_full)}%22",
        "NumLookup":  f"https://www.numlookupapi.com/lookup?phone={e164_clean}",
        "Archive.org": f"https://web.archive.org/web/*/\"{e164_clean}\"",
        
        # ── شبكات التواصل (البحث من خلال المتصفح أضمن وأدق للـ OSINT) ──
        "Facebook":   f"https://www.facebook.com/search/top/?q=0{national}",
        "Instagram":  f"https://www.instagram.com/explore/tags/{e164_clean}/",
        "Twitter/X":  f"https://x.com/search?q=0{national}&f=user",
        "TikTok":     f"https://www.tiktok.com/search/user?q=0{national}",
        "LinkedIn":   f"https://www.linkedin.com/search/results/all/?keywords=0{national}",
    }

def open_links_menu(links):
    print("\n[*] روابط التحري المتاحة:")
    categories = {
        "── تحري مباشر ──":     ["Truecaller","Google","NumLookup"],
        "── تواصل اجتماعي ──":  ["WhatsApp"],
        "── شبكات اجتماعية ──": ["Facebook","Instagram","LinkedIn","Twitter/X","TikTok"],
        "── أرشيف ──":          ["Archive.org"],
    }
    i = 1
    order_map = {}
    for cat, names in categories.items():
        print(f"\n  {cat}")
        for name in names:
            if name in links:
                print(f"    {i}. {name:<14} → {links[name]}")
                order_map[i] = (name, links[name])
                i += 1
    print("\n  A = فتح الكل | أرقام مفصولة بفاصلة | Enter للتخطي")
    choice = input("[?] اختر: ").strip().lower()
    if choice == "a":
        for _, url in order_map.values():
            webbrowser.open(url)
            time.sleep(0.4)
        print("[✔] تم فتح جميع الروابط.")
    elif choice:
        try:
            for idx in [int(x.strip()) for x in choice.split(",")]:
                if idx in order_map:
                    webbrowser.open(order_map[idx][1])
                    print(f"[✔] تم فتح: {order_map[idx][0]}")
        except ValueError:
            print("[!] اختيار غير صالح.")

def main():
    print(BANNER)
    init_db()
    show_history()
    config = load_config()
    config = setup_api_keys(config)
    print("\n" + "─" * 54)
    raw_input = input("\n[*] أدخل رقم الهاتف: ").strip()
    cleaned = clean_input(raw_input)
    if cleaned.startswith("+") or cleaned.startswith("00"):
        default_country = None
    else:
        default_country = select_default_country()
    e164 = normalize_number(raw_input, default_country)
    if not e164:
        print("[✖] ما قدرنا نعالج الرقم.")
        input("\n[*] اضغط Enter للخروج...")
        return
    print(f"\n[*] الرقم بعد المعالجة: {e164}")
    print("─" * 54)
    try:
        parsed = phonenumbers.parse(e164, None)
        if not phonenumbers.is_valid_number(parsed):
            print("[✖] الرقم غير صالح دولياً.")
            input("\n[*] اضغط Enter للخروج...")
            return
    except NumberParseException as err:
        print(f"[!] خطأ في تحليل الرقم: {err}")
        input("\n[*] اضغط Enter للخروج...")
        return
    print("[✔] الرقم صالح دولياً.")
    country_code_str = str(parsed.country_code)
    national_number  = str(parsed.national_number)
    location         = geocoder.description_for_number(parsed, "ar") or "غير محددة"
    service_provider = carrier.name_for_number(parsed, "en") or get_palestine_carrier(country_code_str, national_number)
    time_zones       = timezone.time_zones_for_number(parsed)
    region_code      = phonenumbers.region_code_for_number(parsed) or "غير محدد"
    intl_format      = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
    national_format  = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL)
    line_type_str    = get_line_type(phonenumbers.number_type(parsed))
    if country_code_str == "972" and national_number.startswith(("50","52","54","55","58")):
        location = "إسرائيل / فلسطين المحتلة"
    elif country_code_str == "970":
        location = "فلسطين 🇵🇸"
    print(f"""
┌─────────────────────────────────────────────────────┐
│               📋 بطاقة تعريف الرقم                  │
├─────────────────────────────────────────────────────┤
│  الصيغة الدولية  : {intl_format:<32}│
│  الصيغة الوطنية  : {national_format:<32}│
│  كود الدولة      : +{country_code_str:<31}│
│  كود المنطقة     : {region_code:<32}│
│  الدولة / المنطقة: {location:<32}│
│  الشركة المشغلة  : {service_provider:<32}│
│  نوع الخط        : {line_type_str:<32}│
│  المنطقة الزمنية : {', '.join(time_zones):<32}│
└─────────────────────────────────────────────────────┘""")
    numverify_result = None
    print("\n[*] جاري الفحص عبر Numverify API...")
    numverify_result = check_numverify(e164, config.get("numverify_key",""))
    if numverify_result:
        print(f"""
  ┌─ Numverify ────────────────────────────────────┐
  │  الشركة   : {numverify_result['carrier']:<37}│
  │  نوع الخط : {numverify_result['line_type']:<37}│
  │  الموقع   : {numverify_result['location']:<37}│
  └────────────────────────────────────────────────┘""")
    else:
        print("  [–] Numverify: لا يوجد مفتاح أو فشل الاتصال.")
    ipqs_result = None
    print("\n[*] جاري فحص مستوى الخطورة عبر IPQualityScore...")
    ipqs_result = check_ipqs(e164, config.get("ipqs_key",""))
    if ipqs_result:
        fraud_bar = "█" * (ipqs_result['fraud_score'] // 10) + "░" * (10 - ipqs_result['fraud_score'] // 10)
        print(f"""
  ┌─ IPQualityScore ───────────────────────────────┐
  │  مستوى الخطر : [{fraud_bar}] {ipqs_result['fraud_score']}%      │
  │  SPAM         : {'نعم ⚠️' if ipqs_result['spam'] else 'لا ✔️':<37}│
  │  مدفوع مسبقاً : {'نعم' if ipqs_result['prepaid'] else 'لا':<37}│
  │  إساءة حديثة : {'نعم ⚠️' if ipqs_result['recent_abuse'] else 'لا ✔️':<37}│
  │  الشركة       : {ipqs_result['carrier']:<37}│
  └────────────────────────────────────────────────┘""")
    else:
        print("  [–] IPQualityScore: لا يوجد مفتاح أو فشل الاتصال.")
    archive_hit = 0
    print("\n[*] جاري البحث في أرشيف الإنترنت (Archive.org)...")
    archive_results = check_archive(e164, national_number)
    if archive_results:
        archive_hit = 1
        for query, info in archive_results.items():
            print(f"\n  ✔ وُجد {info['count']} نتيجة للرقم [{query}] في الأرشيف:")
            for s in info["samples"]:
                print(f"    • {s['title']}")
                print(f"      https://archive.org/details/{s['identifier']}")
    else:
        print("  [–] لا توجد نتائج في Archive.org.")
    save_scan({
        "phone": e164, "country": country_code_str, "region": region_code,
        "carrier": service_provider, "line_type": line_type_str, "location": location,
        "timezones": ", ".join(time_zones),
        "numverify": json.dumps(numverify_result, ensure_ascii=False) if numverify_result else None,
        "ipqs": json.dumps(ipqs_result, ensure_ascii=False) if ipqs_result else None,
        "archive_hit": archive_hit,
    })
    print("\n[✔] تم حفظ نتيجة الفحص في قاعدة البيانات.")
    links = build_osint_links(parsed)
    open_links_menu(links)
    print("\n" + "═" * 54)
    input("[*] اضغط Enter للخروج...")

if __name__ == "__main__":
    main()

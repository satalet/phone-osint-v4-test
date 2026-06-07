import streamlit as st
import phonenumbers
from phonenumbers import geocoder, carrier, NumberParseException
import json

# استدعاء ملفك الأساسي (تأكد إن اسمه phone_crawler_v4.py بدون مسافات)
import phone_crawler_v4 as osint

# إعدادات الصفحة
st.set_page_config(page_title="Phone OSINT v4", page_icon="📡", layout="wide")

# --- القائمة الجانبية (Sidebar) ---
st.sidebar.title("عن الأداة")
st.sidebar.info("تم التطوير والبرمجة بواسطة: **أبو باسم** 👨‍💻")
st.sidebar.markdown("---")

# جلب الإعدادات المحفوظة
config = osint.load_config()

st.sidebar.subheader("🔑 إعدادات الـ APIs")
numverify_key = st.sidebar.text_input("Numverify API Key", value=config.get("numverify_key", ""), type="password")
ipqs_key = st.sidebar.text_input("IPQualityScore API Key", value=config.get("ipqs_key", ""), type="password")

# حفظ المفاتيح إذا تعدلت
if st.sidebar.button("💾 حفظ المفاتيح"):
    config["numverify_key"] = numverify_key
    config["ipqs_key"] = ipqs_key
    osint.save_config(config)
    st.sidebar.success("تم الحفظ بنجاح!")

# --- واجهة الموقع الأساسية ---
st.title("📡 مستكشف الأرقام الميداني الشامل")
st.markdown("أداة OSINT للبحث عن معلومات أرقام الهواتف بسرعة واحترافية")
st.divider()

# إعدادات الإدخال
col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    phone_input = st.text_input("أدخل رقم الهاتف (يفضل مع رمز الدولة +):")
with col2:
    # جلب قائمة الدول من ملفك لعرضها كقائمة منسدلة
    country_choices = {name: code for k, (code, name) in osint.COUNTRIES.items()}
    selected_country_name = st.selectbox("الدولة الافتراضية:", list(country_choices.keys()))
    default_country_code = country_choices[selected_country_name]
with col3:
    st.write("")
    st.write("") # لمحاذاة الزر مع المربعات
    analyze_btn = st.button("🔍 افحص الرقم", use_container_width=True)

# --- عملية الفحص ---
if analyze_btn and phone_input:
    # 1. معالجة الرقم باستخدام دالتك
    e164 = osint.normalize_number(phone_input, default_country_code)
    
    if not e164:
        st.error("❌ صيغة الرقم غير صحيحة ولم نتمكن من معالجته.")
    else:
        try:
            parsed = phonenumbers.parse(e164, None)
            if not phonenumbers.is_valid_number(parsed):
                st.error("❌ الرقم غير صالح دولياً.")
            else:
                # 2. استخراج البيانات الأساسية
                country_code_str = str(parsed.country_code)
                national_number  = str(parsed.national_number)
                location = geocoder.description_for_number(parsed, "ar") or "غير محددة"
                service_provider = carrier.name_for_number(parsed, "en") or osint.get_palestine_carrier(country_code_str, national_number)
                line_type_str = osint.get_line_type(phonenumbers.number_type(parsed))
                
                # تصحيح إسرائيل/فلسطين حسب الكود تبعك
                if country_code_str == "972" and national_number.startswith(("50", "52", "54", "55", "58")):
                    location = "إسرائيل / فلسطين المحتلة"
                elif country_code_str == "970":
                    location = "فلسطين 🇵🇸"

                st.success(f"الرقم {e164} صالح دولياً!")

                # عرض البطاقة
                st.subheader("📋 بطاقة تعريف الرقم")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("الدولة / المنطقة", location)
                m2.metric("الشركة المشغلة", service_provider)
                m3.metric("نوع الخط", line_type_str)
                m4.metric("الصيغة الدولية", phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL))

                st.divider()

                # 3. فحص الـ APIs والأرشيف
                st.subheader("🔍 نتائج الفحص العميق")
                api_col1, api_col2, api_col3 = st.columns(3)

                nv_res, ipqs_res, archive_hit = None, None, 0

                with api_col1:
                    st.markdown("**1️⃣ Numverify API**")
                    if numverify_key:
                        with st.spinner("جاري الفحص..."):
                            nv_res = osint.check_numverify(e164, numverify_key)
                            if nv_res:
                                st.json(nv_res)
                            else:
                                st.warning("لم يتم العثور على نتيجة أو المفتاح غير صالح.")
                    else:
                        st.info("مفتاح Numverify غير متوفر.")

                with api_col2:
                    st.markdown("**2️⃣ IPQualityScore API**")
                    if ipqs_key:
                        with st.spinner("جاري الفحص..."):
                            ipqs_res = osint.check_ipqs(e164, ipqs_key)
                            if ipqs_res:
                                fraud_score = ipqs_res.get('fraud_score', 0)
                                color = "red" if fraud_score > 70 else "orange" if fraud_score > 30 else "green"
                                st.progress(fraud_score / 100, text=f"مستوى الخطر: {fraud_score}%")
                                st.json(ipqs_res)
                            else:
                                st.warning("لم يتم العثور على نتيجة أو المفتاح غير صالح.")
                    else:
                        st.info("مفتاح IPQualityScore غير متوفر.")

                with api_col3:
                    st.markdown("**3️⃣ أرشيف الإنترنت (Archive.org)**")
                    with st.spinner("جاري البحث..."):
                        arc_res = osint.check_archive(e164, national_number)
                        if arc_res:
                            archive_hit = 1
                            for q, info in arc_res.items():
                                st.write(f"📌 الرقم `{q}`: وُجد **{info['count']}** نتائج.")
                        else:
                            st.info("لا توجد نتائج مسجلة في الأرشيف.")

                st.divider()

                # 4. روابط التحري المباشر (توليد أزرار بدل القائمة)
                st.subheader("🔗 روابط التحري المباشر والتواصل")
                links = osint.build_osint_links(parsed)
                link_cols = st.columns(5)
                idx = 0
                for name, url in links.items():
                    link_cols[idx % 5].link_button(name, url, use_container_width=True)
                    idx += 1

                # 5. حفظ العملية في قاعدة بيانات SQLite الخاصة بك
                osint.save_scan({
                    "phone":       e164,
                    "country":     country_code_str,
                    "region":      phonenumbers.region_code_for_number(parsed) or "غير محدد",
                    "carrier":     service_provider,
                    "line_type":   line_type_str,
                    "location":    location,
                    "timezones":   "",
                    "numverify":   json.dumps(nv_res, ensure_ascii=False) if nv_res else None,
                    "ipqs":        json.dumps(ipqs_res, ensure_ascii=False) if ipqs_res else None,
                    "archive_hit": archive_hit,
                })
                
        except NumberParseException:
            st.error("❌ حدث خطأ أثناء تحليل الرقم. تأكد من الصيغة.")

# --- توقيع أسفل الصفحة ---
st.divider()
st.markdown("<p style='text-align: center; color: gray;'>تم التطوير بواسطة <b>أبو باسم</b> © 2026</p>", unsafe_allow_html=True)

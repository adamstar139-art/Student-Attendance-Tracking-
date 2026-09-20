import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import io
import copy

# =========================================================
# 0. ربط قاعدة البيانات السحابية الدائمة (Supabase Cloud)
# =========================================================
try:
    from supabase import create_client, Client
    _SUPABASE_LIB = True
except Exception:
    _SUPABASE_LIB = False

@st.cache_resource(show_spinner=False)
def get_supabase():
    """إنشاء اتصال واحد مع Supabase وإعادة استخدامه للسرعة مع مرونة فائقة في قراءة Secrets"""
    if not _SUPABASE_LIB:
        return None
    url, key = None, None
    # 1. القراءة من قسم [supabase]
    if "supabase" in st.secrets:
        sec = st.secrets["supabase"]
        if hasattr(sec, "get"):
            url = sec.get("url") or sec.get("URL") or sec.get("SUPABASE_URL")
            key = sec.get("key") or sec.get("KEY") or sec.get("SUPABASE_KEY") or sec.get("anon_key")
    # 2. القراءة المباشرة من المستوى الرئيسي في Secrets
    if not url and hasattr(st.secrets, "get"):
        url = st.secrets.get("url") or st.secrets.get("SUPABASE_URL")
    if not key and hasattr(st.secrets, "get"):
        key = st.secrets.get("key") or st.secrets.get("SUPABASE_KEY") or st.secrets.get("anon_key")

    if not url or not key:
        return None
    try:
        clean_url = str(url).strip().strip('"').strip("'")
        clean_key = str(key).strip().strip('"').strip("'")
        if not clean_url or not clean_key:
            return None
        return create_client(clean_url, clean_key)
    except Exception:
        return None

def supabase_ready():
    return get_supabase() is not None

# --- دوال قراءة وحفظ حضور الطلاب ---
STU_COLS = ["التاريخ", "اسم المعلم", "الصف", "الفصل", "الحصة", "رقم الطالب", "اسم الطالب", "الحالة"]

@st.cache_data(ttl=5, show_spinner=False)
def _fetch_student_rows():
    sb = get_supabase()
    if sb is None:
        return []
    try:
        res = sb.table("thaghr_student_attendance").select(
            "date, teacher_name, grade, section, period, student_id, student_name, status"
        ).order("id", desc=True).limit(50000).execute()
        return res.data or []
    except Exception:
        return []

def load_student_attendance_db():
    rows = _fetch_student_rows()
    if not rows:
        return pd.DataFrame(columns=STU_COLS)
    df = pd.DataFrame(rows)
    rename = {
        "date": "التاريخ",
        "teacher_name": "اسم المعلم",
        "grade": "الصف",
        "section": "الفصل",
        "period": "الحصة",
        "student_id": "رقم الطالب",
        "student_name": "اسم الطالب",
        "status": "الحالة",
    }
    df = df.rename(columns=rename)
    for c in STU_COLS:
        if c not in df.columns:
            df[c] = ""
    return df[STU_COLS]

def save_student_attendance_to_db(records):
    sb = get_supabase()
    if sb is None:
        st.error("❌ لم يتم الاتصال بـ Supabase. يرجى التأكد من إضافة url و key في Secrets.")
        return
    try:
        for r in records:
            sb.table("thaghr_student_attendance").delete().eq(
                "date", str(r['التاريخ'])
            ).eq("student_id", str(r['رقم الطالب'])).eq("period", str(r['الحصة'])).execute()

        payload = [{
            "date": str(r['التاريخ']),
            "teacher_name": str(r['اسم المعلم']),
            "grade": str(r['الصف']),
            "section": str(r['الفصل']),
            "period": str(r['الحصة']),
            "student_id": str(r['رقم الطالب']),
            "student_name": str(r['اسم الطالب']),
            "status": str(r['الحالة']),
        } for r in records]

        if payload:
            sb.table("thaghr_student_attendance").insert(payload).execute()
    except Exception as ex:
        st.error(f"حدث خطأ أثناء الحفظ: {ex}")
    finally:
        st.cache_data.clear()

def delete_student_attendance_from_db(scope):
    sb = get_supabase()
    if sb is None:
        return
    try:
        today_str = str(date.today())
        if "يومي" in scope:
            sb.table("thaghr_student_attendance").delete().eq("date", today_str).execute()
        elif "أسبوعي" in scope:
            seven = str(date.today() - timedelta(days=7))
            sb.table("thaghr_student_attendance").delete().gte("date", seven).execute()
        else:
            sb.table("thaghr_student_attendance").delete().neq("student_id", "none").execute()
    except Exception:
        pass
    finally:
        st.cache_data.clear()

# --- دوال سجلات المعلمين ---
@st.cache_data(ttl=5, show_spinner=False)
def _fetch_teacher_rows():
    sb = get_supabase()
    if sb is None:
        return []
    try:
        res = sb.table("thaghr_teacher_daily_logs").select(
            "date, hijri_date, teacher_name, status, sessions_count, notes"
        ).order("id", desc=True).limit(50000).execute()
        return res.data or []
    except Exception:
        return []

def load_teacher_logs_from_db():
    rows = _fetch_teacher_rows()
    out = []
    for r in rows:
        out.append({
            "التاريخ": r.get("date", ""),
            "التاريخ_الهجري": r.get("hijri_date", ""),
            "اسم المعلم": r.get("teacher_name", ""),
            "الحالة": r.get("status", ""),
            "الحصص المرصودة": r.get("sessions_count", 0) or 0,
            "ملاحظات": r.get("notes", "-"),
        })
    return out

def save_teacher_logs_to_db(records, target_date_str=None):
    sb = get_supabase()
    if sb is None:
        return
    try:
        if target_date_str:
            sb.table("thaghr_teacher_daily_logs").delete().eq("date", target_date_str).execute()
        payload = [{
            "date": str(r['التاريخ']),
            "hijri_date": str(r.get('التاريخ_الهجري', '')),
            "teacher_name": str(r['اسم المعلم']),
            "status": str(r['الحالة']),
            "sessions_count": int(r.get('الحصص المرصودة', 0) or 0),
            "notes": str(r.get('ملاحظات', '-')),
        } for r in records]
        if payload:
            sb.table("thaghr_teacher_daily_logs").insert(payload).execute()
    except Exception as ex:
        st.error(f"حدث خطأ أثناء حفظ المعلمين: {ex}")
    finally:
        st.cache_data.clear()

def delete_teacher_logs_from_db(scope):
    sb = get_supabase()
    if sb is None:
        return
    try:
        today_str = str(date.today())
        if "يومي" in scope:
            sb.table("thaghr_teacher_daily_logs").delete().eq("date", today_str).execute()
        elif "أسبوعي" in scope:
            seven = str(date.today() - timedelta(days=7))
            sb.table("thaghr_teacher_daily_logs").delete().gte("date", seven).execute()
        else:
            sb.table("thaghr_teacher_daily_logs").delete().neq("teacher_name", "none").execute()
    except Exception:
        pass
    finally:
        st.cache_data.clear()

# --- دوال إدارة الطلاب (إضافة / نقل) ---
def add_student_db(student_id, student_name, grade, section):
    sb = get_supabase()
    if sb is None:
        return
    try:
        sb.table("thaghr_custom_student_roster").upsert({
            "student_id": str(student_id),
            "student_name": str(student_name),
            "grade": str(grade),
            "section": str(section),
        }).execute()
    except Exception as ex:
        st.error(f"خطأ أثناء إضافة الطالب: {ex}")
    finally:
        st.cache_data.clear()

def move_student_db(student_id, student_name, new_grade, new_section):
    add_student_db(student_id, student_name, new_grade, new_section)

@st.cache_data(ttl=5, show_spinner=False)
def _fetch_roster_rows():
    sb = get_supabase()
    if sb is None:
        return []
    try:
        res = sb.table("thaghr_custom_student_roster").select(
            "student_id, student_name, grade, section"
        ).limit(50000).execute()
        return res.data or []
    except Exception:
        return []

def get_active_students_db():
    st_db = copy.deepcopy(STUDENTS_DB)
    rows = _fetch_roster_rows()
    for row in rows:
        st_id = row.get("student_id")
        st_name = row.get("student_name")
        new_grade = row.get("grade")
        new_section = row.get("section")
        for g in list(st_db.keys()):
            for s in list(st_db[g].keys()):
                st_db[g][s] = [x for x in st_db[g][s] if str(x['id']).strip() != str(st_id).strip()]
        if new_grade in st_db and new_section in st_db[new_grade]:
            st_db[new_grade][new_section].append({"id": str(st_id), "name": str(st_name)})
    return st_db

# =========================================================
# قوائم الطلاب المحفورة
# =========================================================
STUDENTS_DB = {
    "الأول المتوسط": {
        "أول أول (فصل 1)": [
            {"id": "1167628468", "name": "ابراهيم بن محمد بن علي الوهيبي"},
            {"id": "2395664317", "name": "بلال عبدالرزاق عيسى العيسى"},
            {"id": "1170582165", "name": "حسام بن محمد بن علي ال رايان البارقي"},
            {"id": "1169004353", "name": "ريان عبدالله جابر الاسمري"},
            {"id": "2446713998", "name": "زيد زياد عبد اللطيف ابو قبع"},
            {"id": "2527104554", "name": "سامي سعد عباس حمد"},
            {"id": "1170111759", "name": "سعد ناصر سعد السيف"},
            {"id": "1195559479", "name": "عبدالعزيز عبدالله عبدالعزيز العمار"},
            {"id": "1153310501", "name": "عبدالله بن سليمان بن عبدالله الراجحي"},
            {"id": "1170836520", "name": "عبدالله سعد بن محمد العيشان"},
            {"id": "1171448515", "name": "علي احمد علي كريري"},
            {"id": "1170853053", "name": "علي سعد علي القحطاني"},
            {"id": "1172018036", "name": "عمر عبدالله سعد الجبرين"},
            {"id": "2552851368", "name": "مازن اسلام احمد ابراهيم موسى"},
            {"id": "013609321", "name": "محمد أحمد علي عقيل"},
            {"id": "2394606749", "name": "محمد اشرف مسعود ابوخاطر"},
            {"id": "1170042046", "name": "محمد بن فيصل بن مصلح الشمراني"},
            {"id": "1169174164", "name": "محمد نايف فراج الدعجاني"},
            {"id": "2380890976", "name": "وائل -- بولعيش"}
        ],
        "أول ثاني (فصل 2)": [
            {"id": "1170348286", "name": "الوليد ابن خالد بن فهد العتيبي"},
            {"id": "1172433185", "name": "باسل محمد فرج الدوسري"},
            {"id": "1173391556", "name": "بسام بن عبدالكريم بن عبدالله الحرقان الدوسري"},
            {"id": "1169185053", "name": "تركي عبدالله مسفر الدوسري"},
            {"id": "1170108078", "name": "تميم فهد عبدالعزيز العزاز"},
            {"id": "1170970741", "name": "جاسر بن عبدالله بن منصور المطارحة الحارثي"},
            {"id": "1168982427", "name": "راكان عبدالله يحي كريري"},
            {"id": "1172590968", "name": "ريان عبدالله منصور السبر"},
            {"id": "2392863888", "name": "ريان وليد - حلاق"},
            {"id": "1170420473", "name": "سيف عبدالكريم بريك العصيمي"},
            {"id": "1168942108", "name": "صالح حسن فتحي سندى"},
            {"id": "1173182138", "name": "عبدالرحمن ابراهيم عبدالله الحضيف"},
            {"id": "1172448548", "name": "عبدالله صالح حمد الصفيان"},
            {"id": "1170000945", "name": "فهد ابن احمد بن فهد العثمان"},
            {"id": "1167092616", "name": "فهد عويض ثعيل المطيري"},
            {"id": "1170413171", "name": "فهد نايف فهد الحسينان"},
            {"id": "1170294118", "name": "فيصل موينع عبدالله بن موينع"},
            {"id": "1171524604", "name": "فيصل ناصر سيف العريفي"},
            {"id": "2502333707", "name": "محمد اسلام محمد دراز"},
            {"id": "1170374993", "name": "مشاري عثمان سعد ناصر السعد"},
            {"id": "1170884165", "name": "يزن محمد علي اليحيا"},
            {"id": "1170548737", "name": "يوسف محمد عبدالله الدوسري"}
        ]
    },
    "الثاني المتوسط": {
        "ثاني أول (فصل 1)": [
            {"id": "1163760935", "name": "احمد سامي بن احمد العمران"},
            {"id": "1153756612", "name": "الوليد عبدالله بن ابراهيم المبدل"},
            {"id": "1164269209", "name": "ذياب بن محمد بن ذياب بن محمد ال مريع القحطاني"},
            {"id": "1163187972", "name": "راكان سالم بن محمد بن مسفر القحطاني"},
            {"id": "1171617069", "name": "سعود خالد عبدالله الحمد"},
            {"id": "1163458878", "name": "سعود مشعل بن ابراهيم الشثري"},
            {"id": "1167623758", "name": "سلطان عبدالله حسن القحطاني"},
            {"id": "1164769430", "name": "عبدالرحمن حمد بن محمد العريفي"},
            {"id": "1167893740", "name": "عبدالرحمن ربيع جابر خبراني"},
            {"id": "1159740032", "name": "عبدالعزيز سعود بن فهد العتيبي"},
            {"id": "1164747436", "name": "عبدالمجيد بن محمد بن مسعود آل عايض القحطاني"},
            {"id": "1160901128", "name": "فيصل بن عبدالله بن سعود بن عبدالعزيز الجميعه"},
            {"id": "1162168627", "name": "مبارك صالح مبارك هليل"},
            {"id": "1163212978", "name": "محمد بن عبدالله بن حمد بن ناصر بن عمران"},
            {"id": "1161858301", "name": "محمد عبدالمحسن ناصر الحزام"},
            {"id": "1175902442", "name": "محمد فايز عبدالرحمن بن يوسف"},
            {"id": "1165686179", "name": "مشاري سلطان سالم الشمراني"},
            {"id": "1166040053", "name": "معاذ عبدالله سعود العريفي"},
            {"id": "1167081981", "name": "ناصر حسين محمد ال جبران"},
            {"id": "1171868639", "name": "وائل بن عبدالله بن عامر علي ال عبيد الغامدي"},
            {"id": "1163191222", "name": "يزيد بن طارق بن علي الحديثي"}
        ],
        "ثاني ثاني (فصل 2)": [
            {"id": "1166753291", "name": "ابراهيم بن مبارك بن راشد بن عبدالرحمن السبعان آل موينع"},
            {"id": "1163613795", "name": "ابراهيم ياسر ابراهيم الحلوى"},
            {"id": "1167148251", "name": "حامد بن محمد بن حامد شباط"},
            {"id": "1164599977", "name": "حسام حسن محمد الشهري"},
            {"id": "1169057351", "name": "خالد تركي عايض القحطاني"},
            {"id": "1164120600", "name": "خالد داود بن عابد الحارثي"},
            {"id": "1165839455", "name": "سطام عبدالعزيز عبدالله العريفي"},
            {"id": "1163778960", "name": "سعود سلطان بن هليل العتيبي"},
            {"id": "1166582989", "name": "طلال محمد منير المهدرس"},
            {"id": "1165143783", "name": "عبدالكريم مساعد عبدالعزيز الهزاع"},
            {"id": "1164277830", "name": "عبداللطيف ابراهيم محمد الطمره"},
            {"id": "1165495258", "name": "عبدالله سامي سعد الحوشاني"},
            {"id": "013609088", "name": "علي أحمد علي عقيل"},
            {"id": "1164825802", "name": "عمر بن سعد بن هلال الشبانات"},
            {"id": "1163537838", "name": "فارس مشعل عبدالله بن موينع"},
            {"id": "1162761306", "name": "فهد عيسى محمد العيسى"},
            {"id": "1164997858", "name": "مازن خالد دخيل المطيري"},
            {"id": "2348937422", "name": "مازن رفعت محمد حاج النيل"},
            {"id": "1172720045", "name": "محمد بن علي محسن العثيميني"},
            {"id": "1166803245", "name": "نايف بن بندر بن خلفان العلوي"},
            {"id": "1165668417", "name": "نواف عبدالعزيز عبدالله المرزوق"},
            {"id": "1164387977", "name": "هادي سلطان هادي القحطاني"},
            {"id": "1165002153", "name": "يزيد بن حسين بن متعب بن محمد كعكم"}
        ],
        "ثاني ثالث (فصل 3)": [
            {"id": "1166911709", "name": "ثامر عمر ابراهيم عثمان"},
            {"id": "008464815", "name": "جهاد فارس عبدالقادر حتاوي"},
            {"id": "1164830562", "name": "خالد محمد عبدالكريم الخفاجي"},
            {"id": "1188914319", "name": "سعد ابن مسفر بن سعد القحطاني"},
            {"id": "1165099498", "name": "سعود بن عبدالله بن سعود السحامي"},
            {"id": "1167770468", "name": "سعود ناصر سيف العريفي"},
            {"id": "2344500760", "name": "سعيد محمد - باوزير"},
            {"id": "1164983874", "name": "طلال بن فهد بن عطيه بالحكم الزهراني"},
            {"id": "2362260263", "name": "عبدالرحمن احمد جاسم الحمدي"},
            {"id": "1167153434", "name": "عبدالعزيز ماجد راشد الزير"},
            {"id": "1164512566", "name": "عبدالعزيز وليد ناصر بن سعران"},
            {"id": "1167267341", "name": "عبدالله بن بندر بن فهد المسيحل"},
            {"id": "2358022958", "name": "عز الدين احمد محمد سعد"},
            {"id": "1167515020", "name": "عزام خالد شلهوب بن شلهوب"},
            {"id": "1164747014", "name": "عزام فهد احمد صلوي"},
            {"id": "4533080448", "name": "عمر وليد ياسين درويش علي"},
            {"id": "1163397811", "name": "فارس ابن محمد بن سالم بن نويشي الوهبي الحربي"},
            {"id": "1166629798", "name": "يزيد بن حمد بن مترك بن محمد ال مسعود القحطاني"},
            {"id": "1167371093", "name": "يوسف عايد عواد البلوي"}
        ]
    },
    "الثالث المتوسط": {
        "ثالث أول (فصل 1)": [
            {"id": "1158966166", "name": "أصيل ناصر بن محمد مذكور"},
            {"id": "1162308223", "name": "خالد محمد مسدف معافا"},
            {"id": "1161109093", "name": "راكان بن عبدالله بن سالم اليافعي"},
            {"id": "1160805899", "name": "زياد احمد بن علي اللحيد"},
            {"id": "1160267124", "name": "سطام محمد سعود الدوسري"},
            {"id": "1163270869", "name": "سلطان احمد صالح الفنتوخ"},
            {"id": "1161085236", "name": "ضاري صالح مهنا العازمي"},
            {"id": "1160585624", "name": "عبدالعزيز عبدالله شراز المالكي"},
            {"id": "1160050678", "name": "عبدالعزيز عبدالله عايض الاسمري"},
            {"id": "1161021314", "name": "عبدالله عبيد عبدالله العتيبي"},
            {"id": "1160857700", "name": "عبدالله فهد جلوي سالم الشرمي"},
            {"id": "2502333723", "name": "عماد الدين اسلام محمد دراز"},
            {"id": "1161418593", "name": "فهد عبدالرحمن فهد العتيبي"},
            {"id": "1163074592", "name": "فيصل بن عبدالمحسن بن عايض العصيمي العتيبي"},
            {"id": "1171918236", "name": "مازن خالد عبدربه الزهراني"},
            {"id": "1158815876", "name": "محمد سلطان عبدالعزيز العيد"},
            {"id": "1166075653", "name": "محمد مقعد ساير العتيبي"},
            {"id": "1160693949", "name": "مشاري ابراهيم عبداللطيف المغربي"},
            {"id": "1160803878", "name": "مشاري علي موسى عقيلي"},
            {"id": "1161661846", "name": "مهند عبدالله فهد الزكري"},
            {"id": "1159404795", "name": "نواف وليد حمد الشعلان"},
            {"id": "1168385894", "name": "يوسف نايف مقعد العتيبي"}
        ],
        "ثالث ثاني (فصل 2)": [
            {"id": "1156933093", "name": "تركي عبدالعزيز عبدالله المرزوق"},
            {"id": "1160223317", "name": "تركي عثمان عبدالعزيز العثمان"},
            {"id": "1159683497", "name": "راشد احمد فهد ال سعيد"},
            {"id": "2310646332", "name": "راكان ابراهيم محمد ديوان"},
            {"id": "1161397599", "name": "ريان ناصر عبدالرحمن المرشود"},
            {"id": "1163112129", "name": "صالح بن ممدوح بن صالح بن خالد الجويعي"},
            {"id": "2508581135", "name": "عبد الرحمن محمد صلاح بدر الدين"},
            {"id": "1162188872", "name": "عبدالعزيز تركي عبدالعزيز اللهيم"},
            {"id": "1161340763", "name": "عبدالعزيز عبدالمحسن فهد بن بديع"},
            {"id": "1171845140", "name": "عبدالله متعب بن عبدالرحمن الجبرين"},
            {"id": "1159200318", "name": "عبدالمحسن طارق بن عبدالرحمن العروان"},
            {"id": "1162454266", "name": "عمر فهد محمد السقامي"},
            {"id": "1165152107", "name": "فيصل محمد صالح الفنتوخ"},
            {"id": "1162325722", "name": "ماجد فهد عبدالعزيز الكثيري"},
            {"id": "1162461857", "name": "محمد خالد محمد بن مشرف"},
            {"id": "1161288897", "name": "محمد سعد بن محمد العيشان"},
            {"id": "1156334813", "name": "محمد عبدالعزيز محمد الخالدي"},
            {"id": "1162044851", "name": "مهند ماجد علي كعبي"},
            {"id": "1158021137", "name": "ناصر محمد عبدالله الزريعي"},
            {"id": "1161363443", "name": "نواف سعد بن علي القاسم"},
            {"id": "1162274086", "name": "ياسر تركي اسماعيل مسملي"}
        ],
        "ثالث ثالث (فصل 3)": [
            {"id": "1163525544", "name": "ثامر وليد بن عبدالعزيز الطليحي"},
            {"id": "1160712996", "name": "خالد بن عبدالرؤف بن عبدالرحمن بن عبدالله الشنيير"},
            {"id": "1162560054", "name": "خالد عبدالله خالد الخالدي"},
            {"id": "1174188647", "name": "خالد محمد بن عبدالله ال درعان"},
            {"id": "1159155223", "name": "راشد سعيد راشد عبدالسلام"},
            {"id": "1174226389", "name": "راشد صالح بن عبدالعزيز الحلوان"},
            {"id": "1167756897", "name": "رواد محمد ابراهيم الخليل"},
            {"id": "1159394046", "name": "صالح بن محمد بن صالح الميموني المطيري"},
            {"id": "1158551372", "name": "عبدالرحمن بدر عبدالرحمن الطريقي"},
            {"id": "1195815558", "name": "عبدالرحمن خالد محمد سعيد"},
            {"id": "1158561843", "name": "عبدالله تركي عبدالله الأحمد"},
            {"id": "1159977451", "name": "عبدالله عبدالرحمن عبدالله النجراني"},
            {"id": "1162387458", "name": "علي بن خالد بن علي العجيري"},
            {"id": "1158128270", "name": "علي عبدالله علي ال حمود"},
            {"id": "1161333677", "name": "فارس وليد بن عبدالله الحوطي"},
            {"id": "1158198604", "name": "فهد بن خالد بن فهد بن عبدالعزيز الزيد"},
            {"id": "1159551264", "name": "فيصل عبدالرحمن عزيز القحطاني"},
            {"id": "1186515613", "name": "متعب مطر جمعان الدوسري"},
            {"id": "1159852746", "name": "نواف فهد بن ناصر القحطاني"},
            {"id": "1163027392", "name": "يوسف عبدالله عوض العتيبي"}
        ]
    }
}

TEACHERS_LIST = [
    "محمد سامي السعيد", "علي محمد معوض", "أحمد عبد الحميد سعيد",
    "محمد عبد المنعم أبو كيلة", "هيثم رضا عطية", "عماد الدين نصر كرم",
    "السيد الغريب بدوي", "محمد إبراهيم عبد الرحمن", "أسامة أحمد سالم",
    "عماد بكر عارف", "إبراهيم علي العتيبي", "عيسى خالد العويس", "زيد بن علي التميمي"
]

PERIODS_LIST = [f"الحصة {i}" for i in range(1, 8)]

TEACHER_PASSWORDS = {
    "محمد سامي السعيد": "101", "علي محمد معوض": "102", "أحمد عبد الحميد سعيد": "103",
    "محمد عبد المنعم أبو كيلة": "104", "هيثم رضا عطية": "105", "عماد الدين نصر كرم": "106",
    "السيد الغريب بدوي": "107", "محمد إبراهيم عبد الرحمن": "108", "أسامة أحمد سالم": "109",
    "عماد بكر عارف": "110", "إبراهيم علي العتيبي": "111", "عيسى خالد العويس": "112",
    "زيد بن علي التميمي": "113"
}

# =========================================================
# 1. تهيئة صفحة Streamlit والتنسيق (RTL & CSS احترافي)
# =========================================================
st.set_page_config(
    page_title="نظام تحضير متوسطة الثغر النموذجية",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded"
)

# تطبيق اتجاه RTL وتنسيقات CSS احترافية
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&display=swap');

/* ضبط خط القاهرة والاتجاه من اليمين لليسار لكافة العناصر */
html, body, [class*="css"], .stApp {
    font-family: 'Cairo', sans-serif !important;
    direction: rtl !important;
    text-align: right !important;
    background-color: #F8FAFC !important;
}

/* تنسيق الشريط الجانبي */
[data-testid="stSidebar"] {
    direction: rtl !important;
    text-align: right !important;
    background-color: #0F172A !important;
}

[data-testid="stSidebar"] * {
    direction: rtl !important;
    text-align: right !important;
    color: #F8FAFC !important;
}

/* تنسيق الحاوية الرئيسية */
.main .block-container {
    direction: rtl !important;
    text-align: right !important;
    padding-top: 1.5rem !important;
    padding-bottom: 2rem !important;
}

/* بطاقات الإحصائيات الفاخرة */
.metric-card-box {
    background: linear-gradient(135deg, #FFFFFF 0%, #EFF6FF 100%);
    border-radius: 14px;
    padding: 16px;
    text-align: center;
    border: 1px solid #BFDBFE;
    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.05);
}

.metric-card-val {
    font-size: 30px;
    font-weight: 800;
    line-height: 1.2;
}

.metric-card-lbl {
    font-size: 13px;
    font-weight: 700;
    color: #475569;
    margin-top: 4px;
}

/* بطاقة الطالب في كشف الرصد */
.student-row-card {
    background: #FFFFFF;
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 10px;
    border-right: 5px solid #2563EB;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

/* الأزرار المدورة والأنيميشن */
.stButton > button {
    border-radius: 8px !important;
    font-weight: 700 !important;
    font-family: 'Cairo', sans-serif !important;
    transition: all 0.2s ease-in-out !important;
}

.stButton > button:hover {
    transform: translateY(-1px) !important;
}

/* محاذاة أزرار الاختيار الراديو */
div[role="radiogroup"] {
    direction: rtl !important;
    justify-content: flex-start !important;
}

/* ضبط القوائم والحقول */
.stSelectbox, .stTextInput, .stDateInput, .stNumberInput {
    direction: rtl !important;
    text-align: right !important;
}

.stDataFrame {
    direction: rtl !important;
}

/* شارات حالة الاتصال */
.status-badge-ok {
    background-color: #10B981;
    color: white;
    padding: 6px 12px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: bold;
    display: inline-block;
}

.status-badge-err {
    background-color: #EF4444;
    color: white;
    padding: 6px 12px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: bold;
    display: inline-block;
}
</style>
""", unsafe_allow_html=True)

# شريط حالة الاتصال بالشريط الجانبي
if supabase_ready():
    st.sidebar.markdown("<div style='text-align:center; margin-bottom:15px;'><span class='status-badge-ok'>🟢 متصل بسحابة Supabase</span></div>", unsafe_allow_html=True)
else:
    st.sidebar.markdown("<div style='text-align:center; margin-bottom:15px;'><span class='status-badge-err'>🔴 غير متصل بـ Supabase</span></div>", unsafe_allow_html=True)
    with st.expander("🔌 طريقة تفعيل الربط عبر Secrets (اضغط هنا)", expanded=True):
        st.warning("يرجى نسخ الكود التالي ووضعه في إعدادات التطبيق (Streamlit Cloud > App settings > Secrets):")
        st.code("""[supabase]
url = "https://yathpzoxjfpgahkbjzgz.supabase.co"
key = "sb_publishable_4Igw4yxTyqcZzSvXei6TEg_cuxhLKcE"
""", language="toml")

if 'dev_unlocked' not in st.session_state:
    st.session_state['dev_unlocked'] = False

if not st.session_state['dev_unlocked']:
    st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    div[data-testid="stToolbar"] {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

with st.sidebar.expander("🔐 فك قفل أدوات التعديل والرمز"):
    pwd_dev = st.text_input("أدخل كلمة المرور (adam0000):", type="password", key="pwd_dev_input")
    if st.button("فتح التعديل"):
        if pwd_dev == "adam0000":
            st.session_state['dev_unlocked'] = True
            st.success("تم فك القفل بنجاح!")
            st.rerun()
        else:
            st.error("كلمة المرور غير صحيحة!")

def gregorian_to_hijri_approx(g_date):
    try:
        year, month, day = g_date.year, g_date.month, g_date.day
        if month < 3:
            year -= 1
            month += 12
        a = year // 100
        b = 2 - a + (a // 4)
        jd = int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + b - 1524
        l = jd - 1948440 + 10632
        n = (l - 1) // 10631
        l = l - 10631 * n + 354
        j = ((10985 - l) // 5316) * ((50 * l) // 17719) + ((l // 5670)) * ((43 * l) // 15238)
        l = l - ((30 - j) // 15) * ((17719 * j) // 50) - (j // 16) * ((15238 * j) // 43) + 29
        h_month = (24 * l) // 709
        h_day = l - (709 * h_month) // 24
        h_year = 30 * n + j - 30
        return f"{h_year}/{h_month:02d}/{h_day:02d} هـ"
    except Exception:
        return f"{g_date.strftime('%Y/%m/%d')} هـ"

today_curr = date.today()
hijri_curr = gregorian_to_hijri_approx(today_curr)

# =========================================================
# دوال توليد طباعة HTML
# =========================================================
def generate_printable_html(df_subset, report_title):
    rows_html = ""
    for idx, row in enumerate(df_subset.to_dict('records'), 1):
        status_color = "#DC2626" if row['الحالة'] == "غائب" else "#D97706" if row['الحالة'] in ["خارج الفصل"] else "#CA8A04" if row['الحالة'] == "متأخر" else "#16A34A"
        teacher = row.get('اسم المعلم', 'غير محدد')
        rows_html += f'<tr><td>{idx}</td><td style="text-align: right;"><b>{row["اسم الطالب"]}</b><br><small style="color:#64748B;">الهوية: {row["رقم الطالب"]}</small></td><td>{row["الصف"]}</td><td>{row["الفصل"]}</td><td>{row["الحصة"]}</td><td>{teacher}</td><td style="color:{status_color};font-weight:bold;">{row["الحالة"]}</td></tr>'
    
    html_code = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<title>{report_title}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
body {{ font-family: 'Cairo', sans-serif; text-align: right; padding: 25px; background:#FFF; color:#1E293B; direction: rtl; }}
.header {{ text-align: center; border-bottom: 3px solid #0F2552; padding-bottom: 12px; margin-bottom: 20px; }}
h2 {{ color:#0F2552; margin:5px; font-weight:800; font-size:22px; }}
h4 {{ color:#4B5563; margin:5px; font-weight:700; font-size:16px; }}
table {{ width:100%; border-collapse: collapse; margin-top:10px; }}
th, td {{ border:1px solid #CBD5E1; padding:10px; text-align:center; font-size:13px; }}
th {{ background:#0F2552; color:white; font-weight:700; }}
tr:nth-child(even) {{ background:#F8FAFC; }}
</style>
</head>
<body>
<div class="header">
    <h2>🏫 مدرسة متوسطة الثغر النموذجية</h2>
    <h4>{report_title}</h4>
</div>
<table>
<thead>
<tr><th>#</th><th>اسم الطالب</th><th>الصف</th><th>الفصل</th><th>الحصة</th><th>المعلم</th><th>الحالة</th></tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
</body>
</html>"""
    return html_code

def generate_teacher_range_report_html(teacher_summary_list, start_d, end_d, cal_system):
    rows_html = ""
    for idx, rec in enumerate(teacher_summary_list, 1):
        absent_cnt = rec.get('عدد مرات الغياب', 0)
        late_cnt = rec.get('عدد مرات التأخر', 0)
        present_cnt = rec.get('عدد أيام الحضور', 0)
        absent_style = "color:#DC2626;font-weight:bold;" if absent_cnt > 0 else "color:#16A34A;"
        late_style = "color:#CA8A04;font-weight:bold;" if late_cnt > 0 else "color:#16A34A;"
        rows_html += f'<tr><td>{idx}</td><td style="text-align:right;font-weight:bold;">{rec["اسم المعلم"]}</td><td style="color:#16A34A;font-weight:bold;">{present_cnt} يوم</td><td style="{absent_style}">{absent_cnt} مرة</td><td style="{late_style}">{late_cnt} مرة</td><td>{rec.get("إجمالي الحصص المرصودة", 0)} حصة</td></tr>'
    
    html_code = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<title>تقرير المعلمين</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
body {{ font-family:'Cairo',sans-serif; text-align:right; padding:25px; background:#FFF; color:#1E293B; direction:rtl; }}
.header {{ text-align:center; border-bottom:3px solid #0F2552; padding-bottom:12px; margin-bottom:20px; }}
h2 {{ color:#0F2552; margin:5px; font-weight:800; font-size:22px; }}
table {{ width:100%; border-collapse:collapse; margin-top:10px; }}
th, td {{ border:1px solid #CBD5E1; padding:10px; text-align:center; font-size:14px; }}
th {{ background:#0F2552; color:white; font-weight:700; }}
tr:nth-child(even) {{ background:#F8FAFC; }}
</style>
</head>
<body>
<div class="header">
    <h2>🏫 تقرير حضور وغياب المعلمين</h2>
    <p>الفترة من {start_d} إلى {end_d}</p>
</div>
<table>
<thead>
<tr><th>#</th><th>اسم المعلم</th><th>الحضور</th><th>الغياب</th><th>التأخر</th><th>الحصص المرصودة</th></tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
</body>
</html>"""
    return html_code

# =========================================================
# اختيار لوحة التحكم
# =========================================================
st.sidebar.title("📌 نظام المتابعة")
st.sidebar.markdown("<div style='background:#1E293B; border-right:4px solid #3B82F6; border-radius:8px; padding:10px; margin-bottom:12px; font-weight:700; color:#F8FAFC;'>👇 اختر لوحة التحكم:</div>", unsafe_allow_html=True)
role = st.sidebar.radio(
    "اختر لوحة التحكم:",
    ["👨‍🏫 حساب المعلم (رصد الحضور)", "👔 حساب الوكيل والمدير (المتابعة والتصدير)"],
    label_visibility="collapsed"
)
st.write("")

# =========================================================
# 7. واجهة المعلم (رصد حضور الطلاب)
# =========================================================
if role == "👨‍🏫 حساب المعلم (رصد الحضور)":
    st.markdown("### 📋 رصد حضور وغياب الطلاب")
    students_db = get_active_students_db()

    col_t, col_pin = st.columns([3, 2])
    with col_t:
        teacher_name = st.selectbox("اسم المعلم:", TEACHERS_LIST)
    with col_pin:
        teacher_pin = st.text_input("🔑 كلمة المرور (3 أرقام):", type="password", key=f"t_pin_{teacher_name}", max_chars=3)

    correct_pin = TEACHER_PASSWORDS.get(teacher_name, "101")

    if teacher_pin == correct_pin:
        st.success(f"✅ أهلاً بك {teacher_name}! تم التحقق من كلمة المرور بنجاح.")

        col_g, col_s, col_p, col_d = st.columns(4)
        with col_g:
            grade = st.selectbox("الصف الدراسي:", list(students_db.keys()))
        with col_s:
            section = st.selectbox("الفصل:", list(students_db[grade].keys()))
        with col_p:
            period = st.selectbox("الحصة:", PERIODS_LIST)
        with col_d:
            att_date = st.date_input("التاريخ:", date.today())

        students_list = students_db[grade][section]

        st.markdown(f"""
        <div style="background:#EFF6FF; border-right:5px solid #2563EB; padding:14px; border-radius:10px; margin-top:10px; margin-bottom:20px; box-shadow: 0 2px 6px rgba(0,0,0,0.03);">
            <span style="font-weight:700; color:#1E3A8A; font-size:15px;">
                👨‍🏫 <b>المعلم:</b> {teacher_name} &nbsp;|&nbsp; 🏫 <b>الفصل:</b> {grade} - {section} &nbsp;|&nbsp; ⏰ <b>الحصة:</b> {period} &nbsp;|&nbsp; 📅 <b>التاريخ:</b> {att_date}
            </span>
            <br><span style="font-weight:700; color:#D97706; font-size:14px;">إجمالي طلاب الفصل: {len(students_list)} طالب</span>
        </div>
        """, unsafe_allow_html=True)

        attendance_records = {}
        for idx, student in enumerate(students_list, 1):
            col_info, col_radio = st.columns([4, 3])
            with col_info:
                st.markdown(f"""
                <div class="student-row-card">
                    <b>{idx}. {student['name']}</b><br>
                    <small style="color:#64748B;">رقم الهوية: {student['id']}</small>
                </div>
                """, unsafe_allow_html=True)
            with col_radio:
                status = st.radio(
                    f"حالة {student['name']}:",
                    ["حاضر", "غائب", "خارج الفصل", "متأخر"],
                    key=f"{teacher_name}_{grade}_{section}_{period}_{student['id']}",
                    horizontal=True,
                    label_visibility="collapsed"
                )
                attendance_records[student['id']] = {"name": student['name'], "status": status}

        st.write("---")
        if st.button("💾 حفظ وإرسال كشف الحضور لقاعدة البيانات", type="primary", use_container_width=True):
            records_to_save = []
            for st_id, info in attendance_records.items():
                records_to_save.append({
                    "التاريخ": str(att_date), "اسم المعلم": teacher_name,
                    "الصف": grade, "الفصل": section, "الحصة": period,
                    "رقم الطالب": st_id, "اسم الطالب": info['name'], "الحالة": info['status']
                })
            save_student_attendance_to_db(records_to_save)
            st.success(f"✨ تم حفظ ورصد حضور فصل ({section}) لعدد {len(records_to_save)} طالب بنجاح وبشكل دائم في قاعدة البيانات!")

    elif teacher_pin == "":
        st.info(f"🔒 يرجى إدخال كلمة المرور المكونة من 3 أرقام الخاصة بالمعلم ({teacher_name}) للمتابعة.")
    else:
        st.error(f"❌ كلمة المرور غير صحيحة للمعلم ({teacher_name})! يرجى التأكد وإعادة المحاولة.")

# =========================================================
# 8. حساب الوكيل والمدير
# =========================================================
else:
    if 'admin_authenticated' not in st.session_state:
        st.session_state['admin_authenticated'] = False

    if not st.session_state['admin_authenticated']:
        st.warning("🔒 هذه اللوحة مخصصة لإدارة المدرسة فقط. يرجى إدخال كلمة المرور للمتابعة:")
        pwd_input = st.text_input("كلمة المرور:", type="password")
        if st.button("تسجيل الدخول"):
            if pwd_input == "adam112233":
                st.session_state['admin_authenticated'] = True
                st.success("تم الدخول بنجاح!")
                st.rerun()
            else:
                st.error("كلمة المرور غير صحيحة! يرجى التأكد وإعادة المحاولة.")
    else:
        col_admin_top1, col_admin_top2 = st.columns([4, 1])
        with col_admin_top2:
            if st.button("🚪 تسجيل الخروج", use_container_width=True):
                st.session_state['admin_authenticated'] = False
                st.rerun()

        st.write("---")
        df = load_student_attendance_db()
        teacher_logs_db = load_teacher_logs_from_db()

        metric_dates = ["📆 الكل (إجمالي السجل)"] + (sorted(list(df['التاريخ'].unique()), reverse=True) if not df.empty else [])
        metric_day = st.selectbox("📅 اختر اليوم لعرض إحصائياته (تتغير العدادات تلقائياً):", metric_dates, key="metric_day_sel")

        if not df.empty and not metric_day.startswith("📆"):
            df_metric = df[df['التاريخ'] == metric_day]
        else:
            df_metric = df

        tot_records = len(df_metric)
        tot_absent = len(df_metric[df_metric['الحالة'] == 'غائب']) if not df_metric.empty else 0
        tot_out = len(df_metric[df_metric['الحالة'] == 'خارج الفصل']) if not df_metric.empty else 0
        tot_late = len(df_metric[df_metric['الحالة'] == 'متأخر']) if not df_metric.empty else 0

        _day_lbl = "إجمالي السجل" if metric_day.startswith("📆") else f"يوم {metric_day}"
        st.markdown(f"<div style='text-align:center; color:#0F2552; font-weight:700; margin-bottom:12px;'>📊 الإحصائيات المعروضة: {_day_lbl}</div>", unsafe_allow_html=True)

        m1, m2, m3, m4 = st.columns(4)
        m1.markdown(f'<div class="metric-card-box"><div class="metric-card-val" style="color:#0F2552;">{tot_records}</div><div class="metric-card-lbl">إجمالي الرصد</div></div>', unsafe_allow_html=True)
        m2.markdown(f'<div class="metric-card-box"><div class="metric-card-val" style="color:#DC2626;">{tot_absent}</div><div class="metric-card-lbl">حالات الغياب</div></div>', unsafe_allow_html=True)
        m3.markdown(f'<div class="metric-card-box"><div class="metric-card-val" style="color:#D97706;">{tot_out}</div><div class="metric-card-lbl">خارج الفصل</div></div>', unsafe_allow_html=True)
        m4.markdown(f'<div class="metric-card-box"><div class="metric-card-val" style="color:#CA8A04;">{tot_late}</div><div class="metric-card-lbl">حالات التأخر</div></div>', unsafe_allow_html=True)

        st.write("---")
        col_del1, col_del2 = st.columns(2)
        with col_del1:
            with st.expander("🗑️ إدارة حذف تقارير حضور الطلاب"):
                st.warning("⚠️ اختر نطاق الحذف المطلوب لكشوف الطلاب:")
                del_st_scope = st.radio("نطاق حذف الطلاب:", ["📅 يومي (اليوم)", "🗓️ أسبوعي (آخر 7 أيام)", "📆 شهري / شامل السجل"], key="del_st_scope")
                conf_st_del = st.checkbox("أؤكد حذف سجلات الطلاب", key="conf_st_del")
                if st.button("🚨 حذف تقارير الطلاب", type="primary", key="btn_del_st"):
                    if conf_st_del:
                        delete_student_attendance_from_db(del_st_scope)
                        st.success("🗑️ تم تنفيذ عملية الحذف لسجلات الطلاب بنجاح!")
                        st.rerun()
                    else:
                        st.error("يرجى التأشير على التأكيد أولاً.")
        with col_del2:
            with st.expander("🗑️ إدارة حذف تقارير حضور المعلمين"):
                st.warning("⚠️ اختر نطاق الحذف المطلوب لسجلات المعلمين:")
                del_tc_scope = st.radio("نطاق حذف المعلمين:", ["📅 يومي (اليوم)", "🗓️ أسبوعي (آخر 7 أيام)", "📆 شهري / شامل السجل"], key="del_tc_scope")
                conf_tc_del = st.checkbox("أؤكد حذف سجلات المعلمين", key="conf_tc_del")
                if st.button("🚨 حذف تقارير المعلمين", type="primary", key="btn_del_tc"):
                    if conf_tc_del:
                        delete_teacher_logs_from_db(del_tc_scope)
                        st.success("🗑️ تم تنفيذ عملية الحذف لسجلات المعلمين بنجاح!")
                        st.rerun()
                    else:
                        st.error("يرجى التأشير على التأكيد أولاً.")

        st.write("---")
        st.markdown("### 🔍 فلترة وتخصيص بيانات التقارير والطباعة")
        students_db = get_active_students_db()
        col_f_date, col_f_grade, col_f_sec, col_f_period = st.columns(4)
        with col_f_date:
            unique_dates = ["الكل"] + (sorted(list(df['التاريخ'].unique())) if not df.empty else [str(date.today())])
            filter_date = st.selectbox("📅 اختر التاريخ:", unique_dates)
        with col_f_grade:
            all_grades = list(students_db.keys())
            filter_grade = st.selectbox("🏫 اختر الصف الدراسي:", ["الكل"] + all_grades)
        with col_f_sec:
            if filter_grade != "الكل":
                available_sections = list(students_db[filter_grade].keys())
                filter_section = st.selectbox("🚪 اختر الفصل:", ["الكل"] + available_sections)
            else:
                all_sections = []
                for g in students_db:
                    all_sections.extend(list(students_db[g].keys()))
                filter_section = st.selectbox("🚪 اختر الفصل:", ["الكل"] + sorted(list(set(all_sections))))
        with col_f_period:
            filter_period = st.selectbox("⏰ اختر الحصة:", ["الكل"] + PERIODS_LIST)

        df_filtered = df.copy() if not df.empty else pd.DataFrame()
        if not df_filtered.empty:
            if filter_date != "الكل":
                df_filtered = df_filtered[df_filtered['التاريخ'] == filter_date]
            if filter_grade != "الكل":
                df_filtered = df_filtered[df_filtered['الصف'] == filter_grade]
            if filter_section != "الكل":
                df_filtered = df_filtered[df_filtered['الفصل'] == filter_section]
            if filter_period != "الكل":
                df_filtered = df_filtered[df_filtered['الحصة'] == filter_period]

        tab_teachers, tab_manage_students, tab_absent, tab_out, tab_late, tab_all = st.tabs([
            "👨‍🏫 إحصائية وتقارير وتعديل المعلمين",
            "🎓 إدارة نقل وإضافة الطلاب",
            "🔴 كشف الطلاب الغائبين",
            "🟠 كشف الطلاب خارج الفصل",
            "🟡 كشف المتأخرين عن الحصة",
            "📋 السجل العام الشامل"
        ])

        with tab_teachers:
            st.markdown("### 👨‍🏫 إحصائية وحالة حضور وغياب كادر المعلمين")
            teacher_session_counts = {}
            if not df.empty:
                t_grouped = df.groupby('اسم المعلم')['الحصة'].nunique()
                teacher_session_counts = t_grouped.to_dict()

            st.markdown("#### ⚙️ رصد وتحديد حالة المعلمين اليومية:")
            teachers_summary_data = {}
            saved_teachers_dict = {row['اسم المعلم']: row['الحالة'] for row in teacher_logs_db if row['التاريخ'] == str(date.today())}

            for t_name in TEACHERS_LIST:
                c_name_t, c_status_t, c_info_t = st.columns([2.5, 3, 2.5])
                c_name_t.markdown(f"**{t_name}**")
                cur_status = saved_teachers_dict.get(t_name, "حاضر")
                new_status = c_status_t.radio(
                    f"حالة المعلم {t_name}:",
                    ["حاضر", "غائب", "متأخر"],
                    index=["حاضر", "غائب", "متأخر"].index(cur_status),
                    key=f"t_status_{t_name}", horizontal=True
                )
                sessions_done = teacher_session_counts.get(t_name, 0)
                c_info_t.write(f"الحصص المرصودة: `{sessions_done} حصة`")
                teachers_summary_data[t_name] = {"status": new_status, "sessions": sessions_done}

            st.write("---")
            if st.button("💾 حفظ وإرسال كشف حضور المعلمين", type="primary", use_container_width=True, key="btn_save_send_teachers"):
                today_str = str(date.today())
                records_tc = []
                for t_name, info in teachers_summary_data.items():
                    records_tc.append({
                        "التاريخ": today_str, "التاريخ_الهجري": gregorian_to_hijri_approx(date.today()),
                        "اسم المعلم": t_name, "الحالة": info['status'],
                        "الحصص المرصودة": info['sessions'], "ملاحظات": "تم الحفظ والإرسال"
                    })
                save_teacher_logs_to_db(records_tc, today_str)
                st.success("✨ تم حفظ وإرسال كشف حضور وغياب المعلمين بنجاح في قاعدة البيانات!")
                st.rerun()

            st.write("---")
            with st.expander("✏️ تعديل حالة المعلمين وتوثيق الملاحظات اليومية"):
                st.info("💡 يمكنك تعديل حالة أي معلم أو إضافة ملاحظة ثم الضغط على حفظ التعديلات.")
                edit_date = st.date_input("اختر تاريخ التعديل:", date.today(), key="edit_t_date")
                today_logs = [r for r in teacher_logs_db if r['التاريخ'] == str(edit_date)]
                if not today_logs:
                    today_logs = [{"التاريخ": str(edit_date), "التاريخ_الهجري": gregorian_to_hijri_approx(edit_date), "اسم المعلم": t, "الحالة": "حاضر", "الحصص المرصودة": teacher_session_counts.get(t, 0), "ملاحظات": "-"} for t in TEACHERS_LIST]
                updated_logs = []
                for t_log in today_logs:
                    c1, c2, c3 = st.columns(3)
                    c1.markdown(f"**{t_log['اسم المعلم']}**")
                    new_st = c2.radio(f"حالة {t_log['اسم المعلم']}", ["حاضر", "غائب", "متأخر"], index=["حاضر", "غائب", "متأخر"].index(t_log['الحالة']), key=f"edit_st_{t_log['اسم المعلم']}_{edit_date}", horizontal=True)
                    new_note = c3.text_input(f"ملاحظة {t_log['اسم المعلم']}", value=t_log.get('ملاحظات', '-'), key=f"note_{t_log['اسم المعلم']}_{edit_date}")
                    updated_logs.append({"التاريخ": str(edit_date), "التاريخ_الهجري": gregorian_to_hijri_approx(edit_date), "اسم المعلم": t_log['اسم المعلم'], "الحالة": new_st, "الحصص المرصودة": teacher_session_counts.get(t_log['اسم المعلم'], 0), "ملاحظات": new_note})
                if st.button("💾 حفظ وتحديث تعديلات المعلمين", type="primary", key="btn_update_edited_teachers"):
                    save_teacher_logs_to_db(updated_logs, str(edit_date))
                    st.success("✨ تم حفظ وتعديل سجلات المعلمين بنجاح في قاعدة البيانات!")
                    st.rerun()

            st.write("---")
            st.markdown("### 🖨️ تقرير ملخص إحصائيات المعلمين للفترة")
            col_r1, col_r2, col_r3, col_r4 = st.columns([2.5, 2.5, 2.5, 2.5])
            with col_r1:
                start_report_date = st.date_input("من تاريخ:", date.today() - timedelta(days=7), key="rep_start_date")
            with col_r2:
                end_report_date = st.date_input("إلى تاريخ:", date.today(), key="rep_end_date")
            with col_r3:
                calendar_type = st.radio("نظام التاريخ للتقرير:", ["ميلادي 📅", "هجري 🌙"], horizontal=True)
            with col_r4:
                st.write("")
                st.write("")
                btn_start_search = st.button("▶️ بدء عرض التقرير", type="primary", use_container_width=True)
            if btn_start_search:
                st.session_state['search_teacher_started'] = True
            if st.session_state.get('search_teacher_started', False):
                teacher_summary_list = []
                for t in TEACHERS_LIST:
                    t_logs = []
                    for r in teacher_logs_db:
                        if r['اسم المعلم'] == t:
                            try:
                                r_d = datetime.strptime(r['التاريخ'], "%Y-%m-%d").date()
                                if start_report_date <= r_d <= end_report_date:
                                    t_logs.append(r)
                            except Exception:
                                pass
                    p_cnt = sum(1 for x in t_logs if x['الحالة'] == "حاضر")
                    a_cnt = sum(1 for x in t_logs if x['الحالة'] == "غائب")
                    l_cnt = sum(1 for x in t_logs if x['الحالة'] == "متأخر")
                    tot_sess = sum(x.get('الحصص المرصودة', 0) for x in t_logs)
                    teacher_summary_list.append({"اسم المعلم": t, "عدد أيام الحضور": p_cnt, "عدد مرات الغياب": a_cnt, "عدد مرات التأخر": l_cnt, "إجمالي الحصص المرصودة": tot_sess})
                df_t_summary = pd.DataFrame(teacher_summary_list)
                st.markdown(f"#### 📊 بيانات إحصائية المعلمين من `{start_report_date}` إلى `{end_report_date}`:")
                st.dataframe(df_t_summary, use_container_width=True)
                cal_sys_name = "هجري" if "هجري" in calendar_type else "ميلادي"
                html_t_range = generate_teacher_range_report_html(teacher_summary_list, start_report_date, end_report_date, cal_sys_name)
                teacher_range_excel_buffer = io.BytesIO()
                with pd.ExcelWriter(teacher_range_excel_buffer, engine='openpyxl') as writer:
                    df_t_summary.to_excel(writer, sheet_name='ملخص إحصائيات المعلمين', index=False)
                t_excel_data = teacher_range_excel_buffer.getvalue()
                col_down_t1, col_down_t2, col_down_t3 = st.columns(3)
                col_down_t1.download_button(label="📊 حفظ تقرير الفترة (Excel)", data=t_excel_data, file_name=f"تقرير_المعلمين_{start_report_date}_{end_report_date}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
                col_down_t2.download_button(label="📄 حفظ تقرير الفترة (CSV)", data=df_t_summary.to_csv(index=False).encode('utf-8-sig'), file_name=f"تقرير_المعلمين_{start_report_date}_{end_report_date}.csv", mime="text/csv", use_container_width=True)
                col_down_t3.download_button(label="🖨️ طباعة تقرير المعلمين (PDF)", data=html_t_range.encode('utf-8'), file_name=f"تقرير_المعلمين_{cal_sys_name}_{start_report_date}_{end_report_date}.html", mime="text/html", key="btn_print_t_range", use_container_width=True)
            else:
                st.info("👈 اختر نطاق التاريخ (من / إلى)، ثم انقر على زر **`▶️ بدء عرض التقرير`** للبدء.")

        with tab_manage_students:
            st.markdown("### 🎓 إدارة الطلاب (نقل فصول الطلاب وإضافة طلاب جدد)")
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                st.markdown("#### 🔄 نقل طالب من فصل لآخر")
                st.info("💡 اختر الصف والفصل الحالي، ثم اختر الطالب والمراد النقل إليه.")
                mve_cur_g = st.selectbox("الصف الحالي للطالب:", list(students_db.keys()), key="mve_cur_g")
                mve_cur_s = st.selectbox("الفصل الحالي للطالب:", list(students_db[mve_cur_g].keys()), key="mve_cur_s")
                st_list_curr = students_db[mve_cur_g][mve_cur_s]
                if st_list_curr:
                    st_dict_curr = {f"{s['name']} (رقم الهوية: {s['id']})": s for s in st_list_curr}
                    selected_st_label = st.selectbox("اختر الطالب المراد نقله:", list(st_dict_curr.keys()), key="mve_st_sel")
                    selected_st_obj = st_dict_curr[selected_st_label]
                    mve_tgt_g = st.selectbox("الصف الجديد (الوجهة):", list(students_db.keys()), key="mve_tgt_g")
                    mve_tgt_s = st.selectbox("الفصل الجديد (الوجهة):", list(students_db[mve_tgt_g].keys()), key="mve_tgt_s")
                    if st.button("🔄 تأكيد نقل الطالب للفصل الجديد", type="primary", key="btn_confirm_move_student"):
                        move_student_db(selected_st_obj['id'], selected_st_obj['name'], mve_tgt_g, mve_tgt_s)
                        st.success(f"✨ تم نقل الطالب ({selected_st_obj['name']}) بنجاح إلى ({mve_tgt_g} - {mve_tgt_s})!")
                        st.rerun()
                else:
                    st.warning("لا يوجد طلاب مسجلين في هذا الفصل حالياً.")
            with col_m2:
                st.markdown("#### ➕ إضافة طالب جديد إلى القوائم")
                st.info("💡 أدخل اسم الطالب ورقم الهوية واختر الصف والفصل المطلوب.")
                new_st_name = st.text_input("اسم الطالب الرباعي:", key="add_new_st_name")
                new_st_id = st.text_input("رقم الهوية / الرقم الأكاديمي:", key="add_new_st_id")
                add_g = st.selectbox("الصف الدراسي:", list(students_db.keys()), key="add_st_g")
                add_s = st.selectbox("الفصل:", list(students_db[add_g].keys()), key="add_st_s")
                if st.button("➕ إضافة الطالب للقائمة", type="primary", key="btn_confirm_add_student"):
                    if new_st_name.strip() and new_st_id.strip():
                        add_student_db(new_st_id.strip(), new_st_name.strip(), add_g, add_s)
                        st.success(f"✨ تمت إضافة الطالب ({new_st_name}) بنجاح إلى ({add_g} - {add_s})!")
                        st.rerun()
                    else:
                        st.error("يرجى إدخال اسم الطالب ورقم الهوية بشكل صحيح أولاً!")

        def _render_status_tab(container, status_value, title_txt, empty_msg, key_suffix):
            with container:
                if not df_filtered.empty:
                    dsub = df_filtered[df_filtered['الحالة'] == status_value]
                    st.markdown(f"### {title_txt} (`العدد: {len(dsub)} طالب`)")
                    if not dsub.empty:
                        st.dataframe(dsub[['اسم الطالب', 'رقم الطالب', 'الصف', 'الفصل', 'الحصة', 'اسم المعلم', 'التاريخ']], use_container_width=True)
                        title_suffix = f" - (الصف: {filter_grade} | الفصل: {filter_section} | الحصة: {filter_period} | التاريخ: {filter_date})"
                        html_sub = generate_printable_html(dsub, f"{title_txt}{title_suffix}")
                        st.download_button(label="🖨️ فتح صفحة الطباعة (PDF)", data=html_sub.encode('utf-8'), file_name=f"كشف_{key_suffix}_{date.today()}.html", mime="text/html", key=f"btn_print_{key_suffix}")
                    else:
                        st.success(empty_msg)
                else:
                    st.info("لا توجد بيانات مرصودة تطابق الفلترة المحددة.")

        _render_status_tab(tab_absent, 'غائب', "🔴 قائمة أسماء الطلاب الغائبين", "🎉 لا يوجد طلاب غائبون ضمن التصفية!", "الغائبين")
        _render_status_tab(tab_out, 'خارج الفصل', "🟠 قائمة أسماء الطلاب خارج الفصل", "✅ لا يوجد طلاب خارج الفصل ضمن التصفية!", "خارج_الفصل")
        _render_status_tab(tab_late, 'متأخر', "🟡 قائمة أسماء الطلاب المتأخرين", "✨ لا يوجد طلاب متأخرون ضمن التصفية!", "المتأخرين")

        with tab_all:
            if not df_filtered.empty:
                st.markdown("### 📋 السجل العام الشامل للبيانات المفلترة")
                st.dataframe(df_filtered, use_container_width=True)
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    df_filtered.to_excel(writer, sheet_name='السجل المفلتر', index=False)
                    df_filtered[df_filtered['الحالة'] == 'غائب'].to_excel(writer, sheet_name='كشف الغياب', index=False)
                    df_filtered[df_filtered['الحالة'] == 'خارج الفصل'].to_excel(writer, sheet_name='خارج الفصل', index=False)
                    df_filtered[df_filtered['الحالة'] == 'متأخر'].to_excel(writer, sheet_name='كشف المتأخرين', index=False)
                excel_data = excel_buffer.getvalue()
                col_down1, col_down2 = st.columns(2)
                col_down1.download_button(label="📊 تحميل التقرير المفلتر (Excel)", data=excel_data, file_name=f"تقرير_حضور_مفلتر_{date.today()}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
                col_down2.download_button(label="📄 تحميل التقرير كملف CSV", data=df_filtered.to_csv(index=False).encode('utf-8-sig'), file_name=f"تقرير_حضور_مفلتر_{date.today()}.csv", mime="text/csv", use_container_width=True)
                title_suffix = f" - (الصف: {filter_grade} | الفصل: {filter_section} | الحصة: {filter_period} | التاريخ: {filter_date})"
                html_full = generate_printable_html(df_filtered, f"التقرير الشامل لحضور وغياب الطلاب{title_suffix}")
                st.download_button(label="🖨️ فتح صفحة طباعة السجل العام (PDF)", data=html_full.encode('utf-8'), file_name=f"التقرير_الشامل_{date.today()}.html", mime="text/html", key="btn_print_full")
            else:
                st.info("لا توجد بيانات حضور مرصودة في السجل.")

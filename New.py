"""
Portfolio สหกิจศึกษา (Cooperative Education Portfolio)
เว็บแอป Streamlit สำหรับแสดง/บันทึกประวัตินักศึกษาสหกิจศึกษา, กิจกรรม, และโครงงาน
สามารถอัปโหลด/บันทึกรูปภาพและไฟล์ PDF ได้ ข้อมูลจะถูกเก็บไว้ในโฟลเดอร์ data/ และ uploads/
รันด้วยคำสั่ง:  streamlit run app.py
"""

import streamlit as st
import streamlit.components.v1 as components
from sqlalchemy import text
import uuid
import base64
import json
from datetime import datetime, date
from pathlib import Path

# ----------------------------------------------------------------------------
# CONFIG & PATHS
# ----------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ----------------------------------------------------------------------------
# ฐานข้อมูล — เก็บ "ทุกอย่าง" ไว้ในฐานข้อมูลจริง (รวมถึงรูปภาพ/ไฟล์ PDF ที่แปลง
# เป็น base64 เก็บลงตาราง) ไม่มีการเขียนไฟล์ผู้ใช้ลงดิสก์ของเซิร์ฟเวอร์เลย
# เพื่อให้ข้อมูลไม่หายแม้ตัวเครื่อง/คอนเทนเนอร์ที่รันแอปจะถูกรีสตาร์ทหรือ
# สร้างใหม่ (เช่นตอน deploy ใหม่บน Streamlit Community Cloud ซึ่งดิสก์ในเครื่อง
# จะถูกล้างทุกครั้งที่แอป restart/redeploy)
#
# ค่าเริ่มต้น (ไม่ตั้งค่าอะไรเพิ่ม) จะใช้ไฟล์ SQLite ในเครื่อง data/portfolio.db
# ซึ่งสะดวกสำหรับพัฒนา/ทดสอบในเครื่องตัวเอง แต่ "จะไม่รอด" การ redeploy บน
# Streamlit Community Cloud เพราะดิสก์เป็นแบบชั่วคราว (ephemeral)
#
# วิธีทำให้ข้อมูลอยู่ถาวรจริง ๆ บน Streamlit Community Cloud:
#   1) สมัครฐานข้อมูลฟรีบนคลาวด์ เช่น Supabase / Neon (Postgres ฟรี) หรือ Turso
#      (SQLite แบบ hosted ฟรี)
#   2) เพิ่ม secret ชื่อ DATABASE_URL ใน Streamlit Cloud → Settings → Secrets
#      เช่น: DATABASE_URL = "postgresql://user:pass@host:5432/dbname"
#   3) แค่นี้แอปจะเปลี่ยนไปอ่าน-เขียนฐานข้อมูลคลาวด์นั้นแทนโดยอัตโนมัติ และ
#      ข้อมูลจะอยู่ถาวรไม่ว่าจะรีสตาร์ทเครื่อง/redeploy กี่ครั้งก็ตาม
# ----------------------------------------------------------------------------
try:
    DATABASE_URL = st.secrets["DATABASE_URL"]
except Exception:
    DATABASE_URL = f"sqlite:///{DATA_DIR / 'portfolio.db'}"

USING_LOCAL_SQLITE = DATABASE_URL.startswith("sqlite")


@st.cache_resource
def get_connection():
    return st.connection("portfolio_db", type="sql", url=DATABASE_URL)


conn = get_connection()

DEFAULT_PROFILE = {
    "name_th": "ชื่อ-นามสกุล (ภาษาไทย)",
    "name_en": "Name Surname",
    "role": "นักศึกษาสหกิจศึกษา",
    "department": "ภาควิชา / สาขาวิชา",
    "university": "มหาวิทยาลัย",
    "company": "บริษัทที่ฝึกงาน",
    "company_unit": "ฝ่าย / แผนก",
    "photo": None,
}

# หมวดหมู่เดือนของการฝึกสหกิจศึกษา: มิถุนายน 2569 - กุมภาพันธ์ 2570
# key = ใช้สำหรับเรียงลำดับ (YYYY-MM แบบสากล), label = ข้อความที่แสดงผล (พ.ศ.)
MONTH_CATEGORIES = [
    {"key": "2026-06", "label": "มิถุนายน 2569"},
    {"key": "2026-07", "label": "กรกฎาคม 2569"},
    {"key": "2026-08", "label": "สิงหาคม 2569"},
    {"key": "2026-09", "label": "กันยายน 2569"},
    {"key": "2026-10", "label": "ตุลาคม 2569"},
    {"key": "2026-11", "label": "พฤศจิกายน 2569"},
    {"key": "2026-12", "label": "ธันวาคม 2569"},
    {"key": "2027-01", "label": "มกราคม 2570"},
    {"key": "2027-02", "label": "กุมภาพันธ์ 2570"},
]
MONTH_KEY_TO_LABEL = {m["key"]: m["label"] for m in MONTH_CATEGORIES}
MONTH_LABEL_TO_KEY = {m["label"]: m["key"] for m in MONTH_CATEGORIES}


def format_thai_date(date_str):
    """แปลงวันที่รูปแบบ YYYY-MM-DD เป็น dd/mm/ปี พ.ศ. เช่น 15/06/2569"""
    if not date_str:
        return ""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        return f"{d.day:02d}/{d.month:02d}/{d.year + 543}"
    except Exception:
        return date_str

st.set_page_config(
    page_title="Portfolio สหกิจศึกษา",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ----------------------------------------------------------------------------
# STORAGE HELPERS (อ่าน/เขียนฐานข้อมูลผ่าน SQLAlchemy — ใช้ได้ทั้ง SQLite ในเครื่อง
# และฐานข้อมูลคลาวด์ เช่น Postgres โดยไม่ต้องแก้โค้ดส่วนนี้เลย)
# ----------------------------------------------------------------------------
def _column_exists(s, table: str, column: str) -> bool:
    """เช็คว่าคอลัมน์นี้มีอยู่ในตารางแล้วหรือยัง (รองรับทั้ง SQLite และ Postgres)
    ใช้ก่อนรัน ALTER TABLE เพื่อไม่ให้เกิด error ซ้ำ ๆ ทุกครั้งที่แอป rerun"""
    if USING_LOCAL_SQLITE:
        rows = s.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return any(r[1] == column for r in rows)
    row = s.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).fetchone()
    return row is not None


def init_db():
    with conn.session as s:
        s.execute(text(
            """CREATE TABLE IF NOT EXISTS profile (
                id INTEGER PRIMARY KEY,
                name_th TEXT, name_en TEXT, role TEXT,
                department TEXT, university TEXT,
                company TEXT, company_unit TEXT,
                photo_data TEXT
            )"""
        ))
        s.execute(text(
            """CREATE TABLE IF NOT EXISTS works (
                id TEXT PRIMARY KEY,
                title TEXT, type TEXT,
                month_key TEXT, month_label TEXT,
                date TEXT, description TEXT, created_at TEXT
            )"""
        ))
        s.execute(text(
            """CREATE TABLE IF NOT EXISTS work_files (
                id TEXT PRIMARY KEY,
                work_id TEXT, data_uri TEXT, position INTEGER DEFAULT 0
            )"""
        ))
        s.execute(text(
            """CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                title TEXT, summary TEXT, date TEXT,
                file_name TEXT, file_data TEXT, created_at TEXT
            )"""
        ))
        s.commit()

        # migration: ฐานข้อมูลที่ deploy ไว้ก่อนหน้านี้อาจยังไม่มีคอลัมน์ position
        # (เพิ่มเข้ามาทีหลังเพื่อรักษาลำดับรูปภาพให้ถูกต้อง) เช็คก่อนว่ามีคอลัมน์
        # อยู่แล้วหรือยัง ค่อยเพิ่ม — ไม่ใช้วิธีลองแล้วปล่อยให้ error+rollback ทุกครั้ง
        # เพราะทำให้เกิด query ที่ล้มเหลวซ้ำ ๆ ทุกการโต้ตอบ ส่งผลให้แอปช้าลงจริง
        if not _column_exists(s, "work_files", "position"):
            s.execute(text("ALTER TABLE work_files ADD COLUMN position INTEGER DEFAULT 0"))
            s.commit()

        exists = s.execute(text("SELECT COUNT(*) FROM profile WHERE id = 1")).scalar()
        if not exists:
            s.execute(
                text(
                    """INSERT INTO profile
                       (id, name_th, name_en, role, department, university, company, company_unit, photo_data)
                       VALUES (1, :name_th, :name_en, :role, :department, :university, :company, :company_unit, :photo_data)"""
                ),
                {
                    "name_th": DEFAULT_PROFILE["name_th"],
                    "name_en": DEFAULT_PROFILE["name_en"],
                    "role": DEFAULT_PROFILE["role"],
                    "department": DEFAULT_PROFILE["department"],
                    "university": DEFAULT_PROFILE["university"],
                    "company": DEFAULT_PROFILE["company"],
                    "company_unit": DEFAULT_PROFILE["company_unit"],
                    "photo_data": None,
                },
            )
            s.commit()


@st.cache_data(ttl=60, show_spinner=False)
def get_profile():
    with conn.session as s:
        row = s.execute(text("SELECT * FROM profile WHERE id = 1")).mappings().fetchone()
    if not row:
        p = DEFAULT_PROFILE.copy()
        return p
    p = dict(row)
    p["photo"] = p.pop("photo_data", None)
    return p


def save_profile(p):
    with conn.session as s:
        s.execute(
            text(
                """UPDATE profile SET name_th=:name_th, name_en=:name_en, role=:role,
                   department=:department, university=:university, company=:company,
                   company_unit=:company_unit, photo_data=:photo_data WHERE id = 1"""
            ),
            {
                "name_th": p["name_th"], "name_en": p["name_en"], "role": p["role"],
                "department": p["department"], "university": p["university"],
                "company": p["company"], "company_unit": p["company_unit"],
                "photo_data": p.get("photo"),
            },
        )
        s.commit()
    get_profile.clear()


@st.cache_data(ttl=60, show_spinner=False)
def get_works():
    # ใช้ LEFT JOIN คิวรีเดียวแทนการวน query แยกทีละผลงาน (เดิมเป็น N+1 queries)
    # ลดจำนวนรอบไป-กลับกับฐานข้อมูลบนคลาวด์ ซึ่งเป็นสาเหตุหลักที่ทำให้เว็บช้า
    with conn.session as s:
        rows = s.execute(text(
            """SELECT w.id, w.title, w.type, w.month_key, w.month_label, w.date,
                      w.description, w.created_at, wf.data_uri
               FROM works w
               LEFT JOIN work_files wf ON wf.work_id = w.id
               ORDER BY w.created_at DESC, wf.position"""
        )).mappings().fetchall()

    works_by_id = {}
    order = []
    for row in rows:
        wid = row["id"]
        if wid not in works_by_id:
            w = dict(row)
            w.pop("data_uri", None)
            w["files"] = []
            works_by_id[wid] = w
            order.append(wid)
        if row["data_uri"]:
            works_by_id[wid]["files"].append(row["data_uri"])
    return [works_by_id[wid] for wid in order]


def add_work(item):
    with conn.session as s:
        s.execute(
            text(
                """INSERT INTO works (id, title, type, month_key, month_label, date, description, created_at)
                   VALUES (:id, :title, :type, :month_key, :month_label, :date, :description, :created_at)"""
            ),
            {
                "id": item["id"], "title": item["title"], "type": item["type"],
                "month_key": item["month_key"], "month_label": item["month_label"],
                "date": item["date"], "description": item["description"],
                "created_at": item["created_at"],
            },
        )
        for position, data_uri in enumerate(item.get("files", [])):
            s.execute(
                text("INSERT INTO work_files (id, work_id, data_uri, position) VALUES (:id, :work_id, :data_uri, :position)"),
                {"id": uuid.uuid4().hex, "work_id": item["id"], "data_uri": data_uri, "position": position},
            )
        s.commit()
    get_works.clear()


def delete_work(work_id):
    with conn.session as s:
        s.execute(text("DELETE FROM works WHERE id = :id"), {"id": work_id})
        s.execute(text("DELETE FROM work_files WHERE work_id = :id"), {"id": work_id})
        s.commit()
    get_works.clear()


@st.cache_data(ttl=60, show_spinner=False)
def get_projects():
    with conn.session as s:
        rows = s.execute(text("SELECT * FROM projects ORDER BY created_at DESC")).mappings().fetchall()
    return [dict(r) for r in rows]


def add_project(item):
    with conn.session as s:
        s.execute(
            text(
                """INSERT INTO projects (id, title, summary, date, file_name, file_data, created_at)
                   VALUES (:id, :title, :summary, :date, :file_name, :file_data, :created_at)"""
            ),
            {
                "id": item["id"], "title": item["title"], "summary": item["summary"],
                "date": item["date"], "file_name": item.get("file_name"),
                "file_data": item.get("file_data"), "created_at": item["created_at"],
            },
        )
        s.commit()
    get_projects.clear()


def delete_project(project_id):
    with conn.session as s:
        s.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
        s.commit()
    get_projects.clear()


@st.cache_resource
def _run_init_db_once():
    # ห่อด้วย st.cache_resource เพื่อให้ init_db() รันแค่ครั้งเดียวตอนแอปเริ่มทำงาน
    # (ใช้ร่วมกันทุก session/ทุกคนที่เข้าเว็บ) ไม่ใช่รันซ้ำทุกครั้งที่มีคนคลิก/พิมพ์
    # อะไรก็ตาม (ปกติ Streamlit จะรันทั้งไฟล์ใหม่ทุกครั้งที่มีการโต้ตอบ) การรันซ้ำ
    # ทุกครั้งทำให้เกิด query ตรวจ/สร้างตารางเพิ่มโดยไม่จำเป็นหลายรอบ ส่งผลให้ช้าลง
    init_db()
    return True


_run_init_db_once()


# ----------------------------------------------------------------------------
# ย่อขนาด + บีบอัดรูปภาพก่อนเก็บลงฐานข้อมูล — ตัวการหลักที่ทำให้เว็บช้าคือรูปภาพ
# ต้นฉบับ (หลาย MB ต่อรูป) ถูกแปลงเป็น base64 แล้วโอนไป-กลับกับฐานข้อมูลคลาวด์
# ทุกครั้งที่โหลดหน้า Portfolio ยิ่งมีผลงาน/รูปเยอะยิ่งช้ามาก การย่อขนาดรูปก่อน
# บันทึกช่วยลดปริมาณข้อมูลลงได้หลายสิบเท่า ทำให้หน้าเว็บโหลดเร็วขึ้นอย่างเห็นได้ชัด
# ----------------------------------------------------------------------------
MAX_IMAGE_DIM = 1280       # ความกว้าง/สูงสูงสุดของรูปผลงาน (พิกเซล)
PROFILE_IMAGE_DIM = 600    # รูปโปรไฟล์เล็กกว่า ไม่ต้องเก็บความละเอียดสูง
IMAGE_QUALITY = 72         # คุณภาพ JPEG (0-100) — 70-75 คือจุดสมดุลระหว่างขนาดไฟล์กับความคมชัด


def _compress_image_bytes(raw_bytes: bytes, max_dim: int = MAX_IMAGE_DIM, quality: int = IMAGE_QUALITY) -> bytes:
    try:
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(raw_bytes))
        img = img.convert("RGB")  # ตัด alpha channel เพื่อบันทึกเป็น JPEG ได้
        w, h = img.size
        if max(w, h) > max_dim:
            ratio = max_dim / max(w, h)
            img = img.resize((max(1, int(w * ratio)), max(1, int(h * ratio))), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        return buf.getvalue()
    except Exception:
        # ถ้าแปลง/ย่อไม่ได้ (ไฟล์เสียหรือไม่รองรับ) ใช้ไฟล์ต้นฉบับไปก่อนดีกว่าทำให้แอปพัง
        return raw_bytes


def uploaded_image_to_data_uri(uploaded_file, max_dim: int = MAX_IMAGE_DIM) -> str:
    """แปลงไฟล์รูปภาพที่อัปโหลดเป็น data URI (base64) เก็บลงฐานข้อมูลโดยตรง
    (ไม่เขียนลงดิสก์ของเซิร์ฟเวอร์เลย จึงไม่หายแม้เครื่อง/คอนเทนเนอร์รีสตาร์ท)
    ก่อนเก็บจะย่อขนาด + บีบอัดเป็น JPEG คุณภาพพอเหมาะ เพื่อให้เว็บโหลดเร็วขึ้น"""
    compressed = _compress_image_bytes(uploaded_file.getvalue(), max_dim=max_dim)
    b64 = base64.b64encode(compressed).decode()
    return f"data:image/jpeg;base64,{b64}"


def uploaded_file_to_b64(uploaded_file) -> str:
    """แปลงไฟล์ (เช่น PDF) ที่อัปโหลดเป็น base64 ล้วน ๆ (ไม่มี prefix data:...)
    สำหรับเก็บลงฐานข้อมูลแล้วดึงกลับมาทำเป็นไฟล์ดาวน์โหลดภายหลัง"""
    return base64.b64encode(uploaded_file.getvalue()).decode()


def b64_to_bytes(b64_str) -> bytes:
    if not b64_str:
        return b""
    return base64.b64decode(b64_str)


def init_state():
    # หมายเหตุ: profile / works / projects "ไม่" ถูก cache ไว้ใน session_state
    # อีกต่อไป แต่จะถูกดึงสดจากฐานข้อมูลทุกครั้งที่แสดงผล (get_profile / get_works /
    # get_projects) เพื่อให้ทุกคนที่เข้าเว็บเห็นข้อมูลชุดล่าสุดที่แชร์ร่วมกันเสมอ
    if "page" not in st.session_state:
        st.session_state.page = "Home"
    if "edit_profile" not in st.session_state:
        st.session_state.edit_profile = False
    if "show_add_work" not in st.session_state:
        st.session_state.show_add_work = False
    if "show_add_project" not in st.session_state:
        st.session_state.show_add_project = False
    if "work_filter" not in st.session_state:
        st.session_state.work_filter = "ทั้งหมด"
    if "work_month_filter" not in st.session_state:
        st.session_state.work_month_filter = "ทั้งหมด"
    if "work_search" not in st.session_state:
        st.session_state.work_search = ""


init_state()

# ----------------------------------------------------------------------------
# STYLE  (full-bleed, edge-to-edge layout to match the reference UI)
# ----------------------------------------------------------------------------
st.markdown(
    """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header[data-testid="stHeader"] {background: transparent; height: 0; min-height: 0;}
    div[data-testid="stToolbar"] {display: none;}

    html, body, .stApp, [data-testid="stAppViewContainer"] {
        background: #eef2ef;
        margin: 0;
    }

    /* remove Streamlit's default centered/padded container so content goes edge-to-edge */
    section[data-testid="stMain"] > div.block-container,
    .main .block-container {
        padding: 0 !important;
        margin: 0 !important;
        max-width: 100% !important;
    }
    div[data-testid="stAppViewBlockContainer"] { padding: 0 !important; max-width: 100% !important; }
    div[data-testid="stVerticalBlockBorderWrapper"] { width: 100%; }

    /* ---------- Top navigation bar (full width) ---------- */
    .st-key-topnav {
        background: linear-gradient(90deg, #0e4a30 0%, #157a4b 55%, #0b3a4d 100%);
        padding: 16px 40px;
        color: white;
    }
    .st-key-topnav .stButton > button {
        background: transparent;
        color: #eafff2;
        border: none;
        font-weight: 600;
        font-size: 14.5px;
        border-radius: 20px;
        padding: 8px 18px;
        box-shadow: none;
        transition: background 0.15s ease;
    }
    .st-key-topnav .stButton > button:hover {
        background: rgba(255,255,255,0.14);
        color: white;
        border: none;
    }
    .st-key-topnav .stButton > button:focus:not(:active) {
        background: rgba(255,255,255,0.14);
        color: white;
    }
    .st-key-edit_profile_btn .stButton > button {
        background: rgba(255,255,255,0.14) !important;
        border: 1px solid rgba(255,255,255,0.35) !important;
        color: white !important;
    }
    .st-key-edit_profile_btn .stButton > button:hover {
        background: rgba(255,255,255,0.24) !important;
    }
    .topbar-title { font-size: 19px; font-weight: 800; line-height: 1.2; }
    .topbar-sub { font-size: 12px; opacity: 0.85; margin-top: -2px;}

    /* ---------- Home hero (full-bleed page background) ---------- */
    .st-key-home_hero {
        background: linear-gradient(150deg, #0b4a34 0%, #146c4a 40%, #0a2e42 100%);
        padding: 70px 60px;
        min-height: calc(100vh - 78px);
        color: white;
    }
    .badge-role {
        display:inline-block;
        background: rgba(255,255,255,0.12);
        padding: 6px 16px;
        border-radius: 20px;
        font-size: 13px;
        margin-bottom: 22px;
    }
    .hero-name-th { font-size: 38px; font-weight: 800; margin-bottom: 4px;}
    .hero-name-en { font-size: 19px; color: #8fe3c0; margin-bottom: 26px;}
    .info-row { font-size: 16px; font-weight: 700; margin-top: 18px;}
    .info-sub { font-size: 13px; color: #cfe9de; font-weight: 400;}

    .st-key-home_hero .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        height: 46px;
    }
    .st-key-hero_btn_primary .stButton > button {
        background: white; color: #0b4a34; border: none;
    }
    .st-key-hero_btn_secondary .stButton > button {
        background: transparent; color: white; border: 1px solid rgba(255,255,255,0.5);
    }

    .profile-photo-frame {
        background: white;
        border-radius: 14px;
        padding: 8px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.25);
    }
    .profile-photo-frame img { border-radius: 8px; display: block; width: 100%; }
    .photo-caption { text-align: center; font-size: 12.5px; color: #cfe9de; margin-top: 10px; }
    .photo-placeholder {
        background: rgba(255,255,255,0.08);
        border: 1px dashed rgba(255,255,255,0.4);
        border-radius: 14px;
        padding: 90px 10px;
        text-align: center;
        color: #dfeee6;
    }

    /* ---------- Page content wrapper for Portfolio / Project ---------- */
    .st-key-page_content {
        padding: 34px 44px 60px 44px;
    }

    .stat-card {
        background: white;
        border-radius: 14px;
        padding: 18px 20px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
        text-align: left;
    }
    .stat-num { font-size: 26px; font-weight: 800; color: #111; }
    .stat-label { font-size: 13px; color: #666; }

    .work-card, .project-card {
        background: white;
        border-radius: 14px;
        padding: 12px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
        margin-bottom: 14px;
    }
    .work-title { font-weight: 700; font-size: 14px; margin-bottom: 2px; line-height:1.3;}
    .work-meta { font-size: 11px; color: #888; margin-bottom: 6px; line-height:1.5;}

    /* กล่องที่ครอบ iframe ของแกลเลอรีรูปภาพ (render_work_gallery) ให้ชิดขอบการ์ด */
    div[data-testid="stIFrame"] { margin-bottom: 6px; }

    .empty-box {
        text-align: center;
        padding: 70px 0;
        color: #999;
    }

    /* ---------- Form input fields: clear white background, dark text ---------- */
    div[data-testid="stTextInput"] input,
    div[data-testid="stTextArea"] textarea,
    div[data-testid="stDateInput"] input,
    div[data-testid="stNumberInput"] input {
        background-color: #ffffff !important;
        color: #111111 !important;
        border: 1px solid #cfd8d4 !important;
        border-radius: 8px !important;
        caret-color: #111111 !important;
    }
    div[data-testid="stTextInput"] input::placeholder,
    div[data-testid="stTextArea"] textarea::placeholder {
        color: #8a938e !important;
    }
    div[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
    div[data-testid="stMultiSelect"] div[data-baseweb="select"] > div {
        background-color: #ffffff !important;
        color: #111111 !important;
        border: 1px solid #cfd8d4 !important;
        border-radius: 8px !important;
    }
    div[data-testid="stSelectbox"] ul,
    div[data-testid="stMultiSelect"] ul {
        background-color: #ffffff !important;
        color: #111111 !important;
    }
    div[data-testid="stFileUploaderDropzone"] {
        background-color: #ffffff !important;
        border: 1px dashed #b9c4be !important;
        border-radius: 10px !important;
    }
    div[data-testid="stFileUploaderDropzone"] * {
        color: #333333 !important;
    }
    div[data-testid="stDateInput"] svg { fill: #333333 !important; }

    /* labels above the fields, kept readable on both light & dark page sections */
    .st-key-page_content label,
    .stForm label {
        color: #1c231f !important;
        font-weight: 600 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------------
# TOP NAVIGATION BAR
# ----------------------------------------------------------------------------
NAV_ITEMS = [
    ("Home", "🏠 Home", "หน้าแรก", "nav_home"),
    ("Portfolio", "🗂️ Portfolio", "พอร์ตโฟลิโอ", "nav_portfolio"),
    ("Project", "📋 Project", "โครงงาน", "nav_project"),
]


def top_nav():
    # highlight the active tab as a white pill, like the reference design
    active_key = next(k for name, _, _, k in NAV_ITEMS if name == st.session_state.page)
    st.markdown(
        f"""
        <style>
        .st-key-{active_key} .stButton > button {{
            background: white !important;
            color: #0e4a30 !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container(key="topnav"):
        c_brand, c1, c2, c3, c_spacer, c_edit = st.columns(
            [2.4, 0.9, 1.1, 0.9, 1.6, 1.3]
        )
        with c_brand:
            st.markdown(
                """
                <div class="topbar-title">🎓 Portfolio สหกิจศึกษา</div>
                <div class="topbar-sub">Cooperative Education Portfolio</div>
                """,
                unsafe_allow_html=True,
            )
        for col, (name, label, sub, key) in zip([c1, c2, c3], NAV_ITEMS):
            with col:
                with st.container(key=key):
                    if st.button(f"{label}\n{sub}", use_container_width=True):
                        st.session_state.page = name
                        st.rerun()
        with c_spacer:
            st.write("")
        with c_edit:
            with st.container(key="edit_profile_btn"):
                if st.button("✏️ แก้ไขโปรไฟล์", use_container_width=True):
                    st.session_state.edit_profile = True
                    st.session_state.page = "Home"
                    st.rerun()


# ----------------------------------------------------------------------------
# HOME PAGE
# ----------------------------------------------------------------------------
def profile_edit_form():
    p = get_profile()
    st.subheader("✏️ แก้ไขโปรไฟล์")
    with st.form("profile_form"):
        col1, col2 = st.columns(2)
        with col1:
            name_th = st.text_input("ชื่อ-นามสกุล (ภาษาไทย)", value=p.get("name_th", ""))
            department = st.text_input("ภาควิชา / สาขาวิชา", value=p.get("department", ""))
            company = st.text_input("บริษัทที่ฝึกงาน", value=p.get("company", ""))
        with col2:
            name_en = st.text_input("Name Surname (English)", value=p.get("name_en", ""))
            university = st.text_input("มหาวิทยาลัย", value=p.get("university", ""))
            company_unit = st.text_input("ฝ่าย / แผนก", value=p.get("company_unit", ""))

        role = st.text_input("สถานะ (บทบาท)", value=p.get("role", "นักศึกษาสหกิจศึกษา"))
        photo_file = st.file_uploader("รูปโปรไฟล์ (คลิกเพื่อเปลี่ยน)", type=["png", "jpg", "jpeg"])

        submitted = st.form_submit_button("💾 บันทึกโปรไฟล์", use_container_width=True)
        cancel = st.form_submit_button("ยกเลิก", use_container_width=True)

        if submitted:
            p["name_th"] = name_th
            p["name_en"] = name_en
            p["role"] = role
            p["department"] = department
            p["university"] = university
            p["company"] = company
            p["company_unit"] = company_unit
            if photo_file is not None:
                p["photo"] = uploaded_image_to_data_uri(photo_file, max_dim=PROFILE_IMAGE_DIM)
            save_profile(p)
            st.session_state.edit_profile = False
            st.success("บันทึกโปรไฟล์เรียบร้อยแล้ว")
            st.rerun()

        if cancel:
            st.session_state.edit_profile = False
            st.rerun()


def home_page():
    p = get_profile()

    if st.session_state.edit_profile:
        with st.container(key="page_content"):
            profile_edit_form()
        return

    with st.container(key="home_hero"):
        left, right = st.columns([2.1, 1])
        with left:
            st.markdown(
                f"""
                <div class="badge-role">🎓 {p.get('role','')}</div>
                <div class="hero-name-th">{p.get('name_th','')}</div>
                <div class="hero-name-en">{p.get('name_en','')}</div>
                <div class="info-row">🏛️ {p.get('department','')}
                    <div class="info-sub">Department</div>
                </div>
                <div class="info-row">🎓 {p.get('university','')}
                    <div class="info-sub">University</div>
                </div>
                <div class="info-row">🏢 {p.get('company','')}
                    <div class="info-sub">{p.get('company_unit','')}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.write("")
            st.write("")
            b1, b2 = st.columns(2)
            with b1:
                with st.container(key="hero_btn_primary"):
                    if st.button("ดูพอร์ตโฟลิโอ →", use_container_width=True):
                        st.session_state.page = "Portfolio"
                        st.rerun()
            with b2:
                with st.container(key="hero_btn_secondary"):
                    if st.button("✏️ แก้ไขโปรไฟล์ ", use_container_width=True):
                        st.session_state.edit_profile = True
                        st.rerun()

        with right:
            if p.get("photo"):
                st.markdown(
                    f"""
                    <div class="profile-photo-frame">
                        <img src="{p['photo']}" />
                    </div>
                    <div class="photo-caption">คลิกที่รูปเพื่อเปลี่ยน</div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    """
                    <div class="photo-placeholder">
                        📷<br>ยังไม่มีรูปโปรไฟล์
                    </div>
                    <div class="photo-caption">คลิก 'แก้ไขโปรไฟล์' เพื่อเพิ่มรูป</div>
                    """,
                    unsafe_allow_html=True,
                )


# ----------------------------------------------------------------------------
# PORTFOLIO (WORKS / ACTIVITIES) PAGE
# ----------------------------------------------------------------------------
def add_work_form():
    st.subheader("➕ เพิ่มผลงาน / กิจกรรม")
    with st.form("add_work_form", clear_on_submit=True):
        title = st.text_input("ชื่อผลงาน / กิจกรรม *")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            work_type = st.selectbox("ประเภท", ["รูปภาพ", "PDF", "บทความ"])
        with col_b:
            month_label = st.selectbox(
                "หมวดหมู่เดือน (สหกิจศึกษา)",
                [m["label"] for m in MONTH_CATEGORIES],
            )
        with col_c:
            work_date = st.date_input("วันที่ทำกิจกรรม *", value=date.today())
        description = st.text_area("รายละเอียด")

        uploaded_images = []
        uploaded_pdf = None
        if work_type == "รูปภาพ":
            uploaded_images = st.file_uploader(
                "แนบรูปภาพ (เลือกได้หลายรูปพร้อมกัน)",
                type=["png", "jpg", "jpeg"],
                accept_multiple_files=True,
            )
        elif work_type == "PDF":
            uploaded_pdf = st.file_uploader("แนบไฟล์ PDF", type=["pdf"])

        c1, c2 = st.columns(2)
        with c1:
            submitted = st.form_submit_button("💾 บันทึก", use_container_width=True)
        with c2:
            cancel = st.form_submit_button("ยกเลิก", use_container_width=True)

        if submitted:
            if not title:
                st.error("กรุณากรอกชื่อผลงาน")
            else:
                file_paths = []
                if work_type == "รูปภาพ" and uploaded_images:
                    for img in uploaded_images:
                        file_paths.append(uploaded_image_to_data_uri(img))
                elif work_type == "PDF" and uploaded_pdf is not None:
                    pdf_b64 = uploaded_file_to_b64(uploaded_pdf)
                    file_paths.append(f"data:application/pdf;base64,{pdf_b64}")

                item = {
                    "id": uuid.uuid4().hex,
                    "title": title,
                    "type": work_type,
                    "date": str(work_date),
                    "month_key": MONTH_LABEL_TO_KEY.get(month_label, ""),
                    "month_label": month_label,
                    "description": description,
                    "files": file_paths,
                    "created_at": datetime.now().isoformat(),
                }
                st.session_state.show_add_work = False
                add_work(item)
                n = len(file_paths)
                st.success(f"เพิ่มผลงานเรียบร้อยแล้ว (แนบไฟล์ {n} ไฟล์)" if n else "เพิ่มผลงานเรียบร้อยแล้ว")
                st.rerun()

        if cancel:
            st.session_state.show_add_work = False
            st.rerun()


def render_work_gallery(files, work_id):
    """แสดงรูปเด่น (รูปแรก) สูง 180px พร้อมป้าย '+N รูป' ทับมุม
    กดแล้วเปิด Lightbox เต็มจอ เลื่อนดูรูปทั้งหมดได้ด้วยปุ่ม ‹ › (หรือปุ่มลูกศร
    บนคีย์บอร์ด) มีแถบรูปย่อด้านล่างและตัวนับ 'x / N'
    หมายเหตุ: files เป็น data URI (base64) ที่ดึงมาจากฐานข้อมูลโดยตรงอยู่แล้ว
    ไม่ต้องอ่านจากไฟล์บนดิสก์อีกต่อไป
    """
    if not files:
        return
    data_uris = files
    total = len(data_uris)
    images_json = json.dumps(data_uris)

    badge_html = f'<div class="badge">+{total - 1} รูป</div>' if total > 1 else ""
    strip_html = "".join(
        f'<img src="{uri}" class="strip-thumb" onclick="showIdx({i})" />'
        for i, uri in enumerate(data_uris)
    )
    prev_btn = '<button class="arrow" onclick="nav(-1)">‹</button>' if total > 1 else ""
    next_btn = '<button class="arrow" onclick="nav(1)">›</button>' if total > 1 else ""
    strip_block = f'<div class="strip" onclick="event.stopPropagation()">{strip_html}</div>' if total > 1 else ""
    counter_block = '<div class="counter" id="counter"></div>' if total > 1 else ""

    html = f"""
    <html><head><style>
      * {{ box-sizing: border-box; }}
      body {{ margin:0; font-family:'Sarabun','Noto Sans Thai',sans-serif; background:transparent; }}
      .featured-wrap {{ position:relative; cursor:pointer; border-radius:12px; overflow:hidden; }}
      .featured-img {{ width:100%; height:130px; object-fit:cover; display:block; transition:filter .15s; }}
      .featured-wrap:hover .featured-img {{ filter:brightness(0.85); }}
      .badge {{ position:absolute; bottom:6px; right:6px; background:rgba(0,0,0,0.6); color:#fff;
                 border-radius:6px; font-size:11px; font-weight:600; padding:2px 7px; }}
      .hint {{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
                opacity:0; transition:opacity .15s; }}
      .featured-wrap:hover .hint {{ opacity:1; }}
      .hint span {{ color:#fff; font-size:12px; font-weight:600; background:rgba(0,0,0,0.45);
                     border-radius:6px; padding:3px 8px; }}

      .overlay {{ display:none; position:fixed; inset:0; background:rgba(0,0,0,0.88); z-index:999999;
                   align-items:center; justify-content:center; flex-direction:column; gap:16px; }}
      .overlay.open {{ display:flex; }}
      .close-btn {{ position:absolute; top:16px; right:20px; background:none; border:none; color:#fff;
                     font-size:28px; cursor:pointer; line-height:1; }}
      .stage {{ display:flex; align-items:center; gap:12px; max-width:90vw; }}
      .arrow {{ background:rgba(255,255,255,0.15); border:none; color:#fff; font-size:22px; width:44px;
                 height:44px; border-radius:50%; cursor:pointer; flex-shrink:0; }}
      .main-img {{ max-width:80vw; max-height:78vh; border-radius:10px; object-fit:contain;
                    box-shadow:0 8px 40px rgba(0,0,0,0.5); }}
      .strip {{ display:flex; gap:8px; flex-wrap:wrap; justify-content:center; max-width:80vw; }}
      .strip-thumb {{ width:56px; height:56px; object-fit:cover; border-radius:6px; cursor:pointer;
                       opacity:0.5; border:2px solid transparent; transition:all .15s; }}
      .strip-thumb.active {{ opacity:1; border-color:#1D9E75; }}
      .counter {{ color:rgba(255,255,255,0.6); font-size:13px; }}
    </style></head>
    <body>
      <div class="featured-wrap" onclick="openLB()">
        <img class="featured-img" src="{data_uris[0]}" />
        {badge_html}
        <div class="hint"><span>🔍 ดูรูป</span></div>
      </div>

      <div class="overlay" id="overlay" onclick="if(event.target===this) closeLB()">
        <button class="close-btn" onclick="closeLB()">×</button>
        <div class="stage" onclick="event.stopPropagation()">
          {prev_btn}
          <img class="main-img" id="mainImg" src="" />
          {next_btn}
        </div>
        {strip_block}
        {counter_block}
      </div>

      <script>
        const IMAGES_{work_id} = {images_json};
        let idx_{work_id} = 0;
        const overlay = document.getElementById('overlay');
        const mainImg = document.getElementById('mainImg');
        const counterEl = document.getElementById('counter');

        function update() {{
          mainImg.src = IMAGES_{work_id}[idx_{work_id}];
          if (counterEl) counterEl.innerText = (idx_{work_id} + 1) + ' / ' + IMAGES_{work_id}.length;
          document.querySelectorAll('.strip-thumb').forEach((t, i) => {{
            t.classList.toggle('active', i === idx_{work_id});
          }});
        }}
        function resizeFrame(full) {{
          try {{
            const fe = window.frameElement;
            if (!fe) return;
            if (full) {{
              fe.dataset.prevStyle = fe.getAttribute('style') || '';
              fe.style.position = 'fixed';
              fe.style.top = '0';
              fe.style.left = '0';
              fe.style.width = '100vw';
              fe.style.height = '100vh';
              fe.style.zIndex = '999999';
            }} else {{
              fe.setAttribute('style', fe.dataset.prevStyle || '');
            }}
          }} catch (e) {{}}
        }}
        function openLB() {{
          idx_{work_id} = 0;
          update();
          overlay.classList.add('open');
          resizeFrame(true);
        }}
        function closeLB() {{
          overlay.classList.remove('open');
          resizeFrame(false);
        }}
        function nav(delta) {{
          idx_{work_id} = (idx_{work_id} + delta + IMAGES_{work_id}.length) % IMAGES_{work_id}.length;
          update();
        }}
        function showIdx(i) {{
          idx_{work_id} = i;
          update();
        }}
        document.addEventListener('keydown', function(e) {{
          if (!overlay.classList.contains('open')) return;
          if (e.key === 'ArrowLeft') nav(-1);
          if (e.key === 'ArrowRight') nav(1);
          if (e.key === 'Escape') closeLB();
        }});
      </script>
    </body></html>
    """
    components.html(html, height=130, scrolling=False)


def _work_files(w):
    """คืนค่ารายการไฟล์ของผลงาน รองรับข้อมูลรูปแบบเก่าที่เก็บเป็น 'file' เดี่ยว"""
    if w.get("files"):
        return w["files"]
    if w.get("file"):
        return [w["file"]]
    return []


def _work_month_label(w):
    return w.get("month_label") or MONTH_KEY_TO_LABEL.get(w.get("month_key", ""), "ไม่ระบุเดือน")


def portfolio_page():
    with st.container(key="page_content"):
        _portfolio_page_body()


def _portfolio_page_body():
    works = get_works()

    total_works = len(works)
    months_with_work = len({_work_month_label(w) for w in works}) if works else 0
    total_images = sum(len(_work_files(w)) for w in works if w["type"] == "รูปภาพ")
    total_pdfs = len([w for w in works if w["type"] == "PDF"])

    s1, s2, s3, s4 = st.columns(4)
    for col, icon, num, label in [
        (s1, "📁", total_works, "ผลงานทั้งหมด"),
        (s2, "📅", months_with_work, "เดือนที่มีผลงาน"),
        (s3, "🖼️", total_images, "รูปภาพ"),
        (s4, "📄", total_pdfs, "PDF / รายงาน"),
    ]:
        with col:
            st.markdown(
                f"""
                <div class="stat-card">
                    <div style="font-size:20px;">{icon}</div>
                    <div class="stat-num">{num}</div>
                    <div class="stat-label">{label}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.write("")
    sc1, sc2, sc3, sc4, sc5, sc6 = st.columns([2.4, 1.6, 1, 1, 1, 1.3])
    with sc1:
        st.session_state.work_search = st.text_input(
            "ค้นหา", value=st.session_state.work_search,
            placeholder="🔍 ค้นหาผลงาน...", label_visibility="collapsed",
        )
    with sc2:
        month_options = ["ทั้งหมด"] + [m["label"] for m in MONTH_CATEGORIES]
        st.session_state.work_month_filter = st.selectbox(
            "เดือน", month_options,
            index=month_options.index(st.session_state.work_month_filter)
            if st.session_state.work_month_filter in month_options else 0,
            label_visibility="collapsed",
        )
    with sc3:
        if st.button("ทั้งหมด", use_container_width=True):
            st.session_state.work_filter = "ทั้งหมด"
    with sc4:
        if st.button("รูปภาพ", use_container_width=True):
            st.session_state.work_filter = "รูปภาพ"
    with sc5:
        if st.button("PDF", use_container_width=True):
            st.session_state.work_filter = "PDF"
    with sc6:
        if st.button("➕ เพิ่มผลงาน", use_container_width=True, type="primary"):
            st.session_state.show_add_work = True

    if st.session_state.show_add_work:
        add_work_form()
        st.divider()

    # filter + search
    filtered = works
    if st.session_state.work_filter != "ทั้งหมด":
        filtered = [w for w in filtered if w["type"] == st.session_state.work_filter]
    if st.session_state.work_month_filter != "ทั้งหมด":
        filtered = [w for w in filtered if _work_month_label(w) == st.session_state.work_month_filter]
    if st.session_state.work_search:
        q = st.session_state.work_search.lower()
        filtered = [w for w in filtered if q in w["title"].lower() or q in w.get("description", "").lower()]

    if not filtered:
        st.markdown(
            """
            <div class="empty-box">
                📁<br><br>
                <b>ยังไม่มีผลงาน</b><br>
                กดปุ่ม "เพิ่มผลงาน" เพื่อเริ่มบันทึกสิ่งที่คุณทำในสหกิจศึกษา
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # จัดกลุ่มผลงานตามหมวดหมู่เดือน เรียงจาก มิ.ย. 69 -> ก.พ. 70
    ordered_month_labels = [m["label"] for m in MONTH_CATEGORIES]
    groups = {label: [] for label in ordered_month_labels}
    groups["ไม่ระบุเดือน"] = []
    for w in filtered:
        label = _work_month_label(w)
        groups.setdefault(label, [])
        groups[label].append(w)

    for month_label in ordered_month_labels + ["ไม่ระบุเดือน"]:
        items = groups.get(month_label, [])
        if not items:
            continue
        st.markdown(f"#### 🗓️ {month_label}  <span style='color:#999;font-size:13px;font-weight:400;'>({len(items)} ผลงาน)</span>", unsafe_allow_html=True)
        cols = st.columns(4)
        for i, w in enumerate(sorted(items, key=lambda x: (x.get("date", ""), x["created_at"]), reverse=True)):
            with cols[i % 4]:
                st.markdown('<div class="work-card">', unsafe_allow_html=True)
                files = [f for f in _work_files(w) if f]
                if w["type"] == "รูปภาพ" and files:
                    render_work_gallery(files, w["id"])
                elif w["type"] == "PDF" and files:
                    st.markdown("📄 **ไฟล์ PDF แนบอยู่**")
                    pdf_b64 = files[0].split(",", 1)[-1] if "," in files[0] else files[0]
                    st.download_button(
                        "ดาวน์โหลด PDF", b64_to_bytes(pdf_b64),
                        file_name=f"{w['title']}.pdf",
                        key=f"dl_{w['id']}", use_container_width=True,
                    )
                st.markdown(f'<div class="work-title">{w["title"]}</div>', unsafe_allow_html=True)
                date_str = format_thai_date(w.get("date", ""))
                meta_parts = [f'🏷️ {w["type"]}', f'🗓️ {month_label}']
                if date_str:
                    meta_parts.append(f'📅 {date_str}')
                st.markdown(
                    f'<div class="work-meta">{" &nbsp;•&nbsp; ".join(meta_parts)}</div>',
                    unsafe_allow_html=True,
                )
                if w.get("description"):
                    st.write(w["description"])
                if st.button("🗑️ ลบ", key=f"del_work_{w['id']}"):
                    delete_work(w["id"])
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)
        st.write("")


# ----------------------------------------------------------------------------
# PROJECT PAGE
# ----------------------------------------------------------------------------
def add_project_form():
    st.subheader("➕ เพิ่มโครงงาน")
    with st.form("add_project_form", clear_on_submit=True):
        title = st.text_input("ชื่อโครงงาน *")
        summary = st.text_area("รายละเอียดโครงงาน")
        proj_date = st.date_input("วันที่ส่งโครงงาน", value=date.today())
        uploaded_file = st.file_uploader("อัปโหลดไฟล์รายงาน (PDF)", type=["pdf"])
        c1, c2 = st.columns(2)
        with c1:
            submitted = st.form_submit_button("💾 บันทึก", use_container_width=True)
        with c2:
            cancel = st.form_submit_button("ยกเลิก", use_container_width=True)

        if submitted:
            if not title:
                st.error("กรุณากรอกชื่อโครงงาน")
            else:
                file_name = None
                file_data = None
                if uploaded_file is not None:
                    file_name = uploaded_file.name
                    file_data = uploaded_file_to_b64(uploaded_file)
                item = {
                    "id": uuid.uuid4().hex,
                    "title": title,
                    "summary": summary,
                    "date": str(proj_date),
                    "file_name": file_name,
                    "file_data": file_data,
                    "created_at": datetime.now().isoformat(),
                }
                st.session_state.show_add_project = False
                add_project(item)
                st.success("เพิ่มโครงงานเรียบร้อยแล้ว")
                st.rerun()

        if cancel:
            st.session_state.show_add_project = False
            st.rerun()


def project_page():
    with st.container(key="page_content"):
        _project_page_body()


def _project_page_body():
    top_l, top_r = st.columns([3, 1])
    with top_l:
        st.markdown("### 📋 โครงงานสหกิจศึกษา")
        st.caption("อัปโหลดและแสดงไฟล์รายงานโครงงาน")
    with top_r:
        if st.button("➕ เพิ่มโครงงาน", use_container_width=True, type="primary"):
            st.session_state.show_add_project = True

    if st.session_state.show_add_project:
        add_project_form()
        st.divider()

    projects = get_projects()
    if not projects:
        st.markdown(
            """
            <div class="empty-box">
                📋<br><br>
                <b>ยังไม่มีโครงงาน</b><br>
                กดปุ่ม "+ เพิ่มโครงงาน" เพื่อเริ่มต้น
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    for p in sorted(projects, key=lambda x: x["created_at"], reverse=True):
        st.markdown('<div class="project-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="work-title">📄 {p["title"]}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="work-meta">📅 {format_thai_date(p["date"])}</div>', unsafe_allow_html=True)
        if p.get("summary"):
            st.write(p["summary"])
        if p.get("file_data"):
            st.download_button(
                "📥 ดาวน์โหลดรายงาน", b64_to_bytes(p["file_data"]),
                file_name=p.get("file_name") or f"{p['title']}.pdf",
                key=f"dl_proj_{p['id']}",
            )
        if st.button("🗑️ ลบโครงงาน", key=f"del_proj_{p['id']}"):
            delete_project(p["id"])
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------
def main():
    top_nav()

    page = st.session_state.page
    if page == "Home":
        home_page()
    elif page == "Portfolio":
        portfolio_page()
    elif page == "Project":
        project_page()


if __name__ == "__main__":
    main()

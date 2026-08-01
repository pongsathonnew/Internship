"""
Portfolio สหกิจศึกษา (Cooperative Education Portfolio)
เว็บแอป Streamlit สำหรับแสดง/บันทึกประวัตินักศึกษาสหกิจศึกษา, กิจกรรม, และโครงงาน
สามารถอัปโหลด/บันทึกรูปภาพและไฟล์ PDF ได้ ข้อมูลจะถูกเก็บไว้ในโฟลเดอร์ data/ และ uploads/
รันด้วยคำสั่ง:  streamlit run app.py
"""

import streamlit as st
import sqlite3
import os
import uuid
import base64
from datetime import datetime, date
from pathlib import Path

# ----------------------------------------------------------------------------
# CONFIG & PATHS
# ----------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "uploads"
PROFILE_IMG_DIR = UPLOAD_DIR / "profile"
WORKS_DIR = UPLOAD_DIR / "works"
PROJECTS_DIR = UPLOAD_DIR / "projects"

for d in [DATA_DIR, PROFILE_IMG_DIR, WORKS_DIR, PROJECTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ฐานข้อมูลจริงฝั่งเซิร์ฟเวอร์ (SQLite) — ข้อมูลทุกคนที่เข้าเว็บนี้ (ไม่ว่าจากเครื่อง/
# เบราว์เซอร์ไหน) จะอ่าน-เขียนไฟล์ฐานข้อมูลเดียวกันบนเซิร์ฟเวอร์ ทำให้เห็นข้อมูล
# ชุดเดียวกันเสมอ (ต่างจาก localStorage ที่ผูกกับเบราว์เซอร์ของแต่ละคน)
DB_PATH = DATA_DIR / "portfolio.db"

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
# STORAGE HELPERS (ฐานข้อมูล SQLite ฝั่งเซิร์ฟเวอร์)
# ----------------------------------------------------------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            name_th TEXT, name_en TEXT, role TEXT,
            department TEXT, university TEXT,
            company TEXT, company_unit TEXT, photo TEXT
        )"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS works (
            id TEXT PRIMARY KEY,
            title TEXT, type TEXT,
            month_key TEXT, month_label TEXT,
            date TEXT, description TEXT, created_at TEXT
        )"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS work_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            work_id TEXT, file_path TEXT
        )"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            title TEXT, summary TEXT, date TEXT,
            file TEXT, created_at TEXT
        )"""
    )
    cur.execute("SELECT COUNT(*) FROM profile WHERE id = 1")
    if cur.fetchone()[0] == 0:
        cur.execute(
            """INSERT INTO profile
               (id, name_th, name_en, role, department, university, company, company_unit, photo)
               VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                DEFAULT_PROFILE["name_th"], DEFAULT_PROFILE["name_en"], DEFAULT_PROFILE["role"],
                DEFAULT_PROFILE["department"], DEFAULT_PROFILE["university"],
                DEFAULT_PROFILE["company"], DEFAULT_PROFILE["company_unit"], DEFAULT_PROFILE["photo"],
            ),
        )
    conn.commit()
    conn.close()


def get_profile():
    conn = get_conn()
    row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
    conn.close()
    return dict(row) if row else DEFAULT_PROFILE.copy()


def save_profile(p):
    conn = get_conn()
    conn.execute(
        """UPDATE profile SET name_th=?, name_en=?, role=?, department=?,
           university=?, company=?, company_unit=?, photo=? WHERE id = 1""",
        (
            p["name_th"], p["name_en"], p["role"], p["department"],
            p["university"], p["company"], p["company_unit"], p["photo"],
        ),
    )
    conn.commit()
    conn.close()


def get_works():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM works").fetchall()
    works = []
    for row in rows:
        w = dict(row)
        files = conn.execute(
            "SELECT file_path FROM work_files WHERE work_id = ? ORDER BY id", (w["id"],)
        ).fetchall()
        w["files"] = [f["file_path"] for f in files]
        works.append(w)
    conn.close()
    return works


def add_work(item):
    conn = get_conn()
    conn.execute(
        """INSERT INTO works (id, title, type, month_key, month_label, date, description, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            item["id"], item["title"], item["type"], item["month_key"], item["month_label"],
            item["date"], item["description"], item["created_at"],
        ),
    )
    for fp in item.get("files", []):
        conn.execute("INSERT INTO work_files (work_id, file_path) VALUES (?, ?)", (item["id"], fp))
    conn.commit()
    conn.close()


def delete_work(work_id):
    conn = get_conn()
    conn.execute("DELETE FROM works WHERE id = ?", (work_id,))
    conn.execute("DELETE FROM work_files WHERE work_id = ?", (work_id,))
    conn.commit()
    conn.close()


def get_projects():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM projects").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_project(item):
    conn = get_conn()
    conn.execute(
        "INSERT INTO projects (id, title, summary, date, file, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (item["id"], item["title"], item["summary"], item["date"], item.get("file"), item["created_at"]),
    )
    conn.commit()
    conn.close()


def delete_project(project_id):
    conn = get_conn()
    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()


init_db()


def save_uploaded_file(uploaded_file, target_dir: Path) -> str:
    """Save an uploaded file with a unique name, return the relative path (str)."""
    ext = Path(uploaded_file.name).suffix
    fname = f"{uuid.uuid4().hex}{ext}"
    fpath = target_dir / fname
    with open(fpath, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return str(fpath)


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
        padding: 16px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
        margin-bottom: 14px;
    }
    .work-title { font-weight: 700; font-size: 16px; margin-bottom: 2px;}
    .work-meta { font-size: 12px; color: #888; margin-bottom: 8px;}

    /* รูปเด่น (รูปแรก) ของผลงาน - ใหญ่ ครอปให้เต็มกรอบ แต่ยังกดขยายดูรูปเต็มได้ */
    div[class*="st-key-work_feat_"] {
        position: relative;
        margin-bottom: 10px;
    }
    div[class*="st-key-work_feat_"] img {
        height: 340px !important;
        width: 100% !important;
        object-fit: cover !important;
        border-radius: 12px !important;
    }
    .gallery-badge {
        position: absolute;
        bottom: 14px;
        right: 14px;
        background: rgba(0,0,0,0.62);
        color: white;
        padding: 5px 14px;
        border-radius: 20px;
        font-size: 13px;
        font-weight: 700;
        pointer-events: none;
    }

    /* รูปย่อยที่เหลือ - ขนาดเท่ากันทุกรูป กดขยายดูรูปเต็มได้เช่นกัน */
    div[class*="st-key-work_thumb_"] img {
        height: 140px !important;
        width: 100% !important;
        object-fit: cover !important;
        border-radius: 8px !important;
    }
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
                p["photo"] = save_uploaded_file(photo_file, PROFILE_IMG_DIR)
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
            if p.get("photo") and os.path.exists(p["photo"]):
                img_bytes = Path(p["photo"]).read_bytes()
                b64 = base64.b64encode(img_bytes).decode()
                ext = Path(p["photo"]).suffix.lstrip(".") or "png"
                st.markdown(
                    f"""
                    <div class="profile-photo-frame">
                        <img src="data:image/{ext};base64,{b64}" />
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
                        file_paths.append(save_uploaded_file(img, WORKS_DIR))
                elif work_type == "PDF" and uploaded_pdf is not None:
                    file_paths.append(save_uploaded_file(uploaded_pdf, WORKS_DIR))

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


def render_work_gallery(files, work_id, max_visible_thumbs=8):
    """แสดงรูปแรกเป็นรูปเด่นขนาดใหญ่ (มีป้าย +N รูป ทับมุมถ้ามีรูปเพิ่ม)
    ส่วนรูปที่เหลือย่อเป็นภาพขนาดเท่ากันเรียงต่อกันด้านล่าง
    ใช้ st.image ทุกรูปเพื่อให้กดขยายดูรูปเต็มขนาดได้ (ไอคอนขยายจะขึ้นเมื่อชี้เมาส์/แตะที่รูป)
    """
    if not files:
        return
    featured, rest = files[0], files[1:]

    with st.container(key=f"work_feat_{work_id}"):
        st.image(featured, use_container_width=True)
        if rest:
            st.markdown(
                f'<div class="gallery-badge">+{len(rest)} รูป</div>',
                unsafe_allow_html=True,
            )

    if rest:
        shown = rest[:max_visible_thumbs]
        remaining_hidden = len(rest) - len(shown)
        n_cols = min(len(shown), 4)
        thumb_cols = st.columns(n_cols)
        for idx, fpath in enumerate(shown):
            with thumb_cols[idx % n_cols]:
                with st.container(key=f"work_thumb_{work_id}_{idx}"):
                    st.image(fpath, use_container_width=True)
        if remaining_hidden > 0:
            st.caption(f"และอีก {remaining_hidden} รูป (ทั้งหมด {len(files)} รูป)")


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
        cols = st.columns(2)
        for i, w in enumerate(sorted(items, key=lambda x: (x.get("date", ""), x["created_at"]), reverse=True)):
            with cols[i % 2]:
                st.markdown('<div class="work-card">', unsafe_allow_html=True)
                files = [f for f in _work_files(w) if os.path.exists(f)]
                if w["type"] == "รูปภาพ" and files:
                    render_work_gallery(files, w["id"])
                elif w["type"] == "PDF" and files:
                    st.markdown("📄 **ไฟล์ PDF แนบอยู่**")
                    with open(files[0], "rb") as f:
                        st.download_button(
                            "ดาวน์โหลด PDF", f, file_name=os.path.basename(files[0]),
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
                file_path = None
                if uploaded_file is not None:
                    file_path = save_uploaded_file(uploaded_file, PROJECTS_DIR)
                item = {
                    "id": uuid.uuid4().hex,
                    "title": title,
                    "summary": summary,
                    "date": str(proj_date),
                    "file": file_path,
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
        if p.get("file") and os.path.exists(p["file"]):
            with open(p["file"], "rb") as f:
                st.download_button(
                    "📥 ดาวน์โหลดรายงาน", f, file_name=os.path.basename(p["file"]),
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

import os
import sys
import subprocess
import streamlit as st
import pandas as pd
import sqlite3
import requests
from bs4 import BeautifulSoup
import re
import time
import io
import random
import logging
from datetime import datetime
import concurrent.futures
import pdfplumber
from urllib.parse import urlparse, urljoin, quote_plus, parse_qs, unquote, urlencode, urlunparse, unquote, urlencode, urlunparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ============================================================
# PLAYWRIGHT CHROMIUM OTOMATIK KURULUM
# Streamlit Cloud / GitHub deploy icin gereklidir
# ============================================================

def playwright_browser_kur():
    try:
        browser_path = os.path.expanduser("~/.cache/ms-playwright")
        eksik = True

        if os.path.exists(browser_path):
            for root, dirs, files in os.walk(browser_path):
                if "chrome-headless-shell" in files or "chrome" in files:
                    eksik = False
                    break

        if eksik:
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=False
            )
    except Exception:
        pass


playwright_browser_kur()

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AKTIF = True
except Exception:
    PLAYWRIGHT_AKTIF = False


# ============================================================
# SQUAREXPO FUAR MUSTERI OTOMASYONU V3.2
# ============================================================

APP_TITLE = "Fuar Müşteri Otomasyonu V1.5"
DB_PATH = "fuar_verileri.db"
MAX_WORKERS_DEFAULT = 3
REQUEST_TIMEOUT = 10

# Tarama modu ayarlari runtime'da sidebar'dan guncellenir
SCAN_MODE = "Dengeli"
SEARCH_QUERY_LIMIT = 6
PLAYWRIGHT_FALLBACK_ENABLED = True
WEBSITE_CACHE = {}


# ============================================================
# STREAMLIT AYARLARI
# ============================================================

st.set_page_config(
    page_title=APP_TITLE,
    layout="wide",
    page_icon="🚀"
)


# ============================================================
# GIRIS SISTEMI
# ============================================================

LOGIN_USERNAME = "perge"
LOGIN_PASSWORD = "perge2026"

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False


def giris_ekrani():
    st.markdown("""
    <style>
    .login-wrap {
        max-width: 480px;
        margin: 80px auto;
        padding: 34px;
        border-radius: 24px;
        background: linear-gradient(135deg, rgba(15,23,42,0.98), rgba(30,41,59,0.96));
        border: 1px solid rgba(255,255,255,0.08);
        box-shadow: 0 25px 60px rgba(0,0,0,0.35);
        color: white;
    }

    .login-title {
        font-size: 34px;
        font-weight: 800;
        margin-bottom: 10px;
        text-align: center;
    }

    .login-sub {
        text-align: center;
        color: rgba(255,255,255,0.72);
        margin-bottom: 24px;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="login-wrap">
        <div class="login-title">🔐 Güvenli Giriş</div>
        <div class="login-sub">
            Perge Mimarlık & Squarexpo<br>
            Fuar Müşteri Otomasyonu V1.5
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1,2,1])

    with col2:
        username = st.text_input("Kullanıcı Adı")
        password = st.text_input("Şifre", type="password")

        if st.button("🚀 Giriş Yap", use_container_width=True):
            if username == LOGIN_USERNAME and password == LOGIN_PASSWORD:
                st.session_state["authenticated"] = True
                st.success("Giriş başarılı.")
                st.rerun()
            else:
                st.error("Kullanıcı adı veya şifre hatalı.")

    st.stop()


if not st.session_state["authenticated"]:
    giris_ekrani()



# ============================================================
# GORSEL TASARIM / KURUMSAL UI
# ============================================================

def kurumsal_tasarim_yukle():
    st.markdown("""
    <style>
    .stApp {
        background:
            radial-gradient(circle at top left, rgba(37,99,235,0.16), transparent 32%),
            radial-gradient(circle at top right, rgba(124,58,237,0.12), transparent 28%),
            linear-gradient(180deg, #f8fbff 0%, #eef4ff 100%);
    }

    section.main > div {
        padding-top: 1.4rem;
    }

    .block-container {
        max-width: 1280px;
        padding-top: 1rem;
    }

    .hero-banner {
        position: relative;
        overflow: hidden;
        border-radius: 26px;
        padding: 34px 38px;
        min-height: 245px;
        background:
            linear-gradient(120deg, rgba(7,19,48,0.98), rgba(12,34,84,0.96) 45%, rgba(10,15,35,0.96)),
            radial-gradient(circle at 75% 30%, rgba(59,130,246,0.45), transparent 25%);
        box-shadow: 0 24px 70px rgba(15,23,42,0.24);
        border: 1px solid rgba(255,255,255,0.18);
        color: white;
        margin-bottom: 22px;
    }

    .hero-banner:before {
        content: "";
        position: absolute;
        inset: 0;
        background:
            linear-gradient(90deg, transparent, rgba(59,130,246,0.26), transparent),
            repeating-linear-gradient(90deg, rgba(255,255,255,0.04) 0px, rgba(255,255,255,0.04) 1px, transparent 1px, transparent 80px);
        opacity: .85;
    }

    .hero-glow {
        position: absolute;
        width: 620px;
        height: 90px;
        left: 18%;
        bottom: 18px;
        background: linear-gradient(90deg, #2563eb, #7c3aed, #06b6d4);
        filter: blur(24px);
        opacity: .72;
        transform: rotate(-5deg);
    }

    .hero-content {
        position: relative;
        z-index: 2;
        display: grid;
        grid-template-columns: 1.1fr 1.2fr;
        gap: 32px;
        align-items: center;
    }

    .brand-row {
        display: flex;
        align-items: center;
        gap: 18px;
        margin-bottom: 22px;
        flex-wrap: wrap;
    }

    .brand-pill {
        border: 1px solid rgba(255,255,255,0.20);
        background: rgba(255,255,255,0.08);
        backdrop-filter: blur(12px);
        padding: 14px 18px;
        border-radius: 18px;
        min-width: 190px;
    }

    .brand-pill strong {
        display: block;
        font-size: 25px;
        letter-spacing: 2px;
        line-height: 1;
    }

    .brand-pill span {
        display: block;
        margin-top: 7px;
        color: rgba(255,255,255,0.75);
        font-size: 12px;
        letter-spacing: 1.5px;
    }

    .hero-title {
        font-size: 48px;
        line-height: 1.05;
        font-weight: 800;
        margin: 0;
        letter-spacing: -1.2px;
    }

    .hero-subtitle {
        margin-top: 16px;
        font-size: 18px;
        color: rgba(255,255,255,0.82);
        max-width: 610px;
    }

    .hero-meta {
        display: flex;
        gap: 12px;
        margin-top: 24px;
        flex-wrap: wrap;
    }

    .meta-chip {
        background: rgba(255,255,255,0.11);
        border: 1px solid rgba(255,255,255,0.16);
        padding: 10px 14px;
        border-radius: 999px;
        font-size: 13px;
        color: rgba(255,255,255,0.88);
    }

    .hero-visual {
        min-height: 180px;
        border-radius: 22px;
        border: 1px solid rgba(255,255,255,0.14);
        background:
            linear-gradient(135deg, rgba(255,255,255,0.08), rgba(255,255,255,0.02)),
            radial-gradient(circle at center, rgba(96,165,250,0.34), transparent 50%);
        display: flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        position: relative;
        overflow: hidden;
    }

    .hero-visual:after {
        content: "";
        position: absolute;
        width: 300px;
        height: 300px;
        border: 1px solid rgba(96,165,250,0.24);
        border-radius: 50%;
        box-shadow: 0 0 55px rgba(96,165,250,0.30);
    }

    .hero-visual-inner {
        position: relative;
        z-index: 2;
        font-size: 72px;
        filter: drop-shadow(0 12px 30px rgba(37,99,235,0.45));
    }

    .feature-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 16px;
        margin: 20px 0 24px;
    }

    .feature-card {
        background: rgba(255,255,255,0.80);
        border: 1px solid rgba(148,163,184,0.28);
        border-radius: 20px;
        padding: 18px;
        box-shadow: 0 15px 40px rgba(15,23,42,0.08);
    }

    .feature-card .icon {
        font-size: 28px;
        margin-bottom: 10px;
    }

    .feature-card strong {
        display: block;
        color: #0f172a;
        font-size: 16px;
        margin-bottom: 6px;
    }

    .feature-card span {
        color: #475569;
        font-size: 13px;
    }

    div[data-testid="stTabs"] button {
        font-size: 15px;
        font-weight: 600;
    }

    div[data-testid="stVerticalBlock"] div[data-testid="stDataFrame"] {
        border-radius: 18px;
        overflow: hidden;
        box-shadow: 0 14px 35px rgba(15,23,42,0.08);
    }

    .stButton > button {
        border-radius: 14px !important;
        border: 1px solid rgba(37,99,235,0.24) !important;
        background: linear-gradient(135deg, #2563eb, #4f46e5) !important;
        color: white !important;
        font-weight: 700 !important;
        box-shadow: 0 10px 24px rgba(37,99,235,0.22);
    }

    .stDownloadButton > button {
        border-radius: 14px !important;
        font-weight: 700 !important;
    }

    .footer-note {
        text-align: center;
        color: #64748b;
        font-size: 13px;
        padding: 26px 0 8px;
    }

    @media (max-width: 900px) {
        .hero-content { grid-template-columns: 1fr; }
        .feature-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .hero-title { font-size: 36px; }
    }
    </style>
    """, unsafe_allow_html=True)


def kurumsal_banner_goster():
    st.markdown("""
    <div class="hero-banner">
        <div class="hero-glow"></div>
        <div class="hero-content">
            <div>
                <div class="brand-row">
                    <div class="brand-pill">
                        <strong>PERGE</strong>
                        <span>MİMARLIK</span>
                    </div>
                    <div class="brand-pill">
                        <strong>SQUAREXPO</strong>
                        <span>FUAR | EXPO | EVENTS</span>
                    </div>
                </div>
                <h1 class="hero-title">Fuar Müşteri<br>Otomasyonu V1.5</h1>
                <div class="hero-subtitle">
                    Katılımcı listelerini otomatik tarayın; firma web sitesi, e-posta ve telefon bilgilerine hızlıca ulaşın.
                </div>
                <div class="hero-meta">
                    <div class="meta-chip">🌐 URL Tarama</div>
                    <div class="meta-chip">📄 PDF Analiz</div>
                    <div class="meta-chip">📊 Excel Giriş</div>
                    <div class="meta-chip">⚡ Hızlı Enrichment</div>
                </div>
            </div>
            <div class="hero-visual">
                <div class="hero-visual-inner">🏗️🌍🚀</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def ozellik_kartlari_goster():
    st.markdown("""
    <div class="feature-grid">
        <div class="feature-card">
            <div class="icon">🔎</div>
            <strong>Akıllı Firma Çekimi</strong>
            <span>URL, PDF, Excel ve manuel girişlerden firma isimlerini çoklu motorla ayıklar.</span>
        </div>
        <div class="feature-card">
            <div class="icon">🌐</div>
            <strong>Web Sitesi Bulma</strong>
            <span>Firma adından resmi web sitesini bulmaya çalışır.</span>
        </div>
        <div class="feature-card">
            <div class="icon">📞</div>
            <strong>İletişim Bilgisi</strong>
            <span>Web sitesinden telefon ve e-posta bilgilerini çıkarır.</span>
        </div>
        <div class="feature-card">
            <div class="icon">📥</div>
            <strong>Excel Dışa Aktarım</strong>
            <span>Sonuçları düzenli arşivler ve Excel olarak indirmenizi sağlar.</span>
        </div>
    </div>
    """, unsafe_allow_html=True)



# ============================================================
# LOG AYARLARI
# ============================================================

logging.basicConfig(
    filename="squarexpo_v3.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


# ============================================================
# SESSION STATE
# ============================================================

if "ana_liste" not in st.session_state:
    st.session_state["ana_liste"] = []

if "son_hatalar" not in st.session_state:
    st.session_state["son_hatalar"] = []

if "son_islem_ozeti" not in st.session_state:
    st.session_state["son_islem_ozeti"] = ""

if "website_cache" not in st.session_state:
    st.session_state["website_cache"] = {}


if "batch_index" not in st.session_state:
    st.session_state["batch_index"] = 0

if "son_batch_sonuclari" not in st.session_state:
    st.session_state["son_batch_sonuclari"] = []



# ============================================================
# YARDIMCI FONKSIYONLAR
# ============================================================

def hata_kaydet(mesaj: str):
    logging.error(mesaj)
    st.session_state["son_hatalar"].append(mesaj)
    st.session_state["son_hatalar"] = st.session_state["son_hatalar"][-30:]


def temiz_metin(text):
    if not text:
        return ""
    text = BeautifulSoup(str(text), "html.parser").get_text(" ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def firma_adi_temizle(text):
    text = temiz_metin(text)
    text = text.replace("\xa0", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def domain_al(url):
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower().replace("www.", "")
    except Exception:
        return ""


def url_gecerli_mi(url):
    if not url:
        return False

    try:
        url = str(url).strip()
        low = url.lower()

        if low.startswith(("javascript:", "mailto:", "tel:", "#", "data:", "about:")):
            return False

        if "javascript:void" in low:
            return False

        parsed = urlparse(url)

        if parsed.scheme not in ["http", "https"]:
            return False

        if not parsed.netloc:
            return False

        if "." not in parsed.netloc:
            return False

        return True

    except Exception:
        return False


def normalize_url(url, base_url=None):
    if not url:
        return ""

    url = str(url).strip()

    # Gerçek web sitesi olmayan linkleri direkt ele
    gecersiz_baslangiclar = [
        "javascript:", "mailto:", "tel:", "#", "data:", "about:", "void(0)"
    ]

    if any(url.lower().startswith(x) for x in gecersiz_baslangiclar):
        return ""

    if url.lower() in ["javascript:void(0)", "javascript:;", "void(0)"]:
        return ""

    if base_url and url.startswith("/"):
        return urljoin(base_url, url)

    if url.startswith("//"):
        return "https:" + url

    if not url.startswith("http://") and not url.startswith("https://"):
        # İçinde nokta yoksa büyük ihtimalle gerçek domain değildir
        if "." not in url:
            return ""
        return "https://" + url

    return url


def istenmeyen_link_mi(url):
    blacklist = [
        "javascript:void", "javascript:", "mailto:", "tel:",
        "google.", "bing.", "microsoft.", "facebook.", "instagram.",
        "linkedin.", "youtube.", "twitter.", "x.com", "tiktok.",
        "wikipedia.", "yandex.", "duckduckgo.", "whatsapp.",
        "maps.google", "support.google", "webcache", "translate.google",
        "pinterest.", "reddit.", "medium.", "amazon.", "hepsiburada.",
        "trendyol.", "n11.", "sahibinden."
    ]
    u = url.lower()
    return any(b in u for b in blacklist)


def get_headers(referer=None):
    headers = {
        "User-Agent": random.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
        ]),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def yeni_session():
    session = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=1.2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"]
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def guvenli_get(url, timeout=REQUEST_TIMEOUT, referer=None):
    session = yeni_session()
    try:
        return session.get(
            url,
            headers=get_headers(referer),
            timeout=timeout,
            allow_redirects=True,
            verify=True
        )
    except requests.exceptions.SSLError:
        return session.get(
            url,
            headers=get_headers(referer),
            timeout=timeout,
            allow_redirects=True,
            verify=False
        )


# ============================================================
# VERITABANI
# ============================================================

def db_baglan():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def tabloyu_hazirla():
    conn = db_baglan()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS sonuclar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fuar_etiketi TEXT,
            firma_adi TEXT,
            web_adresi TEXT,
            telefon TEXT,
            eposta TEXT,
            kaynak TEXT,
            durum TEXT,
            hata TEXT,
            tarih TEXT
        )
    """)

    c.execute("CREATE INDEX IF NOT EXISTS idx_firma_adi ON sonuclar(firma_adi)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_fuar_etiketi ON sonuclar(fuar_etiketi)")

    conn.commit()
    conn.close()


def verileri_toplu_kaydet(kayitlar):
    if not kayitlar:
        return

    conn = db_baglan()
    c = conn.cursor()
    tarih = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows = []
    for k in kayitlar:
        rows.append((
            k.get("fuar_etiketi", ""),
            k.get("firma_adi", ""),
            k.get("web_adresi", "Bulunamadi"),
            k.get("telefon", "Bulunamadi"),
            k.get("eposta", "Bulunamadi"),
            k.get("kaynak", ""),
            k.get("durum", ""),
            k.get("hata", ""),
            tarih
        ))

    c.executemany("""
        INSERT INTO sonuclar 
        (fuar_etiketi, firma_adi, web_adresi, telefon, eposta, kaynak, durum, hata, tarih)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)

    conn.commit()
    conn.close()


def arsivi_getir():
    conn = db_baglan()
    try:
        df = pd.read_sql_query("""
            SELECT 
                fuar_etiketi,
                firma_adi,
                web_adresi,
                telefon,
                eposta,
                kaynak,
                durum,
                hata,
                tarih
            FROM sonuclar 
            ORDER BY id DESC
        """, conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df



def islenmis_firmalari_getir(fuar_etiketi):
    """
    Aynı fuar etiketi için daha önce arşive kaydedilmiş firmaları döndürür.
    Böylece sistem kapanırsa kaldığı yerden devam edebilir.
    """
    conn = db_baglan()
    try:
        df = pd.read_sql_query(
            "SELECT DISTINCT firma_adi FROM sonuclar WHERE fuar_etiketi = ?",
            conn,
            params=(fuar_etiketi,)
        )
        firmalar = set(df["firma_adi"].dropna().astype(str).str.lower().str.strip().tolist())
    except Exception:
        firmalar = set()
    conn.close()
    return firmalar


def arsivi_temizle():
    conn = db_baglan()
    conn.execute("DELETE FROM sonuclar")
    conn.commit()
    conn.close()



def firma_gibi_gorunuyor_mu(item):
    """
    Sayfadaki her metni firma sanmamak icin sirket unvani benzeri satirlari secer.
    Ozellikle fuar katilimci listelerinde firma adlari genelde bu kaliplari tasir.
    """
    if not item:
        return False

    text = firma_adi_temizle(item)
    low = text.lower()

    # Net menü / adres / sayfa / zaman kelimeleri
    red_flags = [
        "mah.", "mahalle", "cad.", "cadde", "sok.", "sokak", "no:", "istanbul", "bakırköy",
        "foto galeri", "genel bakış", "genel bakis", "gizlilik", "hazır stant", "hazir stant",
        "medya", "materyal", "medya materyalleri", "medya partnerleri",
        "ziyaretçi", "ziyaretci", "katılımcı", "katilimci", "başvuru", "basvuru",
        "saniye", "dakika", "gün", "gun", "saat", "sonuç", "sonuc",
        "musiad", "müsiad", "fuar", "expo", "web sitesi", "web site",
        "kvkk", "politika", "form", "bilet", "ulaşım", "ulasim",
        "program", "etkinlik", "salon", "harita", "iletişim", "iletisim",
        "dijital teknolojiler", "enerji ve çevre", "enerji ve cevre", "hizmetler ve finans", "metal ve maden", "tekstil deri ve hazır giyim", "tekstil deri ve hazir giyim", "hizmetler ve finans", "metal ve maden", "tekstil deri ve hazır giyim", "tekstil deri ve hazir giyim",
        "gıda, tarım ve hayvancılık", "gida, tarim ve hayvancilik",
        "sektör", "sektor", "kategori", "ürün grubu", "urun grubu"
    ]

    if any(x in low for x in red_flags):
        return False

    if len(text) < 4 or len(text) > 90:
        return False

    if re.fullmatch(r"[\d\s\-\+\(\):\.]+", text):
        return False

    if re.search(r"https?://|www\.|@", low):
        return False

    # Sirket unvani isaretleri
    company_markers = [
        " a.ş", " a.s", " aş", " as ", " anonim", " san ", " sanayi",
        " tic ", " ticaret", " ltd", " ltd.", " şti", " şti.", " sti", " sti.",
        " limited", " şirket", " sirket", " co.", " co ", " inc", " llc",
        " gmbh", " group", " holding", " corporation", " corp"
    ]

    if any(m in f" {low} " for m in company_markers):
        return True

    # Birleşik yazımları da yakala: LTDŞTİ, AŞ, SANVE TIC gibi bozuk OCR/HTML halleri
    compact = low.replace(".", "").replace(" ", "")
    compact_markers = [
        "ltdşti", "ltdsti", "limitedşirket", "limitedsirket",
        "anonimşirket", "anonimsirket", "sanvetic", "sanayiveticaret",
        "aş", "as"
    ]
    if any(m in compact for m in compact_markers):
        return True

    # URL taramasinda kategori / baslik karismasin diye
    # sadece sirket unvani isareti tasiyan metinler firma kabul edilir.
    return False



def musiad_firma_adi_temizle(text):
    """
    MÜSİAD sayfasında satırlar çoğu zaman:
    FIRMA ADI + SEKTÖR + ŞEHİR
    şeklinde geliyor. Bu fonksiyon sondaki sektör/şehir parçalarını temizler.
    """
    if not text:
        return ""

    t = firma_adi_temizle(text)

    sehirler = [
        "ADANA", "ADIYAMAN", "AFYONKARAHİSAR", "AĞRI", "AMASYA", "ANKARA", "ANTALYA",
        "ARTVİN", "AYDIN", "BALIKESİR", "BİLECİK", "BİNGÖL", "BİTLİS", "BOLU",
        "BURDUR", "BURSA", "ÇANAKKALE", "ÇANKIRI", "ÇORUM", "DENİZLİ", "DİYARBAKIR",
        "EDİRNE", "ELAZIĞ", "ERZİNCAN", "ERZURUM", "ESKİŞEHİR", "GAZİANTEP",
        "GİRESUN", "GÜMÜŞHANE", "HAKKARİ", "HATAY", "ISPARTA", "MERSİN", "İSTANBUL",
        "İZMİR", "KARS", "KASTAMONU", "KAYSERİ", "KIRKLARELİ", "KIRŞEHİR",
        "KOCAELİ", "KONYA", "KÜTAHYA", "MALATYA", "MANİSA", "KAHRAMANMARAŞ",
        "MARDİN", "MUĞLA", "MUŞ", "NEVŞEHİR", "NİĞDE", "ORDU", "RİZE", "SAKARYA",
        "SAMSUN", "SİİRT", "SİNOP", "SİVAS", "TEKİRDAĞ", "TOKAT", "TRABZON",
        "TUNCELİ", "ŞANLIURFA", "UŞAK", "VAN", "YOZGAT", "ZONGULDAK", "AKSARAY",
        "BAYBURT", "KARAMAN", "KIRIKKALE", "BATMAN", "ŞIRNAK", "BARTIN", "ARDAHAN",
        "IĞDIR", "YALOVA", "KARABÜK", "KİLİS", "OSMANİYE", "DÜZCE"
    ]

    sektorler = [
        "BASIM YAYIN MEDYA",
        "DİJİTAL TEKNOLOJİLER",
        "ENERJİ VE ÇEVRE",
        "GIDA TARIM VE HAYVANCILIK",
        "GIDA, TARIM VE HAYVANCILIK",
        "HİZMETLER VE FİNANS",
        "MAKİNE",
        "METAL VE MADEN",
        "MOBİLYA",
        "OTOMOTİV",
        "SAĞLIK",
        "TEKSTİL DERİ VE HAZIR GİYİM",
        "TURİZM",
        "İNŞAAT VE YAPI MALZEMELERİ",
        "KİMYA",
        "LOJİSTİK",
        "SAVUNMA SANAYİ",
        "ELEKTRİK ELEKTRONİK",
        "AMBALAJ"
    ]

    # Sondaki şehir bilgisini temizle
    for city in sehirler:
        pattern = r"\s+" + re.escape(city) + r"$"
        t = re.sub(pattern, "", t, flags=re.IGNORECASE).strip()

    # Sondaki sektör bilgisini temizle
    for sektor in sektorler:
        pattern = r"\s+" + re.escape(sektor) + r"$"
        t = re.sub(pattern, "", t, flags=re.IGNORECASE).strip()

    # Bazen önce sektör sonra şehir temizlenince tekrar şehir/sektör kalabilir
    for city in sehirler:
        pattern = r"\s+" + re.escape(city) + r"$"
        t = re.sub(pattern, "", t, flags=re.IGNORECASE).strip()

    for sektor in sektorler:
        pattern = r"\s+" + re.escape(sektor) + r"$"
        t = re.sub(pattern, "", t, flags=re.IGNORECASE).strip()

    return t


def sadece_firma_unvani_mi(text):
    """
    URL sonuçlarında kategori/menü değil, gerçek firma adı kalsın.
    """
    if not text:
        return False

    low = text.lower()

    yasak = [
        "foto galeri", "genel bakış", "genel bakis", "gizlilik", "medya",
        "dijital teknolojiler", "enerji ve çevre", "enerji ve cevre",
        "gıda, tarım ve hayvancılık", "gida, tarim ve hayvancilik",
        "hizmetler ve finans", "metal ve maden", "tekstil deri",
        "hazır stant", "hazir stant", "musiad", "müsiad", "katılımcı", "katilimci"
    ]

    if any(y in low for y in yasak):
        return False

    markerlar = [
        "a.ş", "a.s", " aş", " as ", "anonim", "san", "sanayi",
        "tic", "ticaret", "ltd", "şti", "sti", "limited", "şirket", "sirket",
        "co.", "inc", "llc", "gmbh", "group", "holding"
    ]

    return any(m in f" {low} " for m in markerlar)


def url_firma_sonuclarini_temizle(adaylar):
    temiz = []
    for a in adaylar:
        t = musiad_firma_adi_temizle(a)
        if sadece_firma_unvani_mi(t):
            temiz.append(t)

    # Son genel temizlik ve mükerrer silme
    temiz = firma_listesi_filtrele(temiz)

    final = []
    seen = set()
    for x in temiz:
        key = x.lower().strip()
        if key not in seen:
            seen.add(key)
            final.append(x)

    return final


# ============================================================
# FIRMA LISTESI FILTRELEME
# ============================================================

def firma_listesi_filtrele(adaylar):
    yasakli = [
        "giris", "giriş", "kayıt", "kayit", "menü", "menu", "iletişim", "iletisim",
        "fuar", "expo", "detay", "tıklayın", "tiklayin", "ara", "sayfa",
        "home", "login", "register", "about", "contact", "privacy", "cookie",
        "kvkk", "terms", "sponsor", "visitor", "exhibitor", "download", "pdf",
        "map", "facebook", "instagram", "linkedin", "youtube", "twitter",
        "language", "english", "turkish", "read more", "show more",
        "stand", "booth", "hall", "category", "product", "service",
        "katılımcı", "katilimci", "firmalar", "firma", "sonuç", "sonuc",
        "saniye", "dakika", "gün", "gun", "saat", "2024", "2025", "2026",
        "musiad", "müsiad", "musiad expo", "müsiad expo", "arama",
        "filtre", "tüm", "tum", "liste", "listesi", "loading", "yükleniyor",
        "yukleniyor", "devam", "geri", "ileri", "previous", "next",
        "foto galeri", "genel bakış", "genel bakis", "gizlilik politikası",
        "gizlilik politikasi", "hazır stantlar", "hazir stantlar",
        "medya materyalleri", "medya partnerleri",
        "dijital teknolojiler", "enerji ve çevre", "enerji ve cevre", "hizmetler ve finans", "metal ve maden", "tekstil deri ve hazır giyim", "tekstil deri ve hazir giyim", "hizmetler ve finans", "metal ve maden", "tekstil deri ve hazır giyim", "tekstil deri ve hazir giyim",
        "gıda, tarım ve hayvancılık", "gida, tarim ve hayvancilik"
    ]

    temiz_liste = []

    for item in adaylar:
        item = firma_adi_temizle(item)
        item_lower = item.lower()

        if not item:
            continue
        if len(item) < 3 or len(item) > 85:
            continue
        if any(k in item_lower for k in yasakli):
            continue
        if item.count(" ") > 10:
            continue
        if re.search(r"https?://|www\.|@", item_lower):
            continue
        if re.fullmatch(r"[\d\s\-\+\(\):\.]+", item):
            continue
        if re.search(r"\b\d+\s*(saniye|dakika|gün|gun|saat|sonuç|sonuc)\b", item_lower):
            continue
        if re.search(r"\b\d{1,2}\s*[:.]\s*\d{1,2}\b", item_lower):
            continue
        if re.search(r"\b(mah|mahalle|cad|cadde|sok|sokak|no|adres|address)\b", item_lower):
            continue
        if not re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", item):
            continue

        kelime_sayisi = len(item.split())
        if kelime_sayisi == 1 and len(item) < 5:
            continue

        temiz_liste.append(item)

    seen = set()
    sonuc = []

    for item in temiz_liste:
        key = item.lower().strip()
        if key not in seen:
            seen.add(key)
            sonuc.append(item)

    return sorted(sonuc)




def musiad_katilimci_listesi_cek(url, progress_callback=None):
    """
    MÜSİAD Expo özel motoru V4.1.
    Ana düzeltme:
    - Tailwind class içinde geçen disabled:opacity gibi ifadeler gerçek disabled sanılmıyor.
    - Sonraki butonu gerçek disabled değilse tıklanır.
    - Her sayfada tablo/scroll alanı agresif şekilde aşağı kaydırılır.
    - Katılımcı sütunundaki firma adı alınır.
    """
    if not PLAYWRIGHT_AKTIF:
        raise Exception("Playwright aktif değil. MÜSİAD özel motoru çalışamaz.")

    url = normalize_url(url)
    tum_firmalar = []
    baslangic_zamani = time.time()

    def durum_bildir(adim, sayfa_no=0, toplam_sayfa=0):
        if progress_callback:
            try:
                gecen = time.time() - baslangic_zamani
                progress_callback({
                    "adim": adim,
                    "sayfa_no": sayfa_no,
                    "toplam_sayfa": toplam_sayfa,
                    "bulunan": len(set([x.lower().strip() for x in tum_firmalar])),
                    "gecen": gecen
                })
            except Exception:
                pass

    def firma_ekle(firma):
        firma = firma_adi_temizle(firma)
        firma = musiad_firma_adi_temizle(firma)

        if not firma:
            return

        low = firma.lower()
        yasak = [
            "katılımcı", "katilimci", "sektör", "sektor", "şehir", "sehir",
            "foto galeri", "genel bakış", "genel bakis", "gizlilik", "medya",
            "musiad", "müsiad", "sonraki", "önceki", "onceki"
        ]

        if len(firma) < 3 or len(firma) > 120:
            return
        if any(y in low for y in yasak):
            return
        if re.fullmatch(r"[\d\s\-\+\(\):\.]+", firma):
            return

        tum_firmalar.append(firma)

    def gorunen_tablo_satirlarini_oku(page):
        try:
            rows = page.locator("table tbody tr")
            row_count = rows.count()

            for i in range(row_count):
                try:
                    cells = rows.nth(i).locator("td")
                    if cells.count() == 0:
                        continue

                    firma = cells.nth(0).inner_text(timeout=2000)
                    firma_ekle(firma)

                except Exception:
                    continue
        except Exception:
            pass

    def tum_scroll_alanlarini_kaydir(page):
        """
        Sayfadaki tüm scroll edilebilir alanları aşağı kaydırır.
        Virtual table varsa yeni satırların DOM'a gelmesini sağlar.
        """
        try:
            return page.evaluate("""
                () => {
                    let changed = false;
                    const all = Array.from(document.querySelectorAll('*'));

                    for (const el of all) {
                        try {
                            const canScrollY = el.scrollHeight > el.clientHeight + 10;
                            if (!canScrollY) continue;

                            const before = el.scrollTop;
                            el.scrollTop = el.scrollTop + Math.max(250, Math.floor(el.clientHeight * 0.85));

                            if (el.scrollTop !== before) changed = true;
                        } catch(e) {}
                    }

                    window.scrollBy(0, 500);
                    return changed;
                }
            """)
        except Exception:
            return False

    def sonraki_butonuna_bas(page):
        """
        Sonraki butonuna basar.
        ÖNEMLİ: class içinde 'disabled:' geçmesi gerçek disabled değildir.
        Sadece disabled attribute veya aria-disabled=true gerçek disabled kabul edilir.
        """
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(700)

            clicked = page.evaluate("""
                () => {
                    const els = Array.from(document.querySelectorAll('button, a'));
                    const candidates = els.filter(el => {
                        const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                        return txt.includes('sonraki') || txt.includes('next');
                    });

                    if (!candidates.length) return false;

                    const btn = candidates[candidates.length - 1];

                    const realDisabled =
                        btn.disabled === true ||
                        btn.getAttribute('disabled') !== null ||
                        btn.getAttribute('aria-disabled') === 'true';

                    if (realDisabled) return false;

                    btn.scrollIntoView({block: 'center', inline: 'center'});
                    btn.click();
                    return true;
                }
            """)

            if clicked:
                return True

            # Playwright fallback
            selectors = [
                "button:has-text('Sonraki')",
                "a:has-text('Sonraki')",
                "button:has-text('Next')",
                "a:has-text('Next')"
            ]

            for sel in selectors:
                try:
                    locs = page.locator(sel)
                    count = locs.count()

                    if count > 0:
                        btn = locs.nth(count - 1)

                        if not btn.is_visible():
                            continue

                        disabled_attr = btn.get_attribute("disabled")
                        aria_disabled = btn.get_attribute("aria-disabled")

                        if disabled_attr is not None or aria_disabled == "true":
                            return False

                        btn.scroll_into_view_if_needed(timeout=3000)
                        page.wait_for_timeout(500)
                        btn.click(timeout=5000)
                        return True

                except Exception:
                    continue

            return False

        except Exception:
            return False

    durum_bildir("Tarayıcı başlatılıyor...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled"
            ]
        )

        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1500, "height": 1000},
            locale="tr-TR"
        )

        durum_bildir("Sayfa açılıyor ve katılımcı tablosu bekleniyor...")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)

        for _ in range(25):
            try:
                if page.locator("table tbody tr").count() > 0:
                    break
            except Exception:
                pass
            page.wait_for_timeout(1000)

        # Sayfa sayısını gövdeden tahmin et: "Sayfa 1 / 14"
        toplam_sayfa = 20
        try:
            body_text = page.inner_text("body")
            m = re.search(r"Sayfa\s+\d+\s*/\s*(\d+)", body_text, flags=re.IGNORECASE)
            if m:
                toplam_sayfa = int(m.group(1))
        except Exception:
            pass

        onceki_toplam = -1

        for sayfa_no in range(1, toplam_sayfa + 1):
            durum_bildir(f"Sayfa {sayfa_no}/{toplam_sayfa} okunuyor...", sayfa_no, toplam_sayfa)
            page.wait_for_timeout(1500)

            # Her sayfada önce en üste çek
            try:
                page.evaluate("""
                    () => {
                        const all = Array.from(document.querySelectorAll('*'));
                        for (const el of all) {
                            try {
                                if (el.scrollHeight > el.clientHeight + 10) el.scrollTop = 0;
                            } catch(e) {}
                        }
                    }
                """)
            except Exception:
                pass

            # Görünenleri oku + scroll et + tekrar oku
            durum_bildir(f"Sayfa {sayfa_no}/{toplam_sayfa}: tablo satırları toplanıyor...", sayfa_no, toplam_sayfa)
            stabil = 0
            son_count = len(tum_firmalar)

            for _ in range(35):
                gorunen_tablo_satirlarini_oku(page)
                page.wait_for_timeout(500)

                if len(tum_firmalar) == son_count:
                    stabil += 1
                else:
                    stabil = 0
                    son_count = len(tum_firmalar)

                changed = tum_scroll_alanlarini_kaydir(page)
                page.wait_for_timeout(500)

                if stabil >= 4 and not changed:
                    break

            durum_bildir(f"Sayfa {sayfa_no}/{toplam_sayfa} tamamlandı.", sayfa_no, toplam_sayfa)

            # Sonraki sayfaya geç
            if sayfa_no >= toplam_sayfa:
                break

            before_first = ""
            try:
                before_first = page.locator("table tbody tr").nth(0).locator("td").nth(0).inner_text(timeout=1000)
            except Exception:
                pass

            durum_bildir(f"Sayfa {sayfa_no + 1}/{toplam_sayfa} için Sonraki butonuna basılıyor...", sayfa_no, toplam_sayfa)
            clicked = sonraki_butonuna_bas(page)

            if not clicked:
                break

            # Sayfa değişimini bekle
            changed_page = False
            for _ in range(20):
                page.wait_for_timeout(1000)
                try:
                    after_first = page.locator("table tbody tr").nth(0).locator("td").nth(0).inner_text(timeout=1000)
                    if after_first and after_first != before_first:
                        changed_page = True
                        break
                except Exception:
                    pass

            if not changed_page:
                # Bazı sistemlerde ilk satır aynı kalabilir; toplam firma artışına göre devam edebiliriz.
                if len(tum_firmalar) == onceki_toplam:
                    break

            onceki_toplam = len(tum_firmalar)

        browser.close()

    final = []
    seen = set()

    for f in tum_firmalar:
        f = firma_adi_temizle(f)
        key = f.lower().strip()

        if key and key not in seen:
            seen.add(key)
            final.append(f)

    return final





def maktek_firma_adi_temizle(text):
    """
    MAKTEK sayfasında satırlar genelde:
    FIRMA ADI + ÜLKE + Markalar/Temsilcilikler + Detaylı İncele + Salon/Stant
    şeklinde gelir. Bu fonksiyon sadece firma adını bırakır.
    """
    if not text:
        return ""

    t = firma_adi_temizle(text)
    t = re.sub(r"\s+", " ", t).strip()

    # Detaylı incele ve sonrasını sil
    t = re.split(r"\bDetaylı\s+İncele\b|\bDetayli\s+Incele\b", t, flags=re.IGNORECASE)[0].strip()

    # Salon/Stant ve sonrasını sil
    t = re.split(r"\bSalon\s*:|\bStant\s*:", t, flags=re.IGNORECASE)[0].strip()

    # Ülke bilgisinden itibaren kes
    ulkeler = [
        "Türkı̇ye", "Türkiye", "Turkiye", "Turkey",
        "Almanya", "Amerı̇ka", "Amerika", "Avusturya", "Belçı̇ka", "Belçika",
        "Bulgarı̇stan", "Bulgaristan", "Çek Cumhurı̇yetı̇", "Çek Cumhuriyeti",
        "Çı̇n", "Çin", "Fı̇nlandı̇ya", "Finlandiya", "Fransa", "Güney Kore",
        "Hı̇ndı̇stan", "Hindistan", "Hollanda", "İngı̇ltere", "İngiltere",
        "İspanya", "İsvı̇çre", "İsviçre", "İtalya", "Japonya", "Kanada",
        "Kore", "Macarı̇stan", "Macaristan", "Polonya", "Portekı̇z",
        "Portekiz", "Tayvan"
    ]

    earliest = None
    lower_t = t.lower()

    for ulke in ulkeler:
        idx = lower_t.find(ulke.lower())
        if idx > 0:
            if earliest is None or idx < earliest:
                earliest = idx

    if earliest is not None:
        t = t[:earliest].strip()

    # Markalar/Temsilcilikler ve sonrasını sil
    t = re.split(r"\bMarkalar\b|\bTemsilcilikler\b|\bTemsilci Firma\b", t, flags=re.IGNORECASE)[0].strip()

    # Gereksiz kuyruklar
    t = t.strip(" -–|•,:;")

    return t


def maktek_katilimci_listesi_cek(url, progress_callback=None):
    """
    MAKTEK Avrasya özel motoru.
    Bu site pagination'ı ?page=2 şeklinde statik verdiği için Playwright'a gerek kalmadan
    1'den son sayfaya kadar URL'leri hızlıca okur.
    """
    baslangic_zamani = time.time()
    url = normalize_url(url)

    def bildir(adim, sayfa=0, toplam=0, bulunan=0):
        if progress_callback:
            try:
                progress_callback({
                    "adim": adim,
                    "sayfa_no": sayfa,
                    "toplam_sayfa": toplam,
                    "bulunan": bulunan,
                    "gecen": time.time() - baslangic_zamani
                })
            except Exception:
                pass

    def sayfa_url_uret(base_url, page_no):
        parsed = urlparse(base_url)
        qs = parse_qs(parsed.query)
        if page_no <= 1:
            qs.pop("page", None)
        else:
            qs["page"] = [str(page_no)]
        new_query = urlencode(qs, doseq=True)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))

    def html_firmalari_cek(html):
        soup = BeautifulSoup(html or "", "html.parser")
        adaylar = []

        # En güvenilir alan: Detaylı İncele geçen linkler
        for a in soup.find_all("a"):
            txt = firma_adi_temizle(a.get_text(" "))
            if not txt:
                continue

            if ("Detaylı İncele" in txt or "Detayli Incele" in txt) and ("Salon" in txt or "Stant" in txt):
                firma = maktek_firma_adi_temizle(txt)
                if firma:
                    adaylar.append(firma)

        # Bazı HTML yapılarında metin link dışında olabilir; gövdeden fallback
        if not adaylar:
            body_text = soup.get_text("\n")
            for line in body_text.split("\n"):
                line = firma_adi_temizle(line)
                if ("Detaylı İncele" in line or "Detayli Incele" in line) and ("Salon" in line or "Stant" in line):
                    firma = maktek_firma_adi_temizle(line)
                    if firma:
                        adaylar.append(firma)

        # Filtrele
        temiz = []
        yasak = [
            "SalonNo", "StandNo", "Temsilci Firma", "Katılımcı Listesi",
            "Firmaya Mesaj Gönder", "Mesajınız", "Gönder", "Vazgeç"
        ]

        for f in adaylar:
            low = f.lower()
            if not f or len(f) < 2 or len(f) > 140:
                continue
            if any(y.lower() in low for y in yasak):
                continue
            if re.fullmatch(r"[\d\s\-\+\(\):\.]+", f):
                continue
            temiz.append(f)

        return temiz

    # İlk sayfayı oku
    firmalar = []
    ilk_url = sayfa_url_uret(url, 1)
    bildir("MAKTEK ilk sayfa okunuyor...", 1, 0, 0)

    try:
        res = guvenli_get(ilk_url, timeout=REQUEST_TIMEOUT, referer="https://www.google.com/")
        html = res.text or ""
    except Exception as e:
        raise Exception(f"MAKTEK ilk sayfa okunamadı: {str(e)}")

    # Son sayfa sayısını HTML'den bul
    toplam_sayfa = 1
    try:
        soup = BeautifulSoup(html, "html.parser")
        hrefs = " ".join([a.get("href", "") for a in soup.find_all("a", href=True)])
        nums = [int(x) for x in re.findall(r"[?&]page=(\d+)", hrefs)]
        if nums:
            toplam_sayfa = max(nums)
        else:
            body = soup.get_text(" ")
            # Sayfada 50 / 51 gibi görünen alanları da yakala
            nums2 = [int(x) for x in re.findall(r"\b([1-9]\d?)\b", body)]
            if nums2:
                toplam_sayfa = max([n for n in nums2 if n <= 80] or [1])
    except Exception:
        toplam_sayfa = 1

    # Güvenlik limiti
    toplam_sayfa = min(max(toplam_sayfa, 1), 80)

    # 1. sayfa
    sayfa_firmalari = html_firmalari_cek(html)
    firmalar.extend(sayfa_firmalari)
    bildir(f"MAKTEK sayfa 1/{toplam_sayfa} tamamlandı.", 1, toplam_sayfa, len(set([x.lower() for x in firmalar])))

    # Diğer sayfalar
    for page_no in range(2, toplam_sayfa + 1):
        try:
            bildir(f"MAKTEK sayfa {page_no}/{toplam_sayfa} okunuyor...", page_no, toplam_sayfa, len(set([x.lower() for x in firmalar])))
            page_url = sayfa_url_uret(url, page_no)
            time.sleep(random.uniform(0.25, 0.65))
            r = guvenli_get(page_url, timeout=REQUEST_TIMEOUT, referer=ilk_url)

            if r.status_code >= 400:
                continue

            page_firmalar = html_firmalari_cek(r.text or "")
            firmalar.extend(page_firmalar)

            bildir(f"MAKTEK sayfa {page_no}/{toplam_sayfa} tamamlandı.", page_no, toplam_sayfa, len(set([x.lower() for x in firmalar])))

        except Exception as e:
            logging.warning(f"MAKTEK sayfa okunamadı {page_no}: {str(e)}")
            continue

    # Mükerrer temizliği
    final = []
    seen = set()

    for f in firmalar:
        f = firma_adi_temizle(f)
        key = f.lower().strip()
        if key and key not in seen:
            seen.add(key)
            final.append(f)

    bildir("MAKTEK katılımcı çekimi tamamlandı.", toplam_sayfa, toplam_sayfa, len(final))
    return final




# ============================================================
# EVRENSEL URL MOTORLARI
# ============================================================

def url_sayfa_parametreli_mi(url):
    """
    URL'nin ?page=2 gibi sayfa parametresine uygun olup olmadığını anlamak için kullanılır.
    """
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        return "page" in qs or True
    except Exception:
        return False


def sayfa_url_uret_genel(base_url, page_no, param_name="page"):
    parsed = urlparse(base_url)
    qs = parse_qs(parsed.query)

    if page_no <= 1:
        qs.pop(param_name, None)
    else:
        qs[param_name] = [str(page_no)]

    new_query = urlencode(qs, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


def toplam_sayfa_tahmin_et(html):
    """
    HTML içinden pagination sayısını tahmin eder.
    ?page=51, Sayfa 1 / 14, pagination linkleri gibi işaretleri arar.
    """
    toplam = 1

    try:
        soup = BeautifulSoup(html or "", "html.parser")

        hrefs = " ".join([a.get("href", "") for a in soup.find_all("a", href=True)])
        nums = [int(x) for x in re.findall(r"[?&]page=(\d+)", hrefs)]
        if nums:
            toplam = max(toplam, max(nums))

        body = soup.get_text(" ")
        m = re.search(r"Sayfa\s+\d+\s*/\s*(\d+)", body, flags=re.IGNORECASE)
        if m:
            toplam = max(toplam, int(m.group(1)))

        # Pagination butonlarında yalnızca 1-80 arası makul sayıları dikkate al
        page_nums = []
        for a in soup.find_all(["a", "button"]):
            txt = firma_adi_temizle(a.get_text(" "))
            if re.fullmatch(r"\d{1,2}", txt):
                n = int(txt)
                if 1 <= n <= 80:
                    page_nums.append(n)

        if page_nums:
            toplam = max(toplam, max(page_nums))

    except Exception:
        pass

    return min(max(toplam, 1), 80)


def genel_firma_satiri_mi(text):
    """
    Genel URL motoru için firma adı olabilecek satırları seçer.
    Çok katı değil; çünkü bazı fuar sitelerinde marka adı sadece tek kelimedir.
    """
    if not text:
        return False

    t = firma_adi_temizle(text)
    low = t.lower()

    yasak = [
        "katılımcı", "katilimci", "sektör", "sektor", "şehir", "sehir",
        "sonraki", "önceki", "onceki", "next", "previous",
        "detaylı incele", "detayli incele", "firma ara", "arama",
        "salon", "stant", "stand", "hall", "booth",
        "gizlilik", "kvkk", "cookie", "iletişim", "iletisim",
        "fuar", "expo", "visitor", "exhibitor list", "download",
        "pdf", "excel", "home", "login", "register"
    ]

    if len(t) < 3 or len(t) > 130:
        return False

    if any(y in low for y in yasak):
        return False

    if re.search(r"https?://|www\.|@", low):
        return False

    if re.fullmatch(r"[\d\s\-\+\(\):\.]+", t):
        return False

    if not re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", t):
        return False

    return True


def genel_html_firma_adaylari_cek(html):
    """
    Bilinmeyen fuar siteleri için HTML'den firma adaylarını çıkarır.
    Table, card, class name, title/data-name ve link metinlerini dener.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    adaylar = []

    for tag in soup(["script", "style", "noscript", "svg", "footer", "header", "nav"]):
        tag.decompose()

    # 1) Tablolarda ilk hücre çoğu zaman firma adıdır
    for row in soup.select("table tbody tr, table tr"):
        try:
            cells = row.find_all(["td", "th"])
            if len(cells) >= 1:
                first = firma_adi_temizle(cells[0].get_text(" "))
                if genel_firma_satiri_mi(first):
                    adaylar.append(first)
        except Exception:
            continue

    # 2) Firma kartları / yaygın class isimleri
    selectors = [
        "[class*='company']", "[class*='exhibitor']", "[class*='participant']",
        "[class*='firma']", "[class*='katilimci']", "[class*='katılımcı']",
        "[class*='brand']", "[class*='name']", "[data-name]", "[data-title]",
        "h2", "h3", "h4", "a[title]", "img[alt]"
    ]

    for sel in selectors:
        try:
            for item in soup.select(sel):
                vals = [
                    item.get_text(" "),
                    item.get("title"),
                    item.get("data-title"),
                    item.get("data-name"),
                    item.get("alt")
                ]
                for v in vals:
                    v = firma_adi_temizle(v)
                    if genel_firma_satiri_mi(v):
                        adaylar.append(v)
        except Exception:
            continue

    # 3) JSON benzeri alanlar
    json_patterns = [
        r'"company"\s*:\s*"([^"]{3,120})"',
        r'"companyName"\s*:\s*"([^"]{3,120})"',
        r'"exhibitorName"\s*:\s*"([^"]{3,120})"',
        r'"name"\s*:\s*"([^"]{3,120})"',
        r'"title"\s*:\s*"([^"]{3,120})"',
    ]

    raw_html = str(html or "")
    for pattern in json_patterns:
        for match in re.findall(pattern, raw_html, flags=re.IGNORECASE):
            m = firma_adi_temizle(match)
            if genel_firma_satiri_mi(m):
                adaylar.append(m)

    # Temizle / tekilleştir
    final = []
    seen = set()
    for a in adaylar:
        a = firma_adi_temizle(a)
        key = a.lower().strip()
        if key and key not in seen:
            seen.add(key)
            final.append(a)

    return final


def genel_pagination_url_motoru(url, progress_callback=None):
    """
    Bilinmeyen ama ?page=2, ?page=3 gibi çalışan siteler için genel pagination motoru.
    MAKTEK özel motoru kadar kesin değildir ama birçok fuarda işe yarar.
    """
    baslangic_zamani = time.time()

    def bildir(adim, sayfa=0, toplam=0, bulunan=0):
        if progress_callback:
            try:
                progress_callback({
                    "adim": adim,
                    "sayfa_no": sayfa,
                    "toplam_sayfa": toplam,
                    "bulunan": bulunan,
                    "gecen": time.time() - baslangic_zamani
                })
            except Exception:
                pass

    firmalar = []
    url = normalize_url(url)

    try:
        bildir("Genel pagination motoru: ilk sayfa okunuyor...", 1, 0, 0)
        res = guvenli_get(url, timeout=REQUEST_TIMEOUT, referer="https://www.google.com/")
        if res.status_code >= 400:
            return []

        html = res.text or ""
        toplam_sayfa = toplam_sayfa_tahmin_et(html)

        # Eğer 1 sayfa görünüyorsa bu motoru zorlamaya gerek yok
        if toplam_sayfa <= 1:
            return []

        ilk_firmalar = genel_html_firma_adaylari_cek(html)
        firmalar.extend(ilk_firmalar)
        bildir(f"Genel pagination: sayfa 1/{toplam_sayfa} tamamlandı.", 1, toplam_sayfa, len(set([x.lower() for x in firmalar])))

        for page_no in range(2, toplam_sayfa + 1):
            try:
                bildir(f"Genel pagination: sayfa {page_no}/{toplam_sayfa} okunuyor...", page_no, toplam_sayfa, len(set([x.lower() for x in firmalar])))
                page_url = sayfa_url_uret_genel(url, page_no)
                time.sleep(random.uniform(0.25, 0.7))
                r = guvenli_get(page_url, timeout=REQUEST_TIMEOUT, referer=url)

                if r.status_code >= 400:
                    continue

                page_firmalar = genel_html_firma_adaylari_cek(r.text or "")

                # Eğer sayfa boşsa devam etmeyelim
                if not page_firmalar:
                    continue

                firmalar.extend(page_firmalar)
                bildir(f"Genel pagination: sayfa {page_no}/{toplam_sayfa} tamamlandı.", page_no, toplam_sayfa, len(set([x.lower() for x in firmalar])))

            except Exception as e:
                logging.warning(f"Genel pagination sayfa okunamadı {page_no}: {str(e)}")
                continue

    except Exception as e:
        logging.warning(f"Genel pagination motoru hata: {str(e)}")
        return []

    final = []
    seen = set()
    for f in firmalar:
        f = firma_adi_temizle(f)
        key = f.lower().strip()
        if key and key not in seen:
            seen.add(key)
            final.append(f)

    bildir("Genel pagination motoru tamamlandı.", 0, 0, len(final))
    return final


def genel_playwright_next_motoru(url, progress_callback=None):
    """
    Bilinmeyen JavaScript siteleri için genel Playwright next-button motoru.
    Tabloyu veya kartları okur, Sonraki/Next butonuna basmayı dener.
    """
    if not PLAYWRIGHT_AKTIF:
        return []

    baslangic_zamani = time.time()

    def bildir(adim, sayfa=0, toplam=0, bulunan=0):
        if progress_callback:
            try:
                progress_callback({
                    "adim": adim,
                    "sayfa_no": sayfa,
                    "toplam_sayfa": toplam,
                    "bulunan": bulunan,
                    "gecen": time.time() - baslangic_zamani
                })
            except Exception:
                pass

    firmalar = []
    url = normalize_url(url)

    try:
        bildir("Genel JavaScript motoru: tarayıcı açılıyor...", 0, 0, 0)

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled"
                ]
            )

            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
                viewport={"width": 1450, "height": 950},
                locale="tr-TR"
            )

            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(6000)

            toplam_sayfa = 20
            try:
                body_text = page.inner_text("body")
                m = re.search(r"Sayfa\s+\d+\s*/\s*(\d+)", body_text, flags=re.IGNORECASE)
                if m:
                    toplam_sayfa = int(m.group(1))
            except Exception:
                pass

            toplam_sayfa = min(max(toplam_sayfa, 1), 40)

            for sayfa_no in range(1, toplam_sayfa + 1):
                bildir(f"Genel JS motoru: sayfa {sayfa_no}/{toplam_sayfa} okunuyor...", sayfa_no, toplam_sayfa, len(set([x.lower() for x in firmalar])))

                page.wait_for_timeout(1500)

                # Scroll ederek görünür alanı genişlet
                for _ in range(6):
                    try:
                        html = page.content()
                        page_firmalar = genel_html_firma_adaylari_cek(html)
                        firmalar.extend(page_firmalar)

                        page.evaluate("""
                            () => {
                                const all = Array.from(document.querySelectorAll('*'));
                                for (const el of all) {
                                    try {
                                        if (el.scrollHeight > el.clientHeight + 10) {
                                            el.scrollTop = el.scrollTop + Math.floor(el.clientHeight * 0.8);
                                        }
                                    } catch(e) {}
                                }
                                window.scrollBy(0, 600);
                            }
                        """)
                    except Exception:
                        pass
                    page.wait_for_timeout(700)

                if sayfa_no >= toplam_sayfa:
                    break

                # Sonraki butonu
                clicked = False
                try:
                    clicked = page.evaluate("""
                        () => {
                            const els = Array.from(document.querySelectorAll('button, a'));
                            const btn = els.find(el => {
                                const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                                const disabled = el.disabled === true || el.getAttribute('disabled') !== null || el.getAttribute('aria-disabled') === 'true';
                                return !disabled && (txt.includes('sonraki') || txt.includes('next'));
                            });
                            if (btn) {
                                btn.scrollIntoView({block:'center'});
                                btn.click();
                                return true;
                            }
                            return false;
                        }
                    """)
                except Exception:
                    clicked = False

                if not clicked:
                    break

                page.wait_for_timeout(2500)

            browser.close()

    except Exception as e:
        logging.warning(f"Genel Playwright next motoru hata: {str(e)}")
        return []

    final = []
    seen = set()
    for f in firmalar:
        f = firma_adi_temizle(f)
        key = f.lower().strip()
        if key and key not in seen:
            seen.add(key)
            final.append(f)

    bildir("Genel JavaScript motoru tamamlandı.", 0, 0, len(final))
    return final


def evrensel_url_firma_cek(url, progress_callback=None):
    """
    Tüm URL firma çekme motorlarını tek yerde yöneten ana akış.
    Yeni site geldiğinde ana panel bozulmaz; buraya yeni adaptör eklenir.
    """
    url_l = (url or "").lower()
    firmalar = []

    # 1) Bilinen adaptörler
    if "musiadexpo.com" in url_l:
        if progress_callback:
            progress_callback({"adim": "MÜSİAD adaptörü seçildi.", "sayfa_no": 0, "toplam_sayfa": 0, "bulunan": 0, "gecen": 0})
        firmalar = musiad_katilimci_listesi_cek(url, progress_callback=progress_callback)

    elif "maktekfuari.com" in url_l:
        if progress_callback:
            progress_callback({"adim": "MAKTEK adaptörü seçildi.", "sayfa_no": 0, "toplam_sayfa": 0, "bulunan": 0, "gecen": 0})
        firmalar = maktek_katilimci_listesi_cek(url, progress_callback=progress_callback)

    # 2) Genel pagination motoru
    if not firmalar:
        if progress_callback:
            progress_callback({"adim": "Genel pagination motoru deneniyor...", "sayfa_no": 0, "toplam_sayfa": 0, "bulunan": 0, "gecen": 0})
        firmalar = genel_pagination_url_motoru(url, progress_callback=progress_callback)

    # 3) Genel statik HTML motoru
    if not firmalar:
        if progress_callback:
            progress_callback({"adim": "Genel statik HTML motoru deneniyor...", "sayfa_no": 0, "toplam_sayfa": 0, "bulunan": 0, "gecen": 0})
        firmalar = firmalari_url_den_cek(url)

    # 4) Genel JavaScript / Next button motoru
    if not firmalar:
        if progress_callback:
            progress_callback({"adim": "Genel JavaScript motoru deneniyor...", "sayfa_no": 0, "toplam_sayfa": 0, "bulunan": 0, "gecen": 0})
        firmalar = genel_playwright_next_motoru(url, progress_callback=progress_callback)

    # 5) Son fallback: eski Playwright selector motoru
    if not firmalar:
        if progress_callback:
            progress_callback({"adim": "Son fallback tarayıcı motoru deneniyor...", "sayfa_no": 0, "toplam_sayfa": 0, "bulunan": 0, "gecen": 0})
        firmalar = firmalari_url_den_cek_playwright(url)

    # Son temizlik
    final = []
    seen = set()
    for f in firmalar:
        f = firma_adi_temizle(f)
        key = f.lower().strip()
        if key and key not in seen:
            seen.add(key)
            final.append(f)

    return final



# ============================================================
# URL'DEN FIRMA CEKME
# ============================================================

def firmalari_url_den_cek(url):
    url = normalize_url(url)
    res = guvenli_get(url, timeout=25, referer="https://www.google.com/")

    if res.status_code >= 400:
        raise Exception(f"HTTP {res.status_code} hatasi alindi.")

    html = res.text
    soup = BeautifulSoup(html, "html.parser")

    adaylar = []

    for tag in soup(["script", "style", "noscript", "svg", "footer", "header", "nav"]):
        tag.decompose()

    selectorler = [
        "a", "h1", "h2", "h3", "h4",
        ".exhibitor", ".exhibitor-name", ".company", ".company-name",
        ".firma", ".firma-adi", ".katilimci", ".katilimci-adi",
        "[class*='exhibitor']", "[class*='company']", "[class*='firma']",
        "[class*='katilimci']", "[title]", "[data-title]", "[data-name]"
    ]

    for sel in selectorler:
        try:
            for item in soup.select(sel):
                texts = [
                    item.get_text(" "),
                    item.get("title"),
                    item.get("data-title"),
                    item.get("data-name"),
                    item.get("alt"),
                ]
                for t in texts:
                    temiz = firma_adi_temizle(t)
                    if temiz:
                        adaylar.append(temiz)
        except Exception:
            continue

    json_patterns = [
        r'"company"\s*:\s*"([^"]{3,100})"',
        r'"companyName"\s*:\s*"([^"]{3,100})"',
        r'"name"\s*:\s*"([^"]{3,100})"',
        r'"title"\s*:\s*"([^"]{3,100})"',
        r'"firma"\s*:\s*"([^"]{3,100})"',
    ]

    for pattern in json_patterns:
        for match in re.findall(pattern, html, flags=re.IGNORECASE):
            adaylar.append(firma_adi_temizle(match))

    # Statik HTML metninde firma unvani gibi gorunen satirlari da al
    page_text = soup.get_text("\n")
    for line in page_text.split("\n"):
        temiz = firma_adi_temizle(line)
        if firma_gibi_gorunuyor_mu(temiz):
            adaylar.append(temiz)

    return url_firma_sonuclarini_temizle(adaylar)


def firmalari_url_den_cek_playwright(url):
    if not PLAYWRIGHT_AKTIF:
        raise Exception("Playwright kurulu degil veya aktif degil.")

    url = normalize_url(url)
    adaylar = []

    durum_bildir("Tarayıcı başlatılıyor...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled"
            ]
        )

        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="tr-TR"
        )

        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)

        for _ in range(6):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(1200)

        html = page.content()
        text = page.inner_text("body")

        browser.close()

    soup = BeautifulSoup(html, "html.parser")

    selectorler = [
        "a", "h1", "h2", "h3", "h4", "h5",
        "[class*='exhibitor']", "[class*='company']", "[class*='firma']",
        "[class*='katilimci']", "[class*='katılımcı']", "[class*='participant']",
        "[class*='brand']", "[class*='card']", "[class*='name']",
        "[title]", "[data-title]", "[data-name]", "img[alt]"
    ]

    for sel in selectorler:
        try:
            for item in soup.select(sel):
                texts = [
                    item.get_text(" "),
                    item.get("title"),
                    item.get("data-title"),
                    item.get("data-name"),
                    item.get("alt"),
                ]
                for t in texts:
                    temiz = firma_adi_temizle(t)
                    if temiz:
                        adaylar.append(temiz)
        except Exception:
            continue

    # Body text komple firma sayilmaz.
    # Sadece sirket unvani gibi gorunen satirlar adaylara eklenir.
    for line in text.split("\n"):
        temiz = firma_adi_temizle(line)
        if firma_gibi_gorunuyor_mu(temiz):
            adaylar.append(temiz)

    return url_firma_sonuclarini_temizle(adaylar)


# ============================================================
# WEBSITE BULMA VE ILETISIM CEKME
# ============================================================

def arama_linkini_temizle(href):
    """
    Bing / DuckDuckGo arama sonucu linklerini gerçek web sitesine çevirir.
    Bing bazen /ck/a?...&u=a1aHR0cHM... şeklinde base64 benzeri link verir.
    DuckDuckGo ise uddg parametresinde gerçek URL taşır.
    """
    if not href:
        return ""

    href = str(href).strip()

    if href.lower().startswith(("javascript:", "mailto:", "tel:", "#", "data:", "about:")):
        return ""

    if "javascript:void" in href.lower():
        return ""

    # DuckDuckGo yönlendirme çöz
    if "uddg=" in href:
        try:
            parsed = urlparse(href)
            qs = parse_qs(parsed.query)
            if "uddg" in qs:
                return unquote(qs["uddg"][0])
        except Exception:
            return ""

    # Bing /ck/a yönlendirme çöz
    if href.startswith("/ck/a") or "bing.com/ck/a" in href:
        try:
            parsed = urlparse(href)
            qs = parse_qs(parsed.query)
            u = qs.get("u", [""])[0]

            if u:
                # Bing genellikle a1 + base64url şeklinde verir
                if u.startswith("a1"):
                    encoded = u[2:]
                    padding = "=" * (-len(encoded) % 4)
                    try:
                        import base64
                        decoded = base64.urlsafe_b64decode(encoded + padding).decode("utf-8", errors="ignore")
                        if decoded.startswith("http"):
                            return decoded
                    except Exception:
                        pass

                # Bazen düz URL encode olur
                u2 = unquote(u)
                if u2.startswith("http"):
                    return u2
        except Exception:
            return ""

    # Bing bazen tam link yerine /url?q= benzeri verebilir
    if "url=" in href or "q=" in href:
        try:
            parsed = urlparse(href)
            qs = parse_qs(parsed.query)
            for key in ["url", "q"]:
                val = qs.get(key, [""])[0]
                val = unquote(val)
                if val.startswith("http"):
                    return val
        except Exception:
            pass

    return href




def turkce_karakter_temizle(text):
    if not text:
        return ""
    tr_map = str.maketrans({
        "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
        "Ç": "c", "Ğ": "g", "İ": "i", "I": "i", "Ö": "o", "Ş": "s", "Ü": "u"
    })
    return text.translate(tr_map)


def firma_adi_sadelestir(firma_adi):
    """
    Firma adını arama motoru ve domain tahmini için sadeleştirir.
    Örn:
    ALSER TEKNOLOJI SAN CE TIC LTD ŞTİ -> alser teknoloji
    AKÇIR GIDA TARIM SAN TIC LTD ŞTİ -> akcir gida tarim
    """
    text = firma_adi_temizle(firma_adi)
    text = turkce_karakter_temizle(text).lower()

    # HTML/OCR kaynaklı bozukluklar
    text = text.replace(" ce tic ", " ve tic ")
    text = text.replace(" san ce tic ", " san ve tic ")
    text = text.replace(" san ve tic ", " ")
    text = text.replace(" san tic ", " ")
    text = text.replace(" ve san ", " ")
    text = text.replace(" ve tic ", " ")

    # Şirket unvanları ve çok genel kelimeler
    stop_words = [
        "a.s", "as", "aş", "anonim", "sirketi", "sirket", "limited", "ltd", "sti", "şti",
        "sanayi", "san", "ticaret", "tic", "ve", "ile", "imalat", "ithalat", "ihracat",
        "pazarlama", "dis", "dıs", "dış", "ic", "iç", "urunleri", "ürünleri"
    ]

    text = re.sub(r"[^a-z0-9\s]", " ", text)
    words = [w.strip() for w in text.split() if w.strip()]

    # Önce stop words çıkartılmış marka kökü
    marka_words = [w for w in words if w not in stop_words and len(w) > 1]

    # Eğer hepsi silindiyse ilk kelimeleri kullan
    if not marka_words:
        marka_words = [w for w in words if len(w) > 1]

    return marka_words


def firma_arama_sorgulari_uret(firma_adi):
    important_words = firma_onemli_kelimeleri(firma_adi)
    original = firma_adi_temizle(firma_adi)

    sorgular = []

    if original:
        sorgular.extend([
            f'"{original}"',
            f'"{original}" iletişim',
            f'"{original}" resmi web sitesi',
        ])

    if important_words:
        marka1 = important_words[0]
        marka2 = " ".join(important_words[:2])
        marka3 = " ".join(important_words[:3])

        # Öncelik çok kelimeli sorgularda: ABBA TEKNOLOJI gibi
        for q in [marka3, marka2, marka1]:
            if q:
                sorgular.extend([
                    f'"{q}" resmi web sitesi',
                    f'"{q}" iletişim',
                    f'{q} site:com.tr',
                    f'{q} official website',
                    f'{q} firma'
                ])

        # Domain kombinasyon sorgusu
        if len(important_words) >= 2:
            combo = important_words[0] + important_words[1]
            sorgular.extend([
                f'{combo}',
                f'{combo} iletişim',
                f'{combo} web sitesi'
            ])

    final = []
    seen = set()
    for q in sorgular:
        k = q.lower().strip()
        if k and k not in seen:
            seen.add(k)
            final.append(q)

    return final[:14]


def domain_adaylari_uret(firma_adi):
    words = firma_onemli_kelimeleri(firma_adi)

    aday_kokler = []

    if words:
        # En doğru adaylar: marka + ayırt edici ikinci kelime
        if len(words) >= 2:
            aday_kokler.append(words[0] + words[1])
            aday_kokler.append(words[0] + "-" + words[1])
        if len(words) >= 3:
            aday_kokler.append(words[0] + words[1] + words[2])
            aday_kokler.append(words[0] + "-" + words[1] + "-" + words[2])

        # Sonra tek marka
        aday_kokler.append(words[0])

        # İlk kelime + diğer sektör/ayırt edici kelimeler
        for w in words[1:5]:
            aday_kokler.append(words[0] + w)
            aday_kokler.append(words[0] + "-" + w)

    clean_roots = []
    seen = set()
    for root in aday_kokler:
        root = re.sub(r"[^a-z0-9-]", "", root)
        if len(root) >= 3 and root not in seen:
            seen.add(root)
            clean_roots.append(root)

    # Türkiye için com.tr önce, sonra com
    tlds = [".com.tr", ".com", ".net", ".com.tr/iletisim", ".com/iletisim", ".com.tr/contact", ".com/contact"]

    adaylar = []
    for root in clean_roots:
        for tld in tlds:
            adaylar.append(f"https://www.{root}{tld}")
            adaylar.append(f"https://{root}{tld}")

    return adaylar[:50]


def web_sitesi_dogrula(url):
    """
    Aday web sitesini hızlı kontrol eder.
    """
    try:
        if not url_gecerli_mi(url):
            return False

        r = guvenli_get(url, timeout=8, referer="https://www.google.com/")

        if r.status_code >= 400:
            return False

        text = (r.text or "")[:5000].lower()

        # Çok bariz parking/satılık sayfaları ele
        kotu = [
            "domain is for sale", "buy this domain", "parked domain",
            "this domain may be for sale", "godaddy", "sedo.com"
        ]
        if any(k in text for k in kotu):
            return False

        return True

    except Exception:
        return False


def playwright_arama_linkleri_bul(query):
    """
    Requests ile arama sonuçları zayıf kalırsa Playwright ile DuckDuckGo HTML araması yapar.
    """
    if not PLAYWRIGHT_AKTIF:
        return []

    linkler = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled"
                ]
            )

            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
                viewport={"width": 1300, "height": 900},
                locale="tr-TR"
            )

            url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)

            hrefs = page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href]'))
                    .map(a => a.getAttribute('href'))
                    .filter(Boolean)
                    .slice(0, 80)
            """)

            browser.close()

        for href in hrefs:
            clean = arama_linkini_temizle(href)
            clean = normalize_url(clean)

            if url_gecerli_mi(clean) and not istenmeyen_link_mi(clean):
                linkler.append(clean)

    except Exception as e:
        logging.warning(f"Playwright arama hatasi: {query} - {str(e)}")

    # Domain tekilleştir
    final = []
    seen = set()
    for l in linkler:
        d = domain_al(l)
        if d and d not in seen:
            seen.add(d)
            final.append(l)

    return final[:5]




def firma_kelime_seti(firma_adi):
    words = firma_adi_sadelestir(firma_adi)
    return set([w for w in words if len(w) >= 3])



def firma_onemli_kelimeleri(firma_adi):
    """
    Domain doğrulamada kullanılır.
    Şirket unvanlarını atar ama teknoloji/yazılım/makine/gıda gibi ayırt edici kelimeleri korur.
    """
    text = firma_adi_temizle(firma_adi)
    text = turkce_karakter_temizle(text).lower()
    text = text.replace(" ce tic ", " ve tic ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)

    stop = {
        "a", "s", "as", "aş", "anonim", "sirket", "sirketi", "limited",
        "ltd", "sti", "şti", "sanayi", "san", "ticaret", "tic", "ve",
        "ile", "hizmetleri", "hizmet", "ltdsti", "ltdşti"
    }

    words = [w for w in text.split() if len(w) >= 3 and w not in stop]

    # Mükerrerleri koruyarak temizle
    final = []
    seen = set()
    for w in words:
        if w not in seen:
            seen.add(w)
            final.append(w)

    return final


def domain_firma_eslesme_skoru(url, firma_adi, page_text=""):
    """
    ABBA örneği gibi kısa marka yanılmalarını engeller.
    Domain sadece ilk kelimeyi içeriyor ama ikinci/üçüncü ayırt edici kelimeyi içermiyorsa cezalandırır.
    """
    domain = domain_al(url)
    if not domain:
        return -100

    domain_clean = turkce_karakter_temizle(domain.lower())
    domain_root = domain_clean.replace("www.", "")
    domain_root = re.sub(r"\.(com\.tr|com|net|org|tr|co|io|de|it|cn|uk)$", "", domain_root)

    page_low = turkce_karakter_temizle((page_text or "").lower()[:10000])
    words = firma_onemli_kelimeleri(firma_adi)

    if not words:
        return 0

    score = 0
    domain_matches = []
    text_matches = []

    for w in words:
        if w in domain_root:
            domain_matches.append(w)
            score += 40
        if w in page_low:
            text_matches.append(w)
            score += 8

    # İlk marka kelimesi + ikinci ayırt edici kelime domain içinde beraber geçerse çok güçlü sinyal
    if len(words) >= 2:
        first, second = words[0], words[1]
        if first in domain_root and second in domain_root:
            score += 65

        # İlk kelime var ama ikinci/üçüncü kelimeden hiçbiri yoksa kısa marka yanılması olabilir
        other_words = words[1:4]
        if first in domain_root and not any(w in domain_root for w in other_words):
            # Domain çok kısa ise daha sert ceza: abba.com gibi
            if len(domain_root.replace("-", "")) <= len(first) + 2:
                score -= 55
            else:
                score -= 25

    # Domain, ilk iki kelimenin bitişik kombinasyonunu içeriyorsa güçlü sinyal: abbateknoloji
    if len(words) >= 2:
        combo = words[0] + words[1]
        if combo in domain_root.replace("-", ""):
            score += 90

    # İlk üç kombinasyon
    if len(words) >= 3:
        combo3 = words[0] + words[1] + words[2]
        if combo3 in domain_root.replace("-", ""):
            score += 50

    # Sayfa içinde tam firma kelimesi/önemli kelime yoğunluğu
    if len(text_matches) >= 2:
        score += 20
    if len(domain_matches) >= 2:
        score += 35

    # Çok kısa global domainler için güvenlik
    generic_risk_domains = {
        "abba.com", "abc.com", "mega.com", "star.com", "best.com", "global.com"
    }
    if domain in generic_risk_domains and len(words) >= 2:
        score -= 80

    return score



def domain_puanla(url, firma_adi, page_text=""):
    """
    Aday web sitesini firma adına göre puanlar.
    V5.4:
    - Tek kelimelik marka yanılmalarını azaltır.
    - ABBA -> abba.com yerine abbateknoloji.com gibi çok kelimeli eşleşmeleri öne çıkarır.
    """
    try:
        domain = domain_al(url)
        if not domain:
            return -100

        low_domain = turkce_karakter_temizle(domain.lower())
        low_text = turkce_karakter_temizle((page_text or "").lower()[:10000])
        words = firma_onemli_kelimeleri(firma_adi)

        puan = 0

        if istenmeyen_link_mi(url):
            return -100

        # Çok kelimeli firma-domain eşleşme skoru
        puan += domain_firma_eslesme_skoru(url, firma_adi, page_text)

        # Türkiye firmaları için com.tr güçlü sinyal
        if domain.endswith(".com.tr"):
            puan += 22
        elif domain.endswith(".com"):
            puan += 8
        elif domain.endswith(".net") or domain.endswith(".org"):
            puan += 4

        # İletişim sayfası veya kurumsal sayfa pozitif
        if any(x in url.lower() for x in ["iletisim", "iletişim", "contact", "kurumsal", "about"]):
            puan += 8

        # Domain içinde tek başına sadece ilk kelime varsa dikkatli ol
        if len(words) >= 2:
            root = low_domain.replace("www.", "")
            root = re.sub(r"\.(com\.tr|com|net|org|tr|co|io|de|it|cn|uk)$", "", root)
            if words[0] in root and not any(w in root for w in words[1:4]):
                # Sayfa içeriği de ikinci kelimeyi desteklemiyorsa ciddi ceza
                if not any(w in low_text for w in words[1:4]):
                    puan -= 45

        # Çok uzun, takip parametreli, haber/rehber gibi siteler negatif
        if len(url) > 130:
            puan -= 8
        if any(x in url.lower() for x in ["haber", "news", "firma-rehberi", "yellow", "rehber", "directory", "blog"]):
            puan -= 18

        # Sayfa içinde iletişim sinyalleri
        if any(x in low_text for x in ["iletisim", "iletişim", "contact", "e-posta", "email", "telefon"]):
            puan += 10

        return puan

    except Exception:
        return -100


def aday_site_oku_ve_puanla(url, firma_adi):
    """
    Aday siteyi hızlı okur, parking/boş sayfa değilse puan döner.
    """
    try:
        if not url_gecerli_mi(url):
            return {"url": url, "puan": -100, "text": ""}

        r = guvenli_get(url, timeout=8, referer="https://www.google.com/")
        if r.status_code >= 400:
            return {"url": url, "puan": -50, "text": ""}

        html = r.text or ""
        text = temiz_metin(html)

        bad = [
            "domain is for sale", "buy this domain", "parked domain",
            "this domain may be for sale", "sedo.com", "godaddy"
        ]
        if any(b in html.lower() for b in bad):
            return {"url": url, "puan": -100, "text": text}

        puan = domain_puanla(url, firma_adi, text)
        return {"url": url, "puan": puan, "text": text}

    except Exception:
        return {"url": url, "puan": -30, "text": ""}


def en_iyi_websitesini_sec(linkler, firma_adi):
    """
    Link listesinden en doğru web sitesini seçer.
    """
    if not linkler:
        return ""

    # Domain tekilleştir
    temiz = []
    seen = set()
    for link in linkler:
        link = normalize_url(link)
        if not url_gecerli_mi(link):
            continue
        if istenmeyen_link_mi(link):
            continue
        d = domain_al(link)
        if not d or d in seen:
            continue
        seen.add(d)
        temiz.append(link)

    if not temiz:
        return ""

    sonuclar = []
    # İlk 8 adayı kontrol et; fazla kontrol yavaşlatır
    for link in temiz[:8]:
        sonuclar.append(aday_site_oku_ve_puanla(link, firma_adi))

    sonuclar = sorted(sonuclar, key=lambda x: x["puan"], reverse=True)

    if sonuclar and sonuclar[0]["puan"] >= 15:
        return sonuclar[0]["url"]

    # Puan düşükse yine de en iyi com.tr/com adayını döndür
    for s in sonuclar:
        d = domain_al(s["url"])
        if d.endswith(".com.tr") and s["puan"] >= 5:
            return s["url"]

    if sonuclar and sonuclar[0]["puan"] > 0:
        return sonuclar[0]["url"]

    return ""


def metinden_obfuscated_email_temizle(text):
    """
    info [at] domain [dot] com gibi yazılmış e-postaları yakalamaya çalışır.
    """
    if not text:
        return ""

    t = text
    t = re.sub(r"\s*\[\s*at\s*\]\s*", "@", t, flags=re.I)
    t = re.sub(r"\s*\(\s*at\s*\)\s*", "@", t, flags=re.I)
    t = re.sub(r"\s+at\s+", "@", t, flags=re.I)
    t = re.sub(r"\s*\[\s*dot\s*\]\s*", ".", t, flags=re.I)
    t = re.sub(r"\s*\(\s*dot\s*\)\s*", ".", t, flags=re.I)
    t = re.sub(r"\s+dot\s+", ".", t, flags=re.I)
    return t


def mailto_ve_tel_linklerini_ayikla(html):
    mailler = []
    telefonlar = []

    try:
        soup = BeautifulSoup(html or "", "html.parser")
        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()

            if href.lower().startswith("mailto:"):
                mail = href.split(":", 1)[1].split("?")[0].strip()
                if mail:
                    mailler.append(mail)

            if href.lower().startswith("tel:"):
                tel = href.split(":", 1)[1].strip()
                if tel:
                    telefonlar.append(tel)

    except Exception:
        pass

    return mailler, telefonlar


def temiz_mail_listesi(mailler):
    final = []
    yasakli = [
        "example.com", "domain.com", "email.com", "sentry.", "wixpress.",
        "schema.org", "wordpress.org", "yoursite", "yourdomain"
    ]

    for m in mailler:
        m = str(m).strip().lower()
        m = m.replace("mailto:", "").split("?")[0]
        m = re.sub(r"^[^a-z0-9]+|[^a-z0-9.]+$", "", m)

        if not re.fullmatch(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", m):
            continue
        if any(y in m for y in yasakli):
            continue
        if m not in final:
            final.append(m)

    # İşe yarar mailler öne gelsin
    oncelik = ["info@", "sales@", "export@", "contact@", "iletisim@", "muhasebe@", "marketing@"]
    final = sorted(final, key=lambda x: 0 if any(x.startswith(o) for o in oncelik) else 1)

    return final[:8]


def temiz_telefon_listesi(telefonlar):
    final = []

    for tel in telefonlar:
        tel = str(tel).strip()
        tel = tel.replace("tel:", "")
        tel = re.sub(r"\s+", " ", tel)
        rakam = re.sub(r"\D", "", tel)

        if len(rakam) < 10 or len(rakam) > 15:
            continue

        # Çok tekrar eden saçma numaraları ele
        if len(set(rakam)) <= 2:
            continue

        if tel not in final:
            final.append(tel)

    return final[:8]


def iletisim_linki_oncelik_puani(url):
    low = url.lower()
    puan = 0
    if "iletisim" in low or "iletişim" in low:
        puan += 50
    if "contact" in low:
        puan += 45
    if "bize-ulasin" in low or "bize-ulaşın" in low:
        puan += 40
    if "kurumsal" in low or "about" in low:
        puan += 15
    return puan


def firma_websitesi_bul(firma_adi):
    """
    Firma adından resmi web sitesini bulmaya çalışır.
    V5.0:
    - Arama sorgularını sade firma kökleriyle üretir.
    - Bing/DuckDuckGo linklerini çözer.
    - Aday web sitelerini firma adıyla puanlar.
    - En doğru domaini seçmeye çalışır.
    """
    firma_adi_temiz = firma_adi_temizle(firma_adi)
    sorgular = firma_arama_sorgulari_uret(firma_adi_temiz)[:SEARCH_QUERY_LIMIT]

    bulunan_linkler = []

    for sorgu_text in sorgular:
        arama_url_listesi = [
            f"https://www.bing.com/search?q={quote_plus(sorgu_text)}",
            f"https://duckduckgo.com/html/?q={quote_plus(sorgu_text)}"
        ]

        for arama_url in arama_url_listesi:
            try:
                time.sleep(random.uniform(0.5, 1.1))
                res = guvenli_get(arama_url, timeout=REQUEST_TIMEOUT, referer="https://www.google.com/")

                if res.status_code >= 400:
                    continue

                soup = BeautifulSoup(res.text, "html.parser")

                for a in soup.select("li.b_algo h2 a[href], h2 a[href], a.result__a[href], a[href]"):
                    href_raw = a.get("href", "").strip()
                    href = arama_linkini_temizle(href_raw)
                    href = normalize_url(href)

                    if not url_gecerli_mi(href):
                        continue
                    if istenmeyen_link_mi(href):
                        continue
                    if any(href.lower().endswith(ext) for ext in [".pdf", ".jpg", ".jpeg", ".png", ".webp", ".gif", ".doc", ".docx", ".xls", ".xlsx"]):
                        continue

                    bulunan_linkler.append(href)

            except Exception as e:
                logging.warning(f"Arama hatasi: {firma_adi_temiz} - {str(e)}")
                continue

        # İlk 2 sorgudan yeterli aday çıktıysa seçime geç
        if len(set([domain_al(x) for x in bulunan_linkler if domain_al(x)])) >= 4:
            break

    # Requests sonuç vermezse Playwright fallback sadece derin modda çalışır
    if not bulunan_linkler and PLAYWRIGHT_FALLBACK_ENABLED:
        for sorgu_text in sorgular[:max(1, min(3, SEARCH_QUERY_LIMIT))]:
            bulunan_linkler.extend(playwright_arama_linkleri_bul(sorgu_text))
            if bulunan_linkler:
                break

    secilen = en_iyi_websitesini_sec(bulunan_linkler, firma_adi_temiz)
    if secilen:
        return secilen

    # Son çare domain tahmini
    domain_adaylari = domain_adaylari_uret(firma_adi_temiz)
    dogrulanan = []

    for aday in domain_adaylari[:20]:
        sonuc = aday_site_oku_ve_puanla(aday, firma_adi_temiz)
        if sonuc["puan"] >= 8:
            dogrulanan.append(sonuc)

    if dogrulanan:
        dogrulanan = sorted(dogrulanan, key=lambda x: x["puan"], reverse=True)
        return dogrulanan[0]["url"]

    return ""


def eposta_ayikla(text):
    if not text:
        return []

    text = metinden_obfuscated_email_temizle(text)

    mailler = re.findall(
        r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
        text
    )

    return temiz_mail_listesi(mailler)


def telefon_ayikla(text):
    if not text:
        return []

    text = text.replace("&nbsp;", " ")

    patternler = [
        r"\+90[\s\-\.]?\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{2}[\s\-\.]?\d{2}",
        r"0[\s\-\.]?\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{2}[\s\-\.]?\d{2}",
        r"\+\d{1,3}[\s\-\.]?\(?\d{2,4}\)?[\s\-\.]?\d{3,4}[\s\-\.]?\d{2,4}[\s\-\.]?\d{2,4}",
        r"\(\d{3}\)\s*\d{3}[\s\-\.]?\d{2}[\s\-\.]?\d{2}",
    ]

    telefonlar = []
    for p in patternler:
        telefonlar.extend(re.findall(p, text))

    return temiz_telefon_listesi(telefonlar)


def iletisim_sayfasi_linkleri_bul(base_url, html):
    soup = BeautifulSoup(html or "", "html.parser")
    adaylar = []

    anahtarlar = [
        "contact", "contact-us", "contacts", "iletisim", "iletişim",
        "bize-ulasin", "bize-ulaşın", "kurumsal", "about", "about-us",
        "communication", "reach-us", "support"
    ]

    for a in soup.find_all("a", href=True):
        text = temiz_metin(a.get_text(" ")).lower()
        href_raw = a.get("href", "")
        href = href_raw.lower()

        if any(k in text or k in href for k in anahtarlar):
            full = normalize_url(href_raw, base_url=base_url)
            if url_gecerli_mi(full):
                adaylar.append(full)

    # Standart olası iletişim URL'lerini de dene
    standart_yollar = [
        "/iletisim", "/iletişim", "/contact", "/contact-us",
        "/kurumsal", "/hakkimizda", "/hakkımızda", "/about", "/about-us"
    ]

    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"

    for yol in standart_yollar:
        adaylar.append(root + yol)

    adaylar = list(dict.fromkeys(adaylar))
    adaylar = sorted(adaylar, key=iletisim_linki_oncelik_puani, reverse=True)

    return adaylar[:8]


def websitesinden_iletisim_bul(web_url):
    sonuc = {
        "web_adresi": web_url or "Bulunamadi",
        "telefon": "Bulunamadi",
        "eposta": "Bulunamadi",
        "kaynak": "",
        "durum": "Basladi",
        "hata": ""
    }

    if not web_url:
        sonuc["durum"] = "Web sitesi bulunamadi"
        return sonuc

    web_url = normalize_url(web_url)

    try:
        time.sleep(random.uniform(0.4, 1.0))
        res = guvenli_get(web_url, timeout=REQUEST_TIMEOUT, referer="https://www.google.com/")
        html = res.text or ""
        text = temiz_metin(html)

        mailto_mailler, tel_linkleri = mailto_ve_tel_linklerini_ayikla(html)

        mailler = []
        telefonlar = []

        mailler.extend(mailto_mailler)
        mailler.extend(eposta_ayikla(html + " " + text))

        telefonlar.extend(tel_linkleri)
        telefonlar.extend(telefon_ayikla(html + " " + text))

        kaynak = web_url

        # Ana sayfada eksik varsa iletişim/kurumsal sayfaları tara
        if not temiz_mail_listesi(mailler) or not temiz_telefon_listesi(telefonlar):
            for contact_url in iletisim_sayfasi_linkleri_bul(web_url, html):
                try:
                    time.sleep(random.uniform(0.3, 0.9))
                    c_res = guvenli_get(contact_url, timeout=REQUEST_TIMEOUT, referer=web_url)

                    if c_res.status_code >= 400:
                        continue

                    c_html = c_res.text or ""
                    c_text = temiz_metin(c_html)

                    c_mailto, c_tel_links = mailto_ve_tel_linklerini_ayikla(c_html)

                    mailler.extend(c_mailto)
                    mailler.extend(eposta_ayikla(c_html + " " + c_text))

                    telefonlar.extend(c_tel_links)
                    telefonlar.extend(telefon_ayikla(c_html + " " + c_text))

                    if temiz_mail_listesi(mailler) or temiz_telefon_listesi(telefonlar):
                        kaynak = contact_url

                    if temiz_mail_listesi(mailler) and temiz_telefon_listesi(telefonlar):
                        break

                except Exception as e:
                    logging.warning(f"Iletisim sayfasi okunamadi: {contact_url} - {str(e)}")
                    continue

        temiz_mailler = temiz_mail_listesi(mailler)
        temiz_telefonlar = temiz_telefon_listesi(telefonlar)

        if temiz_mailler:
            sonuc["eposta"] = ", ".join(temiz_mailler)
        if temiz_telefonlar:
            sonuc["telefon"] = ", ".join(temiz_telefonlar)

        sonuc["kaynak"] = kaynak
        sonuc["durum"] = "Tamamlandi"

        if sonuc["eposta"] == "Bulunamadi" and sonuc["telefon"] == "Bulunamadi":
            sonuc["durum"] = "Web bulundu, iletisim bulunamadi"

    except Exception as e:
        sonuc["durum"] = "Hata"
        sonuc["hata"] = str(e)
        logging.error(f"Site iletisim hatasi: {web_url} - {str(e)}")

    return sonuc


def derin_bilgi_bul(firma_adi):
    sonuc = {
        "firma_adi": firma_adi,
        "web_adresi": "Bulunamadi",
        "telefon": "Bulunamadi",
        "eposta": "Bulunamadi",
        "kaynak": "",
        "durum": "",
        "hata": ""
    }

    try:
        time.sleep(random.uniform(1.0, 2.5))

        cache_key = firma_adi.lower().strip()
        if cache_key in WEBSITE_CACHE:
            web = WEBSITE_CACHE[cache_key]
        else:
            web = firma_websitesi_bul(firma_adi)
            WEBSITE_CACHE[cache_key] = web

        if not web:
            sonuc["durum"] = "Web sitesi bulunamadi"
            return sonuc

        iletisim = websitesinden_iletisim_bul(web)

        sonuc.update(iletisim)
        sonuc["firma_adi"] = firma_adi

        return sonuc

    except Exception as e:
        sonuc["durum"] = "Hata"
        sonuc["hata"] = str(e)
        logging.error(f"Derin bilgi hatasi: {firma_adi} - {str(e)}")
        return sonuc


# ============================================================
# PDF / EXCEL / MANUEL
# ============================================================

def pdf_firmalari_oku(pdf_file):
    firmalar = []

    try:
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    for line in page_text.split("\n"):
                        temiz = firma_adi_temizle(line)
                        if temiz:
                            firmalar.append(temiz)
    except Exception as e:
        raise Exception(f"PDF okuma hatasi: {str(e)}")

    return firma_listesi_filtrele(firmalar)


def excel_firmalari_oku(excel_file):
    try:
        df_upload = pd.read_excel(excel_file)

        if df_upload.empty:
            return []

        ilk_sutun = df_upload.iloc[:, 0].dropna().astype(str).tolist()
        return firma_listesi_filtrele(ilk_sutun)

    except Exception as e:
        raise Exception(f"Excel okuma hatasi: {str(e)}")


def listeye_ekle(yeni_firmalar, listeyi_sifirla=False):
    yeni_firmalar = firma_listesi_filtrele(yeni_firmalar)

    if listeyi_sifirla:
        st.session_state["ana_liste"] = yeni_firmalar
    else:
        mevcut = st.session_state["ana_liste"]
        birlesik = mevcut + yeni_firmalar
        st.session_state["ana_liste"] = firma_listesi_filtrele(birlesik)

    return len(yeni_firmalar)



def sure_formatla(saniye):
    try:
        saniye = int(saniye)
        dk = saniye // 60
        sn = saniye % 60
        if dk <= 0:
            return f"{sn} sn"
        return f"{dk} dk {sn} sn"
    except Exception:
        return "-"



def tarama_modu_ayarlari(mod):
    """
    Hız / güvenlik dengesi.
    Hızlı: Daha fazla paralel firma, az sorgu, Playwright fallback kapalı.
    Dengeli: Orta paralellik, orta sorgu, Playwright fallback açık.
    Derin: Daha az paralellik, fazla sorgu, Playwright fallback açık.
    """
    if mod == "Hızlı Tarama":
        return {
            "workers": 6,
            "query_limit": 2,
            "playwright_fallback": False,
            "aciklama": "Hızlı mod: En seri mod. Firma başına az sorgu dener, tarayıcı fallback kapalıdır."
        }

    if mod == "Derin Tarama":
        return {
            "workers": 1,
            "query_limit": 8,
            "playwright_fallback": True,
            "aciklama": "Derin mod: Eksik kalan firmalar için kullanılır. Yavaş ama daha güçlüdür."
        }

    return {
        "workers": 4,
        "query_limit": 4,
        "playwright_fallback": False,
        "aciklama": "Dengeli mod: Çökmeden hızlı çalışması için güvenli ayar. Tarayıcı fallback kapalıdır."
    }


# ============================================================
# ARAYUZ
# ============================================================

tabloyu_hazirla()

kurumsal_tasarim_yukle()
kurumsal_banner_goster()
ozellik_kartlari_goster()

with st.sidebar:
    st.success("🔐 Giriş yapıldı")

    if st.button("🚪 Çıkış Yap", use_container_width=True):
        st.session_state["authenticated"] = False
        st.rerun()

    st.header("⚙️ Tarama Ayarlari")

    if PLAYWRIGHT_AKTIF:
        st.success("Playwright aktif: JS sayfalari okunabilir.")
    else:
        st.warning("Playwright pasif: Sadece statik HTML okunur.")

    fuar_etiketi = st.text_input("Fuar Etiketi", value="Genel_Liste")

    tarama_modu = st.selectbox(
        "Tarama Modu",
        ["Hızlı Tarama", "Dengeli", "Derin Tarama"],
        index=1,
        help="Hızlı mod daha seri çalışır; Derin mod eksikleri bulmak için daha fazla arama yapar."
    )

    mod_ayar = tarama_modu_ayarlari(tarama_modu)

    max_workers = st.slider(
        "Aynı anda taranacak firma sayısı",
        min_value=1,
        max_value=8,
        value=mod_ayar["workers"],
        help="Streamlit Cloud için 4-6 arası genelde güvenlidir. Çökme olursa düşür."
    )

    globals()["SCAN_MODE"] = tarama_modu
    globals()["SEARCH_QUERY_LIMIT"] = mod_ayar["query_limit"]
    globals()["PLAYWRIGHT_FALLBACK_ENABLED"] = mod_ayar["playwright_fallback"]

    st.caption(mod_ayar["aciklama"])
    st.caption(f"Firma başına arama limiti: {SEARCH_QUERY_LIMIT} | Playwright fallback: {'Açık' if PLAYWRIGHT_FALLBACK_ENABLED else 'Kapalı'}")

    listeyi_sifirla = st.checkbox("Yeni veri eklenince mevcut havuzu sifirla", value=True)

    st.divider()
    st.subheader("📦 Paketli Tarama")

    paket_boyutu = st.selectbox(
        "Bir seferde işlenecek firma sayısı",
        [25, 50, 100, 150],
        index=1,
        help="Streamlit Cloud için 25 veya 50 daha güvenlidir. Büyük listelerde uygulamanın kapanmasını önler."
    )

    sadece_islenmemis = st.checkbox(
        "Daha önce işlenen firmaları atla",
        value=True,
        help="Aynı fuar etiketiyle daha önce arşive kaydedilen firmalar tekrar taranmaz."
    )

    st.divider()

    if st.button("🧹 Islem Havuzunu Temizle", use_container_width=True):
        st.session_state["ana_liste"] = []
        st.rerun()

    if st.button("🧯 Hata Loglarini Temizle", use_container_width=True):
        st.session_state["son_hatalar"] = []
        st.rerun()


t1, t2, t3, t4 = st.tabs(["🌐 URL Tarama", "📄 PDF Analiz", "📊 Excel Giris", "📂 Manuel Liste"])


# ============================================================
# URL SEKMESI
# ============================================================

with t1:
    st.subheader("🌐 Katilimci Listesi URL Tarama")

    url_input = st.text_input(
        "Hedef URL",
        placeholder="https://ornekfuar.com/katilimci-listesi"
    )

    url_button = st.button("🔍 URL'den Firmalari Cek", use_container_width=False)

    if url_button:
        if not url_input.strip():
            st.warning("Lutfen bir URL gir.")
        else:
            try:
                progress_bar = st.progress(0)
                durum_kutusu = st.empty()
                metrik_alani = st.empty()
                baslangic = time.time()

                def progress_guncelle(info):
                    adim = info.get("adim", "İşlem sürüyor...")
                    sayfa_no = info.get("sayfa_no", 0)
                    toplam_sayfa = info.get("toplam_sayfa", 0)
                    bulunan = info.get("bulunan", 0)
                    gecen = info.get("gecen", time.time() - baslangic)

                    oran = 0.05
                    kalan_text = "Hesaplanıyor..."

                    if toplam_sayfa and sayfa_no:
                        oran = min(max(sayfa_no / toplam_sayfa, 0.05), 0.98)
                        if sayfa_no > 0:
                            tahmini_toplam = gecen / sayfa_no * toplam_sayfa
                            kalan = max(tahmini_toplam - gecen, 0)
                            kalan_text = sure_formatla(kalan)

                    progress_bar.progress(oran)
                    durum_kutusu.info(f"🔄 {adim}")

                    metrik_alani.markdown(
                        f"""
                        **Bulunan firma:** {bulunan} &nbsp;&nbsp; | &nbsp;&nbsp;
                        **Geçen süre:** {sure_formatla(gecen)} &nbsp;&nbsp; | &nbsp;&nbsp;
                        **Tahmini kalan:** {kalan_text}
                        """
                    )

                with st.spinner("URL okunuyor ve firma isimleri cikariliyor..."):
                    firmalar = []

                    # Evrensel çoklu motor:
                    # 1) Bilinen adaptörler: MÜSİAD / MAKTEK
                    # 2) Genel pagination
                    # 3) Genel statik HTML
                    # 4) Genel JavaScript / Sonraki butonu
                    # 5) Fallback Playwright selector
                    firmalar = evrensel_url_firma_cek(url_input, progress_callback=progress_guncelle)

                    progress_bar.progress(1.0)
                    durum_kutusu.success("✅ URL tarama tamamlandı.")
                    adet = listeye_ekle(firmalar, listeyi_sifirla=listeyi_sifirla)

                if adet > 0:
                    st.success(f"✅ {adet} firma havuza aktarildi.")
                    st.rerun()
                else:
                    st.error("Bu URL'den firma adi cikarilamadi. Site veriyi gizli API ile cekiyor veya bot erisimini kisitliyor olabilir.")

            except Exception as e:
                hata_kaydet(f"URL tarama hatasi: {str(e)}")
                st.error(f"URL tarama hatasi: {str(e)}")


# ============================================================
# PDF SEKMESI
# ============================================================

with t2:
    st.subheader("📄 PDF Katilimci Katalogu Analiz")
    pdf_file = st.file_uploader("Katalog PDF'i yukleyin", type=["pdf"])

    if pdf_file:
        try:
            with st.spinner("PDF okunuyor..."):
                pdf_firmalar = pdf_firmalari_oku(pdf_file)

            st.info(f"PDF icinde {len(pdf_firmalar)} olasi firma adi bulundu.")

            if pdf_firmalar:
                st.dataframe(pd.DataFrame({"Firma Adi": pdf_firmalar}), use_container_width=True)

            if st.button("📥 PDF Firmalarini Havuza Aktar", use_container_width=True):
                adet = listeye_ekle(pdf_firmalar, listeyi_sifirla=listeyi_sifirla)
                st.success(f"✅ {adet} firma havuza aktarildi.")
                st.rerun()

        except Exception as e:
            hata_kaydet(str(e))
            st.error(str(e))


# ============================================================
# EXCEL SEKMESI
# ============================================================

with t3:
    st.subheader("📊 Excel Firma Listesi Giris")
    excel_file = st.file_uploader("Firma Listesi Excel'i yukleyin", type=["xlsx", "xls"])

    if excel_file:
        try:
            excel_firmalar = excel_firmalari_oku(excel_file)

            st.info(f"Excel icinde {len(excel_firmalar)} firma bulundu. Ilk sutun firma adi kabul edilir.")

            if excel_firmalar:
                st.dataframe(pd.DataFrame({"Firma Adi": excel_firmalar}), use_container_width=True)

            if st.button("📊 Excel Firmalarini Havuza Aktar", use_container_width=True):
                adet = listeye_ekle(excel_firmalar, listeyi_sifirla=listeyi_sifirla)
                st.success(f"✅ {adet} firma havuza aktarildi.")
                st.rerun()

        except Exception as e:
            hata_kaydet(str(e))
            st.error(str(e))


# ============================================================
# MANUEL SEKMESI
# ============================================================

with t4:
    st.subheader("📂 Manuel Firma Listesi")

    manuel_input = st.text_area(
        "Firma isimlerini yapistirin",
        placeholder="Her satira bir firma adi gelecek sekilde yapistirin.",
        height=220
    )

    if st.button("➕ Manuel Listeyi Havuza Aktar", use_container_width=True):
        if not manuel_input.strip():
            st.warning("Liste bos gorunuyor.")
        else:
            manuel_firmalar = [f.strip() for f in manuel_input.split("\n") if f.strip()]
            adet = listeye_ekle(manuel_firmalar, listeyi_sifirla=listeyi_sifirla)
            st.success(f"✅ {adet} firma havuza aktarildi.")
            st.rerun()


# ============================================================
# ISLEM HAVUZU
# ============================================================

st.divider()
st.subheader(f"📋 Islem Havuzu: {len(st.session_state['ana_liste'])} Firma")

if st.session_state["ana_liste"]:
    havuz_df = pd.DataFrame({"Firma Adi": st.session_state["ana_liste"]})
    st.dataframe(havuz_df, use_container_width=True, height=300)

    output_havuz = io.BytesIO()
    with pd.ExcelWriter(output_havuz, engine="openpyxl") as writer:
        havuz_df.to_excel(writer, index=False)

    st.download_button(
        label="📥 Havuzu Excel Olarak Indir",
        data=output_havuz.getvalue(),
        file_name=f"{fuar_etiketi}_firma_havuzu.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    tara = st.button("⚡ BU PAKETİ TARA VE ARŞİVE KAYDET", use_container_width=True)

    if tara:
        tum_firmalar = st.session_state["ana_liste"]

        if sadece_islenmemis:
            islenmisler = islenmis_firmalari_getir(fuar_etiketi)
            firmalar_filtreli = [f for f in tum_firmalar if f.lower().strip() not in islenmisler]
        else:
            firmalar_filtreli = tum_firmalar

        toplam_kalan = len(firmalar_filtreli)

        if toplam_kalan == 0:
            st.success("✅ Bu fuar etiketi için işlem bekleyen firma kalmadı.")
            st.stop()

        paket_firmalar = firmalar_filtreli[:paket_boyutu]
        toplam_firma = len(paket_firmalar)
        baslangic_tarama = time.time()

        progress_bar = st.progress(0)
        status_area = st.empty()
        metrik_area = st.empty()
        sonuc_placeholder = st.empty()

        kayitlar = []
        basarili = 0
        web_bulunamadi = 0
        hata_sayisi = 0

        status_area.info(
            f"🚀 {SCAN_MODE} başladı. Bu pakette {toplam_firma} firma işlenecek. "
            f"Toplam bekleyen: {toplam_kalan}. Paralel işlem: {max_workers}."
        )

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(derin_bilgi_bul, firma): firma for firma in paket_firmalar}
            pending = set(futures.keys())
            tamamlanan_sayi = 0

            while pending:
                done, pending = concurrent.futures.wait(
                    pending,
                    timeout=1,
                    return_when=concurrent.futures.FIRST_COMPLETED
                )

                if not done:
                    gecen = time.time() - baslangic_tarama
                    metrik_area.markdown(
                        f"""
                        **Mod:** {SCAN_MODE} &nbsp;&nbsp; | &nbsp;&nbsp;
                        **Paket:** {toplam_firma} firma &nbsp;&nbsp; | &nbsp;&nbsp;
                        **Tamamlanan:** {tamamlanan_sayi}/{toplam_firma} &nbsp;&nbsp; | &nbsp;&nbsp;
                        **Bekleyen:** {len(pending)} &nbsp;&nbsp; | &nbsp;&nbsp;
                        **Geçen:** {sure_formatla(gecen)}
                        """
                    )
                    status_area.info(
                        f"🔎 Arka planda {max_workers} firma aynı anda taranıyor. Sonuçlar geldikçe ara kayıt yapılacak..."
                    )
                    continue

                for future in done:
                    firma = futures[future]
                    tamamlanan_sayi += 1

                    try:
                        res = future.result()
                    except Exception as e:
                        res = {
                            "firma_adi": firma,
                            "web_adresi": "Bulunamadi",
                            "telefon": "Bulunamadi",
                            "eposta": "Bulunamadi",
                            "kaynak": "",
                            "durum": "Hata",
                            "hata": str(e)
                        }

                    res["fuar_etiketi"] = fuar_etiketi
                    kayitlar.append(res)

                    try:
                        verileri_toplu_kaydet([res])
                    except Exception as e:
                        hata_kaydet(f"Ara kayıt hatası: {str(e)}")

                    if res.get("durum") == "Tamamlandi":
                        basarili += 1
                    elif "bulunamadi" in res.get("durum", "").lower():
                        web_bulunamadi += 1
                    elif res.get("durum") == "Hata":
                        hata_sayisi += 1

                    oran = tamamlanan_sayi / toplam_firma
                    gecen = time.time() - baslangic_tarama
                    tahmini_toplam = gecen / tamamlanan_sayi * toplam_firma if tamamlanan_sayi else 0
                    kalan = max(tahmini_toplam - gecen, 0)

                    progress_bar.progress(oran)
                    status_area.info(
                        f"İşleniyor: {tamamlanan_sayi}/{toplam_firma} | Son tamamlanan firma: {firma}"
                    )

                    metrik_area.markdown(
                        f"""
                        **Mod:** {SCAN_MODE} &nbsp;&nbsp; | &nbsp;&nbsp;
                        **Bu paket:** {tamamlanan_sayi}/{toplam_firma} &nbsp;&nbsp; | &nbsp;&nbsp;
                        **Toplam bekleyen:** {toplam_kalan} &nbsp;&nbsp; | &nbsp;&nbsp;
                        **Başarılı:** {basarili} &nbsp;&nbsp; | &nbsp;&nbsp;
                        **Web bulunamadı:** {web_bulunamadi} &nbsp;&nbsp; | &nbsp;&nbsp;
                        **Hata:** {hata_sayisi} &nbsp;&nbsp; | &nbsp;&nbsp;
                        **Geçen:** {sure_formatla(gecen)} &nbsp;&nbsp; | &nbsp;&nbsp;
                        **Tahmini kalan:** {sure_formatla(kalan)}
                        """
                    )

                    if len(kayitlar) % 5 == 0 or tamamlanan_sayi == toplam_firma:
                        sonuc_placeholder.dataframe(pd.DataFrame(kayitlar), use_container_width=True)

        st.session_state["son_batch_sonuclari"] = kayitlar
        kalan_sonraki = max(toplam_kalan - toplam_firma, 0)

        st.session_state["son_islem_ozeti"] = (
            f"Paket tamamlandı. Bu paket: {len(kayitlar)} | "
            f"Başarılı: {basarili} | "
            f"Web bulunamadı: {web_bulunamadi} | "
            f"Hata: {hata_sayisi} | "
            f"Kalan: {kalan_sonraki}"
        )

        st.success("✅ Paket tamamlandı ve sonuçlar arşive ara kayıt olarak işlendi.")
        st.info(st.session_state["son_islem_ozeti"])

        islenen_set = set([f.lower().strip() for f in paket_firmalar])
        st.session_state["ana_liste"] = [
            f for f in st.session_state["ana_liste"]
            if f.lower().strip() not in islenen_set
        ]

        if kalan_sonraki > 0:
            st.warning(f"📦 Bu paket bitti. Kalan yaklaşık {kalan_sonraki} firma var. Devam etmek için tekrar 'BU PAKETİ TARA VE ARŞİVE KAYDET' butonuna bas.")
        else:
            st.success("🎉 Tüm firmalar tamamlandı.")

        st.rerun()

else:
    st.info("Henuz islem havuzunda firma yok. URL, PDF, Excel veya manuel giristen firma ekleyebilirsin.")


# ============================================================
# ARSIV
# ============================================================

st.divider()
st.subheader("🗄️ Kalici Arsiv")

df_arsiv = arsivi_getir()

if not df_arsiv.empty:
    filtre_fuar = st.text_input("Arsiv icinde ara", placeholder="Firma adi, mail, web sitesi veya fuar etiketi yazin")

    df_goster = df_arsiv.copy()

    if filtre_fuar.strip():
        aranan = filtre_fuar.lower().strip()
        mask = df_goster.astype(str).apply(lambda col: col.str.lower().str.contains(aranan, na=False)).any(axis=1)
        df_goster = df_goster[mask]

    st.dataframe(df_goster, use_container_width=True, height=420)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_goster.to_excel(writer, index=False, sheet_name="Fuar Listesi")

    c1, c2, c3 = st.columns([1, 1, 3])

    with c1:
        st.download_button(
            label="📥 Arsivi Excel Indir",
            data=output.getvalue(),
            file_name=f"{fuar_etiketi}_fuar_liste.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    with c2:
        with st.expander("🗑️ Arsiv Temizle"):
            st.warning("Bu islem tum arsivi siler.")
            if st.button("Evet, Tum Arsivi Sil"):
                arsivi_temizle()
                st.success("Arsiv temizlendi.")
                st.rerun()

else:
    st.info("Arsiv henuz bos.")


# ============================================================
# HATA PANELI
# ============================================================

with st.expander("🧯 Son Hatalar / Sistem Loglari"):
    if st.session_state["son_hatalar"]:
        for h in st.session_state["son_hatalar"]:
            st.code(h)
    else:
        st.info("Su anda gorunur hata yok.")

    st.caption("Ayrica sunucu klasorunde squarexpo_v3.log dosyasi olusur.")


st.markdown("""
<div class="footer-note">
    Perge Mimarlık & Squarexpo iş birliği ile geliştirildi ❤️ Fuar Müşteri Otomasyonu V1.5
</div>
""", unsafe_allow_html=True)

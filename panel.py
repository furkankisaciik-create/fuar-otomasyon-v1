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
from urllib.parse import urlparse, urljoin, quote_plus, parse_qs
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

APP_TITLE = "SQUAREXPO Fuar Musteri Otomasyonu V3.2"
DB_PATH = "fuar_verileri.db"
MAX_WORKERS_DEFAULT = 3
REQUEST_TIMEOUT = 15


# ============================================================
# STREAMLIT AYARLARI
# ============================================================

st.set_page_config(
    page_title=APP_TITLE,
    layout="wide",
    page_icon="🚀"
)


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
        parsed = urlparse(url)
        return parsed.scheme in ["http", "https"] and bool(parsed.netloc)
    except Exception:
        return False


def normalize_url(url, base_url=None):
    if not url:
        return ""
    url = url.strip()

    if base_url and url.startswith("/"):
        return urljoin(base_url, url)

    if url.startswith("//"):
        return "https:" + url

    if not url.startswith("http://") and not url.startswith("https://"):
        return "https://" + url

    return url


def istenmeyen_link_mi(url):
    blacklist = [
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




def musiad_katilimci_listesi_cek(url):
    """
    MÜSİAD Expo özel motoru.
    Katılımcı tablosundaki tüm sayfaları Sonraki butonu ile dolaşır.
    Sadece Katılımcı sütunundaki firma adlarını alır.
    """
    if not PLAYWRIGHT_AKTIF:
        raise Exception("Playwright aktif değil. MÜSİAD özel motoru çalışamaz.")

    url = normalize_url(url)
    firmalar = []

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
            viewport={"width": 1400, "height": 900},
            locale="tr-TR"
        )

        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)

        # Tablo yüklenene kadar kısa denemeler
        for _ in range(10):
            try:
                if page.locator("table tbody tr").count() > 0:
                    break
            except Exception:
                pass
            page.wait_for_timeout(1000)

        sayfa_sayisi = 0
        max_sayfa = 50

        while sayfa_sayisi < max_sayfa:
            sayfa_sayisi += 1
            page.wait_for_timeout(1200)

            # Tablo satırlarından ilk hücreyi yani Katılımcı sütununu al
            rows = page.locator("table tbody tr")
            row_count = rows.count()

            for i in range(row_count):
                try:
                    first_cell = rows.nth(i).locator("td").nth(0).inner_text(timeout=3000)
                    firma = firma_adi_temizle(first_cell)
                    firma = musiad_firma_adi_temizle(firma)
                    if firma and sadece_firma_unvani_mi(firma):
                        firmalar.append(firma)
                except Exception:
                    continue

            # Sonraki butonunu bul
            next_candidates = [
                "button:has-text('Sonraki')",
                "a:has-text('Sonraki')",
                "button:has-text('Next')",
                "a:has-text('Next')",
                "[aria-label*='Sonraki']",
                "[aria-label*='Next']"
            ]

            next_button = None
            for sel in next_candidates:
                try:
                    loc = page.locator(sel).last
                    if loc.count() > 0 and loc.is_visible():
                        next_button = loc
                        break
                except Exception:
                    continue

            if next_button is None:
                break

            try:
                disabled_attr = next_button.get_attribute("disabled")
                aria_disabled = next_button.get_attribute("aria-disabled")
                class_attr = next_button.get_attribute("class") or ""

                if disabled_attr is not None or aria_disabled == "true" or "disabled" in class_attr.lower():
                    break

                onceki_ilk = ""
                try:
                    if row_count > 0:
                        onceki_ilk = rows.nth(0).locator("td").nth(0).inner_text(timeout=1000)
                except Exception:
                    pass

                next_button.click(timeout=5000)
                page.wait_for_timeout(2500)

                # Sayfanın değişmesini bekle
                for _ in range(10):
                    try:
                        yeni_rows = page.locator("table tbody tr")
                        if yeni_rows.count() > 0:
                            yeni_ilk = yeni_rows.nth(0).locator("td").nth(0).inner_text(timeout=1000)
                            if yeni_ilk != onceki_ilk:
                                break
                    except Exception:
                        pass
                    page.wait_for_timeout(800)

            except Exception:
                break

        browser.close()

    # Mükerrerleri sil
    final = []
    seen = set()
    for f in firmalar:
        key = f.lower().strip()
        if key not in seen:
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

def firma_websitesi_bul(firma_adi):
    sorgu = quote_plus(f"{firma_adi} official website contact")
    arama_url_listesi = [
        f"https://www.bing.com/search?q={sorgu}",
        f"https://duckduckgo.com/html/?q={sorgu}"
    ]

    for arama_url in arama_url_listesi:
        try:
            time.sleep(random.uniform(0.8, 1.8))
            res = guvenli_get(arama_url, timeout=REQUEST_TIMEOUT, referer="https://www.google.com/")

            if res.status_code >= 400:
                continue

            soup = BeautifulSoup(res.text, "html.parser")
            linkler = []

            for a in soup.find_all("a", href=True):
                href = a.get("href", "").strip()

                if "uddg=" in href:
                    try:
                        parsed = urlparse(href)
                        qs = parse_qs(parsed.query)
                        if "uddg" in qs:
                            href = qs["uddg"][0]
                    except Exception:
                        pass

                href = normalize_url(href)

                if not url_gecerli_mi(href):
                    continue
                if istenmeyen_link_mi(href):
                    continue

                domain = domain_al(href)
                if not domain:
                    continue

                linkler.append(href)

            for link in linkler:
                if link.startswith("http"):
                    return link

        except Exception as e:
            logging.warning(f"Arama hatasi: {firma_adi} - {str(e)}")
            continue

    return ""


def eposta_ayikla(text):
    if not text:
        return []

    mailler = re.findall(
        r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
        text
    )

    filtreli = []
    yasakli = ["example.com", "domain.com", "email.com", "sentry.", "wixpress.", "schema.org"]

    for m in mailler:
        m = m.strip().lower()
        if any(y in m for y in yasakli):
            continue
        if m not in filtreli:
            filtreli.append(m)

    return filtreli[:5]


def telefon_ayikla(text):
    if not text:
        return []

    patternler = [
        r"\+90[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}",
        r"0[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}",
        r"\+\d{1,3}[\s\-]?\(?\d{2,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{2,4}[\s\-]?\d{2,4}",
    ]

    telefonlar = []
    for p in patternler:
        telefonlar.extend(re.findall(p, text))

    temiz = []

    for tel in telefonlar:
        tel = re.sub(r"\s+", " ", tel).strip()
        rakam = re.sub(r"\D", "", tel)
        if 10 <= len(rakam) <= 15:
            if tel not in temiz:
                temiz.append(tel)

    return temiz[:5]


def iletisim_sayfasi_linkleri_bul(base_url, html):
    soup = BeautifulSoup(html, "html.parser")
    adaylar = []

    anahtarlar = [
        "contact", "contact-us", "contacts", "iletisim", "iletişim",
        "bize-ulasin", "bize-ulaşın", "kurumsal", "about", "about-us"
    ]

    for a in soup.find_all("a", href=True):
        text = temiz_metin(a.get_text(" ")).lower()
        href = a.get("href", "").lower()

        if any(k in text or k in href for k in anahtarlar):
            full = normalize_url(a.get("href"), base_url=base_url)
            if url_gecerli_mi(full):
                adaylar.append(full)

    adaylar = list(dict.fromkeys(adaylar))
    adaylar = sorted(
        adaylar,
        key=lambda x: 0 if any(k in x.lower() for k in ["contact", "iletisim", "iletişim"]) else 1
    )

    return adaylar[:4]


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
        time.sleep(random.uniform(0.8, 1.8))
        res = guvenli_get(web_url, timeout=REQUEST_TIMEOUT, referer="https://www.google.com/")
        html = res.text or ""
        text = temiz_metin(html)

        mailler = eposta_ayikla(html + " " + text)
        telefonlar = telefon_ayikla(html + " " + text)

        kaynak = web_url

        if not mailler or not telefonlar:
            for contact_url in iletisim_sayfasi_linkleri_bul(web_url, html):
                try:
                    time.sleep(random.uniform(0.6, 1.4))
                    c_res = guvenli_get(contact_url, timeout=REQUEST_TIMEOUT, referer=web_url)
                    c_html = c_res.text or ""
                    c_text = temiz_metin(c_html)

                    if not mailler:
                        mailler = eposta_ayikla(c_html + " " + c_text)
                    if not telefonlar:
                        telefonlar = telefon_ayikla(c_html + " " + c_text)

                    if mailler or telefonlar:
                        kaynak = contact_url

                    if mailler and telefonlar:
                        break

                except Exception as e:
                    logging.warning(f"Iletisim sayfasi okunamadi: {contact_url} - {str(e)}")
                    continue

        if mailler:
            sonuc["eposta"] = ", ".join(mailler)
        if telefonlar:
            sonuc["telefon"] = ", ".join(telefonlar)

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

        web = firma_websitesi_bul(firma_adi)

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


# ============================================================
# ARAYUZ
# ============================================================

tabloyu_hazirla()

st.title("🚀 SQUAREXPO Fuar Musteri Otomasyonu V3.2")
st.caption("Katilimci listesi URL / PDF / Excel / manuel giristen firma havuzu olusturur; firma web sitesi, mail ve telefon bulmaya calisir.")

with st.sidebar:
    st.header("⚙️ Tarama Ayarlari")

    if PLAYWRIGHT_AKTIF:
        st.success("Playwright aktif: JS sayfalari okunabilir.")
    else:
        st.warning("Playwright pasif: Sadece statik HTML okunur.")

    fuar_etiketi = st.text_input("Fuar Etiketi", value="Genel_Liste")

    max_workers = st.slider(
        "Ayni anda taranacak firma sayisi",
        min_value=1,
        max_value=8,
        value=MAX_WORKERS_DEFAULT,
        help="Canli sunucuda hata alirsan 1-3 arasi kullan."
    )

    listeyi_sifirla = st.checkbox("Yeni veri eklenince mevcut havuzu sifirla", value=True)

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
                with st.spinner("URL okunuyor ve firma isimleri cikariliyor..."):
                    firmalar = []

                    # MÜSİAD özel tablo motoru: tüm sayfaları dolaşır ve Katılımcı sütununu alır
                    if "musiadexpo.com" in url_input.lower():
                        st.info("MÜSİAD özel katılımcı motoru çalışıyor. Tüm sayfalar dolaşılıyor...")
                        firmalar = musiad_katilimci_listesi_cek(url_input)

                    # Genel motorlar
                    if not firmalar:
                        firmalar = firmalari_url_den_cek(url_input)

                    if not firmalar:
                        st.warning("Statik HTML icinde firma bulunamadi. JavaScript tarayici motoru deneniyor...")
                        firmalar = firmalari_url_den_cek_playwright(url_input)

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

    tara = st.button("⚡ FIRMALARI TARA VE ARSIVE KAYDET", use_container_width=True)

    if tara:
        firmalar = st.session_state["ana_liste"]

        progress_bar = st.progress(0)
        status_area = st.empty()
        sonuc_placeholder = st.empty()

        kayitlar = []
        basarili = 0
        web_bulunamadi = 0
        hata_sayisi = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(derin_bilgi_bul, firma): firma for firma in firmalar}

            for i, future in enumerate(concurrent.futures.as_completed(futures)):
                firma = futures[future]

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

                if res.get("durum") == "Tamamlandi":
                    basarili += 1
                elif "bulunamadi" in res.get("durum", "").lower():
                    web_bulunamadi += 1
                elif res.get("durum") == "Hata":
                    hata_sayisi += 1

                progress_bar.progress((i + 1) / len(firmalar))
                status_area.info(f"Isleniyor: {i + 1}/{len(firmalar)} | Son firma: {firma}")

                if len(kayitlar) % 5 == 0 or i == len(firmalar) - 1:
                    sonuc_placeholder.dataframe(pd.DataFrame(kayitlar), use_container_width=True)

        verileri_toplu_kaydet(kayitlar)

        st.session_state["son_islem_ozeti"] = (
            f"Tamamlandi. Toplam: {len(kayitlar)} | "
            f"Basarili: {basarili} | "
            f"Web bulunamadi: {web_bulunamadi} | "
            f"Hata: {hata_sayisi}"
        )

        st.success("✅ Islem tamamlandi ve arsive kaydedildi.")
        st.info(st.session_state["son_islem_ozeti"])

        st.session_state["ana_liste"] = []
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

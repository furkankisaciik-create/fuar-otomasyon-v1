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
from urllib.parse import urlparse, urljoin, quote_plus, parse_qs, unquote
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

    if progress_callback:
        try:
            progress_callback({
                "adim": "Katılımcı çekimi tamamlandı.",
                "sayfa_no": 0,
                "toplam_sayfa": 0,
                "bulunan": len(final),
                "gecen": time.time() - baslangic_zamani
            })
        except Exception:
            pass

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
        "pazarlama", "dis", "dıs", "dış", "ic", "iç", "urunleri", "ürünleri",
        "makine", "insaat", "inşaat", "gida", "gıda", "tarim", "tarım", "teknoloji",
        "teknolojileri", "metal", "plastik", "tekstil", "otomotiv", "elektrik",
        "elektronik", "mobilya", "ambalaj", "kimya", "medikal", "promosyon"
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
    words = firma_adi_sadelestir(firma_adi)
    original = firma_adi_temizle(firma_adi)

    sorgular = []

    if original:
        sorgular.extend([
            f'"{original}"',
            f'"{original}" iletişim',
            f'"{original}" resmi web sitesi',
        ])

    if words:
        marka1 = words[0]
        marka2 = " ".join(words[:2])
        marka3 = " ".join(words[:3])

        for q in [marka3, marka2, marka1]:
            if q and q not in sorgular:
                sorgular.extend([
                    f"{q} resmi web sitesi",
                    f"{q} iletişim",
                    f"{q} firma",
                    f"{q} site:com.tr",
                    f"{q} official website"
                ])

    # Tekilleştir
    final = []
    seen = set()
    for q in sorgular:
        k = q.lower().strip()
        if k and k not in seen:
            seen.add(k)
            final.append(q)

    return final[:12]


def domain_adaylari_uret(firma_adi):
    words = firma_adi_sadelestir(firma_adi)

    aday_kokler = []

    if words:
        aday_kokler.append(words[0])
        if len(words) >= 2:
            aday_kokler.append(words[0] + words[1])
            aday_kokler.append(words[0] + "-" + words[1])
        if len(words) >= 3:
            aday_kokler.append(words[0] + words[1] + words[2])

    # Mükerrer temizle
    clean_roots = []
    seen = set()
    for root in aday_kokler:
        root = re.sub(r"[^a-z0-9-]", "", root)
        if len(root) >= 3 and root not in seen:
            seen.add(root)
            clean_roots.append(root)

    tlds = [".com.tr", ".com", ".net", ".com.tr/iletisim", ".com/iletisim"]

    adaylar = []
    for root in clean_roots:
        for tld in tlds:
            adaylar.append(f"https://www.{root}{tld}")
            adaylar.append(f"https://{root}{tld}")

    return adaylar[:30]


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



def firma_websitesi_bul(firma_adi):
    """
    Firma adından resmi web sitesini bulmaya çalışır.
    V4.5:
    - Firma adını sadeleştirir.
    - Marka köküyle arama yapar.
    - Bing / DuckDuckGo sonuçlarını çözer.
    - Son çare domain tahmini yapar.
    """
    firma_adi_temiz = firma_adi_temizle(firma_adi)
    sorgular = firma_arama_sorgulari_uret(firma_adi_temiz)[:SEARCH_QUERY_LIMIT]

    bulunan_linkler = []

    # 1) Requests ile Bing + DuckDuckGo araması
    for sorgu_text in sorgular:
        arama_url_listesi = [
            f"https://www.bing.com/search?q={quote_plus(sorgu_text)}",
            f"https://duckduckgo.com/html/?q={quote_plus(sorgu_text)}"
        ]

        for arama_url in arama_url_listesi:
            try:
                time.sleep(random.uniform(0.8, 1.8))
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

                    domain = domain_al(href)
                    if not domain or len(domain) < 4:
                        continue

                    bulunan_linkler.append(href)

            except Exception as e:
                logging.warning(f"Arama hatasi: {firma_adi_temiz} - {str(e)}")
                continue

        # İlk sorgularda iyi sonuç varsa fazla bekleme
        if bulunan_linkler:
            break

    # 2) Requests sonuç vermezse Playwright DuckDuckGo araması
    if not bulunan_linkler and PLAYWRIGHT_FALLBACK_ENABLED:
        for sorgu_text in sorgular[:max(1, min(3, SEARCH_QUERY_LIMIT))]:
            bulunan_linkler.extend(playwright_arama_linkleri_bul(sorgu_text))
            if bulunan_linkler:
                break

    # 3) Linkleri domain bazlı tekilleştir
    temiz_linkler = []
    gorulen_domain = set()

    for link in bulunan_linkler:
        d = domain_al(link)
        if d and d not in gorulen_domain:
            gorulen_domain.add(d)
            temiz_linkler.append(link)

    if temiz_linkler:
        return temiz_linkler[0]

    # 4) Son çare: domain tahmini
    for aday in domain_adaylari_uret(firma_adi_temiz):
        if web_sitesi_dogrula(aday):
            return aday

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
            "query_limit": 3,
            "playwright_fallback": False,
            "aciklama": "Hızlı mod: Web sitesi bulmaya odaklanır, daha az sorgu dener."
        }

    if mod == "Derin Tarama":
        return {
            "workers": 2,
            "query_limit": 10,
            "playwright_fallback": True,
            "aciklama": "Derin mod: Daha yavaş ama eksik kalan firmalar için daha güçlü arama yapar."
        }

    return {
        "workers": 4,
        "query_limit": 6,
        "playwright_fallback": True,
        "aciklama": "Dengeli mod: Hız ve doğruluk arasında güvenli ayar."
    }


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

    global SCAN_MODE, SEARCH_QUERY_LIMIT, PLAYWRIGHT_FALLBACK_ENABLED
    SCAN_MODE = tarama_modu
    SEARCH_QUERY_LIMIT = mod_ayar["query_limit"]
    PLAYWRIGHT_FALLBACK_ENABLED = mod_ayar["playwright_fallback"]

    st.caption(mod_ayar["aciklama"])
    st.caption(f"Firma başına arama limiti: {SEARCH_QUERY_LIMIT} | Playwright fallback: {'Açık' if PLAYWRIGHT_FALLBACK_ENABLED else 'Kapalı'}")

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

                    # MÜSİAD özel tablo motoru: tüm sayfaları dolaşır ve Katılımcı sütununu alır
                    if "musiadexpo.com" in url_input.lower():
                        st.info("MÜSİAD özel katılımcı motoru çalışıyor. Tüm sayfalar dolaşılıyor...")
                        firmalar = musiad_katilimci_listesi_cek(url_input, progress_callback=progress_guncelle)

                    # Genel motorlar
                    if not firmalar:
                        progress_guncelle({"adim": "Genel statik HTML motoru deneniyor...", "bulunan": 0, "gecen": time.time() - baslangic})
                        firmalar = firmalari_url_den_cek(url_input)

                    if not firmalar:
                        st.warning("Statik HTML icinde firma bulunamadi. JavaScript tarayici motoru deneniyor...")
                        progress_guncelle({"adim": "JavaScript tarayıcı motoru deneniyor...", "bulunan": 0, "gecen": time.time() - baslangic})
                        firmalar = firmalari_url_den_cek_playwright(url_input)

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

    tara = st.button("⚡ FIRMALARI TARA VE ARSIVE KAYDET", use_container_width=True)

    if tara:
        firmalar = st.session_state["ana_liste"]
        toplam_firma = len(firmalar)
        baslangic_tarama = time.time()

        progress_bar = st.progress(0)
        status_area = st.empty()
        metrik_area = st.empty()
        sonuc_placeholder = st.empty()

        kayitlar = []
        basarili = 0
        web_bulunamadi = 0
        hata_sayisi = 0

        status_area.info(f"🚀 {SCAN_MODE} başladı. Aynı anda {max_workers} firma taranıyor.")

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

                tamamlanan = i + 1
                oran = tamamlanan / toplam_firma
                gecen = time.time() - baslangic_tarama
                tahmini_toplam = gecen / tamamlanan * toplam_firma if tamamlanan else 0
                kalan = max(tahmini_toplam - gecen, 0)

                progress_bar.progress(oran)
                status_area.info(f"İşleniyor: {tamamlanan}/{toplam_firma} | Son firma: {firma}")

                metrik_area.markdown(
                    f"""
                    **Mod:** {SCAN_MODE} &nbsp;&nbsp; | &nbsp;&nbsp;
                    **Paralel işlem:** {max_workers} &nbsp;&nbsp; | &nbsp;&nbsp;
                    **Başarılı:** {basarili} &nbsp;&nbsp; | &nbsp;&nbsp;
                    **Web bulunamadı:** {web_bulunamadi} &nbsp;&nbsp; | &nbsp;&nbsp;
                    **Hata:** {hata_sayisi} &nbsp;&nbsp; | &nbsp;&nbsp;
                    **Geçen:** {sure_formatla(gecen)} &nbsp;&nbsp; | &nbsp;&nbsp;
                    **Tahmini kalan:** {sure_formatla(kalan)}
                    """
                )

                if len(kayitlar) % 5 == 0 or i == toplam_firma - 1:
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

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
import os
import subprocess
import sys

def playwright_browser_kur():
    browser_path = os.path.expanduser("~/.cache/ms-playwright")
    if not os.path.exists(browser_path) or not os.listdir(browser_path):
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=False
        )

playwright_browser_kur()from datetime import datetime
import concurrent.futures
import pdfplumber
from urllib.parse import urlparse, urljoin, quote_plus
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AKTIF = True
except Exception:
    PLAYWRIGHT_AKTIF = False

# ============================================================
# SQUAREXPO FUAR MÜŞTERİ OTOMASYONU V3
# Daha dayanıklı canlı sürüm
# ============================================================

APP_TITLE = "SQUAREXPO Fuar Müşteri Otomasyonu V3"
DB_PATH = "fuar_verileri.db"
MAX_WORKERS_DEFAULT = 3
REQUEST_TIMEOUT = 15

# ------------------------------------------------------------
# STREAMLIT AYARLARI
# ------------------------------------------------------------
st.set_page_config(
    page_title=APP_TITLE,
    layout="wide",
    page_icon="🚀"
)

# ------------------------------------------------------------
# LOG AYARLARI
# ------------------------------------------------------------
logging.basicConfig(
    filename="squarexpo_v3.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ------------------------------------------------------------
# SESSION STATE
# ------------------------------------------------------------
if "ana_liste" not in st.session_state:
    st.session_state["ana_liste"] = []

if "son_hatalar" not in st.session_state:
    st.session_state["son_hatalar"] = []

if "son_islem_ozeti" not in st.session_state:
    st.session_state["son_islem_ozeti"] = ""


# ============================================================
# YARDIMCI FONKSİYONLAR
# ============================================================

def hata_kaydet(mesaj: str):
    """Hataları hem log dosyasına hem de panelde gösterilecek listeye kaydeder."""
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
        domain = parsed.netloc.lower().replace("www.", "")
        return domain
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
    """Retry destekli requests session oluşturur."""
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
    """Tek merkezden güvenli GET isteği."""
    session = yeni_session()
    try:
        res = session.get(
            url,
            headers=get_headers(referer),
            timeout=timeout,
            allow_redirects=True,
            verify=True
        )
        return res
    except requests.exceptions.SSLError:
        # Bazı eski fuar sitelerinde SSL problemi olabiliyor. Son çare olarak verify=False.
        try:
            res = session.get(
                url,
                headers=get_headers(referer),
                timeout=timeout,
                allow_redirects=True,
                verify=False
            )
            return res
        except Exception as e:
            raise e
    except Exception as e:
        raise e


# ============================================================
# VERİTABANI
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

    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_firma_adi 
        ON sonuclar(firma_adi)
    """)

    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_fuar_etiketi 
        ON sonuclar(fuar_etiketi)
    """)

    conn.commit()
    conn.close()


def verileri_toplu_kaydet(kayitlar):
    """SQLite kilitlenmesini azaltmak için kayıtları tek seferde yazar."""
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
            k.get("web_adresi", "Bulunamadı"),
            k.get("telefon", "Bulunamadı"),
            k.get("eposta", "Bulunamadı"),
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


# ============================================================
# URL'DEN KATILIMCI/FİRMA ÇEKME
# ============================================================

def firmalari_url_den_cek(url):
    """
    Katılımcı listesi URL'sinden olası firma adlarını çıkarmaya çalışır.
    Bu fonksiyon genel çalışır; her fuar sitesinin HTML yapısı farklı olabilir.
    """
    url = normalize_url(url)
    res = guvenli_get(url, timeout=25, referer="https://www.google.com/")

    if res.status_code >= 400:
        raise Exception(f"HTTP {res.status_code} hatası alındı.")

    html = res.text
    soup = BeautifulSoup(html, "html.parser")

    adaylar = []

    # Görünmeyen/işe yaramayan alanları kaldır
    for tag in soup(["script", "style", "noscript", "svg", "footer", "header", "nav"]):
        tag.decompose()

    # 1) Sık kullanılan HTML alanları
    selectorler = [
        "a", "h1", "h2", "h3", "h4",
        ".exhibitor", ".exhibitor-name", ".company", ".company-name",
        ".firma", ".firma-adi", ".katilimci", ".katilimci-adi",
        "[class*='exhibitor']", "[class*='company']", "[class*='firma']", "[class*='katilimci']",
        "[title]", "[data-title]", "[data-name]"
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

    # 2) JSON/HTML içinde firma benzeri alanları yakalama
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

    return firma_listesi_filtrele(adaylar)


def firma_listesi_filtrele(adaylar):
    yasakli = [
        "giriş", "kayıt", "menü", "iletişim", "fuar", "expo", "detay",
        "tıklayın", "ara", "sayfa", "home", "login", "register",
        "about", "contact", "privacy", "cookie", "kvkk", "terms",
        "sponsor", "visitor", "exhibitor", "download", "pdf", "map",
        "facebook", "instagram", "linkedin", "youtube", "twitter",
        "language", "english", "turkish", "read more", "show more",
        "stand", "booth", "hall", "category", "product", "service"
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
        if re.fullmatch(r"[\d\s\-\+\(\)]+", item):
            continue
        if not re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", item):
            continue

        temiz_liste.append(item)

    # Mükerrer temizliği
    seen = set()
    sonuc = []
    for item in temiz_liste:
        key = item.lower().strip()
        if key not in seen:
            seen.add(key)
            sonuc.append(item)

    return sorted(sonuc)


def firmalari_url_den_cek_playwright(url):
    """
    JavaScript ile yüklenen fuar sayfaları için gerçek tarayıcı motoru.
    Streamlit Cloud / VPS üzerinde çalışması için playwright ve chromium kurulmalıdır.
    """
    if not PLAYWRIGHT_AKTIF:
        raise Exception("Playwright kurulu değil. Terminalde: pip install playwright && playwright install chromium")

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

        # Sayfa aşağı kaydırılır; lazy-load varsa firmalar yüklensin
        for _ in range(6):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(1200)

        html = page.content()
        text = page.inner_text("body")

        browser.close()

    soup = BeautifulSoup(html, "html.parser")

    # HTML taglerinden aday çıkar
    selectorler = [
        "a", "h1", "h2", "h3", "h4", "h5",
        "div", "span", "p",
        "[class*='exhibitor']", "[class*='company']", "[class*='firma']",
        "[class*='katilimci']", "[class*='participant']",
        "[title]", "[data-title]", "[data-name]"
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

    # Body text satırlarından aday çıkar
    for line in text.split("\n"):
        temiz = firma_adi_temizle(line)
        if temiz:
            adaylar.append(temiz)

    return firma_listesi_filtrele(adaylar)


# ============================================================
# WEB SİTESİ BULMA
# ============================================================

def firma_websitesi_bul(firma_adi):
    """
    Bing ve DuckDuckGo HTML sonuçları üzerinden web sitesi bulmaya çalışır.
    Not: Canlı sunucularda arama motorları bazen engelleyebilir.
    Daha profesyonel kullanımda SerpAPI / Brave Search API önerilir.
    """
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

                # DuckDuckGo yönlendirme linkleri bazen uddg parametresinde gerçek URL taşır
                if "uddg=" in href:
                    try:
                        from urllib.parse import parse_qs
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

            # En temiz ilk sonucu dön
            for link in linkler:
                if link.startswith("http"):
                    return link

        except Exception as e:
            logging.warning(f"Arama hatası: {firma_adi} - {str(e)}")
            continue

    return ""


# ============================================================
# WEB SİTESİNDEN MAİL / TELEFON ÇEKME
# ============================================================

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

    # Türkiye ve uluslararası telefon formatları için esnek regex
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

    # Öncelik: contact / iletişim sayfaları
    adaylar = list(dict.fromkeys(adaylar))
    adaylar = sorted(adaylar, key=lambda x: 0 if any(k in x.lower() for k in ["contact", "iletisim", "iletişim"]) else 1)

    return adaylar[:4]


def websitesinden_iletisim_bul(web_url):
    sonuc = {
        "web_adresi": web_url or "Bulunamadı",
        "telefon": "Bulunamadı",
        "eposta": "Bulunamadı",
        "kaynak": "",
        "durum": "Başladı",
        "hata": ""
    }

    if not web_url:
        sonuc["durum"] = "Web sitesi bulunamadı"
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

        # Ana sayfada bulamazsa iletişim sayfalarına bak
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
                    logging.warning(f"İletişim sayfası okunamadı: {contact_url} - {str(e)}")
                    continue

        if mailler:
            sonuc["eposta"] = ", ".join(mailler)
        if telefonlar:
            sonuc["telefon"] = ", ".join(telefonlar)

        sonuc["kaynak"] = kaynak
        sonuc["durum"] = "Tamamlandı"

        if sonuc["eposta"] == "Bulunamadı" and sonuc["telefon"] == "Bulunamadı":
            sonuc["durum"] = "Web bulundu, iletişim bulunamadı"

    except Exception as e:
        sonuc["durum"] = "Hata"
        sonuc["hata"] = str(e)
        logging.error(f"Site iletişim hatası: {web_url} - {str(e)}")

    return sonuc


def derin_bilgi_bul(firma_adi):
    """
    Firma adı -> Web sitesi -> Mail/Telefon
    """
    sonuc = {
        "firma_adi": firma_adi,
        "web_adresi": "Bulunamadı",
        "telefon": "Bulunamadı",
        "eposta": "Bulunamadı",
        "kaynak": "",
        "durum": "",
        "hata": ""
    }

    try:
        time.sleep(random.uniform(1.0, 2.5))

        web = firma_websitesi_bul(firma_adi)

        if not web:
            sonuc["durum"] = "Web sitesi bulunamadı"
            return sonuc

        iletisim = websitesinden_iletisim_bul(web)

        sonuc.update(iletisim)
        sonuc["firma_adi"] = firma_adi

        return sonuc

    except Exception as e:
        sonuc["durum"] = "Hata"
        sonuc["hata"] = str(e)
        logging.error(f"Derin bilgi hatası: {firma_adi} - {str(e)}")
        return sonuc


# ============================================================
# PDF / EXCEL / MANUEL GİRİŞ
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
        raise Exception(f"PDF okuma hatası: {str(e)}")

    return firma_listesi_filtrele(firmalar)


def excel_firmalari_oku(excel_file):
    try:
        df_upload = pd.read_excel(excel_file)
        if df_upload.empty:
            return []

        ilk_sutun = df_upload.iloc[:, 0].dropna().astype(str).tolist()
        return firma_listesi_filtrele(ilk_sutun)
    except Exception as e:
        raise Exception(f"Excel okuma hatası: {str(e)}")


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
# ARAYÜZ
# ============================================================

tabloyu_hazirla()

st.title("🚀 SQUAREXPO Fuar Müşteri Otomasyonu V3")
st.caption("Katılımcı listesi URL / PDF / Excel / manuel girişten firma havuzu oluşturur; firma web sitesi, mail ve telefon bulmaya çalışır.")

with st.sidebar:
    st.header("⚙️ Tarama Ayarları")
    if PLAYWRIGHT_AKTIF:
        st.success("Playwright aktif: JS sayfaları okunabilir.")
    else:
        st.warning("Playwright pasif: Sadece statik HTML okunur.")
    fuar_etiketi = st.text_input("Fuar Etiketi", value="Genel_Liste")

    max_workers = st.slider(
        "Aynı anda taranacak firma sayısı",
        min_value=1,
        max_value=8,
        value=MAX_WORKERS_DEFAULT,
        help="Canlı sunucuda hata alırsan 1-3 arası kullan. Fazla artırmak IP engeli ve timeout riskini yükseltir."
    )

    listeyi_sifirla = st.checkbox("Yeni veri eklenince mevcut havuzu sıfırla", value=True)

    st.divider()

    if st.button("🧹 İşlem Havuzunu Temizle", use_container_width=True):
        st.session_state["ana_liste"] = []
        st.rerun()

    if st.button("🧯 Hata Loglarını Temizle", use_container_width=True):
        st.session_state["son_hatalar"] = []
        st.rerun()


t1, t2, t3, t4 = st.tabs(["🌐 URL Tarama", "📄 PDF Analiz", "📊 Excel Giriş", "📂 Manuel Liste"])


# ------------------------------------------------------------
# URL SEKMESİ
# ------------------------------------------------------------
with t1:
    st.subheader("🌐 Katılımcı Listesi URL Tarama")
    url_input = st.text_input(
        "Hedef URL",
        placeholder="https://ornekfuar.com/katilimci-listesi"
    )

    c1, c2 = st.columns([1, 3])
    with c1:
        url_button = st.button("🔍 URL'den Firmaları Çek", use_container_width=True)

    if url_button:
        if not url_input.strip():
            st.warning("Lütfen bir URL gir.")
        else:
            try:
                with st.spinner("URL okunuyor ve firma isimleri çıkarılıyor..."):
                    firmalar = firmalari_url_den_cek(url_input)

                    # Statik HTML'den sonuç çıkmazsa gerçek tarayıcı motorunu dene
                    if not firmalar:
                        st.warning("Statik HTML içinde firma bulunamadı. JavaScript tarayıcı motoru deneniyor...")
                        firmalar = firmalari_url_den_cek_playwright(url_input)

                    adet = listeye_ekle(firmalar, listeyi_sifirla=listeyi_sifirla)

                if adet > 0:
                    st.success(f"✅ {adet} firma havuza aktarıldı.")
                    st.rerun()
                else:
                    st.error("Bu URL'den firma adı çıkarılamadı. Site veriyi gizli API ile çekiyor veya bot erişimini kısıtlıyor olabilir.")
            except Exception as e:
                hata_kaydet(f"URL tarama hatası: {str(e)}")
                st.error(f"URL tarama hatası: {str(e)}")


# ------------------------------------------------------------
# PDF SEKMESİ
# ------------------------------------------------------------
with t2:
    st.subheader("📄 PDF Katılımcı Kataloğu Analiz")
    pdf_file = st.file_uploader("Katalog PDF'i yükleyin", type=["pdf"])

    if pdf_file:
        try:
            with st.spinner("PDF okunuyor..."):
                pdf_firmalar = pdf_firmalari_oku(pdf_file)

            st.info(f"PDF içinde {len(pdf_firmalar)} olası firma adı bulundu.")
            if pdf_firmalar:
                st.dataframe(pd.DataFrame({"Firma Adı": pdf_firmalar}), use_container_width=True)

            if st.button("📥 PDF Firmalarını Havuza Aktar", use_container_width=True):
                adet = listeye_ekle(pdf_firmalar, listeyi_sifirla=listeyi_sifirla)
                st.success(f"✅ {adet} firma havuza aktarıldı.")
                st.rerun()

        except Exception as e:
            hata_kaydet(str(e))
            st.error(str(e))


# ------------------------------------------------------------
# EXCEL SEKMESİ
# ------------------------------------------------------------
with t3:
    st.subheader("📊 Excel Firma Listesi Giriş")
    excel_file = st.file_uploader("Firma Listesi Excel'i yükleyin", type=["xlsx", "xls"])

    if excel_file:
        try:
            excel_firmalar = excel_firmalari_oku(excel_file)

            st.info(f"Excel içinde {len(excel_firmalar)} firma bulundu. İlk sütun firma adı kabul edilir.")
            if excel_firmalar:
                st.dataframe(pd.DataFrame({"Firma Adı": excel_firmalar}), use_container_width=True)

            if st.button("📊 Excel Firmalarını Havuza Aktar", use_container_width=True):
                adet = listeye_ekle(excel_firmalar, listeyi_sifirla=listeyi_sifirla)
                st.success(f"✅ {adet} firma havuza aktarıldı.")
                st.rerun()

        except Exception as e:
            hata_kaydet(str(e))
            st.error(str(e))


# ------------------------------------------------------------
# MANUEL SEKMESİ
# ------------------------------------------------------------
with t4:
    st.subheader("📂 Manuel Firma Listesi")
    manuel_input = st.text_area(
        "Firma isimlerini yapıştırın",
        placeholder="Her satıra bir firma adı gelecek şekilde yapıştırın.",
        height=220
    )

    if st.button("➕ Manuel Listeyi Havuza Aktar", use_container_width=True):
        if not manuel_input.strip():
            st.warning("Liste boş görünüyor.")
        else:
            manuel_firmalar = [f.strip() for f in manuel_input.split("\n") if f.strip()]
            adet = listeye_ekle(manuel_firmalar, listeyi_sifirla=listeyi_sifirla)
            st.success(f"✅ {adet} firma havuza aktarıldı.")
            st.rerun()


# ============================================================
# İŞLEM HAVUZU
# ============================================================

st.divider()
st.subheader(f"📋 İşlem Havuzu: {len(st.session_state['ana_liste'])} Firma")

if st.session_state["ana_liste"]:
    havuz_df = pd.DataFrame({"Firma Adı": st.session_state["ana_liste"]})
    st.dataframe(havuz_df, use_container_width=True, height=300)

    c1, c2 = st.columns([2, 1])

    with c1:
        tara = st.button("⚡ FİRMALARI TARA VE ARŞİVE KAYDET", use_container_width=True)

    with c2:
        if st.button("📥 Sadece Havuzu Excel İndir", use_container_width=True):
            pass

    # Havuz Excel indirme
    output_havuz = io.BytesIO()
    with pd.ExcelWriter(output_havuz, engine="openpyxl") as writer:
        havuz_df.to_excel(writer, index=False)

    st.download_button(
        label="📥 Havuzu Excel Olarak İndir",
        data=output_havuz.getvalue(),
        file_name=f"{fuar_etiketi}_firma_havuzu.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

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
                        "web_adresi": "Bulunamadı",
                        "telefon": "Bulunamadı",
                        "eposta": "Bulunamadı",
                        "kaynak": "",
                        "durum": "Hata",
                        "hata": str(e)
                    }

                res["fuar_etiketi"] = fuar_etiketi
                kayitlar.append(res)

                if res.get("durum") == "Tamamlandı":
                    basarili += 1
                elif "bulunamadı" in res.get("durum", "").lower():
                    web_bulunamadi += 1
                elif res.get("durum") == "Hata":
                    hata_sayisi += 1

                progress_bar.progress((i + 1) / len(firmalar))
                status_area.info(f"İşleniyor: {i + 1}/{len(firmalar)} | Son firma: {firma}")

                if len(kayitlar) % 5 == 0 or i == len(firmalar) - 1:
                    sonuc_placeholder.dataframe(pd.DataFrame(kayitlar), use_container_width=True)

        # Veritabanına tek seferde yaz
        verileri_toplu_kaydet(kayitlar)

        st.session_state["son_islem_ozeti"] = (
            f"Tamamlandı. Toplam: {len(kayitlar)} | "
            f"Başarılı: {basarili} | "
            f"Web bulunamadı: {web_bulunamadi} | "
            f"Hata: {hata_sayisi}"
        )

        st.success("✅ İşlem tamamlandı ve arşive kaydedildi.")
        st.info(st.session_state["son_islem_ozeti"])

        # İşlem bitince havuzu temizle
        st.session_state["ana_liste"] = []
        st.rerun()

else:
    st.info("Henüz işlem havuzunda firma yok. URL, PDF, Excel veya manuel girişten firma ekleyebilirsin.")


# ============================================================
# ARŞİV
# ============================================================

st.divider()
st.subheader("🗄️ Kalıcı Arşiv")

df_arsiv = arsivi_getir()

if not df_arsiv.empty:
    filtre_fuar = st.text_input("Arşiv içinde ara", placeholder="Firma adı, mail, web sitesi veya fuar etiketi yazın")

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
            label="📥 Arşivi Excel İndir",
            data=output.getvalue(),
            file_name=f"{fuar_etiketi}_fuar_liste.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    with c2:
        with st.expander("🗑️ Arşiv Temizle"):
            st.warning("Bu işlem tüm arşivi siler.")
            if st.button("Evet, Tüm Arşivi Sil"):
                arsivi_temizle()
                st.success("Arşiv temizlendi.")
                st.rerun()

else:
    st.info("Arşiv henüz boş.")


# ============================================================
# HATA PANELİ
# ============================================================

with st.expander("🧯 Son Hatalar / Sistem Logları"):
    if st.session_state["son_hatalar"]:
        for h in st.session_state["son_hatalar"]:
            st.code(h)
    else:
        st.info("Şu anda görünür hata yok.")

    st.caption("Ayrıca sunucu klasöründe squarexpo_v3.log dosyası oluşur.")

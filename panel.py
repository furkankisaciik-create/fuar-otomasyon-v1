import streamlit as st
import pandas as pd
from DrissionPage import WebPage, ChromiumOptions
import time
import io
import re
import sqlite3
import requests
from PyPDF2 import PdfReader
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# --- BULUT (CLOUD) AYARLARI ---
def get_browser_options():
    co = ChromiumOptions()
    co.set_paths(browser_path='/usr/bin/chromium') 
    co.headless() 
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    co.set_argument('--disable-dev-shm-usage')
    return co

# --- VERİTABANI İŞLEMLERİ ---
def tabloyu_hazirla():
    conn = sqlite3.connect('fuar_verileri.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sonuclar 
                 (fuar_etiketi TEXT, firma_adi TEXT, web_adresi TEXT, telefon TEXT, eposta TEXT, tarih TEXT)''')
    conn.commit()
    conn.close()

def veriyi_kaydet(etiket, firma, web, tel, mail):
    conn = sqlite3.connect('fuar_verileri.db')
    c = conn.cursor()
    tarih = datetime.now().strftime("%d/%m/%Y %H:%M")
    c.execute("INSERT INTO sonuclar VALUES (?, ?, ?, ?, ?, ?)", (etiket, firma, web, tel, mail, tarih))
    conn.commit()
    conn.close()

def arsivi_getir():
    conn = sqlite3.connect('fuar_verileri.db')
    try:
        df = pd.read_sql_query("SELECT * FROM sonuclar", conn)
    except:
        df = pd.DataFrame(columns=["fuar_etiketi", "firma_adi", "web_adresi", "telefon", "eposta", "tarih"])
    conn.close()
    return df

tabloyu_hazirla()

# --- SİSTEM AYARLARI ---
SISTEM_ISMI = "Fuar Müşteri Otomasyon Sistemi V1.0"
FIRMA_1 = "SQUAREXPO"
FIRMA_2 = "PERGE MİMARLIK"

st.set_page_config(page_title=SISTEM_ISMI, layout="wide", page_icon="🏢")

# --- BANNER ---
st.markdown(f"""
    <style>
    .banner-container {{ background: linear-gradient(90deg, #0F172A 0%, #1E3A8A 100%); padding: 20px; border-radius: 12px; text-align: center; color: white; border-bottom: 4px solid #F59E0B; }}
    .banner-title {{ font-size: 30px; font-weight: 800; }}
    </style>
    <div class="banner-container"><div class="banner-title">{SISTEM_ISMI}</div><div style='color:#F59E0B;'>{FIRMA_1} | {FIRMA_2}</div></div>
    """, unsafe_allow_html=True)

# --- YARDIMCI FONKSİYONLAR ---
def veri_ayikla(html):
    tel = re.findall(r'(?:\+90|0)?\s?\(?\d{3}\)?\s?\d{3}\s?\d{2}\s?\d{2}', html)
    mail = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)
    c_tel = next((t for t in tel if len(re.sub(r'\D', '', str(t))) >= 10), "Bulunamadı")
    c_mail = next((m for m in mail if not m.lower().endswith(('.png', '.jpg', '.jpeg', '.svg', '.webp'))), "Bulunamadı")
    return c_tel, c_mail

def tekli_sorgu(firma, etiket):
  def tekli_sorgu(firma, etiket):
    link = "Bulunamadı"
    t, m = "Bulunamadı", "Bulunamadı"
    
    # Gerçek tarayıcı kimlikleri (User-Agent) listesi
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36',
        'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    
    try:
        # AŞAMA 1: Arama motorunu atlayıp doğrudan Google'ın 'I'm Feeling Lucky' (Kendimi Şanslı Hissediyorum) mantığını simüle edelim
        # Bu yöntem doğrudan ilgili firmanın web sitesine yönlendirme linkini yakalamaya çalışır
        search_url = f"https://www.google.com/search?q={firma}+official+website&btnI=I"
        
        response = requests.get(search_url, headers=headers, timeout=15, allow_redirects=True)
        link = response.url # Eğer yönlendirme başarılıysa doğrudan site URL'sini alırız
        
        # Eğer hala Google'da kalmışsak (yönlendirme olmadıysa) arama sonuçlarından çekelim
        if "google.com/search" in link:
            links = re.findall(r'href="(https?://.*?)"', response.text)
            for l in links:
                if "google.com" not in l and "youtube" not in l:
                    link = l
                    break

        # AŞAMA 2: Site içeriğine erişim ve veri kazıma
        if link != "Bulunamadı" and "google.com" not in link:
            # Sitenin korumasını aşmak için ek parametreler
            site_r = requests.get(link, headers=headers, timeout=20, verify=False)
            site_r.encoding = site_r.apparent_encoding # Türkçe karakterler için
            t, m = veri_ayikla(site_r.text)
            
        veriyi_kaydet(etiket, firma, link, t, m)
        return True
        
    except Exception:
        # Eğer hiçbir şey işe yaramazsa en azından firmanın adıyla bir kayıt oluştur
        veriyi_kaydet(etiket, firma, link, "Erişim Yok", "Erişim Yok")
        return False
        # 2. AŞAMA: Bulunan siteye git ve iletişim bilgilerini çek
        if link != "Bulunamadı":
            p.get(link)
            time.sleep(4) # Sayfanın tam yüklenmesi için 4 saniye
            t, m = veri_ayikla(p.html)
            
            # Eğer ana sayfada bulamazsa /contact veya /iletisim sayfasına bakmayı dene
            if t == "Bulunamadı" and m == "Bulunamadı":
                contact_link = p.ele('text:iletişim') or p.ele('text:contact') or p.ele('text:İLETİŞİM')
                if contact_link:
                    contact_link.click()
                    time.sleep(3)
                    t, m = veri_ayikla(p.html)
        
        p.quit()
        veriyi_kaydet(etiket, firma, link, t, m)
        return True
        
    except Exception as e:
        if p: p.quit()
        veriyi_kaydet(etiket, firma, link, "Bağlantı Sorunu", "Bağlantı Sorunu")
        return False
        # 2. AŞAMA: Siteye Girip Veri Çekme
        if link != "Bulunamadı":
            co = get_browser_options()
            p = WebPage(addr_or_opts=co)
            p.get(link)
            time.sleep(3) # Sayfanın iyice açılmasını bekleyelim
            t, m = veri_ayikla(p.html)
            p.quit()
        
        veriyi_kaydet(etiket, firma, link, t, m)
        return True
        
    except Exception as e:
        veriyi_kaydet(etiket, firma, link, "Hata", "Hata")
        return False
# --- KENAR ÇUBUĞU ---
st.sidebar.markdown(f"### ⚙️ {FIRMA_1} Kontrol")
hiz = st.sidebar.slider("Tarama Hızı", 1, 5, 2)
fuar_etiketi = st.sidebar.text_input("Fuar Etiketi:", "Genel_Liste")

if 'ana_liste' not in st.session_state:
    st.session_state['ana_liste'] = []

# --- ANA PANEL ---
st.subheader("📥 Veri Giriş Kanalları")
k1, k2, k3, k4 = st.tabs(["🌐 URL", "📄 PDF", "📊 EXCEL", "📂 MANUEL"])

with k1:
    url_input = st.text_input("Web sitesi URL girin:")
    if st.button("URL'den Oku"):
        st.warning("Bu özellik bir sonraki güncellemede aktif olacak.")

with k2:
    pdf_dosya = st.file_uploader("Firma Listesi içeren PDF yükleyin", type=['pdf'])
    if pdf_dosya:
        reader = PdfReader(pdf_dosya)
        pdf_metin = ""
        for page in reader.pages:
            pdf_metin += page.extract_text()
        # Basit bir mantıkla satırları firma ismi olarak alıyoruz
        firmalar = [f.strip() for f in pdf_metin.split('\n') if len(f.strip()) > 2]
        if st.button(f"{len(firmalar)} Firmayı PDF'den Aktar"):
            st.session_state['ana_liste'] = firmalar
            st.success("PDF Verileri Havuza Alındı!")

with k3:
    excel_dosya = st.file_uploader("Excel Dosyası Yükleyin", type=['xlsx', 'xls'])
    if excel_dosya:
        df_excel = pd.read_excel(excel_dosya)
        st.write("Dosya Önizlemesi:", df_excel.head())
        kolon = st.selectbox("Firma isimlerinin olduğu kolonu seçin:", df_excel.columns)
        if st.button("Excel'den Aktar"):
            st.session_state['ana_liste'] = df_excel[kolon].astype(str).tolist()
            st.success("Excel Verileri Havuza Alındı!")

with k4:
    st.subheader("📝 Manuel Veri Girişi")
    st.info("Kendi bulduğunuz firma bilgilerini buraya girerek doğrudan tabloya ekleyebilirsiniz.")
    
    # Form yapısı verilerin düzenli girilmesini sağlar
    with st.form("manuel_ekleme_formu", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            m_firma = st.text_input("Firma Adı *")
            m_web = st.text_input("Web Adresi", value="www.")
        with col2:
            m_tel = st.text_input("Telefon")
            m_mail = st.text_input("E-posta")
        
        submit_button = st.form_submit_button("📥 Tabloya Kaydet")
        
        if submit_button:
            if m_firma:
                # Bot çalıştırmadan doğrudan veritabanına (Kalıcı Arşiv) kaydediyoruz
                veriyi_kaydet(st.session_state.get('fuar_etiketi', 'Genel_Liste'), m_firma, m_web, m_tel, m_mail)
                st.success(f"✅ {m_firma} başarıyla arşive eklendi!")
                st.rerun() 
            else:
                st.error("Lütfen firma adını giriniz.")

# --- İŞLEME BÖLÜMÜ ---
if st.session_state['ana_liste']:
    st.divider()
    st.info(f"📋 Havuzda **{len(st.session_state['ana_liste'])}** firma taranmayı bekliyor.")
    if st.button("🚀 TARAMAYI VE KAYDI BAŞLAT"):
        bar = st.progress(0)
        toplam = len(st.session_state['ana_liste'])
        for i, firma in enumerate(st.session_state['ana_liste']):
            tekli_sorgu(firma, fuar_etiketi)
            bar.progress((i + 1) / toplam)
            st.toast(f"{firma} işlendi!")
        st.success("Tüm liste başarıyla tarandı ve Arşive kaydedildi!")
        st.session_state['ana_liste'] = [] 
        st.rerun()

# --- ARŞİV ---
st.divider()
st.subheader("🗄️ KALICI ARŞİV")
df_arsiv = arsivi_getir()
if not df_arsiv.empty:
    st.dataframe(df_arsiv, use_container_width=True)
    xlsx = io.BytesIO()
    with pd.ExcelWriter(xlsx, engine='openpyxl') as writer:
        df_arsiv.to_excel(writer, index=False)
    st.download_button("📥 Arşivi Excel Olarak İndir", xlsx.getvalue(), "fuar_arsiv.xlsx")
else:
    st.info("Henüz kayıtlı veri bulunmuyor. Bir tarama başlatın.")

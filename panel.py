import streamlit as st
import pandas as pd
from DrissionPage import WebPage
import time
import io
import re
import requests
from PyPDF2 import PdfReader
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# --- SİSTEM AYARLARI ---
SISTEM_ISMI = "Fuar Müşteri Otomasyon Sistemi V1.0"
FIRMA_1 = "SQUAREXPO"
FIRMA_2 = "PERGE MİMARLIK"

if 'sekme_basligi' not in st.session_state:
    st.session_state['sekme_basligi'] = SISTEM_ISMI

st.set_page_config(page_title=st.session_state['sekme_basligi'], layout="wide", page_icon="🏢")

# --- KURUMSAL BANNER TASARIMI ---
st.markdown(f"""
    <style>
    .banner-container {{
        background: linear-gradient(90deg, #0F172A 0%, #1E3A8A 100%);
        padding: 25px;
        border-radius: 12px;
        text-align: center;
        color: white;
        margin-bottom: 20px;
        border-bottom: 4px solid #F59E0B;
    }}
    .banner-title {{ font-size: 32px; font-weight: 800; text-transform: uppercase; }}
    .brand-footer {{ display: flex; justify-content: center; gap: 40px; margin-top: 10px; font-weight: 700; color: #F59E0B; }}
    </style>

    <div class="banner-container">
        <div class="banner-title">{SISTEM_ISMI}</div>
        <div class="brand-footer">
            <span>{FIRMA_1}</span> | <span>{FIRMA_2}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- HAFIZA VE FONKSİYONLAR ---
if 'toplanan_veriler' not in st.session_state: st.session_state['toplanan_veriler'] = []
if 'ana_liste' not in st.session_state: st.session_state['ana_liste'] = []
if 'tablo_arsivi' not in st.session_state: st.session_state['tablo_arsivi'] = {}

def veri_ayikla(html):
    tel = re.findall(r'(?:\+90|0)?\s?\(?\d{3}\)?\s?\d{3}\s?\d{2}\s?\d{2}', html)
    mail = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)
    c_tel = next((t for t in tel if len(re.sub(r'\D', '', str(t))) >= 10), "Bulunamadı")
    c_mail = next((m for m in mail if not m.lower().endswith(('.png', '.jpg', '.jpeg', '.svg', '.webp'))), "Bulunamadı")
    return c_tel, c_mail

def pdf_metin_cikar(kaynak):
    try:
        reader = PdfReader(kaynak)
        metin = ""
        for page in reader.pages:
            metin += page.extract_text() or ""
        # Satırları temizle ve listele
        temiz_liste = [s.strip() for s in metin.split('\n') if len(s.strip()) > 3]
        return list(dict.fromkeys(temiz_liste))
    except Exception as e:
        st.error(f"PDF Okuma Hatası: {e}")
        return []

def tekli_sorgu(firma):
    p = None
    try:
        p = WebPage()
        p.get(f'https://www.bing.com/search?q={firma} resmi web sitesi iletişim')
        time.sleep(1); link = p.ele('tag:h2').ele('tag:a').attr('href')
        p.get(link); time.sleep(1); t, m = veri_ayikla(p.html); p.quit()
        return {"Firma Adı": firma, "Web Adresi": link, "Telefon": t, "E-posta": m}
    except:
        if p: p.quit()
        return {"Firma Adı": firma, "Web Adresi": "Bulunamadı", "Telefon": "Bulunamadı", "E-posta": "Bulunamadı"}

# --- YAN PANEL ---
st.sidebar.markdown(f"### ⚙️ {FIRMA_1} Kontrol")
hiz_ayari = st.sidebar.slider("Tarama Hızı", 1, 10, 5)
fuar_etiketi = st.sidebar.text_input("Fuar Etiketi:", "Fuar_Listesi")

# --- 4 KANAL GİRİŞ PANELİ ---
st.markdown("### 📥 Veri Giriş Kanalları")
kanal1, kanal2, kanal3, kanal4 = st.tabs([
    "🌐 1. URL (WEB/PDF)", 
    "📄 2. DOSYA (PDF)", 
    "📊 3. EXCEL", 
    "📂 4. MANUEL"
])

with kanal1:
    url_adresi = st.text_input("Web sitesi veya PDF Linki yapıştırın:")
    if st.button("Kaynağı Çözümle"):
        with st.spinner("Veriler ayıklanıyor..."):
            # KRİTİK: URL PDF Mİ KONTROLÜ
            if ".pdf" in url_adresi.lower() or "pdf" in url_adresi.lower():
                try:
                    response = requests.get(url_adresi, timeout=15)
                    st.session_state['ana_liste'] = pdf_metin_cikar(io.BytesIO(response.content))
                    st.toast("PDF Linki başarıyla okundu.")
                except Exception as e:
                    st.error(f"PDF Linkine ulaşılamadı: {e}")
            else:
                # Normal Web Sayfası Taraması
                p = WebPage(); p.get(url_adresi); time.sleep(4)
                tags = p.eles('tag:h3') + p.eles('tag:h4')
                st.session_state['ana_liste'] = list(set([t.text.strip() for t in tags if len(t.text.strip()) > 2]))
                p.quit()
                st.toast("Web sayfası tarandı.")
        st.rerun()

with kanal2:
    pdf_dosya = st.file_uploader("Bilgisayardan PDF Yükle", type=["pdf"])
    if pdf_dosya and st.button("Dosyayı Oku"):
        st.session_state['ana_liste'] = pdf_metin_cikar(pdf_dosya); st.rerun()

with kanal3:
    excel_dosya = st.file_uploader("Excel Dosyası Yükle", type=["xlsx", "xls"])
    if excel_dosya and st.button("Exceli Oku"):
        df_ex = pd.read_excel(excel_dosya)
        st.session_state['ana_liste'] = df_ex.iloc[:, 0].dropna().astype(str).tolist(); st.rerun()

with kanal4:
    manuel_input = st.text_area("İsimleri buraya yapıştırın:", height=150)
    if st.button("Listeyi Kaydet"):
        st.session_state['ana_liste'] = [x.strip() for x in manuel_input.split('\n') if x.strip()]; st.rerun()

# --- ANALİZ VE SONUÇ ---
st.divider()

if st.session_state['ana_liste']:
    liste = st.session_state['ana_liste']
    st.info(f"📋 Havuzda **{len(liste)}** firma hazır.")
    if st.button("🚀 OTOMASYONU BAŞLAT"):
        with ThreadPoolExecutor(max_workers=hiz_ayari) as executor:
            tarananlar = [d['Firma Adı'] for d in st.session_state['toplanan_veriler']]
            kalanlar = [f for f in liste if f not in tarananlar]
            for res in executor.map(tekli_sorgu, kalanlar):
                st.session_state['toplanan_veriler'].append(res)
                st.toast(f"Veri Alındı: {res['Firma Adı']}")
        st.session_state['tablo_arsivi'][f"{fuar_etiketi}_{datetime.now().strftime('%d%m_%H%M')}"] = pd.DataFrame(st.session_state['toplanan_veriler'])

    if st.session_state['toplanan_veriler']:
        df_final = pd.DataFrame(st.session_state['toplanan_veriler'])
        st.dataframe(df_final, use_container_width=True)
        xlsx_out = io.BytesIO(); df_final.to_excel(xlsx_out, index=False)
        st.download_button(f"📥 {fuar_etiketi} Excelini İndir", xlsx_out.getvalue(), f"{fuar_etiketi}.xlsx")

# ARŞİV
if st.session_state['tablo_arsivi']:
    with st.expander("🗄️ Geçmiş Tablo Arşivi"):
        secilen = st.selectbox("Arşiv Kaydı Seç:", list(st.session_state['tablo_arsivi'].keys()))
        st.dataframe(st.session_state['tablo_arsivi'][secilen], use_container_width=True)
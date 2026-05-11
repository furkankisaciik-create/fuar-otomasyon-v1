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
    # Streamlit Cloud'da Chromium yolu genellikle buradadır:
    co.set_paths(browser_path='/usr/bin/chromium') 
    co.headless() 
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--remote-debugging-port=9222')
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
    df = pd.read_sql_query("SELECT * FROM sonuclar", conn)
    conn.close()
    return df

tabloyu_hazirla()

# --- SİSTEM AYARLARI ---
SISTEM_ISMI = "Fuar Müşteri Otomasyon Sistemi V1.0"
FIRMA_1 = "SQUAREXPO"
FIRMA_2 = "PERGE MİMARLIK"

st.set_page_config(page_title=SISTEM_ISMI, layout="wide", page_icon="🏢")

# --- BANNER TASARIMI ---
st.markdown(f"""
    <style>
    .banner-container {{ background: linear-gradient(90deg, #0F172A 0%, #1E3A8A 100%); padding: 20px; border-radius: 12px; text-align: center; color: white; border-bottom: 4px solid #F59E0B; }}
    .banner-title {{ font-size: 30px; font-weight: 800; }}
    </style>
    <div class="banner-container"><div class="banner-title">{SISTEM_ISMI}</div><div style='color:#F59E0B;'>{FIRMA_1} | {FIRMA_2}</div></div>
    """, unsafe_allow_html=True)

def veri_ayikla(html):
    tel = re.findall(r'(?:\+90|0)?\s?\(?\d{3}\)?\s?\d{3}\s?\d{2}\s?\d{2}', html)
    mail = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)
    c_tel = next((t for t in tel if len(re.sub(r'\D', '', str(t))) >= 10), "Bulunamadı")
    c_mail = next((m for m in mail if not m.lower().endswith(('.png', '.jpg', '.jpeg', '.svg', '.webp'))), "Bulunamadı")
    return c_tel, c_mail

def tekli_sorgu(firma, etiket):
    p = None
    try:
        co = get_browser_options()
        p = WebPage(addr_or_opts=co)
        p.get(f'https://www.bing.com/search?q={firma} resmi web sitesi iletişim')
        time.sleep(1)
        link = p.ele('tag:h2').ele('tag:a').attr('href')
        p.get(link)
        time.sleep(1)
        t, m = veri_ayikla(p.html)
        p.quit()
        veriyi_kaydet(etiket, firma, link, t, m)
        return {"Firma": firma, "Web": link, "Tel": t, "Mail": m}
    except:
        if p: p.quit()
        veriyi_kaydet(etiket, firma, "Bulunamadı", "Bulunamadı", "Bulunamadı")
        return {"Firma": firma, "Web": "Bulunamadı", "Tel": "Bulunamadı", "Mail": "Bulunamadı"}

# --- ARAYÜZ ---
st.sidebar.markdown(f"### ⚙️ {FIRMA_1} Kontrol")
hiz = st.sidebar.slider("Tarama Hızı", 1, 5, 2)
fuar_etiketi = st.sidebar.text_input("Fuar Etiketi:", "Genel_Liste")

if 'ana_liste' not in st.session_state: st.session_state['ana_liste'] = []

k1, k2, k3, k4 = st.tabs(["🌐 URL", "📄 PDF", "📊 EXCEL", "📂 MANUEL"])

with k4:
    manuel = st.text_area("İsimleri Yapıştırın:")
    if st.button("Kaydet"):
        st.session_state['ana_liste'] = [x.strip() for x in manuel.split('\n') if x.strip()]
        st.rerun()

if st.session_state['ana_liste']:
    st.info(f"📋 {len(st.session_state['ana_liste'])} firma hazır.")
    if st.button("🚀 TARAMAYI BAŞLAT"):
        with ThreadPoolExecutor(max_workers=hiz) as executor:
            for _ in executor.map(lambda f: tekli_sorgu(f, fuar_etiketi), st.session_state['ana_liste']):
                st.toast("Veri Kaydedildi!")

st.divider()
st.subheader("🗄️ KALICI ARŞİV")
df = arsivi_getir()
if not df.empty:
    st.dataframe(df, use_container_width=True)

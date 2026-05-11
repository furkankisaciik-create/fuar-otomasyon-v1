import streamlit as st
import pandas as pd
import sqlite3
import requests
from bs4 import BeautifulSoup
import re
import time
import io
from datetime import datetime
import concurrent.futures
import pdfplumber

# --- SİSTEM AYARLARI ---
st.set_page_config(page_title="SQUAREXPO Otomasyon V2", layout="wide", page_icon="🚀")

# --- SESSION STATE BAŞLATMA ---
if 'ana_liste' not in st.session_state:
    st.session_state['ana_liste'] = []

# --- VERİTABANI FONKSİYONLARI ---
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
    df = pd.read_sql_query("SELECT * FROM sonuclar ORDER BY tarih DESC", conn)
    conn.close()
    return df

# --- DERİN TARAMA MOTORU (MİNİ SEKME MANTIĞI) ---
def derin_bilgi_bul(firma_adi):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    sonuc = {"web": "Bulunamadı", "tel": "Bulunamadı", "mail": "Bulunamadı"}
    
    # Çoklu motor araması (Bing üzerinden hızlı giriş)
    arama_sorgusu = f"https://www.bing.com/search?q={firma_adi.replace(' ', '+')}+official+website+contact"
    try:
        response = requests.get(arama_sorgusu, headers=headers, timeout=8)
        soup = BeautifulSoup(response.text, 'html.parser')
        links = [a['href'] for a in soup.find_all('a', href=True) if "http" in a['href']]
        
        for link in links:
            if not any(x in link for x in ["google", "bing", "facebook", "linkedin", "instagram", "youtube", "twitter", "microsoft"]):
                sonuc["web"] = link
                break
        
        if sonuc["web"] != "Bulunamadı":
            site_res = requests.get(sonuc["web"], headers=headers, timeout=8)
            text = site_res.text
            # İletişim bilgilerini ayıkla
            mail_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
            if mail_match: sonuc["mail"] = mail_match.group(0)
            tel_match = re.search(r'\+?\d[\d\s-]{8,15}', text)
            if tel_match: sonuc["tel"] = tel_match.group(0).strip()
    except: pass
    return sonuc

# --- ANA ARAYÜZ ---
tabloyu_hazirla()
st.title("🚀 Fuar Müşteri Otomasyonu V2.0")

fuar_etiketi = st.text_input("Fuar Etiketi:", value="Genel_Liste")

t1, t2, t3, t4 = st.tabs(["🌐 URL Tarama", "📄 PDF Analiz", "📊 Excel Giriş", "📂 Manuel Liste"])

# --- 1. URL SEKMESİ ---
with t1:
    url_input = st.text_input("Hedef URL (Katılımcı Listesi Sayfası):")
    if st.button("🔍 URL'den Firmaları Çek"):
        res = requests.get(url_input, headers={'User-Agent': 'Mozilla/5.0'})
        bulunanlar = list(set(re.findall(r'<(?:h3|strong|b)>(.*?)</(?:h3|strong|b)>', res.text)))
        st.session_state['ana_liste'] = [re.sub('<.*?>', '', f).strip() for f in bulunanlar if len(f) > 3]
        st.success(f"✅ {len(st.session_state['ana_liste'])} firma havuzuna alındı.")

# --- 2. PDF SEKMESİ (GERİ GELDİ) ---
with t2:
    pdf_file = st.file_uploader("Katalog PDF'i Yükleyin", type=['pdf'])
    if pdf_file:
        with pdfplumber.open(pdf_file) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() + "\n"
        # Satırları firma ismi olarak alalım
        pdf_firmalar = [f.strip() for f in text.split('\n') if len(f.strip()) > 4]
        if st.button(f"📥 {len(pdf_firmalar)} Firmayı PDF'den Havuza Aktar"):
            st.session_state['ana_liste'] = pdf_firmalar
            st.success("PDF verileri havuzda!")

# --- 3. EXCEL SEKMESİ (GERİ GELDİ) ---
with t3:
    excel_file = st.file_uploader("Firma Listesi Excel'i Yükleyin", type=['xlsx'])
    if excel_file:
        df_upload = pd.read_excel(excel_file)
        # İlk sütunu firma ismi kabul ediyoruz
        excel_firmalar = df_upload.iloc[:, 0].dropna().astype(str).tolist()
        if st.button(f"📊 {len(excel_firmalar)} Firmayı Excel'den Havuza Aktar"):
            st.session_state['ana_liste'] = excel_firmalar
            st.success("Excel verileri havuzda!")

# --- 4. MANUEL SEKMESİ ---
with t4:
    manuel_input = st.text_area("İsimleri Yapıştırın (Her satıra bir tane):")
    if st.button("➕ Listeye Ekle"):
        st.session_state['ana_liste'].extend([f.strip() for f in manuel_input.split('\n') if f.strip()])
        st.rerun()

# --- İŞLEME BÖLÜMÜ (HIZLI PARALEL MOTOR) ---
if st.session_state['ana_liste']:
    st.divider()
    st.subheader(f"📋 İşlem Havuzu ({len(st.session_state['ana_liste'])} Firma)")
    if st.button("⚡ FİRMALARI ARKA PLANDA TARA VE KAYDET", use_container_width=True):
        bar = st.progress(0)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(derin_bilgi_bul, f): f for f in st.session_state['ana_liste']}
            for i, future in enumerate(concurrent.futures.as_completed(futures)):
                f_adi = futures[future]
                res = future.result()
                veriyi_kaydet(fuar_etiketi, f_adi, res["web"], res["tel"], res["mail"])
                bar.progress((i + 1) / len(st.session_state['ana_liste']))
        st.success("✅ İşlem Tamamlandı! Arşiv Güncellendi.")
        st.session_state['ana_liste'] = []
        st.rerun()

# --- ARŞİV VE EXCEL İNDİR (MODERNE EDİLDİ) ---
st.divider()
df_arsiv = arsivi_getir()
st.subheader("🗄️ Kalıcı Arşiv")
if not df_arsiv.empty:
    st.dataframe(df_arsiv, use_container_width=True)
    
    c1, c2 = st.columns([1, 4])
    with c1:
        # Excel İndirme Butonu
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_arsiv.to_excel(writer, index=False)
        st.download_button(label="📥 Excel Olarak İndir", data=output.getvalue(), file_name="fuar_liste.xlsx")
    with c2:
        with st.expander("⚙️ Ayarlar"):
            if st.button("🗑️ Arşivi Tamamen Temizle"):
                conn = sqlite3.connect('fuar_verileri.db')
                conn.execute("DELETE FROM sonuclar")
                conn.commit()
                conn.close()
                st.rerun()
else:
    st.info("Arşiv henüz boş.")

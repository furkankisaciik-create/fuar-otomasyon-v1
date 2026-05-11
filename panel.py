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

# --- SİSTEM AYARLARI ---
st.set_page_config(page_title="SQUAREXPO Otomasyon V2", layout="wide", page_icon="🚀")

# --- SESSION STATE BAŞLATMA ---
if 'ana_liste' not in st.session_state:
    st.session_state['ana_liste'] = []
if 'fuar_etiketi' not in st.session_state:
    st.session_state['fuar_etiketi'] = "Genel_Liste"

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

# --- AKILLI TARAMA MOTORU (ARKA PLANDA ÇALIŞAN KISIM) ---
def derin_bilgi_bul(firma_adi):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/119.0.0.0'}
    sonuc = {"web": "Bulunamadı", "tel": "Bulunamadı", "mail": "Bulunamadı"}
    
    # Adım 1: Arama Motoru üzerinden siteyi bul (Bing/DuckDuckGo kombinasyonu)
    arama_sorgusu = f"https://www.bing.com/search?q={firma_adi.replace(' ', '+')}+official+website+contact"
    try:
        response = requests.get(arama_sorgusu, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        links = [a['href'] for a in soup.find_all('a', href=True) if "http" in a['href']]
        
        for link in links:
            if not any(x in link for x in ["google", "bing", "facebook", "linkedin", "instagram", "youtube", "twitter"]):
                sonuc["web"] = link
                break
        
        # Adım 2: Site içine girip "Cımbızla" veri çek (İstediğin Arka Plan Sekme Mantığı)
        if sonuc["web"] != "Bulunamadı":
            site_res = requests.get(sonuc["web"], headers=headers, timeout=10)
            text = site_res.text
            
            # E-posta Yakala
            mail_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
            if mail_match: sonuc["mail"] = mail_match.group(0)
            
            # Telefon Yakala
            tel_match = re.search(r'\+?\d[\d\s-]{8,15}', text)
            if tel_match: sonuc["tel"] = tel_match.group(0).strip()
            
    except:
        pass
    return sonuc

# --- ARAYÜZ ---
tabloyu_hazirla()
st.title("🚀 Fuar Müşteri Otomasyonu V2.0")

fuar_etiketi = st.text_input("Fuar Etiketi:", value=st.session_state['fuar_etiketi'])

tab_url, tab_pdf, tab_excel, tab_manuel = st.tabs(["🌐 URL Tarama", "📄 PDF Analiz", "📊 Excel Giriş", "📂 Manuel Liste"])

# 1. URL SEKMESİ (MÜSİAD VB. İÇİN DERİN TARAMA)
with tab_url:
    url_input = st.text_input("Hedef URL:")
    if st.button("URL'den Firma Ayıkla"):
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url_input, headers=headers)
        # <h3> veya <strong> içindeki her şeyi isim olarak yakalamaya çalışır
        bulunanlar = list(set(re.findall(r'<(?:h3|strong|b)>(.*?)</(?:h3|strong|b)>', res.text)))
        st.session_state['ana_liste'] = [re.sub('<.*?>', '', f).strip() for f in bulunanlar if len(f) > 3]
        st.success(f"{len(st.session_state['ana_liste'])} firma bulundu.")

# 4. MANUEL LİSTE (KOPYALA-YAPIŞTIR DESTEĞİ)
with tab_manuel:
    manuel_input = st.text_area("Firma İsimlerini Buraya Yapıştırın (Her satıra bir tane):")
    if st.button("Listeye Ekle"):
        yeni_firmalar = [f.strip() for f in manuel_input.split('\n') if f.strip()]
        st.session_state['ana_liste'].extend(yeni_firmalar)
        st.rerun()

# --- İŞLEME BÖLÜMÜ (HIZLANDIRILMIŞ PARALEL MOTOR) ---
if st.session_state['ana_liste']:
    st.divider()
    st.subheader(f"📋 İşlem Havuzu ({len(st.session_state['ana_liste'])} Firma)")
    
    if st.button("⚡ HIZLI TARAMAYI BAŞLAT (PARALEL)", use_container_width=True):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # AYNI ANDA 5 FİRMAYI TARAR (Hızın anahtarı burada)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_firma = {executor.submit(derin_bilgi_bul, f): f for f in st.session_state['ana_liste']}
            
            for i, future in enumerate(concurrent.futures.as_completed(future_to_firma)):
                firma = future_to_firma[future]
                data = future.result()
                veriyi_kaydet(fuar_etiketi, firma, data["web"], data["tel"], data["mail"])
                
                # Arayüzü güncelle
                progress = (i + 1) / len(st.session_state['ana_liste'])
                progress_bar.progress(progress)
                status_text.text(f"İşleniyor: {firma}")
        
        st.success("Tüm liste başarıyla arşive işlendi!")
        st.session_state['ana_liste'] = []
        st.rerun()

# --- ARŞİV VE YÖNETİM ---
st.divider()
df_arsiv = arsivi_getir()
st.subheader("🗄️ Kalıcı Arşiv")
st.dataframe(df_arsiv, use_container_width=True)

col_exp, col_clear = st.columns([4,1])
with col_exp:
    xlsx = io.BytesIO()
    with pd.ExcelWriter(xlsx, engine='openpyxl') as writer:
        df_arsiv.to_excel(writer, index=False)
    st.download_button("📥 Excel Olarak İndir", data=xlsx.getvalue(), file_name="fuar_liste.xlsx")

with col_clear:
    with st.expander("Ayarlar"):
        if st.button("🗑️ Arşivi Sıfırla"):
            conn = sqlite3.connect('fuar_verileri.db')
            conn.execute("DELETE FROM sonuclar")
            conn.commit()
            conn.close()
            st.rerun()

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
import hmac
from datetime import datetime, timedelta
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

APP_TITLE = "Fuar Müşteri Otomasyonu V3.1"
DB_PATH = "fuar_verileri.db"
MAX_WORKERS_DEFAULT = 3
REQUEST_TIMEOUT = 10

# Tarama modu ayarlari runtime'da sidebar'dan guncellenir
SCAN_MODE = "Dengeli"
SEARCH_QUERY_LIMIT = 6
PLAYWRIGHT_FALLBACK_ENABLED = True
WEBSITE_CACHE = {}
URL_WEBSITE_HINTS = {}


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

def auth_secret_get(name, default=""):
    value = os.environ.get(name, "")
    if value:
        return str(value)

    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass

    try:
        auth_config = st.secrets.get("auth", {})
        short_name = name.removeprefix("PANEL_").lower()
        if short_name in auth_config:
            return str(auth_config[short_name])
    except Exception:
        pass

    return str(default)


def auth_int_get(name, default):
    try:
        return int(auth_secret_get(name, default))
    except (TypeError, ValueError):
        return int(default)


def auth_config_getir():
    return {
        "username": auth_secret_get("PANEL_USERNAME"),
        "password": auth_secret_get("PANEL_PASSWORD"),
        "session_timeout_minutes": max(5, auth_int_get("PANEL_SESSION_TIMEOUT_MINUTES", 480)),
        "max_failed_attempts": max(3, auth_int_get("PANEL_MAX_FAILED_ATTEMPTS", 5)),
        "lock_seconds": max(30, auth_int_get("PANEL_LOGIN_LOCK_SECONDS", 90)),
    }


if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "auth_last_activity" not in st.session_state:
    st.session_state["auth_last_activity"] = 0.0
if "login_failed_attempts" not in st.session_state:
    st.session_state["login_failed_attempts"] = 0
if "login_locked_until" not in st.session_state:
    st.session_state["login_locked_until"] = 0.0


def auth_oturumunu_kontrol_et():
    if not st.session_state.get("authenticated", False):
        return False

    config = auth_config_getir()
    now = time.time()
    last_activity = float(st.session_state.get("auth_last_activity", 0.0) or 0.0)
    timeout_seconds = config["session_timeout_minutes"] * 60

    if last_activity and now - last_activity > timeout_seconds:
        st.session_state["authenticated"] = False
        st.session_state["auth_last_activity"] = 0.0
        return False

    st.session_state["auth_last_activity"] = now
    return True


def giris_ekrani():
    config = auth_config_getir()

    st.markdown("""
    <style>
    :root {
        --login-ink: #17212b;
        --login-muted: #64717d;
        --login-line: #d9e0e5;
        --login-surface: #ffffff;
        --login-canvas: #edf1f3;
        --login-brand: #123f3a;
        --login-brand-deep: #0b2d2a;
        --login-accent: #d7513b;
        --login-soft: #dcebe7;
    }

    [data-testid="stAppViewContainer"] {
        background:
            linear-gradient(90deg, rgba(18,63,58,0.035) 1px, transparent 1px),
            linear-gradient(rgba(18,63,58,0.035) 1px, transparent 1px),
            var(--login-canvas);
        background-size: 42px 42px;
    }

    [data-testid="stHeader"],
    [data-testid="stToolbar"],
    footer {
        display: none;
    }

    [data-testid="stMainBlockContainer"],
    .block-container {
        width: min(1120px, calc(100% - 40px));
        max-width: 1120px;
        padding: 0;
        margin: 0 auto;
    }

    .login-topline {
        display: flex;
        align-items: center;
        justify-content: space-between;
        min-height: 72px;
        color: var(--login-ink);
        border-bottom: 1px solid rgba(23,33,43,0.10);
        margin-bottom: 34px;
    }

    .login-wordmark {
        display: flex;
        align-items: center;
        gap: 13px;
    }

    .login-monogram {
        width: 38px;
        height: 38px;
        display: grid;
        place-items: center;
        color: #ffffff;
        background: var(--login-brand);
        border-radius: 6px;
        font-size: 14px;
        font-weight: 800;
    }

    .login-wordmark strong,
    .login-wordmark span {
        display: block;
        letter-spacing: 0;
    }

    .login-wordmark strong {
        color: var(--login-ink);
        font-size: 14px;
        line-height: 1.2;
    }

    .login-wordmark span {
        color: var(--login-muted);
        font-size: 11px;
        margin-top: 3px;
    }

    .login-environment {
        display: flex;
        align-items: center;
        gap: 8px;
        color: #46615d;
        font-size: 12px;
        font-weight: 650;
    }

    .login-environment i {
        display: block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #2d8c72;
        box-shadow: 0 0 0 4px rgba(45,140,114,0.12);
    }

    .login-brand-panel {
        min-height: 510px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        padding: 48px;
        color: #ffffff;
        background:
            linear-gradient(150deg, rgba(255,255,255,0.07), transparent 46%),
            var(--login-brand);
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 8px;
        box-shadow: 0 24px 60px rgba(23,33,43,0.14);
        position: relative;
        overflow: hidden;
    }

    .login-brand-panel::after {
        content: "";
        position: absolute;
        right: -72px;
        bottom: 86px;
        width: 250px;
        height: 1px;
        background: rgba(255,255,255,0.22);
        transform: rotate(-38deg);
        box-shadow:
            0 26px 0 rgba(255,255,255,0.12),
            0 52px 0 rgba(255,255,255,0.07);
    }

    .login-kicker {
        display: inline-flex;
        align-items: center;
        width: fit-content;
        min-height: 28px;
        padding: 0 10px;
        border: 1px solid rgba(255,255,255,0.20);
        border-radius: 4px;
        color: #d8ebe6;
        font-size: 11px;
        font-weight: 750;
        text-transform: uppercase;
    }

    .login-brand-panel h1 {
        max-width: 560px;
        margin: 24px 0 16px;
        color: #ffffff;
        font-size: clamp(36px, 4.3vw, 58px);
        line-height: 1.02;
        letter-spacing: 0;
        font-weight: 780;
    }

    .login-brand-panel p {
        max-width: 520px;
        margin: 0;
        color: rgba(255,255,255,0.72);
        font-size: 16px;
        line-height: 1.65;
    }

    .login-brand-footer {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 1px;
        border: 1px solid rgba(255,255,255,0.13);
        border-radius: 6px;
        overflow: hidden;
        position: relative;
        z-index: 1;
    }

    .login-brand-footer div {
        min-height: 76px;
        padding: 16px;
        background: rgba(6,31,29,0.32);
    }

    .login-brand-footer strong,
    .login-brand-footer span {
        display: block;
        letter-spacing: 0;
    }

    .login-brand-footer strong {
        color: #ffffff;
        font-size: 13px;
    }

    .login-brand-footer span {
        color: rgba(255,255,255,0.58);
        font-size: 11px;
        margin-top: 5px;
        line-height: 1.35;
    }

    .login-form-heading {
        padding: 22px 6px 20px;
    }

    .login-form-heading .eyebrow {
        color: var(--login-accent);
        font-size: 11px;
        font-weight: 800;
        text-transform: uppercase;
    }

    .login-form-heading h2 {
        margin: 10px 0 8px;
        color: var(--login-ink);
        font-size: 30px;
        line-height: 1.14;
        letter-spacing: 0;
    }

    .login-form-heading p {
        margin: 0;
        color: var(--login-muted);
        font-size: 14px;
        line-height: 1.55;
    }

    [data-testid="stForm"] {
        padding: 28px;
        background: var(--login-surface);
        border: 1px solid var(--login-line);
        border-radius: 8px;
        box-shadow: 0 18px 46px rgba(23,33,43,0.09);
    }

    [data-testid="stForm"] label p {
        color: #34414c;
        font-size: 13px;
        font-weight: 700;
    }

    [data-testid="stTextInput"] input {
        min-height: 48px;
        color: var(--login-ink);
        background: #f8fafb;
        border: 1px solid #cdd6dc;
        border-radius: 6px;
        font-size: 15px;
    }

    [data-testid="stTextInput"] input:focus {
        border-color: var(--login-brand);
        box-shadow: 0 0 0 3px rgba(18,63,58,0.12);
    }

    [data-testid="stFormSubmitButton"] button {
        min-height: 48px;
        margin-top: 8px;
        color: #ffffff;
        background: var(--login-brand);
        border: 1px solid var(--login-brand);
        border-radius: 6px;
        font-size: 14px;
        font-weight: 760;
    }

    [data-testid="stFormSubmitButton"] button:hover {
        color: #ffffff;
        background: var(--login-brand-deep);
        border-color: var(--login-brand-deep);
    }

    [data-testid="stAlert"] {
        border-radius: 6px;
        border-width: 1px;
    }

    .login-security-note {
        display: flex;
        align-items: flex-start;
        gap: 11px;
        margin: 18px 6px 0;
        color: var(--login-muted);
        font-size: 12px;
        line-height: 1.55;
    }

    .login-security-note b {
        display: block;
        flex: 0 0 auto;
        width: 22px;
        height: 22px;
        border-radius: 50%;
        color: var(--login-brand);
        background: var(--login-soft);
        text-align: center;
        line-height: 22px;
        font-size: 12px;
    }

    .login-legal {
        margin-top: 30px;
        padding: 18px 0 28px;
        color: #7a858e;
        border-top: 1px solid rgba(23,33,43,0.09);
        font-size: 11px;
        text-align: center;
    }

    @media (max-width: 840px) {
        [data-testid="stMainBlockContainer"],
        .block-container {
            width: min(100% - 28px, 620px);
        }

        .login-topline {
            margin-bottom: 18px;
        }

        .login-environment {
            display: none;
        }

        [data-testid="stHorizontalBlock"] {
            flex-direction: column;
        }

        [data-testid="column"] {
            width: 100%;
            flex: 1 1 100%;
        }

        .login-brand-panel {
            min-height: 335px;
            padding: 30px;
        }

        .login-brand-panel h1 {
            font-size: 38px;
        }

        .login-brand-footer {
            display: none;
        }

        .login-form-heading {
            padding-top: 10px;
        }
    }

    @media (max-width: 480px) {
        .login-topline {
            min-height: 62px;
        }

        .login-brand-panel {
            min-height: 300px;
            padding: 24px;
        }

        .login-brand-panel h1 {
            font-size: 32px;
        }

        .login-brand-panel p {
            font-size: 14px;
        }

        [data-testid="stForm"] {
            padding: 22px;
        }
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="login-topline">
        <div class="login-wordmark">
            <div class="login-monogram">PS</div>
            <div>
                <strong>PERGE × SQUAREXPO</strong>
                <span>Fuar Veri Operasyonları</span>
            </div>
        </div>
        <div class="login-environment"><i></i> Güvenli erişim servisi aktif</div>
    </div>
    """, unsafe_allow_html=True)

    brand_col, form_col = st.columns([1.18, 0.82])

    with brand_col:
        st.markdown("""
        <section class="login-brand-panel">
            <div>
                <div class="login-kicker">Kurumsal çalışma alanı</div>
                <h1>Fuar Veri<br>Operasyon Merkezi</h1>
                <p>
                    Yetkili ekipler için merkezi araştırma, doğrulama ve
                    müşteri veri yönetimi çalışma alanı.
                </p>
            </div>
            <div class="login-brand-footer">
                <div>
                    <strong>Perge Mimarlık</strong>
                    <span>Kurumsal çözüm ortağı</span>
                </div>
                <div>
                    <strong>Squarexpo</strong>
                    <span>Fuar ve etkinlik operasyonları</span>
                </div>
                <div>
                    <strong>V3.1</strong>
                    <span>Güvenli operasyon paneli</span>
                </div>
            </div>
        </section>
        """, unsafe_allow_html=True)

    with form_col:
        st.markdown("""
        <div class="login-form-heading">
            <div class="eyebrow">Yetkili kullanıcı erişimi</div>
            <h2>Hesabınıza giriş yapın</h2>
            <p>Kurumsal kullanıcı bilgilerinizle güvenli oturum başlatın.</p>
        </div>
        """, unsafe_allow_html=True)

        if not config["username"] or not config["password"]:
            st.error(
                "Giriş bilgileri yapılandırılmamış. Sunucuda PANEL_USERNAME ve "
                "PANEL_PASSWORD ortam değişkenlerini veya Streamlit Secrets ayarlarını tanımlayın."
            )
            st.stop()

        now = time.time()
        locked_until = float(st.session_state.get("login_locked_until", 0.0) or 0.0)
        remaining = max(0, int(locked_until - now))

        if remaining > 0:
            st.error(f"Çok fazla hatalı deneme yapıldı. {remaining} saniye sonra tekrar deneyin.")
            st.stop()

        with st.form("login_form", clear_on_submit=False):
            username = st.text_input(
                "Kullanıcı adı",
                placeholder="Kurumsal kullanıcı adınız",
                key="login_username"
            )
            password = st.text_input(
                "Şifre",
                type="password",
                placeholder="Şifrenizi girin",
                key="login_password"
            )
            submitted = st.form_submit_button(
                "Güvenli giriş yap",
                type="primary",
                use_container_width=True
            )

        st.markdown("""
        <div class="login-security-note">
            <b>✓</b>
            <span>Oturumlar zaman aşımı, hatalı deneme kilidi ve güvenli kimlik doğrulama ile korunur.</span>
        </div>
        """, unsafe_allow_html=True)

        if submitted:
            username_ok = hmac.compare_digest(username.strip(), config["username"])
            password_ok = hmac.compare_digest(password, config["password"])

            if username_ok and password_ok:
                st.session_state["authenticated"] = True
                st.session_state["auth_last_activity"] = time.time()
                st.session_state["login_failed_attempts"] = 0
                st.session_state["login_locked_until"] = 0.0
                st.rerun()

            failures = int(st.session_state.get("login_failed_attempts", 0)) + 1
            st.session_state["login_failed_attempts"] = failures

            if failures >= config["max_failed_attempts"]:
                st.session_state["login_failed_attempts"] = 0
                st.session_state["login_locked_until"] = time.time() + config["lock_seconds"]
                st.error(
                    f"Çok fazla hatalı deneme yapıldı. "
                    f"{config['lock_seconds']} saniye süreyle giriş kilitlendi."
                )
            else:
                st.error("Kullanıcı adı veya şifre hatalı.")

    st.markdown("""
    <div class="login-legal">
        Bu sistem yalnızca yetkilendirilmiş kullanıcıların erişimine açıktır.
        Tüm erişim denemeleri güvenlik politikalarına tabidir.
    </div>
    """, unsafe_allow_html=True)

    st.stop()


if not auth_oturumunu_kontrol_et():
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
                <h1 class="hero-title">Fuar Müşteri<br>Otomasyonu V3.1</h1>
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
            <span>URL, PDF, Excel ve manuel girişlerden firma isimlerini merkezi motorla ayıklar.</span>
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

if "url_website_hints" not in st.session_state:
    st.session_state["url_website_hints"] = {}

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


if "force_queue_run" not in st.session_state:
    st.session_state["force_queue_run"] = False



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


def url_website_hint_key(firma_adi):
    return firma_adi_temizle(firma_adi).lower().strip()


def url_website_hint_kaydet(firma_adi, web_url):
    firma = firma_adi_temizle(firma_adi)
    web = normalize_url(web_url)
    if not firma or not web or istenmeyen_link_mi(web):
        return
    key = url_website_hint_key(firma)
    URL_WEBSITE_HINTS[key] = web
    try:
        st.session_state.setdefault("url_website_hints", {})[key] = web
    except Exception:
        pass


def url_website_hint_getir(firma_adi):
    key = url_website_hint_key(firma_adi)
    try:
        web = st.session_state.get("url_website_hints", {}).get(key, "")
        if web:
            return normalize_url(web)
    except Exception:
        pass
    return normalize_url(URL_WEBSITE_HINTS.get(key, ""))


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
            tarih TEXT,
            web_guven INTEGER DEFAULT 0,
            mail_guven INTEGER DEFAULT 0,
            telefon_guven INTEGER DEFAULT 0,
            genel_guven INTEGER DEFAULT 0,
            manuel_kontrol TEXT DEFAULT 'Evet',
            sirket_tipi TEXT DEFAULT 'Belirsiz',
            ulke_tahmini TEXT DEFAULT 'Belirsiz',
            ulke_guven INTEGER DEFAULT 0
        )
    """)

    c.execute("CREATE INDEX IF NOT EXISTS idx_firma_adi ON sonuclar(firma_adi)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_fuar_etiketi ON sonuclar(fuar_etiketi)")

    # Kalıcı işlem kuyruğu: Uygulama kapanırsa kalan firmalar kaybolmaz
    c.execute("""
        CREATE TABLE IF NOT EXISTS islem_kuyrugu (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fuar_etiketi TEXT,
            firma_adi TEXT,
            durum TEXT DEFAULT 'Bekliyor',
            deneme_sayisi INTEGER DEFAULT 0,
            son_hata TEXT,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(fuar_etiketi, firma_adi)
        )
    """)

    c.execute("CREATE INDEX IF NOT EXISTS idx_kuyruk_fuar ON islem_kuyrugu(fuar_etiketi)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kuyruk_durum ON islem_kuyrugu(durum)")


    # Eski veritabanları için güven skoru kolonlarını ekle
    yeni_kolonlar = {
        "web_guven": "INTEGER DEFAULT 0",
        "mail_guven": "INTEGER DEFAULT 0",
        "telefon_guven": "INTEGER DEFAULT 0",
        "genel_guven": "INTEGER DEFAULT 0",
        "manuel_kontrol": "TEXT DEFAULT 'Evet'",
        "sirket_tipi": "TEXT DEFAULT 'Belirsiz'",
        "ulke_tahmini": "TEXT DEFAULT 'Belirsiz'",
        "ulke_guven": "INTEGER DEFAULT 0"
    }

    for kolon, tip in yeni_kolonlar.items():
        try:
            c.execute(f"ALTER TABLE sonuclar ADD COLUMN {kolon} {tip}")
        except Exception:
            pass


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
            tarih,
            int(k.get("web_guven", 0) or 0),
            int(k.get("mail_guven", 0) or 0),
            int(k.get("telefon_guven", 0) or 0),
            int(k.get("genel_guven", 0) or 0),
            k.get("manuel_kontrol", "Evet"),
            k.get("sirket_tipi", "Belirsiz"),
            k.get("ulke_tahmini", "Belirsiz"),
            int(k.get("ulke_guven", 0) or 0)
        ))

    c.executemany("""
        INSERT INTO sonuclar 
        (fuar_etiketi, firma_adi, web_adresi, telefon, eposta, kaynak, durum, hata, tarih,
         web_guven, mail_guven, telefon_guven, genel_guven, manuel_kontrol,
         sirket_tipi, ulke_tahmini, ulke_guven)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)

    conn.commit()
    conn.close()




def arsiv_klasor_sil(fuar_etiketi, kuyruk_dahil=True):
    """
    Seçili araştırma klasörünü arşivden siler.
    İstenirse aynı fuar etiketine ait işlem kuyruğunu da temizler.
    """
    conn = db_baglan()
    try:
        conn.execute("DELETE FROM sonuclar WHERE fuar_etiketi = ?", (fuar_etiketi,))
        if kuyruk_dahil:
            conn.execute("DELETE FROM islem_kuyrugu WHERE fuar_etiketi = ?", (fuar_etiketi,))
        conn.commit()
        ok = True
    except Exception:
        ok = False
    conn.close()
    return ok


def arsiv_filtreli_kayitlari_sil(fuar_etiketi, firma_listesi):
    """
    Seçili klasörde filtrelenmiş tabloda görünen firma kayıtlarını siler.
    """
    firmalar = kaynak_firmalarini_normalize_et(firma_listesi)
    if not firmalar:
        return 0

    conn = db_baglan()
    c = conn.cursor()
    silinen = 0

    try:
        for firma in firmalar:
            c.execute(
                "DELETE FROM sonuclar WHERE fuar_etiketi = ? AND firma_adi = ?",
                (fuar_etiketi, firma)
            )
            silinen += c.rowcount

            try:
                c.execute(
                    "DELETE FROM islem_kuyrugu WHERE fuar_etiketi = ? AND firma_adi = ?",
                    (fuar_etiketi, firma)
                )
            except Exception:
                pass

        conn.commit()
    except Exception:
        pass

    conn.close()
    return silinen



def arsiv_klasor_ozeti_getir():
    """
    Arşivi fuar etiketi / araştırma klasörü gibi özetler.
    """
    conn = db_baglan()
    try:
        df = pd.read_sql_query("""
            SELECT 
                fuar_etiketi,
                COUNT(*) AS toplam_kayit,
                SUM(CASE WHEN web_adresi IS NOT NULL AND web_adresi != '' AND web_adresi != 'Bulunamadi' THEN 1 ELSE 0 END) AS web_bulunan,
                SUM(CASE WHEN eposta IS NOT NULL AND eposta != '' AND eposta != 'Bulunamadi' THEN 1 ELSE 0 END) AS mail_bulunan,
                SUM(CASE WHEN telefon IS NOT NULL AND telefon != '' AND telefon != 'Bulunamadi' THEN 1 ELSE 0 END) AS telefon_bulunan,
                SUM(CASE WHEN genel_guven >= 75 THEN 1 ELSE 0 END) AS yuksek_guven,
                SUM(CASE WHEN genel_guven >= 45 AND genel_guven < 75 THEN 1 ELSE 0 END) AS orta_guven,
                SUM(CASE WHEN genel_guven < 45 OR genel_guven IS NULL THEN 1 ELSE 0 END) AS dusuk_guven,
                SUM(CASE WHEN manuel_kontrol = 'Evet' THEN 1 ELSE 0 END) AS manuel_kontrol,
                SUM(CASE WHEN sirket_tipi = 'Yerli' THEN 1 ELSE 0 END) AS yerli_firma,
                SUM(CASE WHEN sirket_tipi = 'Yabancı' THEN 1 ELSE 0 END) AS yabanci_firma,
                SUM(CASE WHEN sirket_tipi = 'Belirsiz' OR sirket_tipi IS NULL THEN 1 ELSE 0 END) AS belirsiz_firma,
                MIN(tarih) AS ilk_tarih,
                MAX(tarih) AS son_tarih
            FROM sonuclar
            GROUP BY fuar_etiketi
            ORDER BY son_tarih DESC
        """, conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


def arsiv_klasor_detay_getir(fuar_etiketi):
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
                web_guven,
                mail_guven,
                telefon_guven,
                genel_guven,
                manuel_kontrol,
                sirket_tipi,
                ulke_tahmini,
                ulke_guven,
                tarih
            FROM sonuclar
            WHERE fuar_etiketi = ?
            ORDER BY id DESC
        """, conn, params=(fuar_etiketi,))
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


def arsiv_eksikleri_havuza_al(fuar_etiketi, tip="web"):
    """
    Seçili arşiv klasöründe eksik veya düşük güvenli firmaları tekrar havuza alır.
    tip:
    - web: web bulunamayanlar
    - mail_tel: mail veya telefon eksik olanlar
    - dusuk_guven: genel güveni düşük olanlar
    - manuel: manuel kontrol gerekenler
    """
    df = arsiv_klasor_detay_getir(fuar_etiketi)
    if df.empty:
        return 0

    if tip == "web":
        mask = (df["web_adresi"].fillna("").isin(["", "Bulunamadi"]))
    elif tip == "mail_tel":
        mask = (
            df["eposta"].fillna("").isin(["", "Bulunamadi"]) |
            df["telefon"].fillna("").isin(["", "Bulunamadi"])
        )
    elif tip == "dusuk_guven":
        mask = (pd.to_numeric(df["genel_guven"], errors="coerce").fillna(0) < 45)
    elif tip == "manuel":
        mask = (df["manuel_kontrol"].fillna("") == "Evet")
    else:
        mask = (df["web_adresi"].fillna("").isin(["", "Bulunamadi"]))

    firmalar = df.loc[mask, "firma_adi"].dropna().astype(str).tolist()
    firmalar = kaynak_firmalarini_normalize_et(firmalar)

    mevcut = st.session_state.get("ana_liste", [])
    st.session_state["ana_liste"] = kaynak_firmalarini_normalize_et(mevcut + firmalar)
    kuyruga_firma_ekle(fuar_etiketi, firmalar)
    return len(firmalar)



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
                web_guven,
                mail_guven,
                telefon_guven,
                genel_guven,
                manuel_kontrol,
                sirket_tipi,
                ulke_tahmini,
                ulke_guven,
                tarih
            FROM sonuclar 
            ORDER BY id DESC
        """, conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df




def kuyruga_firma_ekle(fuar_etiketi, firmalar):
    """
    Bulunan tüm firmaları kalıcı işlem kuyruğuna yazar.
    Böylece 139 firma bulunduysa 139'u da veritabanında bekleyen iş olur.
    Sistem kapanırsa kalanlar kaybolmaz.
    """
    firmalar = kaynak_firmalarini_normalize_et(firmalar)
    if not firmalar:
        return 0

    conn = db_baglan()
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    eklendi = 0
    for firma in firmalar:
        try:
            c.execute("""
                INSERT OR IGNORE INTO islem_kuyrugu
                (fuar_etiketi, firma_adi, durum, deneme_sayisi, son_hata, created_at, updated_at)
                VALUES (?, ?, 'Bekliyor', 0, '', ?, ?)
            """, (fuar_etiketi, firma, now, now))
            if c.rowcount > 0:
                eklendi += 1
        except Exception:
            pass

    conn.commit()
    conn.close()
    return eklendi



def kuyruk_havuz_senkronize_et(fuar_etiketi, firmalar):
    """
    Mevcut işlem havuzunu kalıcı kuyrukla senkronize eder.
    """
    firmalar = kaynak_firmalarini_normalize_et(firmalar)
    if not firmalar:
        return {"toplam": 0, "yeni": 0, "kurtarilan": 0, "bekleyen": 0}

    yeni = kuyruga_firma_ekle(fuar_etiketi, firmalar)

    try:
        kurtarilan = kuyruk_takilanlari_bekliyora_al(fuar_etiketi, dakika=0)
    except Exception:
        kurtarilan = 0

    ozet = kuyruk_ozeti_getir(fuar_etiketi)
    return {
        "toplam": len(firmalar),
        "yeni": yeni,
        "kurtarilan": kurtarilan,
        "bekleyen": ozet.get("Bekliyor", 0),
    }



def kuyruk_ozeti_getir(fuar_etiketi):
    conn = db_baglan()
    try:
        df = pd.read_sql_query("""
            SELECT 
                durum,
                COUNT(*) AS adet
            FROM islem_kuyrugu
            WHERE fuar_etiketi = ?
            GROUP BY durum
        """, conn, params=(fuar_etiketi,))
    except Exception:
        df = pd.DataFrame()
    conn.close()

    ozet = {"Bekliyor": 0, "İşleniyor": 0, "Tamamlandı": 0, "Hata": 0}
    if not df.empty:
        for _, row in df.iterrows():
            ozet[str(row["durum"])] = int(row["adet"])
    return ozet


def kuyruk_bekleyen_firmalari_getir(fuar_etiketi, limit=50, sadece_islenmemis=True):
    """
    İşlem kuyruğundan sıradaki bekleyen/hatalı firmaları alır.
    Arşivde daha önce işlenmiş olanları atlar.
    """
    islenmisler = islenmis_firmalari_getir(fuar_etiketi) if sadece_islenmemis else set()

    conn = db_baglan()
    try:
        df = pd.read_sql_query("""
            SELECT firma_adi
            FROM islem_kuyrugu
            WHERE fuar_etiketi = ?
              AND durum IN ('Bekliyor', 'Hata')
            ORDER BY 
              CASE WHEN durum = 'Bekliyor' THEN 0 ELSE 1 END,
              deneme_sayisi ASC,
              id ASC
            LIMIT ?
        """, conn, params=(fuar_etiketi, int(limit) * 3))
    except Exception:
        df = pd.DataFrame()
    conn.close()

    if df.empty:
        return []

    firmalar = []
    for f in df["firma_adi"].dropna().astype(str).tolist():
        if sadece_islenmemis and f.lower().strip() in islenmisler:
            kuyruk_durum_guncelle(fuar_etiketi, f, "Tamamlandı")
            continue
        firmalar.append(f)
        if len(firmalar) >= limit:
            break

    return kaynak_firmalarini_normalize_et(firmalar)


def kuyruk_durum_guncelle(fuar_etiketi, firma_adi, durum, hata=""):
    conn = db_baglan()
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        if durum == "Hata":
            c.execute("""
                UPDATE islem_kuyrugu
                SET durum = ?, son_hata = ?, deneme_sayisi = COALESCE(deneme_sayisi, 0) + 1, updated_at = ?
                WHERE fuar_etiketi = ? AND firma_adi = ?
            """, (durum, str(hata)[:500], now, fuar_etiketi, firma_adi))
        else:
            c.execute("""
                UPDATE islem_kuyrugu
                SET durum = ?, son_hata = ?, updated_at = ?
                WHERE fuar_etiketi = ? AND firma_adi = ?
            """, (durum, str(hata)[:500], now, fuar_etiketi, firma_adi))
        conn.commit()
    except Exception:
        pass

    conn.close()


def kuyruk_toplu_durum_guncelle(fuar_etiketi, firmalar, durum):
    for f in firmalar:
        kuyruk_durum_guncelle(fuar_etiketi, f, durum)


def kuyruk_sifirla(fuar_etiketi):
    conn = db_baglan()
    try:
        conn.execute("DELETE FROM islem_kuyrugu WHERE fuar_etiketi = ?", (fuar_etiketi,))
        conn.commit()
    except Exception:
        pass
    conn.close()



def kuyruk_takilanlari_bekliyora_al(fuar_etiketi, dakika=5):
    """
    Uygulama kesilirse bazı işler 'İşleniyor' durumunda takılı kalabilir.
    Bu fonksiyon belirli süreden eski İşleniyor kayıtlarını tekrar Bekliyor yapar.
    """
    conn = db_baglan()
    c = conn.cursor()

    try:
        cutoff = (datetime.now() - timedelta(minutes=dakika)).strftime("%Y-%m-%d %H:%M:%S")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            UPDATE islem_kuyrugu
            SET durum = 'Bekliyor',
                son_hata = 'Otomatik kurtarma: işlem yarıda kesildiği için tekrar kuyruğa alındı',
                updated_at = ?
            WHERE fuar_etiketi = ?
              AND durum = 'İşleniyor'
              AND (updated_at IS NULL OR updated_at < ?)
        """, (now, fuar_etiketi, cutoff))
        adet = c.rowcount
        conn.commit()
    except Exception:
        adet = 0

    conn.close()
    return adet



def kuyruk_bekleyenleri_havuza_yansit(fuar_etiketi):
    """
    Bekleyenleri session havuzuna da ekler. Görsel olarak kullanıcının kalanları görmesini sağlar.
    """
    bekleyen = kuyruk_bekleyen_firmalari_getir(fuar_etiketi, limit=10000, sadece_islenmemis=True)
    mevcut = st.session_state.get("ana_liste", [])
    st.session_state["ana_liste"] = kaynak_firmalarini_normalize_et(mevcut + bekleyen)
    return len(bekleyen)



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




def metalexpo_site_home(web_url):
    try:
        u = normalize_url(web_url)
        p = urlparse(u)
        if not p.scheme or not p.netloc:
            return ""
        return f"{p.scheme}://{p.netloc}/"
    except Exception:
        return ""


def metalexpo_firma_adi_temizle(text):
    t = firma_adi_temizle(text)
    t = re.split(r"\bHALL\b|\bSALON\b|\bSTAND\b|\bBOOTH\b", t, flags=re.IGNORECASE)[0]
    t = re.sub(r"\s+", " ", t).strip(" -|")
    return t


def metalexpo_katilimci_listesi_cek(url, progress_callback=None):
    """
    Metal Expo sayfasi firma adini ve resmi site linkini ayni anchor icinde verir:
    FIRMA ADI HALL 7 / 7C-8 -> href resmi web sitesi.
    Bu adaptor genel HTML temizleyiciden once calisir ve web sitesi ipuclarini da saklar.
    """
    baslangic = time.time()
    url = normalize_url(url)

    def bildir(adim, bulunan=0):
        if progress_callback:
            try:
                progress_callback({
                    "adim": adim,
                    "sayfa_no": 1,
                    "toplam_sayfa": 1,
                    "bulunan": bulunan,
                    "gecen": int(time.time() - baslangic)
                })
            except Exception:
                pass

    bildir("METAL EXPO sayfasi okunuyor...", 0)

    r = guvenli_get(url, timeout=REQUEST_TIMEOUT, referer="https://www.google.com/")
    if r.status_code >= 400:
        raise Exception(f"METAL EXPO HTTP {r.status_code} hatasi alindi.")

    soup = BeautifulSoup(r.text or "", "html.parser")
    firmalar = []

    for a in soup.find_all("a", href=True):
        text = firma_adi_temizle(a.get_text(" "))
        if not re.search(r"\bHALL\s+\d+", text, flags=re.IGNORECASE):
            continue

        firma = metalexpo_firma_adi_temizle(text)
        if not firma or len(firma) < 2 or len(firma) > 110:
            continue

        firmalar.append(firma)

        href = normalize_url(a.get("href", ""), base_url=url)
        home = metalexpo_site_home(href)
        if home and not istenmeyen_link_mi(home):
            url_website_hint_kaydet(firma, home)

        if len(firmalar) % 25 == 0:
            bildir("METAL EXPO firmalari okunuyor...", len(set(x.lower() for x in firmalar)))

    final = []
    seen = set()
    for f in firmalar:
        key = f.lower().strip()
        if key and key not in seen:
            seen.add(key)
            final.append(f)

    bildir("METAL EXPO katilimci cekimi tamamlandi.", len(final))
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

    elif "metalexpo.com.tr" in url_l:
        if progress_callback:
            progress_callback({"adim": "METAL EXPO adaptoru secildi.", "sayfa_no": 0, "toplam_sayfa": 0, "bulunan": 0, "gecen": 0})
        firmalar = metalexpo_katilimci_listesi_cek(url, progress_callback=progress_callback)

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



# ============================================================
# UNIVERSAL BRAND / DOMAIN INTELLIGENCE V3.1
# ============================================================

GENERIC_COMPANY_WORDS_FOR_DOMAIN = {
    # Turkish legal/company words
    "anonim", "limited", "sirket", "sirketi", "sanayi", "san", "ticaret", "tic",
    "ltd", "sti", "şti", "as", "aş", "a", "s", "ve", "ile", "hizmet", "hizmetleri",
    "endustri", "endustriyel", "endüstri", "endüstriyel",

    # English legal/company words
    "company", "co", "ltd", "limited", "inc", "llc", "corp", "corporation", "group",
    "holding", "industry", "industries", "industrial", "international", "global",

    # Sector/generic words that often do NOT appear in the official domain
    "shipyard", "shipyards", "ship", "marine", "maritime", "denizcilik", "tersane",
    "tersanesi", "gemi", "yacht", "yat", "boat", "boatyard",
    "makina", "makine", "machine", "machinery", "teknoloji", "technology",
    "software", "yazilim", "yazılım", "metal", "plastik", "plastic", "kimya",
    "chemical", "chemicals", "gida", "gıda", "food", "ambalaj", "packaging",
    "pompa", "pump", "pumps", "motor", "valve", "valves", "otomotiv", "automotive",
    "elektrik", "electric", "electronics", "elektronik", "medikal", "medical",
    "kozmetik", "cosmetic", "cosmetics", "tekstil", "textile", "insaat", "inşaat",
    "construction", "energy", "enerji"
}


def normalize_domain_token(text):
    t = turkce_karakter_temizle(str(text or "").lower())
    t = re.sub(r"[^a-z0-9]", "", t)
    return t


def firma_domain_kelime_profili(firma_adi):
    """
    Firma adını marka kökü ve yardımcı kelimeler olarak ayırır.
    Ana fikir:
    - Resmi domain çoğu zaman ilk güçlü marka kelimesidir.
    - Sektör/unvan kelimeleri domain içinde bulunmayabilir.
    Örnek:
    Sanmar Shipyards -> marka: sanmar
    Sefine Shipyard -> marka: sefine
    Çeksan -> marka: ceksan
    ABBA Teknoloji Yazılım -> marka: abba, destek: teknoloji/yazilim
    """
    raw_words = firma_onemli_kelimeleri(firma_adi) if "firma_onemli_kelimeleri" in globals() else firma_adi_sadelestir(firma_adi)

    marka_adaylari = []
    destek_kelimeler = []
    jenerik_kelimeler = []

    for w in raw_words:
        token = normalize_domain_token(w)
        if not token or len(token) < 2:
            continue

        if token in GENERIC_COMPANY_WORDS_FOR_DOMAIN:
            jenerik_kelimeler.append(token)
        else:
            marka_adaylari.append(token)

    # Marka adayı yoksa ilk kelimeyi marka kabul et
    if not marka_adaylari and raw_words:
        token = normalize_domain_token(raw_words[0])
        if token:
            marka_adaylari.append(token)

    marka = marka_adaylari[0] if marka_adaylari else ""

    # Marka haricindeki ayırt edici kelimeler destek sinyali olur
    destek_kelimeler = [x for x in marka_adaylari[1:5] if x != marka]

    return {
        "marka": marka,
        "marka_adaylari": marka_adaylari[:5],
        "destek_kelimeler": destek_kelimeler[:5],
        "jenerik_kelimeler": jenerik_kelimeler[:8],
        "tum_tokenlar": list(dict.fromkeys(marka_adaylari + destek_kelimeler + jenerik_kelimeler))
    }


def domain_root_al(url):
    d = domain_al(url).lower().replace("www.", "")
    d = re.sub(r"\.(com\.tr|net\.tr|org\.tr|com\.cn|co\.uk|co\.kr|com|net|org|tr|cn|de|it|fr|uk|us|in|jp|ru|pl|nl|be|bg|hu|pk|tw|ae|es|pt|io|co)$", "", d)
    return normalize_domain_token(d)


def universal_domain_match_score(url, firma_adi, page_text=""):
    """
    Evrensel domain doğrulama skoru.
    Firmaya özel kural yazmaz. Marka-domain uyumu, destek kelimeler, sayfa içeriği ve TLD sinyallerini birlikte puanlar.
    """
    if not url or istenmeyen_link_mi(url):
        return -100

    domain = domain_al(url)
    root = domain_root_al(url)
    profile = firma_domain_kelime_profili(firma_adi)

    marka = profile["marka"]
    destek = profile["destek_kelimeler"]
    jenerik = profile["jenerik_kelimeler"]
    tum = profile["tum_tokenlar"]

    text = turkce_karakter_temizle((page_text or "").lower()[:15000])
    score = 0

    if not root:
        return -100

    # 1) Marka kökü en güçlü sinyal
    if marka:
        if root == marka:
            score += 85
        elif marka in root or root in marka:
            score += 68
        elif len(marka) >= 5 and marka[:5] in root:
            score += 38

    # 2) Diğer marka adayları destek sinyali
    for w in destek:
        if w in root:
            score += 28
        if w in text:
            score += 8

    # 3) Jenerik sektör kelimeleri domain içinde olursa artı ama zorunlu değil
    for w in jenerik:
        if w in root:
            score += 10
        if w in text:
            score += 5

    # 4) Sayfa içeriğinde marka ve firma kelimeleri
    if marka and marka in text:
        score += 22

    text_hit = 0
    for w in tum[:8]:
        if len(w) >= 3 and w in text:
            text_hit += 1
    if text_hit >= 2:
        score += 18
    elif text_hit == 1:
        score += 7

    # 5) Türkiye domain avantajı
    if domain.endswith(".com.tr"):
        score += 24
    elif domain.endswith(".tr"):
        score += 18
    elif domain.endswith(".com"):
        score += 8

    # 6) Contact / iletişim sayfası sinyali
    low_url = url.lower()
    if any(x in low_url for x in ["iletisim", "iletişim", "contact", "home/contact", "kurumsal", "about"]):
        score += 8

    # 7) Tek marka çok genel ise daha dikkatli ol
    risky_short = {"abc", "star", "mega", "global", "best", "pro", "max", "net", "sun", "blue", "red"}
    if marka in risky_short and root == marka and text_hit == 0:
        score -= 45

    # 8) Domain kökü marka ile alakasızsa ceza
    if marka and marka not in root and root not in marka:
        # destek kelime de yoksa alakasız olabilir
        if not any(w in root for w in destek):
            score -= 28

    return score


def universal_direct_domain_candidates(firma_adi):
    """
    Firma adından firmaya özel olmayan direkt domain adayları üretir.
    Önce marka kökü denenir, sonra marka+destek kombinasyonları.
    """
    profile = firma_domain_kelime_profili(firma_adi)
    marka = profile["marka"]
    destek = profile["destek_kelimeler"]

    roots = []
    if marka:
        roots.append(marka)

    for w in destek[:3]:
        roots.append(marka + w)
        roots.append(marka + "-" + w)

    roots = [r for r in list(dict.fromkeys(roots)) if r and len(r) >= 3]

    tlds = [
        ".com.tr", ".tr", ".com", ".net.tr", ".net", ".org",
        ".com.tr/iletisim", ".com.tr/contact", ".com.tr/en/contact",
        ".com.tr/home/contact", ".com/iletisim", ".com/contact",
        ".com/en/contact", ".com/home/contact"
    ]

    adaylar = []
    for r in roots:
        for tld in tlds:
            adaylar.append(f"https://www.{r}{tld}")
            adaylar.append(f"https://{r}{tld}")

    return list(dict.fromkeys(adaylar))[:80]


def universal_direct_domain_fallback_bul(firma_adi):
    """
    Arama motoru başarısız olursa direkt marka kökünden domainleri dener.
    """
    adaylar = universal_direct_domain_candidates(firma_adi)
    scored = []

    for aday in adaylar:
        try:
            sonuc = aday_site_oku_ve_puanla(aday, firma_adi)
            puan = sonuc.get("puan", -100)
            if puan >= 12:
                scored.append(sonuc)
        except Exception:
            continue

    if scored:
        scored = sorted(scored, key=lambda x: x.get("puan", 0), reverse=True)
        return scored[0]["url"]

    return ""



def firma_arama_sorgulari_uret(firma_adi):
    important_words = firma_onemli_kelimeleri(firma_adi)
    original = firma_adi_temizle(firma_adi)
    profile = firma_domain_kelime_profili(firma_adi)
    marka = profile["marka"]
    destek = profile["destek_kelimeler"]

    sorgular = []

    if original:
        sorgular.extend([
            f'"{original}"',
            f'"{original}" iletişim',
            f'"{original}" resmi web sitesi',
            f'"{original}" official website',
            f'"{original}" contact',
        ])

    if marka:
        sorgular.extend([
            f'{marka} resmi web sitesi',
            f'{marka} iletişim',
            f'{marka} contact',
            f'{marka} official website',
            f'{marka} site:com.tr',
            f'{marka}.com.tr'
        ])

    if important_words:
        marka2 = " ".join(important_words[:2])
        marka3 = " ".join(important_words[:3])

        for q in [marka3, marka2]:
            if q:
                sorgular.extend([
                    f'"{q}" resmi web sitesi',
                    f'"{q}" iletişim',
                    f'{q} site:com.tr',
                    f'{q} official website',
                    f'{q} contact'
                ])

    for w in destek[:3]:
        if marka and w:
            combo = marka + " " + w
            sorgular.extend([
                f'"{combo}" official website',
                f'"{combo}" contact',
                f'{combo} site:com.tr'
            ])

    final = []
    seen = set()
    for q in sorgular:
        k = q.lower().strip()
        if k and k not in seen:
            seen.add(k)
            final.append(q)

    return final[:20]


def domain_adaylari_uret(firma_adi):
    """
    V3.1 evrensel domain aday motoru.
    Önce kısa marka kökü denenir, sonra marka+destek kombinasyonları denenir.
    """
    adaylar = []
    adaylar.extend(universal_direct_domain_candidates(firma_adi))

    words = firma_onemli_kelimeleri(firma_adi)
    profile = firma_domain_kelime_profili(firma_adi)
    marka = profile["marka"]
    destek = profile["destek_kelimeler"]

    kokler = []

    if marka:
        kokler.append(marka)

    if len(words) >= 2:
        w0 = normalize_domain_token(words[0])
        w1 = normalize_domain_token(words[1])
        if w0 and w1:
            kokler.append(w0 + w1)
            kokler.append(w0 + "-" + w1)

    for w in destek[:4]:
        kokler.append(marka + w)
        kokler.append(marka + "-" + w)

    kokler = [k for k in list(dict.fromkeys(kokler)) if k and len(k) >= 3]

    tlds = [
        ".com.tr", ".tr", ".com", ".net.tr", ".net", ".org",
        ".com.tr/iletisim", ".com.tr/contact", ".com.tr/en/contact",
        ".com.tr/home/contact", ".com/iletisim", ".com/contact",
        ".com/en/contact", ".com/home/contact"
    ]

    for root in kokler:
        for tld in tlds:
            adaylar.append(f"https://www.{root}{tld}")
            adaylar.append(f"https://{root}{tld}")

    return list(dict.fromkeys(adaylar))[:100]


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
    V3.1 Evrensel domain puanlama.
    Kısa marka domainlerini yanlış elemez; sektör/unvan kelimelerini zorunlu saymaz.
    Örnek mantık:
    - Sanmar Shipyards -> sanmar.com.tr kabul edilebilir.
    - Sefine Shipyard -> sefine.com.tr kabul edilebilir.
    - Çeksan -> ceksan.com.tr kabul edilebilir.
    Ama bu firmalara özel kural içermez.
    """
    try:
        if not url or istenmeyen_link_mi(url):
            return -100

        domain = domain_al(url)
        if not domain:
            return -100

        puan = universal_domain_match_score(url, firma_adi, page_text)

        # Rehber/haber/dizin sitelerini cezalandır
        low_url = url.lower()
        if any(x in low_url for x in ["haber", "news", "firma-rehberi", "yellow", "rehber", "directory", "blog", "linkedin.com", "facebook.com"]):
            puan -= 35

        # Boş/park domain sinyalleri
        low_text = turkce_karakter_temizle((page_text or "").lower()[:12000])
        if any(x in low_text for x in ["domain is for sale", "buy this domain", "parked domain", "this domain may be for sale"]):
            puan -= 80

        # İletişim sinyalleri ek artı
        if any(x in low_text for x in ["iletisim", "iletişim", "contact", "e-posta", "email", "telefon", "phone"]):
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

    # Evrensel son çare: marka kökü direkt domain fallback
    direkt = universal_direct_domain_fallback_bul(firma_adi_temiz)
    if direkt:
        return direkt

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



# ============================================================
# DEEP CONTACT EXTRACTION V3.1
# ============================================================

def html_entity_temizle(text):
    try:
        import html as html_lib
        return html_lib.unescape(str(text or ""))
    except Exception:
        return str(text or "")


def cloudflare_email_decode(cfhex):
    """
    Cloudflare email protection: data-cfemail değerini çözer.
    """
    try:
        r = int(cfhex[:2], 16)
        email = ''.join([chr(int(cfhex[i:i+2], 16) ^ r) for i in range(2, len(cfhex), 2)])
        return email
    except Exception:
        return ""


def cloudflare_mailleri_ayikla(html):
    mailler = []
    try:
        for cf in re.findall(r'data-cfemail=["\']([a-fA-F0-9]+)["\']', html or ""):
            decoded = cloudflare_email_decode(cf)
            if decoded:
                mailler.append(decoded)
    except Exception:
        pass
    return mailler


def attribute_iceriklerini_topla(html):
    """
    HTML içindeki href, content, data, aria-label, title gibi alanları düz metne ekler.
    Bazı mail/telefonlar görünen textte değil attribute içinde olur.
    """
    try:
        soup = BeautifulSoup(html or "", "html.parser")
        parcalar = []

        for tag in soup.find_all(True):
            for attr in ["href", "content", "data-email", "data-phone", "data-tel", "aria-label", "title", "alt", "value"]:
                val = tag.get(attr)
                if val:
                    parcalar.append(str(val))

        return " ".join(parcalar)
    except Exception:
        return ""


def js_json_iletisim_parcalari(html):
    """
    Script/JSON içinde gömülü email ve telefon parçalarını yakalamak için ham HTML döndürür.
    """
    if not html:
        return ""
    text = html_entity_temizle(html)
    text = text.replace("\\u0040", "@").replace("\\u002e", ".").replace("\\/", "/")
    text = text.replace("\\x40", "@").replace("\\x2e", ".")
    return text


def whatsapp_telefonlari_ayikla(html):
    telefonlar = []
    try:
        for m in re.findall(r"(?:wa\.me/|whatsapp://send\?phone=|api\.whatsapp\.com/send\?phone=)(\+?\d{8,15})", html or "", flags=re.I):
            telefonlar.append(m)
    except Exception:
        pass
    return telefonlar


def telefon_label_yakinindan_ayikla(text):
    """
    Telefon / Tel / Phone / Fax etiketinin yakınındaki numaraları yakalar.
    """
    if not text:
        return []

    telefonlar = []
    patterns = [
        r"(?:Telefon|Tel|Phone|Call|Santral|Pbx|PBX|Fax)\s*[:：]?\s*(\+?\d[\d\s\-\(\)\.]{8,25})",
        r"(\+90\s*\d{3}\s*\d{3}\s*\d{2}\s*\d{2})",
        r"(\+90\s*\d{3}\s*\d{2}\s*\d{2}\s*\d{2})",
        r"(0\s*\d{3}\s*\d{3}\s*\d{2}\s*\d{2})",
        r"(\(\s*0?\d{3}\s*\)\s*\d{3}\s*\d{2}\s*\d{2})",
    ]

    for p in patterns:
        for m in re.findall(p, text, flags=re.I):
            telefonlar.append(m)

    return telefonlar


def mail_label_yakinindan_ayikla(text):
    """
    Mail / E-posta / Email etiketinin yakınındaki e-postaları yakalar.
    """
    if not text:
        return []

    text = metinden_obfuscated_email_temizle(text)
    mailler = []

    patterns = [
        r"(?:Mail|E-posta|Eposta|Email|E-mail)\s*[:：]?\s*([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})",
        r"([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})"
    ]

    for p in patterns:
        for m in re.findall(p, text, flags=re.I):
            mailler.append(m)

    return mailler


def contact_url_adaylari_uret(web_url):
    """
    Domain üzerinden farklı dil ve farklı yol kombinasyonlarıyla contact sayfaları üretir.
    """
    web_url = normalize_url(web_url)
    parsed = urlparse(web_url)
    root = f"{parsed.scheme}://{parsed.netloc}"

    paths = [
        "/iletisim", "/iletisim/", "/tr/iletisim", "/tr/iletisim/",
        "/iletişim", "/bize-ulasin", "/bize-ulasin/", "/bize-ulaşın",
        "/contact", "/contact/", "/contact-us", "/contact-us/", "/home/contact", "/home/contact/", "/home/contacts", "/home/iletisim", "/home/iletisim/",
        "/en/contact", "/en/contact/", "/en/contact-us", "/en/contact-us/", "/tr/contact", "/tr/contact/",
        "/kurumsal/iletisim", "/kurumsal/iletisim/",
        "/corporate/contact", "/corporate/contact/",
        "/communication", "/reach-us", "/locations", "/offices",
        "/hakkimizda", "/hakkimizda/", "/about", "/about/", "/about-us",
        "/footer", "/site-haritasi", "/sitemap"
    ]

    adaylar = [web_url]
    for p in paths:
        adaylar.append(root + p)

    return list(dict.fromkeys(adaylar))[:25]


def sayfa_deep_contact_oku(url, referer="https://www.google.com/"):
    """
    Tek sayfadan tüm derin iletişim sinyallerini çıkarmaya çalışır.
    """
    sonuc = {"mailler": [], "telefonlar": [], "html": "", "text": "", "ok": False}

    try:
        r = guvenli_get(url, timeout=REQUEST_TIMEOUT, referer=referer)
        if r.status_code >= 400:
            return sonuc

        html = html_entity_temizle(r.text or "")
        attr_text = attribute_iceriklerini_topla(html)
        js_text = js_json_iletisim_parcalari(html)
        visible_text = temiz_metin(html)

        full_text = " ".join([html, attr_text, js_text, visible_text])
        full_text = html_entity_temizle(full_text)

        mailler = []
        telefonlar = []

        mailto_mailler, tel_linkleri = mailto_ve_tel_linklerini_ayikla(html)

        mailler.extend(mailto_mailler)
        mailler.extend(cloudflare_mailleri_ayikla(html))
        mailler.extend(mail_label_yakinindan_ayikla(full_text))
        mailler.extend(eposta_ayikla(full_text))

        telefonlar.extend(tel_linkleri)
        telefonlar.extend(whatsapp_telefonlari_ayikla(html))
        telefonlar.extend(telefon_label_yakinindan_ayikla(full_text))
        telefonlar.extend(telefon_ayikla(full_text))

        sonuc["mailler"] = temiz_mail_listesi(mailler)
        sonuc["telefonlar"] = temiz_telefon_listesi(telefonlar)
        sonuc["html"] = html
        sonuc["text"] = visible_text
        sonuc["ok"] = True

    except Exception:
        pass

    return sonuc


def playwright_deep_contact_oku(url):
    """
    JS ile yüklenen sayfalar için son çare Playwright ile sayfayı render edip okur.
    Sadece Derin Tarama modunda çalışır.
    """
    sonuc = {"mailler": [], "telefonlar": [], "html": "", "text": "", "ok": False}

    if not PLAYWRIGHT_FALLBACK_ENABLED or not PLAYWRIGHT_AKTIF:
        return sonuc

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            )
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121 Safari/537.36",
                viewport={"width": 1440, "height": 1000},
                locale="tr-TR"
            )
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(5000)

            # Cookie varsa basmayı dene
            try:
                page.evaluate("""
                    () => {
                        const words = ['kabul', 'accept', 'tamam', 'onay'];
                        const els = Array.from(document.querySelectorAll('button, a'));
                        for (const el of els) {
                            const txt = (el.innerText || '').toLowerCase();
                            if (words.some(w => txt.includes(w))) {
                                try { el.click(); } catch(e) {}
                            }
                        }
                    }
                """)
                page.wait_for_timeout(1000)
            except Exception:
                pass

            # scroll
            for _ in range(5):
                try:
                    page.evaluate("window.scrollBy(0, 700)")
                except Exception:
                    pass
                page.wait_for_timeout(600)

            html = page.content()
            text = page.inner_text("body")
            browser.close()

            full_text = " ".join([html_entity_temizle(html), html_entity_temizle(text), attribute_iceriklerini_topla(html)])
            mailler = []
            telefonlar = []
            mailto_mailler, tel_linkleri = mailto_ve_tel_linklerini_ayikla(html)

            mailler.extend(mailto_mailler)
            mailler.extend(cloudflare_mailleri_ayikla(html))
            mailler.extend(mail_label_yakinindan_ayikla(full_text))
            mailler.extend(eposta_ayikla(full_text))

            telefonlar.extend(tel_linkleri)
            telefonlar.extend(whatsapp_telefonlari_ayikla(html))
            telefonlar.extend(telefon_label_yakinindan_ayikla(full_text))
            telefonlar.extend(telefon_ayikla(full_text))

            sonuc["mailler"] = temiz_mail_listesi(mailler)
            sonuc["telefonlar"] = temiz_telefon_listesi(telefonlar)
            sonuc["html"] = html
            sonuc["text"] = text
            sonuc["ok"] = True

    except Exception:
        pass

    return sonuc



def websitesinden_iletisim_bul(web_url):
    """
    Deep Contact Extraction V3.1
    Homepage + contact + footer + attribute + script/json + mailto/tel + whatsapp + Cloudflare + Playwright fallback.
    """
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
        tum_mailler = []
        tum_telefonlar = []
        kaynak = web_url
        okunan = 0

        aday_url_listesi = contact_url_adaylari_uret(web_url)

        # Önce requests ile derin tarama
        for idx, u in enumerate(aday_url_listesi):
            try:
                time.sleep(random.uniform(0.25, 0.75))
                data = sayfa_deep_contact_oku(u, referer=web_url if idx > 0 else "https://www.google.com/")
                if not data.get("ok"):
                    continue

                okunan += 1

                if data.get("mailler"):
                    tum_mailler.extend(data["mailler"])
                    kaynak = u

                if data.get("telefonlar"):
                    tum_telefonlar.extend(data["telefonlar"])
                    kaynak = u

                # Ana hedef: en az bir mail + bir telefon
                if temiz_mail_listesi(tum_mailler) and temiz_telefon_listesi(tum_telefonlar):
                    break

            except Exception:
                continue

        # Bulunamadıysa ve derin moddaysa JS render fallback
        if (not temiz_mail_listesi(tum_mailler) or not temiz_telefon_listesi(tum_telefonlar)) and PLAYWRIGHT_FALLBACK_ENABLED:
            for u in aday_url_listesi[:6]:
                data = playwright_deep_contact_oku(u)
                if data.get("mailler"):
                    tum_mailler.extend(data["mailler"])
                    kaynak = u
                if data.get("telefonlar"):
                    tum_telefonlar.extend(data["telefonlar"])
                    kaynak = u

                if temiz_mail_listesi(tum_mailler) and temiz_telefon_listesi(tum_telefonlar):
                    break

        temiz_mailler = temiz_mail_listesi(tum_mailler)
        temiz_telefonlar = temiz_telefon_listesi(tum_telefonlar)

        if temiz_mailler:
            sonuc["eposta"] = ", ".join(temiz_mailler)

        if temiz_telefonlar:
            sonuc["telefon"] = ", ".join(temiz_telefonlar)

        sonuc["kaynak"] = kaynak

        if sonuc["eposta"] != "Bulunamadi" or sonuc["telefon"] != "Bulunamadi":
            sonuc["durum"] = f"Tamamlandi | Deep contact sayfa: {okunan}"
        else:
            sonuc["durum"] = f"Web bulundu, iletisim bulunamadi | Deep contact sayfa: {okunan}"

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
            sonuc = sonuc_guven_skorlari_ekle(sonuc, firma_adi)
            return sonuc

        iletisim = websitesinden_iletisim_bul(web)

        sonuc.update(iletisim)
        sonuc["firma_adi"] = firma_adi

        sonuc = sonuc_guven_skorlari_ekle(sonuc, firma_adi)
        return sonuc

    except Exception as e:
        sonuc["durum"] = "Hata"
        sonuc["hata"] = str(e)
        logging.error(f"Derin bilgi hatasi: {firma_adi} - {str(e)}")
        sonuc = sonuc_guven_skorlari_ekle(sonuc, firma_adi)
        return sonuc



# ============================================================
# MERKEZI KAYNAK NORMALIZASYON MOTORU V3.1
# ============================================================

def firma_adi_standartlastir(firma):
    if not firma:
        return ""

    f = firma_adi_temizle(firma)
    f = f.replace("\u200b", " ").replace("\ufeff", " ")
    f = re.sub(r"\s+", " ", f).strip()

    # Web/mail/tel kırıntılarını temizle
    f = re.split(r"https?://|https?//|www\.|mailto:|tel:|@", f, flags=re.I)[0].strip()

    # Kaynaklardan gelen kuyruk alanları
    cut_patterns = [
        r"\bTürkiye\b", r"\bTurkey\b", r"\bTurkiye\b", r"\bChina\b", r"\bGermany\b",
        r"\bItaly\b", r"\bIndia\b", r"\bUnited States\b", r"\bUnited Kingdom\b",
        r"\bHall\b", r"\bBooth\b", r"\bStand\b", r"\bStant\b", r"\bSalon\b",
        r"\bCountry\b", r"\bÜlke\b", r"\bSector\b", r"\bSektör\b", r"\bKategori\b",
        r"\bProducts\b", r"\bProduct Group\b", r"\bProduct Groups\b",
        r"\bDetaylı İncele\b", r"\bDetayli Incele\b"
    ]

    earliest = None
    for p in cut_patterns:
        m = re.search(p, f, flags=re.I)
        if m and m.start() > 2:
            earliest = m.start() if earliest is None else min(earliest, m.start())

    if earliest is not None:
        f = f[:earliest].strip()

    return f.strip(" -–|•,:;")


def firma_adi_gecerli_mi(firma):
    f = firma_adi_standartlastir(firma)
    low = f.lower().strip()

    if not f or len(f) < 2 or len(f) > 140:
        return False

    if re.fullmatch(r"[\d\s\-\+\(\):\./]+", f):
        return False

    if re.search(r"https?://|https?//|www\.|@", low):
        return False

    hard_garbage = [
        "country", "ülke", "ulke", "sector", "sektör", "sektor",
        "category", "kategori", "product group", "product groups",
        "hall", "booth", "stand", "stant", "salon", "page", "sayfa",
        "exhibitor list", "katılımcı listesi", "katilimci listesi",
        "see you next year", "gelecek sene", "görüşmek üzere", "gorusmek uzere",
        "visitor", "organizer", "privacy", "cookie", "kvkk",
        "phone", "telephone", "email", "e-mail", "website", "web site"
    ]
    if any(g in low for g in hard_garbage):
        return False

    if re.search(r"\b\d{1,2}\s*[-–]\s*\d{1,2}\s*(eylül|eylul|september|june|haziran|may|nisan|april)\b", low):
        return False

    category_words = {
        "products", "product", "care", "cosmetics", "cosmetic", "hygiene",
        "cleaning", "packaging", "machinery", "materials", "ingredients",
        "perfumery", "dermocosmetics", "pharmaceutical", "equipment",
        "equipments", "services", "media", "association", "agencies",
        "label", "manufacturing", "nail", "hair", "baby", "organic",
        "natural", "colour", "color", "raw"
    }
    words = re.findall(r"[a-zA-ZÇĞİÖŞÜçğıöşü]+", low)
    if words:
        category_count = sum(1 for w in words if w in category_words)
        if len(words) <= 6 and category_count >= max(1, len(words) - 1):
            company_markers = ["ltd", "co", "inc", "llc", "gmbh", "a.ş", "a.s", "şti", "limited"]
            if not any(m in low for m in company_markers):
                return False

    return bool(re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", f))


def kaynak_firmalarini_normalize_et(firmalar):
    final, seen = [], set()
    for firma in firmalar or []:
        f = firma_adi_standartlastir(firma)
        if not firma_adi_gecerli_mi(f):
            continue
        key = re.sub(r"\s+", " ", f.lower().strip())
        if key and key not in seen:
            seen.add(key)
            final.append(f)
    return final


def enrichment_kalite_etiketi(res):
    score = 0
    if res.get("web_adresi") and res.get("web_adresi") != "Bulunamadi":
        score += 40
    if res.get("eposta") and res.get("eposta") != "Bulunamadi":
        score += 35
    if res.get("telefon") and res.get("telefon") != "Bulunamadi":
        score += 25
    if score >= 80:
        return "Yüksek"
    if score >= 40:
        return "Orta"
    return "Düşük"



# ============================================================
# PDF / EXCEL / MANUEL
# ============================================================


PDF_COUNTRIES = [
    "Belgium", "Brunei", "Bulgaria", "China", "Czech Republic", "Egypt", "France",
    "Hungary", "India", "Indonesia", "Iran", "Italy", "Pakistan", "Russia",
    "South Korea", "Spain", "Sri Lanka", "Taiwan", "Türkiye", "Turkey", "Turkiye",
    "Ukraine", "United Arab Emirates", "United Kingdom", "United States",
    "Germany", "Almanya", "Italy", "İtalya", "Netherlands", "Hollanda",
    "Poland", "Polonya", "Austria", "Avusturya", "Switzerland", "İsviçre",
    "Japan", "Japonya", "Canada", "Kanada", "USA", "UK"
]

PDF_PRODUCT_GROUPS = [
    "Aesthetic Products & Equipments",
    "Aesthetic Products & Equipment",
    "Associations/ Agencies & Media",
    "Associations/ Agencies",
    "Baby Care Products",
    "Cleaning & Hygiene Products",
    "Colour Cosmetics",
    "Dermocosmetics",
    "Hair Care Products & Equipments",
    "Hair Care Products",
    "Nail Care & Nail Art",
    "Natural & Organic Cosmetics",
    "Natural Cosmetics",
    "Organic Cosmetics",
    "Packaging & Machinery",
    "Packaging",
    "Perfumery",
    "Personal Care Products",
    "Personal Care",
    "Personel Care",
    "Care Products",
    "Hair Care",
    "Cleaning & Hygiene Products; Personal",
    "Pharmaceutical & OTC Products",
    "Private Label & Contract Manufacturing",
    "Private Label",
    "Professional Salon Products & Equipments",
    "Raw Materials & Ingredients",
    "Services for Cosmetic Industry",
    "Beauty Technology",
    "Media",
]

PDF_SECTION_HEADERS = [
    "LIST OF EXHIBITORS BY COUNTRY & PRODUCT GROUPS",
    "LIST OF EXHIBITORS BY PRODUCT GROUPS",
    "AESTHETIC PRODUCTS & EQUIPMENTS",
    "ASSOCIATIONS/ AGENCIES & MEDIA",
    "BABY CARE PRODUCTS",
    "CLEANING & HYGIENE PRODUCTS",
    "COLOUR COSMETICS",
    "DERMOCOSMETICS",
    "HAIR CARE PRODUCTS & EQUIPMENTS",
    "NAIL CARE & NAIL ART",
    "NATURAL & ORGANIC COSMETICS",
    "PACKAGING & MACHINERY",
    "PERFUMERY",
    "PERSONAL CARE PRODUCTS",
]


def pdf_remove_urls(text):
    if not text:
        return ""
    t = str(text)
    t = re.sub(r"https?//\S+", " ", t, flags=re.I)
    t = re.sub(r"https?://\S+", " ", t, flags=re.I)
    t = re.sub(r"www\.\S+", " ", t, flags=re.I)
    t = re.sub(r"\S+\.(com|com\.tr|net|org|co|cn|kr|eu|ru|uk|tr|de|it|fr|hu|pk|tech|me|in|io)(/\S*)?", " ", t, flags=re.I)
    return t


def pdf_is_section_or_country(text):
    if not text:
        return True

    low = firma_adi_temizle(text).lower().strip()

    if not low:
        return True

    if re.fullmatch(r"\d{1,3}", low):
        return True

    for h in PDF_SECTION_HEADERS:
        if low == h.lower():
            return True

    for c in PDF_COUNTRIES:
        if low == c.lower():
            return True

    for pg in PDF_PRODUCT_GROUPS:
        if low == pg.lower():
            return True

    return False


def pdf_cut_before_country_or_group(text):
    """
    BeautyEurasia tipi satırlarda yapı:
    COMPANY NAME + Country + Product Group + Website
    Burada ülke veya ürün grubu başladığı yerde kesilir.
    """
    if not text:
        return ""

    t = firma_adi_temizle(text)
    t = pdf_remove_urls(t)
    t = re.sub(r"\s+", " ", t).strip()

    # Önce ülke isimlerine göre kes
    earliest = None
    for country in sorted(PDF_COUNTRIES, key=len, reverse=True):
        # Ülke kelimesi başta ise firma değildir
        if re.fullmatch(re.escape(country), t, flags=re.I):
            return ""

        m = re.search(r"\b" + re.escape(country) + r"\b", t, flags=re.I)
        if m and m.start() > 1:
            if earliest is None or m.start() < earliest:
                earliest = m.start()

    # Sonra ürün gruplarına göre kes
    for group in sorted(PDF_PRODUCT_GROUPS, key=len, reverse=True):
        m = re.search(r"\b" + re.escape(group) + r"\b", t, flags=re.I)
        if m and m.start() > 1:
            if earliest is None or m.start() < earliest:
                earliest = m.start()

    if earliest is not None:
        t = t[:earliest].strip()

    return t.strip(" -–|•,:;")


def pdf_satir_temizle(line):
    """
    PDF kataloglarından sadece firma adını bırakır.
    Ülke, ürün grubu, web sitesi, salon, stant, adres, telefon gibi alanları temizler.
    """
    if not line:
        return ""

    t = firma_adi_temizle(line)
    t = re.sub(r"\s+", " ", t).strip()

    if pdf_is_section_or_country(t):
        return ""

    # mail / web / telefon ağırlıklı satırları ele
    if re.fullmatch(r".*(@|telephone|phone|tel:|e-mail|email).*", t, flags=re.I):
        return ""

    # Web sitesinden öncesini al
    t = re.split(r"https?://|https?//|www\.|\S+\.(?:com|com\.tr|net|org|co|cn|kr|eu|ru|uk|tr|de|it|fr|hu|pk|tech|me|in|io)", t, flags=re.I)[0].strip()

    # Hall/Booth/Stand gibi alanlardan öncesini al
    t = re.split(
        r"\bHall\b|\bBooth\b|\bStand\b|\bStant\b|\bSalon\b|\bPavilion\b|\bCountry\b|\bÜlke\b|\bUlke\b|\bAddress\b|\bAdres\b|\bPhone\b|\bTel\b|\bE-mail\b|\bEmail\b",
        t,
        flags=re.IGNORECASE
    )[0].strip()

    # Ülke / ürün grubu başlamadan önceki kısım firma adı
    t = pdf_cut_before_country_or_group(t)

    # Kalan satır sadece ülke/bölüm/kategori ise at
    if pdf_is_section_or_country(t):
        return ""

    return t.strip(" -–|•,:;")



def pdf_cop_veri_mi(text):
    """
    PDF'de firma gibi görünen ama aslında kategori/footer/tarih/slogan olan satırları eler.
    BeautyEurasia gibi kataloglarda son sayfalardan gelen çöp verileri temizler.
    """
    if not text:
        return True

    t = firma_adi_temizle(text)
    low = t.lower().strip()

    if not low:
        return True

    # Çok kısa ve genel kategori kelimeleri
    exact_garbage = {
        "care products", "personal care", "personel care", "hair care",
        "cosmetics", "kozmetik", "packaging", "machinery", "perfumery",
        "dermocosmetics", "natural cosmetics", "organic cosmetics",
        "baby care", "cleaning", "hygiene", "colour cosmetics",
        "raw materials", "ingredients", "private label", "media",
        "associations", "agencies", "services", "beauty technology",
        "php#none", "productlist.html", "index.html",
        "gelecek sene", "görüşmek üzere", "gorusmek uzere",
        "see you next year", "see you next year!",
        "thank you", "thanks", "contact us"
    }

    if low in exact_garbage:
        return True

    # Fuar footer / tarih / kapanış mesajları
    footer_patterns = [
        r"see\s+you\s+next\s+year",
        r"gelecek\s+sene",
        r"görüşmek\s+üzere",
        r"gorusmek\s+uzere",
        r"\b\d{1,2}\s*[-–]\s*\d{1,2}\s*(eylül|eylul|september|june|haziran|may|nisan|april)\b",
        r"\b(eylül|eylul|september|june|haziran)\s+20\d{2}\b",
        r"\b20\d{2}\b\s*$",
    ]

    if any(re.search(p, low, flags=re.I) for p in footer_patterns):
        return True

    # Web kırıntıları
    if re.search(r"php#|\.html?$|productlist|index\.|/#none|com/_", low):
        return True

    # Ürün kategorisi gibi duran satırlar
    category_words = [
        "products", "product", "care", "cosmetics", "cosmetic", "hygiene",
        "cleaning", "packaging", "machinery", "materials", "ingredients",
        "perfumery", "dermocosmetics", "pharmaceutical", "equipment",
        "equipments", "services", "media", "association", "agencies",
        "label", "manufacturing", "nail", "hair", "baby", "organic",
        "natural", "colour", "color", "raw"
    ]

    words = re.findall(r"[a-zA-ZÇĞİÖŞÜçğıöşü]+", low)
    if words:
        category_count = sum(1 for w in words if w in category_words)
        # 1-5 kelimelik satırların çoğu kategori kelimesiyse firma değildir
        if len(words) <= 6 and category_count >= max(1, len(words) - 1):
            return True

    # Noktalı virgüllü ürün grubu kırıntıları
    if ";" in t and any(w in low for w in ["products", "care", "cosmetics", "hygiene", "packaging"]):
        return True

    # Sadece küçük harfli web/kırıntı benzeri tek kelime
    if len(t.split()) == 1 and re.fullmatch(r"[a-z0-9_\-/#.]+", low):
        if not any(marker in low for marker in ["ltd", "inc", "llc", "gmbh"]):
            return True

    # Firma gibi olmayan kısa başlıklar
    if len(t.split()) <= 2 and any(w in low for w in [
        "care", "products", "cosmetics", "packaging", "hygiene", "perfumery",
        "machinery", "media", "services"
    ]):
        # "ABC Cosmetics" gibi gerçek firma ihtimalini korumak için şirket marker yoksa ele
        company_markers = ["ltd", "co", "inc", "llc", "gmbh", "a.ş", "a.s", "şti", "limited"]
        if not any(m in low for m in company_markers):
            return True

    return False



def pdf_firma_adayi_mi(text):
    """
    PDF içinden gelen satırın firma adı olup olmadığını değerlendirir.
    """
    if not text:
        return False

    t = pdf_satir_temizle(text)
    low = t.lower()

    if not t:
        return False

    if pdf_cop_veri_mi(t):
        return False

    if len(t) < 3 or len(t) > 120:
        return False

    if pdf_is_section_or_country(t):
        return False

    if re.fullmatch(r"[\d\s\-\+\(\):\./]+", t):
        return False

    if re.search(r"https?://|https?//|www\.|@", low):
        return False

    yasak = [
        "exhibitor list", "katılımcı listesi", "katilimci listesi", "index",
        "contents", "içindekiler", "icindekiler", "page", "sayfa",
        "hall", "booth", "stand", "stant", "salon", "country", "ülke", "ulke",
        "address", "adres", "phone", "telephone", "telefon", "email", "e-mail",
        "website", "web site", "product group", "product groups",
        "category", "kategori", "sector", "sektör", "sektor",
        "organizer", "visitor", "ziyaretçi", "ziyaretci",
        "fuar", "expo", "fair", "exhibition", "detaylı incele", "detayli incele"
    ]

    if any(y in low for y in yasak):
        return False

    if not re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", t):
        return False

    # Çok genel tek kelimeleri at
    if len(t.split()) == 1 and low in ["media", "packaging", "perfumery", "cosmetics", "turkey"]:
        return False

    return True


def pdf_tablolardan_firma_cek(pdf):
    """
    PDF tablolarındaki ilk kolondan firma adı çıkarır.
    BeautyEurasia gibi kataloglarda ilk kolon firma adıdır.
    """
    adaylar = []

    for page in pdf.pages:
        try:
            tables = page.extract_tables()
        except Exception:
            tables = []

        for table in tables or []:
            if not table:
                continue

            for row in table:
                if not row:
                    continue

                # İlk hücre firma adı olma ihtimali en yüksek olan hücredir
                first = pdf_satir_temizle(row[0])
                if pdf_firma_adayi_mi(first):
                    adaylar.append(first)
                    continue

                # İlk hücre boşsa ilk 3 hücrede firma ara
                for cell in row[1:3]:
                    cell = pdf_satir_temizle(cell)
                    if pdf_firma_adayi_mi(cell):
                        adaylar.append(cell)
                        break

    return adaylar


def pdf_metinden_firma_cek(pdf):
    """
    PDF düz metinlerinden satır satır firma adı çıkarır.
    Ürün grubu sayfaları tekrar içerebilir; finalde mükerrer silinir.
    """
    adaylar = []

    for page in pdf.pages:
        try:
            page_text = page.extract_text()
        except Exception:
            page_text = None

        if not page_text:
            continue

        lines = page_text.split("\n")

        for line in lines:
            temiz = pdf_satir_temizle(line)
            if pdf_firma_adayi_mi(temiz):
                adaylar.append(temiz)

    return adaylar


def pdf_adaylari_son_temizle(adaylar):
    """
    PDF'den çıkan adayları mükerrer ve çöp kayıtlardan arındırır.
    """
    final = []
    seen = set()

    for a in adaylar:
        a = pdf_satir_temizle(a)

        if not pdf_firma_adayi_mi(a):
            continue

        if pdf_cop_veri_mi(a):
            continue

        low = a.lower().strip()

        # Çok kısa veya kategori gibi görünen başlıkları ele
        if low in ["turkey", "türkiye", "turkiye", "company", "firma", "hall", "booth"]:
            continue

        key = low
        if key not in seen:
            seen.add(key)
            final.append(a)

    return final


def pdf_firmalari_oku(pdf_file):
    """
    PDF firma çıkarma motoru V3.1.
    - Önce tabloları okur.
    - Sonra düz metin satırlarını okur.
    - Stand/salon/ülke/adres/web/mail/telefon kuyruklarını temizler.
    - Taranmış görsel PDF'lerde OCR olmadığı için metin yoksa uyarı verir.
    """
    adaylar = []
    sayfa_sayisi = 0
    metinli_sayfa = 0

    try:
        with pdfplumber.open(pdf_file) as pdf:
            sayfa_sayisi = len(pdf.pages)

            # 1) Tablolar
            tablo_adaylari = pdf_tablolardan_firma_cek(pdf)
            adaylar.extend(tablo_adaylari)

            # 2) Metin satırları
            metin_adaylari = pdf_metinden_firma_cek(pdf)
            adaylar.extend(metin_adaylari)

            # Metin var mı kontrolü
            for page in pdf.pages:
                try:
                    txt = page.extract_text()
                    if txt and len(txt.strip()) > 20:
                        metinli_sayfa += 1
                except Exception:
                    pass

    except Exception as e:
        raise Exception(f"PDF okuma hatasi: {str(e)}")

    firmalar = pdf_adaylari_son_temizle(adaylar)

    if sayfa_sayisi > 0 and metinli_sayfa == 0:
        raise Exception(
            "Bu PDF metin içermiyor gibi görünüyor. Büyük ihtimalle taranmış/görsel PDF. "
            "Bu durumda OCR motoru gerekir."
        )

    return kaynak_firmalarini_normalize_et(firmalar)


def excel_firmalari_oku(excel_file):
    """
    Excel firma çıkarma motoru V3.1.
    Firma/Company/Exhibitor içeren kolonu otomatik bulur.
    Bulamazsa firma benzeri içerik puanı en yüksek kolonu seçer.
    """
    try:
        df_upload = pd.read_excel(excel_file)
        if df_upload.empty:
            return []

        preferred_keywords = [
            "firma", "firma adı", "firma adi", "company", "company name",
            "exhibitor", "exhibitor name", "katılımcı", "katilimci",
            "organization", "organisation", "brand"
        ]

        selected_col = None
        for col in df_upload.columns:
            col_low = str(col).lower().strip()
            if any(k in col_low for k in preferred_keywords):
                selected_col = col
                break

        if selected_col is None:
            best_score = -1
            best_col = df_upload.columns[0]
            for col in df_upload.columns:
                values = df_upload[col].dropna().astype(str).head(250).tolist()
                if not values:
                    continue
                valid_count = sum(1 for v in values if firma_adi_gecerli_mi(v))
                url_email_count = sum(1 for v in values if re.search(r"https?://|www\.|@", v.lower()))
                score = valid_count - (url_email_count * 2)
                if score > best_score:
                    best_score = score
                    best_col = col
            selected_col = best_col

        firmalar = df_upload[selected_col].dropna().astype(str).tolist()
        return kaynak_firmalarini_normalize_et(firmalar)

    except Exception as e:
        raise Exception(f"Excel okuma hatasi: {str(e)}")


def listeye_ekle(yeni_firmalar, listeyi_sifirla=False):
    """
    Tüm kaynaklardan gelen firmalar bu kapıdan havuza girer.
    URL/PDF/Excel/Manuel fark etmeksizin normalize edilir.
    """
    yeni_firmalar = kaynak_firmalarini_normalize_et(yeni_firmalar)

    if listeyi_sifirla:
        st.session_state["ana_liste"] = yeni_firmalar
    else:
        mevcut = st.session_state["ana_liste"]
        birlesik = mevcut + yeni_firmalar
        st.session_state["ana_liste"] = kaynak_firmalarini_normalize_et(birlesik)

    return len(yeni_firmalar)



def tarama_modu_ayarlari(mod):
    """
    Tarama modu ayarları.
    Hızlı: daha seri, daha az sorgu.
    Dengeli: güvenli ve hızlı varsayılan mod.
    Derin: daha yavaş ama eksik kalan firmalarda daha fazla arama.
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
        "workers": 3,
        "query_limit": 4,
        "playwright_fallback": False,
        "aciklama": "Dengeli mod: Çökmeden hızlı çalışması için güvenli ayar. Tarayıcı fallback kapalıdır."
    }


def sure_formatla(saniye):
    """
    Saniyeyi okunabilir süreye çevirir.
    """
    try:
        saniye = int(saniye)
        dk = saniye // 60
        sn = saniye % 60
        if dk <= 0:
            return f"{sn} sn"
        return f"{dk} dk {sn} sn"
    except Exception:
        return "-"


# ============================================================
# V73 FAST BALANCED QUALITY CORE OVERRIDES
# Eski panel UI/kuyruk/arsiv korunur; Dengeli mod hizlandirilir.
# ============================================================

try:
    from difflib import SequenceMatcher
except Exception:
    SequenceMatcher = None


V72_BAD_RESULT_DOMAINS = {
    "facebook.com", "instagram.com", "linkedin.com", "x.com", "twitter.com",
    "youtube.com", "tiktok.com", "pinterest.com", "wikipedia.org",
    "google.com", "maps.google.com", "bing.com", "duckduckgo.com",
    "yellowpages.com", "kompass.com", "europages.com", "find.com.tr",
    "firma rehberi", "firmasec.com", "turkishexporter.net",
}

V72_ROLE_MAIL_PREFIXES = (
    "info@", "sales@", "export@", "contact@", "iletisim@", "iletişim@",
    "marketing@", "office@", "support@", "hello@", "mail@"
)

V72_CONTACT_WORDS = (
    "iletisim", "iletişim", "contact", "contact-us", "contacts",
    "bize-ulasin", "bize-ulaşın", "communication", "reach-us",
    "kurumsal", "corporate", "about", "hakkimizda", "hakkımızda",
    "location", "locations", "adres", "address", "footer", "sitemap"
)


def v73_mode_limits():
    """
    Streamlit Cloud icin mod bazli is limiti.
    V72 cok fazla aday denedigi icin ilk sonucun gelmesi uzuyordu.
    V73'te Dengeli mod once hizli sonuc uretir; Derin mod sadece eksikler icindir.
    """
    if SCAN_MODE == "Hızlı Tarama":
        return {
            "query_limit": 1,
            "candidate_limit": 4,
            "direct_limit": 0,
            "contact_limit": 5,
            "search_timeout": 4,
            "site_timeout": 4,
            "contact_timeout": 4,
            "firma_cap": 65,
        }

    if SCAN_MODE == "Derin Tarama":
        return {
            "query_limit": min(SEARCH_QUERY_LIMIT, 5),
            "candidate_limit": 10,
            "direct_limit": 22,
            "contact_limit": 18,
            "search_timeout": 7,
            "site_timeout": 6,
            "contact_timeout": 6,
            "firma_cap": 150,
        }

    return {
        "query_limit": min(SEARCH_QUERY_LIMIT, 2),
        "candidate_limit": 6,
        "direct_limit": 6,
        "contact_limit": 7,
        "search_timeout": 5,
        "site_timeout": 5,
        "contact_timeout": 5,
        "firma_cap": 85,
    }


def durum_bildir(*args, **kwargs):
    """
    Bazı eski fallback fonksiyonları global durum_bildir bekliyor.
    Streamlit progress callback yoksa sessiz no-op olarak çalışır.
    """
    return None


def v72_domain_root(url_or_domain):
    d = str(url_or_domain or "").strip().lower()
    if "://" in d:
        d = domain_al(d)
    d = d.replace("www.", "")
    d = d.split("/")[0].split(":")[0]
    d = re.sub(
        r"\.(com\.tr|net\.tr|org\.tr|edu\.tr|gov\.tr|co\.uk|com\.cn|com\.br|com|net|org|tr|co|io|de|it|fr|uk|us|nl|pl|ru|cn|in|ae|es|pt)$",
        "",
        d,
    )
    return normalize_domain_token(d)


def v72_same_site(url, root_domain):
    try:
        d = domain_al(url)
        root = domain_al(root_domain) if "://" in str(root_domain) else str(root_domain)
        d = d.replace("www.", "")
        root = root.replace("www.", "")
        return d == root or d.endswith("." + root) or root.endswith("." + d)
    except Exception:
        return False


def v72_token_similarity(a, b):
    a = normalize_domain_token(a)
    b = normalize_domain_token(b)
    if not a or not b:
        return 0
    if a == b:
        return 100
    if a in b or b in a:
        return 82
    if SequenceMatcher:
        return int(SequenceMatcher(None, a, b).ratio() * 100)
    return 0


def v72_company_profile(firma_adi):
    words = firma_onemli_kelimeleri(firma_adi)
    profile = firma_domain_kelime_profili(firma_adi)
    marka = profile.get("marka") or (normalize_domain_token(words[0]) if words else "")
    tokens = []
    for w in [marka] + words + profile.get("marka_adaylari", []) + profile.get("destek_kelimeler", []):
        t = normalize_domain_token(w)
        if t and len(t) >= 2 and t not in tokens:
            tokens.append(t)
    return {"marka": marka, "tokens": tokens[:10], "words": words[:10]}


def v72_url_kotu_mu(url):
    low = str(url or "").lower()
    if not url_gecerli_mi(url):
        return True
    if istenmeyen_link_mi(url):
        return True
    if any(x in low for x in [
        "/search?", "webcache", "translate.google", "ads.", "doubleclick",
        "facebook.", "instagram.", "linkedin.", "youtube.", "twitter.", "x.com/",
        "pinterest.", "wikipedia.", "blogspot.", "wordpress.com",
        "firma-rehberi", "yellow", "directory", "haber", "/news/"
    ]):
        return True
    if any(low.endswith(ext) for ext in [".pdf", ".jpg", ".jpeg", ".png", ".webp", ".gif", ".doc", ".docx", ".xls", ".xlsx", ".zip"]):
        return True
    return False


def domain_puanla(url, firma_adi, page_text=""):
    """
    V72 domain puanlama:
    - Marka kokunu ana sinyal kabul eder.
    - Sayfa icerigi ve contact sinyaliyle dogrular.
    - Rehber/sosyal/parking sonuclarini sert cezalandirir.
    """
    try:
        if v72_url_kotu_mu(url):
            return -100

        domain = domain_al(url)
        root = v72_domain_root(domain)
        profile = v72_company_profile(firma_adi)
        marka = profile["marka"]
        tokens = profile["tokens"]
        text = turkce_karakter_temizle((page_text or "").lower()[:20000])
        score = 0

        if not root or not tokens:
            return -80

        marka_sim = v72_token_similarity(root, marka)
        if marka_sim >= 96:
            score += 88
        elif marka_sim >= 82:
            score += 66
        elif marka and (marka in root or root in marka):
            score += 62
        elif marka_sim >= 68:
            score += 30

        domain_hits = 0
        text_hits = 0
        for t in tokens:
            if t in root or v72_token_similarity(root, t) >= 86:
                domain_hits += 1
            if len(t) >= 3 and t in text:
                text_hits += 1

        score += min(domain_hits * 22, 58)
        score += min(text_hits * 9, 36)

        if len(tokens) >= 2:
            combo = tokens[0] + tokens[1]
            if combo in root.replace("-", ""):
                score += 55

        if domain.endswith(".com.tr"):
            score += 24
        elif domain.endswith(".tr"):
            score += 18
        elif domain.endswith(".com"):
            score += 8

        low_url = str(url or "").lower()
        if any(w in low_url for w in V72_CONTACT_WORDS):
            score += 8

        if any(w in text for w in ["iletisim", "iletişim", "contact", "email", "e-posta", "telefon", "phone"]):
            score += 10

        if any(w in text for w in ["domain is for sale", "buy this domain", "parked domain", "sedo.com", "godaddy"]):
            score -= 95

        if any(w in low_url for w in ["rehber", "directory", "yellow", "haber", "news", "blog"]):
            score -= 45

        risky_short = {"abc", "star", "mega", "global", "best", "pro", "max", "net", "sun"}
        if marka in risky_short and root == marka and text_hits == 0:
            score -= 50

        if marka and marka not in root and root not in marka and domain_hits == 0:
            score -= 35

        return score
    except Exception:
        return -100


def aday_site_oku_ve_puanla(url, firma_adi):
    try:
        url = normalize_url(url)
        if v72_url_kotu_mu(url):
            return {"url": url, "puan": -100, "text": ""}

        r = guvenli_get(url, timeout=v73_mode_limits()["site_timeout"], referer="https://www.google.com/")
        if r.status_code >= 500:
            return {"url": url, "puan": -45, "text": ""}
        if r.status_code >= 400:
            # Bazi siteler botlara 403 verir; domain yine de kuvvetli olabilir.
            return {"url": url, "puan": max(domain_puanla(url, firma_adi, ""), -20), "text": ""}

        html = r.text or ""
        text = temiz_metin(html)
        puan = domain_puanla(url, firma_adi, text)
        return {"url": url, "puan": puan, "text": text}
    except Exception:
        return {"url": url, "puan": -30, "text": ""}


def en_iyi_websitesini_sec(linkler, firma_adi):
    temiz = []
    seen = set()
    for link in linkler or []:
        link = normalize_url(arama_linkini_temizle(link))
        if v72_url_kotu_mu(link):
            continue
        d = domain_al(link)
        if not d or d in seen:
            continue
        seen.add(d)
        temiz.append(link)

    if not temiz:
        return ""

    candidate_limit = v73_mode_limits()["candidate_limit"]
    sonuclar = [aday_site_oku_ve_puanla(link, firma_adi) for link in temiz[:candidate_limit]]
    sonuclar = sorted(sonuclar, key=lambda x: x.get("puan", -100), reverse=True)

    if sonuclar and sonuclar[0]["puan"] >= 28:
        return sonuclar[0]["url"]

    for s in sonuclar:
        d = domain_al(s["url"])
        if d.endswith(".com.tr") and s.get("puan", 0) >= 8:
            return s["url"]

    if sonuclar and sonuclar[0].get("puan", 0) > 5:
        return sonuclar[0]["url"]

    return ""


def v72_arama_sonuclarindan_link_cek(html):
    linkler = []
    try:
        soup = BeautifulSoup(html or "", "html.parser")
        for a in soup.find_all("a", href=True):
            href = arama_linkini_temizle(a.get("href", ""))
            href = normalize_url(href)
            if href and not v72_url_kotu_mu(href):
                linkler.append(href)
    except Exception:
        pass

    final, seen = [], set()
    for l in linkler:
        d = domain_al(l)
        if d and d not in seen:
            seen.add(d)
            final.append(l)
    return final[:20]


def firma_websitesi_bul(firma_adi):
    """
    V73 web bulma:
    1) Bing + DuckDuckGo sorgu sonuclari
    2) Dengeli modda sinirli aday puanlama
    3) Direkt domain denemesi sadece kisa limitlerle
    """
    firma_adi_temiz = firma_adi_temizle(firma_adi)
    if not firma_adi_temiz:
        return ""

    cache_key = "v73:" + firma_adi_temiz.lower().strip()
    if cache_key in WEBSITE_CACHE:
        return WEBSITE_CACHE[cache_key]

    limits = v73_mode_limits()
    deadline = time.time() + limits["firma_cap"]
    sorgular = firma_arama_sorgulari_uret(firma_adi_temiz)[:limits["query_limit"]]
    bulunan_linkler = []

    for sorgu_text in sorgular:
        if time.time() > deadline:
            break

        arama_url_listesi = [
            f"https://www.bing.com/search?q={quote_plus(sorgu_text)}",
            f"https://duckduckgo.com/html/?q={quote_plus(sorgu_text)}",
        ]

        for arama_url in arama_url_listesi:
            if time.time() > deadline:
                break
            try:
                time.sleep(random.uniform(0.12, 0.35))
                res = guvenli_get(arama_url, timeout=limits["search_timeout"], referer="https://www.google.com/")
                if res.status_code >= 400:
                    continue
                bulunan_linkler.extend(v72_arama_sonuclarindan_link_cek(res.text or ""))
            except Exception as e:
                logging.warning(f"V73 arama hatasi: {firma_adi_temiz} - {str(e)}")

        if len(set([domain_al(x) for x in bulunan_linkler if domain_al(x)])) >= limits["candidate_limit"]:
            break

    secilen = en_iyi_websitesini_sec(bulunan_linkler, firma_adi_temiz)
    if secilen:
        WEBSITE_CACHE[cache_key] = secilen
        return secilen

    if PLAYWRIGHT_FALLBACK_ENABLED and time.time() < deadline:
        for sorgu_text in sorgular[:2]:
            if time.time() > deadline:
                break
            try:
                bulunan_linkler.extend(playwright_arama_linkleri_bul(sorgu_text))
                secilen = en_iyi_websitesini_sec(bulunan_linkler, firma_adi_temiz)
                if secilen:
                    WEBSITE_CACHE[cache_key] = secilen
                    return secilen
            except Exception:
                continue

    # Arama motoru zayif kalirsa direkt marka domainlerini kisa limitlerle dene.
    direct_candidates = domain_adaylari_uret(firma_adi_temiz)[:limits["direct_limit"]]
    direct_scores = []
    for aday in direct_candidates:
        if time.time() > deadline:
            break
        s = aday_site_oku_ve_puanla(aday, firma_adi_temiz)
        if s.get("puan", -100) >= 12:
            direct_scores.append(s)

    if direct_scores:
        direct_scores = sorted(direct_scores, key=lambda x: x.get("puan", 0), reverse=True)
        WEBSITE_CACHE[cache_key] = direct_scores[0]["url"]
        return direct_scores[0]["url"]

    WEBSITE_CACHE[cache_key] = ""
    return ""


def temiz_mail_listesi(mailler):
    final = []
    yasakli = [
        "example.com", "domain.com", "email.com", "sentry.", "wixpress.",
        "schema.org", "wordpress.org", "yoursite", "yourdomain", "test.com",
        "localhost", "noreply@", "no-reply@"
    ]

    for m in mailler or []:
        m = html_entity_temizle(str(m)).strip().lower()
        m = m.replace("mailto:", "").split("?")[0]
        m = re.sub(r"^[^a-z0-9]+|[^a-z0-9.]+$", "", m)

        if not re.fullmatch(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", m):
            continue
        if any(y in m for y in yasakli):
            continue
        if len(m) > 90:
            continue
        if m not in final:
            final.append(m)

    final = sorted(
        final,
        key=lambda x: (
            0 if x.startswith(V72_ROLE_MAIL_PREFIXES) else 1,
            0 if not any(x.endswith(g) for g in ["@gmail.com", "@hotmail.com", "@outlook.com", "@yahoo.com"]) else 1,
            x,
        )
    )
    return final[:10]


def temiz_telefon_listesi(telefonlar):
    final = []
    seen_digits = set()

    for tel in telefonlar or []:
        tel = html_entity_temizle(str(tel)).strip()
        tel = tel.replace("tel:", "")
        tel = re.sub(r"\s+", " ", tel)
        digits = re.sub(r"\D", "", tel)

        if len(digits) < 10 or len(digits) > 15:
            continue
        if len(set(digits)) <= 2:
            continue

        key = digits[-10:] if len(digits) >= 10 else digits
        if key in seen_digits:
            continue
        seen_digits.add(key)

        if tel.startswith("00"):
            tel = "+" + tel[2:]
        final.append(tel)

    final = sorted(final, key=lambda x: 0 if "+90" in x or re.sub(r"\D", "", x).startswith("90") else 1)
    return final[:8]


def v72_mail_site_uyumu(mail, web_url):
    try:
        mail_domain = str(mail).split("@", 1)[1].lower().replace("www.", "")
        site_domain = domain_al(web_url).lower().replace("www.", "")
        return mail_domain == site_domain or mail_domain.endswith("." + site_domain) or site_domain.endswith("." + mail_domain)
    except Exception:
        return False


def v72_sitemap_contact_urls(web_url):
    urls = []
    try:
        parsed = urlparse(normalize_url(web_url))
        root = f"{parsed.scheme}://{parsed.netloc}"
        sm = guvenli_get(root + "/sitemap.xml", timeout=min(v73_mode_limits()["contact_timeout"], 5), referer=web_url)
        if sm.status_code < 400:
            for loc in re.findall(r"<loc>\s*([^<]+)\s*</loc>", sm.text or "", flags=re.I):
                loc = html_entity_temizle(loc.strip())
                low = turkce_karakter_temizle(loc.lower())
                if any(w in low for w in V72_CONTACT_WORDS):
                    urls.append(loc)
    except Exception:
        pass
    return urls[:8]


def contact_url_adaylari_uret(web_url):
    web_url = normalize_url(web_url)
    parsed = urlparse(web_url)
    root = f"{parsed.scheme}://{parsed.netloc}"

    paths = [
        "/iletisim", "/iletisim/", "/tr/iletisim", "/tr/iletisim/",
        "/kurumsal/iletisim", "/kurumsal/iletisim/", "/tr/kurumsal/iletisim",
        "/iletişim", "/bize-ulasin", "/bize-ulasin/", "/bize-ulaşın",
        "/contact", "/contact/", "/contact-us", "/contact-us/",
        "/contacts", "/home/contact", "/home/contacts", "/home/iletisim",
        "/en/contact", "/en/contact/", "/en/contact-us", "/en/contact-us/",
        "/en/contacts", "/tr/contact", "/tr/contact/",
        "/corporate/contact", "/corporate/contact/", "/corporate/contacts",
        "/communication", "/reach-us", "/locations", "/offices",
        "/hakkimizda", "/hakkimizda/", "/hakkımızda", "/about", "/about/", "/about-us",
        "/footer", "/site-haritasi", "/sitemap", "/sitemap.xml"
    ]

    adaylar = [web_url]
    for p in paths:
        adaylar.append(root + p)
    adaylar.extend(v72_sitemap_contact_urls(web_url))

    final, seen = [], set()
    for u in adaylar:
        u = normalize_url(u)
        if not url_gecerli_mi(u):
            continue
        if not v72_same_site(u, root):
            continue
        if u not in seen:
            seen.add(u)
            final.append(u)

    return final[:30]


def v72_html_contact_linkleri(base_url, html):
    links = []
    try:
        soup = BeautifulSoup(html or "", "html.parser")
        for a in soup.find_all("a", href=True):
            text = turkce_karakter_temizle(temiz_metin(a.get_text(" ")).lower())
            href_raw = a.get("href", "")
            href = normalize_url(href_raw, base_url=base_url)
            low = turkce_karakter_temizle((href + " " + text).lower())
            if url_gecerli_mi(href) and v72_same_site(href, base_url) and any(w in low for w in V72_CONTACT_WORDS):
                links.append(href)
    except Exception:
        pass
    return sorted(list(dict.fromkeys(links)), key=iletisim_linki_oncelik_puani, reverse=True)[:10]


def sayfa_deep_contact_oku(url, referer="https://www.google.com/"):
    """
    V73 hizli contact okuma.
    V72'de contact sayfalari 10 sn timeout ile cok bekleyebiliyordu.
    Burada mod limitine gore daha kisa timeout kullanilir.
    """
    sonuc = {"mailler": [], "telefonlar": [], "html": "", "text": "", "ok": False}

    try:
        r = guvenli_get(url, timeout=v73_mode_limits()["contact_timeout"], referer=referer)
        if r.status_code >= 400:
            return sonuc

        html = html_entity_temizle(r.text or "")
        attr_text = attribute_iceriklerini_topla(html)
        js_text = js_json_iletisim_parcalari(html)
        visible_text = temiz_metin(html)

        full_text = " ".join([html, attr_text, js_text, visible_text])
        full_text = html_entity_temizle(full_text)

        mailler = []
        telefonlar = []

        mailto_mailler, tel_linkleri = mailto_ve_tel_linklerini_ayikla(html)

        mailler.extend(mailto_mailler)
        mailler.extend(cloudflare_mailleri_ayikla(html))
        mailler.extend(mail_label_yakinindan_ayikla(full_text))
        mailler.extend(eposta_ayikla(full_text))

        telefonlar.extend(tel_linkleri)
        telefonlar.extend(whatsapp_telefonlari_ayikla(html))
        telefonlar.extend(telefon_label_yakinindan_ayikla(full_text))
        telefonlar.extend(telefon_ayikla(full_text))

        sonuc["mailler"] = temiz_mail_listesi(mailler)
        sonuc["telefonlar"] = temiz_telefon_listesi(telefonlar)
        sonuc["html"] = html
        sonuc["text"] = visible_text
        sonuc["ok"] = True

    except Exception:
        pass

    return sonuc


def websitesinden_iletisim_bul(web_url):
    """
    V73 contact extraction:
    homepage + HTML contact links + generated paths + sitemap + optional Playwright.
    """
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
        tum_mailler = []
        tum_telefonlar = []
        kaynaklar = []
        okunan = 0

        aday_url_listesi = contact_url_adaylari_uret(web_url)

        # Ana sayfayi once oku; oradan gercek iletisim linklerini yakala.
        try:
            home = sayfa_deep_contact_oku(web_url, referer="https://www.google.com/")
            if home.get("ok"):
                okunan += 1
                tum_mailler.extend(home.get("mailler", []))
                tum_telefonlar.extend(home.get("telefonlar", []))
                kaynaklar.append(web_url)
                aday_url_listesi = [web_url] + v72_html_contact_linkleri(web_url, home.get("html", "")) + aday_url_listesi
        except Exception:
            pass

        scan_limit = v73_mode_limits()["contact_limit"]
        seen = set()
        for idx, u in enumerate(aday_url_listesi[:scan_limit]):
            if u in seen:
                continue
            seen.add(u)
            try:
                time.sleep(random.uniform(0.12, 0.45))
                data = sayfa_deep_contact_oku(u, referer=web_url if idx > 0 else "https://www.google.com/")
                if not data.get("ok"):
                    continue
                okunan += 1
                if data.get("mailler"):
                    tum_mailler.extend(data["mailler"])
                    kaynaklar.append(u)
                if data.get("telefonlar"):
                    tum_telefonlar.extend(data["telefonlar"])
                    kaynaklar.append(u)
                if temiz_mail_listesi(tum_mailler) and temiz_telefon_listesi(tum_telefonlar):
                    break
            except Exception:
                continue

        if (not temiz_mail_listesi(tum_mailler) or not temiz_telefon_listesi(tum_telefonlar)) and PLAYWRIGHT_FALLBACK_ENABLED:
            for u in list(dict.fromkeys(aday_url_listesi))[:5]:
                data = playwright_deep_contact_oku(u)
                if data.get("mailler"):
                    tum_mailler.extend(data["mailler"])
                    kaynaklar.append(u)
                if data.get("telefonlar"):
                    tum_telefonlar.extend(data["telefonlar"])
                    kaynaklar.append(u)
                if temiz_mail_listesi(tum_mailler) and temiz_telefon_listesi(tum_telefonlar):
                    break

        temiz_mailler = temiz_mail_listesi(tum_mailler)
        site_uyumlu = [m for m in temiz_mailler if v72_mail_site_uyumu(m, web_url)]
        if site_uyumlu:
            temiz_mailler = site_uyumlu + [m for m in temiz_mailler if m not in site_uyumlu]

        temiz_telefonlar = temiz_telefon_listesi(tum_telefonlar)

        if temiz_mailler:
            sonuc["eposta"] = ", ".join(temiz_mailler[:5])
        if temiz_telefonlar:
            sonuc["telefon"] = ", ".join(temiz_telefonlar[:5])

        sonuc["kaynak"] = list(dict.fromkeys(kaynaklar))[0] if kaynaklar else web_url

        if sonuc["eposta"] != "Bulunamadi" and sonuc["telefon"] != "Bulunamadi":
            sonuc["durum"] = f"Tamamlandi | V72 contact sayfa: {okunan}"
        elif sonuc["eposta"] != "Bulunamadi" or sonuc["telefon"] != "Bulunamadi":
            sonuc["durum"] = f"Kismi tamamlandi | V72 contact sayfa: {okunan}"
        else:
            sonuc["durum"] = f"Web bulundu, iletisim bulunamadi | V72 contact sayfa: {okunan}"

    except Exception as e:
        sonuc["durum"] = "Hata"
        sonuc["hata"] = str(e)
        logging.error(f"V72 site iletisim hatasi: {web_url} - {str(e)}")

    return sonuc


def sonuc_guven_skorlari_ekle(sonuc, firma_adi):
    """
    Eksik olan merkezi skor fonksiyonu.
    Arşiv filtrelerinin anlamlı çalışması için web/mail/telefon/genel güveni üretir.
    """
    try:
        web = sonuc.get("web_adresi", "")
        mail = sonuc.get("eposta", "")
        tel = sonuc.get("telefon", "")

        web_guven = 0
        if web and web != "Bulunamadi":
            puan = domain_puanla(web, firma_adi, "")
            if puan >= 80:
                web_guven = 95
            elif puan >= 50:
                web_guven = 82
            elif puan >= 25:
                web_guven = 68
            elif puan >= 8:
                web_guven = 50
            else:
                web_guven = 30

        mail_guven = 0
        mailler = [] if not mail or mail == "Bulunamadi" else temiz_mail_listesi(str(mail).split(","))
        if mailler:
            mail_guven = 55
            if web and web != "Bulunamadi" and any(v72_mail_site_uyumu(m, web) for m in mailler):
                mail_guven += 35
            if any(m.startswith(V72_ROLE_MAIL_PREFIXES) for m in mailler):
                mail_guven += 10
            mail_guven = min(mail_guven, 100)

        telefon_guven = 0
        telefonlar = [] if not tel or tel == "Bulunamadi" else temiz_telefon_listesi(str(tel).split(","))
        if telefonlar:
            telefon_guven = 62
            digits = " ".join([re.sub(r"\D", "", t) for t in telefonlar])
            if any(10 <= len(re.sub(r"\D", "", t)) <= 15 for t in telefonlar):
                telefon_guven += 18
            if "90" in digits[:4] or any(str(t).strip().startswith("+90") for t in telefonlar):
                telefon_guven += 12
            telefon_guven = min(telefon_guven, 100)

        genel = int(round((web_guven * 0.45) + (mail_guven * 0.32) + (telefon_guven * 0.23)))

        site_domain = domain_al(web) if web and web != "Bulunamadi" else ""
        joined = " ".join([str(web), str(mail), str(tel), str(sonuc.get("kaynak", ""))]).lower()
        if site_domain.endswith(".tr") or "+90" in joined or re.search(r"\b90\d{10}\b", re.sub(r"\D", "", joined)):
            sirket_tipi = "Yerli"
            ulke = "Türkiye"
            ulke_guven = 80
        elif site_domain:
            sirket_tipi = "Yabancı"
            ulke = "Belirsiz"
            ulke_guven = 35
        else:
            sirket_tipi = "Belirsiz"
            ulke = "Belirsiz"
            ulke_guven = 0

        manuel = "Hayır"
        if genel < 70 or web_guven < 50 or (mail_guven == 0 and telefon_guven == 0):
            manuel = "Evet"

        sonuc["web_guven"] = int(web_guven)
        sonuc["mail_guven"] = int(mail_guven)
        sonuc["telefon_guven"] = int(telefon_guven)
        sonuc["genel_guven"] = int(genel)
        sonuc["manuel_kontrol"] = manuel
        sonuc["sirket_tipi"] = sirket_tipi
        sonuc["ulke_tahmini"] = ulke
        sonuc["ulke_guven"] = int(ulke_guven)
        return sonuc
    except Exception as e:
        sonuc["web_guven"] = int(sonuc.get("web_guven", 0) or 0)
        sonuc["mail_guven"] = int(sonuc.get("mail_guven", 0) or 0)
        sonuc["telefon_guven"] = int(sonuc.get("telefon_guven", 0) or 0)
        sonuc["genel_guven"] = int(sonuc.get("genel_guven", 0) or 0)
        sonuc["manuel_kontrol"] = "Evet"
        sonuc["sirket_tipi"] = "Belirsiz"
        sonuc["ulke_tahmini"] = "Belirsiz"
        sonuc["ulke_guven"] = 0
        sonuc["hata"] = (str(sonuc.get("hata", "")) + f" | Skor hatasi: {str(e)}").strip(" |")
        return sonuc


# ============================================================
# V74 PRECISION CORE OVERRIDES
# Bu blok V73 hizini korur ama yanlis web kabulunu sertlestirir.
# Ozellikle Ada/Yonca/Hat/Med/RMK/Kuzey gibi kisa marka yanilmalarini azaltir.
# ============================================================

V74_LEGAL_STOP_WORDS = {
    "anonim", "limited", "sirket", "sirketi", "ltd", "sti", "şti", "as", "aş",
    "sanayi", "san", "ticaret", "tic", "ve", "ile", "co", "inc", "llc", "gmbh",
}

V74_SECTOR_GROUPS = {
    "shipyard": {
        "needles": {"shipyard", "shipyards", "shipbuilding", "shipbuilder", "shiprepair", "ship repair", "drydock", "dry dock", "dockyard", "vessel", "new building", "tersane", "tersanesi", "gemi inşa", "gemi insa"},
        "negative": {"gida", "gıda", "food", "oil", "zeytinyagi", "zeytinyağı", "salca", "salça", "konserve", "yag", "yağ", "network", "ag cozum", "ağ çözüm", "yazilim", "yazılım", "software", "bilisim", "bilişim", "nakliyat", "lojistik", "karayolu", "tasimacilik", "taşımacılık"},
        "roots": ["shipyard", "shipyards", "tersane"],
    },
    "marine": {
        "needles": {"marine", "maritime", "ship", "vessel", "tug", "towage", "pilotage", "boat", "shipyard", "tersane", "denizcilik"},
        "negative": {"gida", "gıda", "food", "restaurant", "hotel", "network", "software", "yazilim", "yazılım"},
        "roots": ["marine", "maritime"],
    },
    "holding": {
        "needles": {"holding", "group", "energy", "enerji", "powership", "fleet", "investment"},
        "negative": {"haber", "news", "blog", "forum"},
        "roots": ["holding", "group"],
    },
    "classification": {
        "needles": {"classification", "class", "survey", "certification", "certificate", "klas", "loydu", "denetim", "uygunluk", "maritime"},
        "negative": {"haber", "news", "blog", "forum"},
        "roots": ["loydu", "class"],
    },
}

V74_GENERIC_ROOTS = {
    "ada", "hat", "yonca", "med", "rmk", "kuzey", "tuzla", "star", "ares",
    "best", "pro", "global", "group", "marine", "ship", "shipyard"
}


def v74_tokenize_company(firma_adi):
    text = turkce_karakter_temizle(firma_adi_temizle(firma_adi)).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    raw = [w for w in text.split() if len(w) >= 2]
    tokens = []
    for w in raw:
        if w in V74_LEGAL_STOP_WORDS:
            continue
        if w not in tokens:
            tokens.append(w)
    return tokens[:10]


def v74_company_profile(firma_adi):
    tokens = v74_tokenize_company(firma_adi)
    sector_tokens = {
        "shipyard", "shipyards", "tersane", "tersanesi", "marine", "maritime",
        "denizcilik", "holding", "group", "loydu", "class", "classification"
    }
    brand_tokens = [t for t in tokens if t not in sector_tokens]
    marka = brand_tokens[0] if brand_tokens else (tokens[0] if tokens else "")
    return {
        "marka": marka,
        "tokens": tokens,
        "brand_tokens": brand_tokens[:5],
        "sector_tokens": [t for t in tokens if t in sector_tokens],
    }


def v74_expected_groups(firma_adi):
    low = turkce_karakter_temizle(firma_adi_temizle(firma_adi)).lower()
    groups = []
    if any(x in low for x in ["shipyard", "shipyards", "tersane", "tersanesi"]):
        groups.append("shipyard")
    if any(x in low for x in ["marine", "maritime", "denizcilik"]):
        groups.append("marine")
    if "holding" in low:
        groups.append("holding")
    if any(x in low for x in ["loydu", "class", "classification"]):
        groups.append("classification")
    return groups


def v74_text_has_any(text, words):
    low = turkce_karakter_temizle(str(text or "").lower())
    return any(w in low for w in words)


def v74_sector_score(url, firma_adi, page_text):
    groups = v74_expected_groups(firma_adi)
    if not groups:
        return 0

    root = v72_domain_root(url)
    low_url = turkce_karakter_temizle(str(url or "").lower())
    text = turkce_karakter_temizle(str(page_text or "").lower()[:24000])
    score = 0

    for group in groups:
        cfg = V74_SECTOR_GROUPS[group]
        root_hit = any(r in root or r in low_url for r in cfg["roots"])
        text_hit = v74_text_has_any(text, cfg["needles"])
        negative_hit = v74_text_has_any(text, cfg["negative"])

        if root_hit:
            score += 55
        if text_hit:
            score += 45
        if not root_hit and not text_hit:
            score -= 80
        if negative_hit:
            score -= 95

    return score


def v74_generic_short_penalty(url, firma_adi, page_text):
    profile = v74_company_profile(firma_adi)
    root = v72_domain_root(url)
    tokens = profile["tokens"]
    marka = profile["marka"]

    if not root or not marka:
        return 0

    penalty = 0
    other_brand_tokens = [t for t in profile["brand_tokens"] if t != marka]
    expected_groups = v74_expected_groups(firma_adi)

    if root == marka and (root in V74_GENERIC_ROOTS or len(root) <= 5):
        if other_brand_tokens and not any(t in root for t in other_brand_tokens):
            penalty -= 55
        if expected_groups:
            penalty -= 70

    # Firma iki kelimelik markaysa tek kelime domaini zayif kabul et: Kuzey Star -> kuzey.com.tr
    if len(tokens) >= 2 and root == tokens[0] and tokens[1] not in {"shipyard", "shipyards", "marine", "holding"}:
        penalty -= 45

    return penalty


def domain_puanla(url, firma_adi, page_text=""):
    """
    V74 domain puanlama:
    - Domain benzerligi tek basina yetmez.
    - Firma adinda Shipyard/Marine/Holding/Loydu varsa sayfa veya domain sektoru de desteklemeli.
    - Kisa/generic domainler ekstra supheli kabul edilir.
    """
    try:
        if v72_url_kotu_mu(url):
            return -100

        domain = domain_al(url)
        root = v72_domain_root(domain)
        profile = v74_company_profile(firma_adi)
        marka = profile["marka"]
        tokens = profile["tokens"]
        text = turkce_karakter_temizle((page_text or "").lower()[:24000])

        if not root or not tokens:
            return -90

        score = 0

        if marka:
            sim = v72_token_similarity(root, marka)
            if root == marka:
                score += 58
            elif marka in root or root in marka:
                score += 62
            elif sim >= 88:
                score += 50
            elif sim >= 72:
                score += 24

        domain_hits = 0
        text_hits = 0
        for t in tokens[:8]:
            if t in root or v72_token_similarity(root, t) >= 88:
                domain_hits += 1
            if len(t) >= 3 and t in text:
                text_hits += 1

        score += min(domain_hits * 24, 72)
        score += min(text_hits * 10, 40)

        # Bitişik marka kombinasyonları çok güçlü sinyal: adashipyard, tktuzlashipyard, rmkmarine
        joined = "".join(tokens[:3])
        if len(joined) >= 6 and joined in root.replace("-", ""):
            score += 70
        if len(tokens) >= 2:
            combo2 = tokens[0] + tokens[1]
            if combo2 in root.replace("-", ""):
                score += 55

        if domain.endswith(".com.tr"):
            score += 18
        elif domain.endswith(".tr"):
            score += 14
        elif domain.endswith(".com"):
            score += 6
        elif domain.endswith(".org") and "loydu" in tokens:
            score += 20

        score += v74_sector_score(url, firma_adi, page_text)
        score += v74_generic_short_penalty(url, firma_adi, page_text)

        if any(w in text for w in ["domain is for sale", "buy this domain", "parked domain", "sedo.com", "godaddy"]):
            score -= 100

        return score
    except Exception:
        return -100


def aday_site_oku_ve_puanla(url, firma_adi):
    try:
        url = normalize_url(url)
        if v72_url_kotu_mu(url):
            return {"url": url, "puan": -100, "text": ""}

        r = guvenli_get(url, timeout=v73_mode_limits()["site_timeout"], referer="https://www.google.com/")
        final_url = getattr(r, "url", url)
        if final_url and final_url != url and v72_url_kotu_mu(final_url):
            return {"url": url, "puan": -100, "text": ""}

        if r.status_code >= 500:
            return {"url": url, "puan": -45, "text": ""}
        if r.status_code >= 400:
            # Sektorlu firmalarda metin okunamiyorsa kisa/generic domaini kabul etme.
            puan = domain_puanla(url, firma_adi, "")
            if v74_expected_groups(firma_adi) and v72_domain_root(url) in V74_GENERIC_ROOTS:
                puan -= 60
            return {"url": url, "puan": max(puan, -80), "text": ""}

        html = r.text or ""
        text = temiz_metin(html)
        puan = domain_puanla(final_url or url, firma_adi, text)
        return {"url": final_url or url, "puan": puan, "text": text}
    except Exception:
        return {"url": url, "puan": -40, "text": ""}


def en_iyi_websitesini_sec(linkler, firma_adi):
    temiz = []
    seen = set()
    for link in linkler or []:
        link = normalize_url(arama_linkini_temizle(link))
        if v72_url_kotu_mu(link):
            continue
        d = domain_al(link)
        if not d or d in seen:
            continue
        seen.add(d)
        temiz.append(link)

    if not temiz:
        return ""

    candidate_limit = max(v73_mode_limits()["candidate_limit"], 8)
    sonuclar = [aday_site_oku_ve_puanla(link, firma_adi) for link in temiz[:candidate_limit]]
    sonuclar = sorted(sonuclar, key=lambda x: x.get("puan", -100), reverse=True)

    if not sonuclar:
        return ""

    best = sonuclar[0]
    threshold = 55 if v74_expected_groups(firma_adi) else 35

    if best.get("puan", -100) >= threshold:
        return best["url"]

    # Sektorlu firmada dusuk puanli com.tr domaini kabul etme; yanlis pozitif en pahali hata.
    if not v74_expected_groups(firma_adi):
        for s in sonuclar:
            d = domain_al(s["url"])
            if d.endswith(".com.tr") and s.get("puan", 0) >= 18:
                return s["url"]

    return ""


def firma_arama_sorgulari_uret(firma_adi):
    original = firma_adi_temizle(firma_adi)
    profile = v74_company_profile(firma_adi)
    tokens = profile["tokens"]
    marka = profile["marka"]
    groups = v74_expected_groups(firma_adi)

    sorgular = []
    if original:
        sorgular.extend([
            f'"{original}" official website',
            f'"{original}" contact',
            f'"{original}"',
        ])

    if groups:
        group_words = " ".join(groups)
        if marka:
            sorgular.extend([
                f'"{original}" {group_words}',
                f'{marka} {" ".join(tokens[1:3])} official website',
                f'{marka} shipyard official website' if "shipyard" in groups else f'{marka} marine official website',
                f'{marka} contact {group_words}',
            ])

    if len(tokens) >= 2:
        combo = " ".join(tokens[:2])
        sorgular.extend([
            f'"{combo}" official website',
            f'{combo} contact',
        ])

    if marka:
        sorgular.extend([
            f'{marka} official website',
            f'{marka} contact',
        ])

    final = []
    seen = set()
    for q in sorgular:
        q = re.sub(r"\s+", " ", q).strip()
        k = q.lower()
        if q and k not in seen:
            seen.add(k)
            final.append(q)
    return final[:18]


def domain_adaylari_uret(firma_adi):
    profile = v74_company_profile(firma_adi)
    tokens = profile["tokens"]
    marka = profile["marka"]
    groups = v74_expected_groups(firma_adi)

    roots = []
    if marka:
        roots.append(marka)

    if len(tokens) >= 2:
        roots.append(tokens[0] + tokens[1])
        roots.append(tokens[0] + "-" + tokens[1])
    if len(tokens) >= 3:
        roots.append(tokens[0] + tokens[1] + tokens[2])
        roots.append(tokens[0] + "-" + tokens[1] + "-" + tokens[2])

    for group in groups:
        for suffix in V74_SECTOR_GROUPS[group]["roots"]:
            if marka:
                roots.append(marka + suffix)
                roots.append(marka + "-" + suffix)
            if len(tokens) >= 2:
                roots.append(tokens[0] + tokens[1] + suffix)

    # Türk Loydu gibi bitişik resmi markalar.
    if "loydu" in tokens:
        roots.append("turkloydu")
        roots.append("turk-loydu")

    roots = [r for r in list(dict.fromkeys(roots)) if r and len(r) >= 3]
    tlds = [".com.tr", ".com", ".com.tr/en", ".com/en", ".org", ".net", ".tr"]

    adaylar = []
    for r in roots:
        for tld in tlds:
            adaylar.append(f"https://www.{r}{tld}")
            adaylar.append(f"https://{r}{tld}")
    return list(dict.fromkeys(adaylar))[:120]


def firma_websitesi_bul(firma_adi):
    firma_adi_temiz = firma_adi_temizle(firma_adi)
    if not firma_adi_temiz:
        return ""

    cache_key = "v74:" + firma_adi_temiz.lower().strip()
    if cache_key in WEBSITE_CACHE:
        return WEBSITE_CACHE[cache_key]

    limits = v73_mode_limits()
    deadline = time.time() + limits["firma_cap"]
    query_limit = max(limits["query_limit"], 3 if v74_expected_groups(firma_adi_temiz) else limits["query_limit"])
    sorgular = firma_arama_sorgulari_uret(firma_adi_temiz)[:query_limit]
    bulunan_linkler = []

    for sorgu_text in sorgular:
        if time.time() > deadline:
            break

        for arama_url in [
            f"https://www.bing.com/search?q={quote_plus(sorgu_text)}",
            f"https://duckduckgo.com/html/?q={quote_plus(sorgu_text)}",
        ]:
            if time.time() > deadline:
                break
            try:
                time.sleep(random.uniform(0.12, 0.35))
                res = guvenli_get(arama_url, timeout=limits["search_timeout"], referer="https://www.google.com/")
                if res.status_code >= 400:
                    continue
                bulunan_linkler.extend(v72_arama_sonuclarindan_link_cek(res.text or ""))
            except Exception as e:
                logging.warning(f"V74 arama hatasi: {firma_adi_temiz} - {str(e)}")

        if len(set([domain_al(x) for x in bulunan_linkler if domain_al(x)])) >= max(limits["candidate_limit"], 8):
            break

    secilen = en_iyi_websitesini_sec(bulunan_linkler, firma_adi_temiz)
    if secilen:
        WEBSITE_CACHE[cache_key] = secilen
        return secilen

    direct_limit = max(limits["direct_limit"], 18 if v74_expected_groups(firma_adi_temiz) else limits["direct_limit"])
    direct_scores = []
    for aday in domain_adaylari_uret(firma_adi_temiz)[:direct_limit]:
        if time.time() > deadline:
            break
        s = aday_site_oku_ve_puanla(aday, firma_adi_temiz)
        if s.get("puan", -100) >= (48 if v74_expected_groups(firma_adi_temiz) else 18):
            direct_scores.append(s)

    if direct_scores:
        direct_scores = sorted(direct_scores, key=lambda x: x.get("puan", 0), reverse=True)
        WEBSITE_CACHE[cache_key] = direct_scores[0]["url"]
        return direct_scores[0]["url"]

    WEBSITE_CACHE[cache_key] = ""
    return ""


def temiz_telefon_listesi(telefonlar):
    final = []
    seen_digits = set()

    for tel in telefonlar or []:
        tel_raw = html_entity_temizle(str(tel)).strip()
        if not tel_raw:
            continue

        # CSS/istatistik kirleri: 0.281738, 0596 196.97 38 gibi parçaları at.
        if re.search(r"\d+\.\d+", tel_raw):
            continue

        tel_clean = tel_raw.replace("tel:", "")
        tel_clean = re.sub(r"\s+", " ", tel_clean).strip()
        digits = re.sub(r"\D", "", tel_clean)

        if len(digits) < 10 or len(digits) > 15:
            continue
        if len(set(digits)) <= 2:
            continue
        if re.search(r"(\d)\1{5,}", digits):
            continue

        if digits.startswith("00") and len(digits) >= 12:
            norm = "+" + digits[2:]
        elif digits.startswith("90") and len(digits) == 12:
            norm = "+90 " + digits[2:5] + " " + digits[5:8] + " " + digits[8:10] + " " + digits[10:12]
        elif digits.startswith("0") and len(digits) == 11:
            norm = "+90 " + digits[1:4] + " " + digits[4:7] + " " + digits[7:9] + " " + digits[9:11]
        elif len(digits) == 10 and digits[0] in "2358":
            norm = "+90 " + digits[0:3] + " " + digits[3:6] + " " + digits[6:8] + " " + digits[8:10]
        else:
            norm = tel_clean

        key = re.sub(r"\D", "", norm)[-10:]
        if key in seen_digits:
            continue
        seen_digits.add(key)
        final.append(norm)

    return final[:6]


def v74_mail_site_uyumu(mail, web_url, firma_adi=""):
    try:
        mail = str(mail or "").strip().lower()
        if "@" not in mail:
            return False
        mail_domain = mail.split("@", 1)[1].replace("www.", "")
        site_domain = domain_al(web_url).lower().replace("www.", "")
        mail_root = v72_domain_root(mail_domain)
        site_root = v72_domain_root(site_domain)
        profile = v74_company_profile(firma_adi)
        marka = profile["marka"]

        if mail_domain == site_domain or mail_domain.endswith("." + site_domain) or site_domain.endswith("." + mail_domain):
            return True
        if mail_root and site_root and (mail_root == site_root or mail_root in site_root or site_root in mail_root):
            return True
        if marka and (mail_root == marka or marka in mail_root or marka in mail.split("@", 1)[0]):
            return True
        if mail_domain.endswith("kep.tr") and marka and marka in mail.split("@", 1)[0]:
            return True
        return False
    except Exception:
        return False


def temiz_mail_listesi(mailler):
    final = []
    yasakli = [
        "example.com", "domain.com", "email.com", "sentry.", "wixpress.",
        "schema.org", "wordpress.org", "yoursite", "yourdomain", "test.com",
        "localhost", "noreply@", "no-reply@", "webevin.com"
    ]

    for m in mailler or []:
        m = html_entity_temizle(str(m)).strip().lower()
        m = m.replace("mailto:", "").split("?")[0]
        m = re.sub(r"^[^a-z0-9]+|[^a-z0-9.]+$", "", m)

        if not re.fullmatch(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", m):
            continue
        if any(y in m for y in yasakli):
            continue
        if len(m) > 90:
            continue
        if m not in final:
            final.append(m)

    final = sorted(
        final,
        key=lambda x: (
            0 if x.startswith(V72_ROLE_MAIL_PREFIXES) else 1,
            1 if any(x.endswith(g) for g in ["@gmail.com", "@hotmail.com", "@outlook.com", "@yahoo.com"]) else 0,
            x,
        )
    )
    return final[:10]


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
        tum_mailler = []
        tum_telefonlar = []
        kaynaklar = []
        okunan = 0

        aday_url_listesi = contact_url_adaylari_uret(web_url)
        try:
            home = sayfa_deep_contact_oku(web_url, referer="https://www.google.com/")
            if home.get("ok"):
                okunan += 1
                tum_mailler.extend(home.get("mailler", []))
                tum_telefonlar.extend(home.get("telefonlar", []))
                kaynaklar.append(web_url)
                aday_url_listesi = [web_url] + v72_html_contact_linkleri(web_url, home.get("html", "")) + aday_url_listesi
        except Exception:
            pass

        seen = set()
        for idx, u in enumerate(aday_url_listesi[:v73_mode_limits()["contact_limit"]]):
            if u in seen:
                continue
            seen.add(u)
            try:
                time.sleep(random.uniform(0.12, 0.4))
                data = sayfa_deep_contact_oku(u, referer=web_url if idx > 0 else "https://www.google.com/")
                if not data.get("ok"):
                    continue
                okunan += 1
                if data.get("mailler"):
                    tum_mailler.extend(data["mailler"])
                    kaynaklar.append(u)
                if data.get("telefonlar"):
                    tum_telefonlar.extend(data["telefonlar"])
                    kaynaklar.append(u)
                if temiz_mail_listesi(tum_mailler) and temiz_telefon_listesi(tum_telefonlar):
                    break
            except Exception:
                continue

        temiz_mailler = temiz_mail_listesi(tum_mailler)
        uyumlu_mailler = [m for m in temiz_mailler if v74_mail_site_uyumu(m, web_url, "")]
        # Firma adi burada yok; yine de site-domain uyumu olmayan mailleri zayif oldugu icin ele.
        if uyumlu_mailler:
            temiz_mailler = uyumlu_mailler
        else:
            temiz_mailler = [m for m in temiz_mailler if v72_mail_site_uyumu(m, web_url)]

        temiz_telefonlar = temiz_telefon_listesi(tum_telefonlar)

        if temiz_mailler:
            sonuc["eposta"] = ", ".join(temiz_mailler[:5])
        if temiz_telefonlar:
            sonuc["telefon"] = ", ".join(temiz_telefonlar[:5])

        sonuc["kaynak"] = list(dict.fromkeys(kaynaklar))[0] if kaynaklar else web_url

        if sonuc["eposta"] != "Bulunamadi" and sonuc["telefon"] != "Bulunamadi":
            sonuc["durum"] = f"Tamamlandi | V74 contact sayfa: {okunan}"
        elif sonuc["eposta"] != "Bulunamadi" or sonuc["telefon"] != "Bulunamadi":
            sonuc["durum"] = f"Kismi tamamlandi | V74 contact sayfa: {okunan}"
        else:
            sonuc["durum"] = f"Web bulundu, iletisim bulunamadi | V74 contact sayfa: {okunan}"

    except Exception as e:
        sonuc["durum"] = "Hata"
        sonuc["hata"] = str(e)
        logging.error(f"V74 site iletisim hatasi: {web_url} - {str(e)}")

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
        time.sleep(random.uniform(0.6, 1.4))
        web = firma_websitesi_bul(firma_adi)

        if not web:
            sonuc["durum"] = "Web sitesi bulunamadi"
            return sonuc_guven_skorlari_ekle(sonuc, firma_adi)

        iletisim = websitesinden_iletisim_bul(web)
        sonuc.update(iletisim)
        sonuc["firma_adi"] = firma_adi

        # Son emniyet: bulunan web sektor/firma uyumunda dusukse web'i de supheli kabul et.
        web_score = domain_puanla(web, firma_adi, " ".join([sonuc.get("eposta", ""), sonuc.get("telefon", ""), sonuc.get("kaynak", "")]))
        if web_score < (45 if v74_expected_groups(firma_adi) else 15):
            sonuc["durum"] = f"Web supheli - manuel kontrol gerekli | Skor: {web_score}"
            sonuc["manuel_kontrol"] = "Evet"

        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)
    except Exception as e:
        sonuc["durum"] = "Hata"
        sonuc["hata"] = str(e)
        logging.error(f"V74 derin bilgi hatasi: {firma_adi} - {str(e)}")
        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)


def sonuc_guven_skorlari_ekle(sonuc, firma_adi):
    try:
        web = sonuc.get("web_adresi", "")
        mail = sonuc.get("eposta", "")
        tel = sonuc.get("telefon", "")

        web_guven = 0
        if web and web != "Bulunamadi":
            puan = domain_puanla(web, firma_adi, "")
            if puan >= 95:
                web_guven = 95
            elif puan >= 70:
                web_guven = 82
            elif puan >= 50:
                web_guven = 65
            elif puan >= 25:
                web_guven = 42
            else:
                web_guven = 20

        mailler = [] if not mail or mail == "Bulunamadi" else temiz_mail_listesi(str(mail).split(","))
        mailler = [m for m in mailler if v74_mail_site_uyumu(m, web, firma_adi)] if web and web != "Bulunamadi" else mailler
        if mailler:
            sonuc["eposta"] = ", ".join(mailler[:5])
        else:
            sonuc["eposta"] = "Bulunamadi"

        mail_guven = 0
        if mailler:
            mail_guven = 70
            if any(v74_mail_site_uyumu(m, web, firma_adi) for m in mailler):
                mail_guven += 25
            if any(m.startswith(V72_ROLE_MAIL_PREFIXES) for m in mailler):
                mail_guven += 5
            mail_guven = min(mail_guven, 100)

        telefonlar = [] if not tel or tel == "Bulunamadi" else temiz_telefon_listesi(str(tel).split(","))
        if telefonlar:
            sonuc["telefon"] = ", ".join(telefonlar[:5])
        else:
            sonuc["telefon"] = "Bulunamadi"

        telefon_guven = 0
        if telefonlar:
            telefon_guven = 75
            if any(str(t).startswith("+90") for t in telefonlar):
                telefon_guven += 15
            telefon_guven = min(telefon_guven, 100)

        genel = int(round((web_guven * 0.50) + (mail_guven * 0.30) + (telefon_guven * 0.20)))

        site_domain = domain_al(web) if web and web != "Bulunamadi" else ""
        joined = " ".join([str(web), str(mail), str(tel), str(sonuc.get("kaynak", ""))]).lower()
        if site_domain.endswith(".tr") or "+90" in joined or re.search(r"\b90\d{10}\b", re.sub(r"\D", "", joined)):
            sirket_tipi = "Yerli"
            ulke = "Türkiye"
            ulke_guven = 80
        elif site_domain:
            sirket_tipi = "Yabancı"
            ulke = "Belirsiz"
            ulke_guven = 35
        else:
            sirket_tipi = "Belirsiz"
            ulke = "Belirsiz"
            ulke_guven = 0

        manuel = "Hayır"
        if genel < 75 or web_guven < 65 or (mail_guven == 0 and telefon_guven == 0):
            manuel = "Evet"

        sonuc["web_guven"] = int(web_guven)
        sonuc["mail_guven"] = int(mail_guven)
        sonuc["telefon_guven"] = int(telefon_guven)
        sonuc["genel_guven"] = int(genel)
        sonuc["manuel_kontrol"] = manuel
        sonuc["sirket_tipi"] = sirket_tipi
        sonuc["ulke_tahmini"] = ulke
        sonuc["ulke_guven"] = int(ulke_guven)
        return sonuc
    except Exception as e:
        sonuc["web_guven"] = int(sonuc.get("web_guven", 0) or 0)
        sonuc["mail_guven"] = int(sonuc.get("mail_guven", 0) or 0)
        sonuc["telefon_guven"] = int(sonuc.get("telefon_guven", 0) or 0)
        sonuc["genel_guven"] = int(sonuc.get("genel_guven", 0) or 0)
        sonuc["manuel_kontrol"] = "Evet"
        sonuc["sirket_tipi"] = "Belirsiz"
        sonuc["ulke_tahmini"] = "Belirsiz"
        sonuc["ulke_guven"] = 0
        sonuc["hata"] = (str(sonuc.get("hata", "")) + f" | V74 skor hatasi: {str(e)}").strip(" |")
        return sonuc


# ============================================================
# V75 CONTACT HUNTER OVERRIDES
# Web dogru bulundugunda mail/telefon kacirmamak icin ek derin contact motoru.
# ============================================================

V75_CONTACT_PATHS = [
    "/contact", "/contact/", "/contact-us", "/contact-us/", "/contacts", "/contacts/",
    "/iletisim", "/iletisim/", "/iletişim", "/iletişim/",
    "/tr/contact", "/tr/contact/", "/tr/contact-us", "/tr/contact-us/",
    "/tr/contacts", "/tr/contacts/", "/tr/iletisim", "/tr/iletisim/",
    "/tr/iletişim", "/tr/iletişim/", "/tr/kurumsal/iletisim", "/tr/kurumsal/iletisim/",
    "/en/contact", "/en/contact/", "/en/contact-us", "/en/contact-us/",
    "/en/contacts", "/en/contacts/", "/en/corporate/contact", "/en/corporate/contact/",
    "/corporate/contact", "/corporate/contact/", "/kurumsal/iletisim", "/kurumsal/iletisim/",
    "/about/contact", "/about-us/contact", "/company/contact",
    "/locations", "/locations/", "/offices", "/offices/",
    "/sitemap.xml"
]


def v75_root_url(web_url):
    u = normalize_url(web_url)
    parsed = urlparse(u)
    return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else u


def v75_decode_contact_text(text):
    t = html_entity_temizle(str(text or ""))
    try:
        t = bytes(t, "utf-8").decode("unicode_escape", errors="ignore")
    except Exception:
        pass
    try:
        t = unquote(t)
    except Exception:
        pass

    replacements = {
        "\\u0040": "@", "\\u002e": ".", "\\x40": "@", "\\x2e": ".",
        "&#64;": "@", "&#x40;": "@", "&commat;": "@",
        "[at]": "@", "(at)": "@", " at ": "@",
        "[dot]": ".", "(dot)": ".", " dot ": ".",
    }
    low = t
    for a, b in replacements.items():
        low = re.sub(re.escape(a), b, low, flags=re.I)
    return low.replace("\\/", "/")


def v75_contact_url_adaylari(web_url):
    web_url = normalize_url(web_url)
    root = v75_root_url(web_url)
    parsed = urlparse(web_url)
    adaylar = [web_url, root, root + "/"]

    # URL /tr veya /en ile geliyorsa ayni dil altinda contact varyasyonlarini one al.
    parts = [p for p in parsed.path.split("/") if p]
    if parts and parts[0].lower() in ["tr", "en", "de", "fr"]:
        lang = "/" + parts[0].lower()
        for p in V75_CONTACT_PATHS:
            if not p.startswith(lang + "/") and p not in ["/sitemap.xml"]:
                adaylar.append(root + lang + p)

    for p in V75_CONTACT_PATHS:
        adaylar.append(root + p)

    # Eski motorun buldugu HTML linkleri ve sitemap sonuclari da korunsun.
    try:
        adaylar.extend(contact_url_adaylari_uret(web_url))
    except Exception:
        pass

    final, seen = [], set()
    for u in adaylar:
        u = normalize_url(u)
        if not url_gecerli_mi(u):
            continue
        if not v72_same_site(u, root):
            continue
        if u not in seen:
            seen.add(u)
            final.append(u)
    return final[:36]


def v75_extract_contacts_from_blob(blob):
    blob = v75_decode_contact_text(blob)
    mailler = []
    telefonlar = []

    try:
        mailler.extend(cloudflare_mailleri_ayikla(blob))
    except Exception:
        pass

    mailler.extend(eposta_ayikla(blob))
    mailler.extend(mail_label_yakinindan_ayikla(blob))

    # +90 (312) 592 10 00, +90-312-266-35-50, 0216 395 75 75 gibi formatlar.
    phone_patterns = [
        r"\+90[\s\-\.\(\)]{0,4}\d{3}[\s\-\.\)]{0,4}\d{3}[\s\-\.]{0,3}\d{2}[\s\-\.]{0,3}\d{2}",
        r"0[\s\-\.\(\)]{0,4}\d{3}[\s\-\.\)]{0,4}\d{3}[\s\-\.]{0,3}\d{2}[\s\-\.]{0,3}\d{2}",
        r"\+\d{1,3}[\s\-\.\(\)]{0,4}\d{2,4}[\s\-\.\)]{0,4}\d{3,4}[\s\-\.]{0,3}\d{2,4}[\s\-\.]{0,3}\d{2,4}",
    ]
    for p in phone_patterns:
        telefonlar.extend(re.findall(p, blob, flags=re.I))

    telefonlar.extend(telefon_label_yakinindan_ayikla(blob))
    telefonlar.extend(telefon_ayikla(blob))
    telefonlar.extend(whatsapp_telefonlari_ayikla(blob))

    return temiz_mail_listesi(mailler), temiz_telefon_listesi(telefonlar)


def v75_attr_and_script_blob(html):
    parts = [html or ""]
    try:
        soup = BeautifulSoup(html or "", "html.parser")
        for tag in soup.find_all(True):
            for attr in [
                "href", "content", "data-email", "data-mail", "data-phone", "data-tel",
                "aria-label", "title", "alt", "value", "data-href", "data-url"
            ]:
                val = tag.get(attr)
                if val:
                    parts.append(str(val))
        for script in soup.find_all("script"):
            txt = script.string or script.get_text(" ")
            if txt:
                parts.append(txt)
    except Exception:
        pass
    return " ".join(parts)


def sayfa_deep_contact_oku(url, referer="https://www.google.com/"):
    """
    V75: statik HTML + attribute + script/json + obfuscated mail/tel birlikte okunur.
    """
    sonuc = {"mailler": [], "telefonlar": [], "html": "", "text": "", "ok": False}

    try:
        r = guvenli_get(url, timeout=v73_mode_limits()["contact_timeout"], referer=referer)
        if r.status_code >= 400:
            return sonuc

        html = html_entity_temizle(r.text or "")
        visible_text = temiz_metin(html)
        blob = " ".join([
            html,
            visible_text,
            attribute_iceriklerini_topla(html),
            js_json_iletisim_parcalari(html),
            v75_attr_and_script_blob(html),
        ])

        mailto_mailler, tel_linkleri = mailto_ve_tel_linklerini_ayikla(html)
        mailler, telefonlar = v75_extract_contacts_from_blob(blob)
        mailler.extend(mailto_mailler)
        telefonlar.extend(tel_linkleri)

        sonuc["mailler"] = temiz_mail_listesi(mailler)
        sonuc["telefonlar"] = temiz_telefon_listesi(telefonlar)
        sonuc["html"] = html
        sonuc["text"] = visible_text
        sonuc["ok"] = True

    except Exception:
        pass

    return sonuc


def v75_playwright_contact_oku(url):
    """
    Dengeli modda bile sadece iletisim bulunamazsa hafif JS render fallback.
    Firma basina birkac sayfayla sinirli tutulur.
    """
    sonuc = {"mailler": [], "telefonlar": [], "html": "", "text": "", "ok": False}

    if not PLAYWRIGHT_AKTIF:
        return sonuc

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            )
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121 Safari/537.36",
                viewport={"width": 1366, "height": 900},
                locale="tr-TR"
            )
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(2500)

            try:
                page.evaluate("""
                    () => {
                        const words = ['kabul', 'accept', 'tamam', 'onay', 'allow'];
                        for (const el of Array.from(document.querySelectorAll('button, a'))) {
                            const txt = (el.innerText || el.textContent || '').toLowerCase();
                            if (words.some(w => txt.includes(w))) {
                                try { el.click(); } catch(e) {}
                            }
                        }
                    }
                """)
                page.wait_for_timeout(600)
            except Exception:
                pass

            for _ in range(3):
                try:
                    page.evaluate("window.scrollBy(0, 900)")
                except Exception:
                    pass
                page.wait_for_timeout(500)

            html = page.content()
            try:
                text = page.inner_text("body")
            except Exception:
                text = ""
            browser.close()

        blob = " ".join([html_entity_temizle(html), html_entity_temizle(text), v75_attr_and_script_blob(html)])
        mailler, telefonlar = v75_extract_contacts_from_blob(blob)
        mailto_mailler, tel_linkleri = mailto_ve_tel_linklerini_ayikla(html)
        mailler.extend(mailto_mailler)
        telefonlar.extend(tel_linkleri)

        sonuc["mailler"] = temiz_mail_listesi(mailler)
        sonuc["telefonlar"] = temiz_telefon_listesi(telefonlar)
        sonuc["html"] = html
        sonuc["text"] = text
        sonuc["ok"] = True
    except Exception as e:
        logging.warning(f"V75 Playwright contact hatasi: {url} - {str(e)}")

    return sonuc


def v75_filter_mails_for_company(mailler, web_url, firma_adi):
    temiz = temiz_mail_listesi(mailler)
    if not temiz:
        return []

    uyumlu = [m for m in temiz if v74_mail_site_uyumu(m, web_url, firma_adi)]
    if uyumlu:
        return uyumlu[:5]

    # Kurumsal sitede mail domaini siteyle ayni degilse son care: info/contact/sales gibi rol mailleri.
    root = v72_domain_root(web_url)
    profile = v74_company_profile(firma_adi)
    marka = profile.get("marka", "")
    soft = []
    for m in temiz:
        local, dom = m.split("@", 1)
        mail_root = v72_domain_root(dom)
        if m.startswith(V72_ROLE_MAIL_PREFIXES) and (root in mail_root or marka in mail_root or marka in local):
            soft.append(m)
    return soft[:5]


def websitesinden_iletisim_bul(web_url, firma_adi=""):
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
        tum_mailler = []
        tum_telefonlar = []
        kaynaklar = []
        okunan = 0

        aday_url_listesi = v75_contact_url_adaylari(web_url)

        try:
            home = sayfa_deep_contact_oku(web_url, referer="https://www.google.com/")
            if home.get("ok"):
                okunan += 1
                tum_mailler.extend(home.get("mailler", []))
                tum_telefonlar.extend(home.get("telefonlar", []))
                kaynaklar.append(web_url)
                aday_url_listesi = [web_url] + v72_html_contact_linkleri(web_url, home.get("html", "")) + aday_url_listesi
        except Exception:
            pass

        contact_limit = max(v73_mode_limits()["contact_limit"], 10)
        seen = set()
        for idx, u in enumerate(aday_url_listesi[:contact_limit]):
            if u in seen:
                continue
            seen.add(u)
            try:
                time.sleep(random.uniform(0.1, 0.35))
                data = sayfa_deep_contact_oku(u, referer=web_url if idx > 0 else "https://www.google.com/")
                if not data.get("ok"):
                    continue
                okunan += 1
                if data.get("mailler"):
                    tum_mailler.extend(data["mailler"])
                    kaynaklar.append(u)
                if data.get("telefonlar"):
                    tum_telefonlar.extend(data["telefonlar"])
                    kaynaklar.append(u)
                if v75_filter_mails_for_company(tum_mailler, web_url, firma_adi) and temiz_telefon_listesi(tum_telefonlar):
                    break
            except Exception:
                continue

        # Static okuma yetmezse JS-render contact fallback.
        temiz_mailler_once = v75_filter_mails_for_company(tum_mailler, web_url, firma_adi)
        temiz_tel_once = temiz_telefon_listesi(tum_telefonlar)
        if (not temiz_mailler_once or not temiz_tel_once) and PLAYWRIGHT_AKTIF:
            for u in list(dict.fromkeys(aday_url_listesi))[:3]:
                data = v75_playwright_contact_oku(u)
                if data.get("mailler"):
                    tum_mailler.extend(data["mailler"])
                    kaynaklar.append(u)
                if data.get("telefonlar"):
                    tum_telefonlar.extend(data["telefonlar"])
                    kaynaklar.append(u)
                if v75_filter_mails_for_company(tum_mailler, web_url, firma_adi) and temiz_telefon_listesi(tum_telefonlar):
                    break

        temiz_mailler = v75_filter_mails_for_company(tum_mailler, web_url, firma_adi)
        temiz_telefonlar = temiz_telefon_listesi(tum_telefonlar)

        if temiz_mailler:
            sonuc["eposta"] = ", ".join(temiz_mailler[:5])
        if temiz_telefonlar:
            sonuc["telefon"] = ", ".join(temiz_telefonlar[:5])

        sonuc["kaynak"] = list(dict.fromkeys(kaynaklar))[0] if kaynaklar else web_url

        if sonuc["eposta"] != "Bulunamadi" and sonuc["telefon"] != "Bulunamadi":
            sonuc["durum"] = f"Tamamlandi | V75 contact sayfa: {okunan}"
        elif sonuc["eposta"] != "Bulunamadi" or sonuc["telefon"] != "Bulunamadi":
            sonuc["durum"] = f"Kismi tamamlandi | V75 contact sayfa: {okunan}"
        else:
            sonuc["durum"] = f"Web bulundu, iletisim bulunamadi | V75 contact sayfa: {okunan}"

    except Exception as e:
        sonuc["durum"] = "Hata"
        sonuc["hata"] = str(e)
        logging.error(f"V75 site iletisim hatasi: {web_url} - {str(e)}")

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
        time.sleep(random.uniform(0.6, 1.3))
        web = firma_websitesi_bul(firma_adi)

        if not web:
            sonuc["durum"] = "Web sitesi bulunamadi"
            return sonuc_guven_skorlari_ekle(sonuc, firma_adi)

        iletisim = websitesinden_iletisim_bul(web, firma_adi=firma_adi)
        sonuc.update(iletisim)
        sonuc["firma_adi"] = firma_adi

        web_score = domain_puanla(web, firma_adi, " ".join([sonuc.get("eposta", ""), sonuc.get("telefon", ""), sonuc.get("kaynak", "")]))
        if web_score < (45 if v74_expected_groups(firma_adi) else 15):
            sonuc["durum"] = f"Web supheli - manuel kontrol gerekli | Skor: {web_score}"
            sonuc["manuel_kontrol"] = "Evet"

        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)
    except Exception as e:
        sonuc["durum"] = "Hata"
        sonuc["hata"] = str(e)
        logging.error(f"V75 derin bilgi hatasi: {firma_adi} - {str(e)}")
        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)


# ============================================================
# V76 SEARCH-SNIPPET CONFIRMATION + CONTACT FALLBACK
# Resmi site bulunamadiginda arama sonucunu daha akilli kullanir.
# Resmi site bulundu ama mail/telefon cikmadiysa Bing/DDG snippet ve ayni-domain
# contact sayfalarini ikinci kaynak gibi tarar.
# ============================================================

V75_FIRMA_WEBSITE_BUL = firma_websitesi_bul
V75_WEBSITE_ILETISIM_BUL = websitesinden_iletisim_bul


def v76_search_result_items(query, limit=12):
    items = []
    urls = [
        f"https://www.bing.com/search?q={quote_plus(query)}",
        f"https://duckduckgo.com/html/?q={quote_plus(query)}",
    ]

    for search_url in urls:
        try:
            r = guvenli_get(search_url, timeout=v73_mode_limits()["search_timeout"], referer="https://www.google.com/")
            if r.status_code >= 400:
                continue

            soup = BeautifulSoup(r.text or "", "html.parser")
            for block in soup.select("li.b_algo, div.result, div.web-result, article, div"):
                a = block.select_one("a[href]")
                if not a:
                    continue
                href = normalize_url(arama_linkini_temizle(a.get("href", "")))
                if not href or v72_url_kotu_mu(href):
                    continue

                text = temiz_metin(block.get_text(" "))
                if not text:
                    text = temiz_metin(a.get_text(" "))
                items.append({"url": href, "text": text[:2000]})

                if len(items) >= limit:
                    break
        except Exception as e:
            logging.warning(f"V76 arama sonucu okunamadi: {query} - {str(e)}")

        if len(items) >= limit:
            break

    final = []
    seen = set()
    for item in items:
        d = domain_al(item["url"])
        key = d + "|" + item["url"].split("?")[0]
        if d and key not in seen:
            seen.add(key)
            final.append(item)
        if len(final) >= limit:
            break
    return final


def v76_exact_domain_fit(url, firma_adi):
    root = v72_domain_root(url)
    profile = v74_company_profile(firma_adi)
    tokens = profile["tokens"]
    if not root or not tokens:
        return False

    root_flat = root.replace("-", "")
    joined2 = "".join(tokens[:2])
    joined3 = "".join(tokens[:3])

    if len(joined3) >= 7 and joined3 in root_flat:
        return True
    if len(joined2) >= 6 and joined2 in root_flat:
        return True

    # TK Tuzla gibi sector kelimesi domainde olmayabilir ama iki marka tokeni beraber gecerse guclu.
    brand_tokens = profile["brand_tokens"]
    if len(brand_tokens) >= 2 and all(t in root_flat for t in brand_tokens[:2]):
        return True

    # Turk Loydu -> turkloydu.org
    if "loydu" in tokens and "turk" in tokens and "turkloydu" in root_flat:
        return True

    return False


def v76_result_text_supports_company(item, firma_adi):
    text = turkce_karakter_temizle((item.get("text", "") + " " + item.get("url", "")).lower())
    profile = v74_company_profile(firma_adi)
    tokens = profile["tokens"]
    if not tokens:
        return 0

    score = 0
    for t in tokens[:6]:
        if t in text:
            score += 14

    for group in v74_expected_groups(firma_adi):
        cfg = V74_SECTOR_GROUPS[group]
        if v74_text_has_any(text, cfg["needles"]):
            score += 35
        if v74_text_has_any(text, cfg["negative"]):
            score -= 80

    if any(w in text for w in ["official", "resmi", "contact", "iletisim", "iletişim", "phone", "email", "e-posta"]):
        score += 12

    if v76_exact_domain_fit(item.get("url", ""), firma_adi):
        score += 55

    return score


def firma_websitesi_bul(firma_adi):
    firma_adi_temiz = firma_adi_temizle(firma_adi)
    if not firma_adi_temiz:
        return ""

    cache_key = "v76:" + firma_adi_temiz.lower().strip()
    if cache_key in WEBSITE_CACHE:
        return WEBSITE_CACHE[cache_key]

    # Once V75/V74 motoru denensin.
    web = V75_FIRMA_WEBSITE_BUL(firma_adi_temiz)
    if web:
        WEBSITE_CACHE[cache_key] = web
        return web

    queries = [
        f'"{firma_adi_temiz}" official website',
        f'"{firma_adi_temiz}" contact',
        f'{firma_adi_temiz} official site',
        f'{firma_adi_temiz} website',
    ]

    groups = v74_expected_groups(firma_adi_temiz)
    if groups:
        queries.extend([
            f'"{firma_adi_temiz}" {" ".join(groups)}',
            f'{firma_adi_temiz} {" ".join(groups)} contact',
        ])

    scored = []
    deadline = time.time() + v73_mode_limits()["firma_cap"]
    for q in queries[:6]:
        if time.time() > deadline:
            break
        for item in v76_search_result_items(q, limit=10):
            url = normalize_url(item.get("url", ""))
            if not url or v72_url_kotu_mu(url):
                continue
            score = domain_puanla(url, firma_adi_temiz, item.get("text", ""))
            score += v76_result_text_supports_company(item, firma_adi_temiz)
            scored.append({"url": url, "score": score, "text": item.get("text", "")})

    # Direkt domain adayi, sayfa acilmasa bile exact domain fit ise kabul edilebilir.
    for url in domain_adaylari_uret(firma_adi_temiz)[:40]:
        if time.time() > deadline:
            break
        if not v76_exact_domain_fit(url, firma_adi_temiz):
            continue
        score = 70
        try:
            checked = aday_site_oku_ve_puanla(url, firma_adi_temiz)
            score = max(score, checked.get("puan", 0))
            url = checked.get("url", url) or url
        except Exception:
            pass
        scored.append({"url": url, "score": score, "text": ""})

    if not scored:
        WEBSITE_CACHE[cache_key] = ""
        return ""

    scored = sorted(scored, key=lambda x: x.get("score", -100), reverse=True)
    threshold = 65 if v74_expected_groups(firma_adi_temiz) else 38
    best = scored[0]

    if best.get("score", -100) >= threshold:
        WEBSITE_CACHE[cache_key] = best["url"]
        return best["url"]

    WEBSITE_CACHE[cache_key] = ""
    return ""


def v76_search_contact_fallback(web_url, firma_adi):
    domain = domain_al(web_url).replace("www.", "")
    root = v72_domain_root(domain)
    queries = [
        f'site:{domain} contact email phone',
        f'site:{domain} iletişim telefon e-posta',
        f'"{firma_adi}" "{domain}" email phone',
        f'"{firma_adi}" "{domain}" iletişim',
        f'"{firma_adi}" contact phone email',
    ]

    mailler = []
    telefonlar = []
    contact_links = []

    for q in queries[:5]:
        for item in v76_search_result_items(q, limit=12):
            url = normalize_url(item.get("url", ""))
            text = item.get("text", "")
            if url and v72_same_site(url, web_url) and any(w in turkce_karakter_temizle(url.lower()) for w in V72_CONTACT_WORDS + ("public/contact", "iletisim-formu", "facilities", "yerleskeler")):
                contact_links.append(url)

            m, t = v75_extract_contacts_from_blob(text)
            mailler.extend(m)
            telefonlar.extend(t)

    # Ayni domaindeki arama sonucu contact linklerini gercek sayfa olarak oku.
    for u in list(dict.fromkeys(contact_links))[:5]:
        data = sayfa_deep_contact_oku(u, referer=web_url)
        if data.get("mailler"):
            mailler.extend(data["mailler"])
        if data.get("telefonlar"):
            telefonlar.extend(data["telefonlar"])

    # Snippet ucuncu kaynak olsa bile mail domaini firma/site ile uyumluysa kabul et.
    filtered_mails = []
    for m in temiz_mail_listesi(mailler):
        if v74_mail_site_uyumu(m, web_url, firma_adi):
            filtered_mails.append(m)
            continue
        try:
            mail_root = v72_domain_root(m.split("@", 1)[1])
            if root and mail_root and (root == mail_root or root in mail_root or mail_root in root):
                filtered_mails.append(m)
        except Exception:
            pass

    return {
        "mailler": temiz_mail_listesi(filtered_mails),
        "telefonlar": temiz_telefon_listesi(telefonlar),
        "links": list(dict.fromkeys(contact_links)),
    }


def websitesinden_iletisim_bul(web_url, firma_adi=""):
    sonuc = V75_WEBSITE_ILETISIM_BUL(web_url, firma_adi=firma_adi)

    mevcut_mail = [] if sonuc.get("eposta") in ["", None, "Bulunamadi"] else temiz_mail_listesi(str(sonuc.get("eposta", "")).split(","))
    mevcut_tel = [] if sonuc.get("telefon") in ["", None, "Bulunamadi"] else temiz_telefon_listesi(str(sonuc.get("telefon", "")).split(","))

    if mevcut_mail and mevcut_tel:
        sonuc["durum"] = str(sonuc.get("durum", "")).replace("V75", "V76")
        return sonuc

    fb = v76_search_contact_fallback(web_url, firma_adi)

    mailler = mevcut_mail + fb.get("mailler", [])
    telefonlar = mevcut_tel + fb.get("telefonlar", [])
    mailler = temiz_mail_listesi(mailler)
    telefonlar = temiz_telefon_listesi(telefonlar)

    if mailler:
        sonuc["eposta"] = ", ".join(mailler[:5])
    if telefonlar:
        sonuc["telefon"] = ", ".join(telefonlar[:5])

    if fb.get("links") and (sonuc.get("kaynak") in ["", None] or str(sonuc.get("kaynak")) == "nan"):
        sonuc["kaynak"] = fb["links"][0]

    if sonuc["eposta"] != "Bulunamadi" and sonuc["telefon"] != "Bulunamadi":
        sonuc["durum"] = "Tamamlandi | V76 contact + search fallback"
    elif sonuc["eposta"] != "Bulunamadi" or sonuc["telefon"] != "Bulunamadi":
        sonuc["durum"] = "Kismi tamamlandi | V76 contact + search fallback"
    else:
        sonuc["durum"] = "Web bulundu, iletisim bulunamadi | V76 contact + search fallback"

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
        time.sleep(random.uniform(0.5, 1.2))
        web = firma_websitesi_bul(firma_adi)

        if not web:
            sonuc["durum"] = "Web sitesi bulunamadi"
            return sonuc_guven_skorlari_ekle(sonuc, firma_adi)

        iletisim = websitesinden_iletisim_bul(web, firma_adi=firma_adi)
        sonuc.update(iletisim)
        sonuc["firma_adi"] = firma_adi
        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)
    except Exception as e:
        sonuc["durum"] = "Hata"
        sonuc["hata"] = str(e)
        logging.error(f"V76 derin bilgi hatasi: {firma_adi} - {str(e)}")
        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)


# ============================================================
# V77 AGGRESSIVE OFFICIAL DOMAIN + CONTACT COMPLETION
# V76'daki iki acigi kapatir:
# 1) Google/Bing'de kolay bulunan resmi siteleri "Bulunamadi" gecme.
# 2) Dogru sitede mail/telefon bulunamazsa resmi site + arama snippet +
#    guvenli ucuncu kaynaklardan, domain/firma uyumu olan iletisimleri tamamla.
# ============================================================

V76_FIRMA_WEBSITE_BUL = firma_websitesi_bul
V76_WEBSITE_ILETISIM_BUL = websitesinden_iletisim_bul


def v77_candidate_roots(firma_adi):
    profile = v74_company_profile(firma_adi)
    tokens = profile["tokens"]
    brand_tokens = profile["brand_tokens"] or tokens[:1]
    groups = v74_expected_groups(firma_adi)
    roots = []

    def add(x):
        x = normalize_domain_token(x)
        if x and len(x) >= 3 and x not in roots:
            roots.append(x)

    if brand_tokens:
        add(brand_tokens[0])
    if len(brand_tokens) >= 2:
        add(brand_tokens[0] + brand_tokens[1])
        add(brand_tokens[0] + "-" + brand_tokens[1])

    if tokens:
        add("".join(tokens[:2]))
        if len(tokens) >= 3:
            add("".join(tokens[:3]))

    if "shipyard" in groups:
        bases = []
        if brand_tokens:
            bases.append(brand_tokens[0])
        if len(brand_tokens) >= 2:
            bases.append(brand_tokens[0] + brand_tokens[1])
            bases.append(brand_tokens[0] + "-" + brand_tokens[1])
        for b in bases:
            add(b + "shipyard")
            add(b + "-shipyard")
            add(b + "shipyards")
        # Shipyard firmalarinda dogru site bazen sadece marka domainidir: cemre.com.tr, sanmar.com.tr.
        for b in bases:
            add(b)

    if "marine" in groups:
        bases = []
        if brand_tokens:
            bases.append(brand_tokens[0])
        if len(brand_tokens) >= 2:
            bases.append(brand_tokens[0] + brand_tokens[1])
            bases.append(brand_tokens[0] + "-" + brand_tokens[1])
        for b in bases:
            add(b + "marine")
            add(b + "-marine")
        for b in bases:
            add(b)

    if "classification" in groups or "loydu" in tokens:
        add("turkloydu")
        add("turk-loydu")

    return roots[:40]


def v77_priority_domain_candidates(firma_adi):
    roots = v77_candidate_roots(firma_adi)
    tlds = [".com.tr", ".com", ".org", ".net", ".tr"]
    paths = ["", "/", "/tr", "/tr/", "/en", "/en/"]
    adaylar = []

    for r in roots:
        for tld in tlds:
            for host in [f"https://www.{r}{tld}", f"https://{r}{tld}"]:
                for path in paths:
                    adaylar.append(host + path)

    return list(dict.fromkeys(adaylar))[:180]


def v77_official_candidate_score(url, firma_adi, text=""):
    root = v72_domain_root(url)
    profile = v74_company_profile(firma_adi)
    tokens = profile["tokens"]
    brand_tokens = profile["brand_tokens"] or tokens[:1]
    groups = v74_expected_groups(firma_adi)
    low_text = turkce_karakter_temizle(str(text or "").lower()[:30000])

    if not root or not tokens:
        return -100

    score = 0
    root_flat = root.replace("-", "")
    brand_join = "".join(brand_tokens[:2])
    token_join2 = "".join(tokens[:2])
    token_join3 = "".join(tokens[:3])

    if brand_tokens and brand_tokens[0] in root_flat:
        score += 38
    if len(brand_tokens) >= 2 and all(t in root_flat for t in brand_tokens[:2]):
        score += 70
    if len(brand_join) >= 6 and brand_join in root_flat:
        score += 80
    if len(token_join2) >= 6 and token_join2 in root_flat:
        score += 85
    if len(token_join3) >= 8 and token_join3 in root_flat:
        score += 90

    for group in groups:
        cfg = V74_SECTOR_GROUPS[group]
        if any(r in root_flat for r in cfg["roots"]):
            score += 55
        if low_text and v74_text_has_any(low_text, cfg["needles"]):
            score += 45
        if low_text and v74_text_has_any(low_text, cfg["negative"]):
            score -= 95

    if domain_al(url).endswith(".com.tr"):
        score += 14
    elif domain_al(url).endswith(".com"):
        score += 7
    elif domain_al(url).endswith(".org") and ("loydu" in tokens or "classification" in groups):
        score += 18

    # Brand-only domain, sector firmada ancak sayfa metni sektoru dogrularsa yuksek olsun.
    if groups and brand_tokens and root_flat == brand_tokens[0]:
        if low_text and any(v74_text_has_any(low_text, V74_SECTOR_GROUPS[g]["needles"]) for g in groups):
            score += 30
        else:
            score -= 35

    return score


def v77_active_site_score(url, firma_adi):
    try:
        r = guvenli_get(url, timeout=v73_mode_limits()["site_timeout"], referer="https://www.google.com/")
        final_url = getattr(r, "url", url) or url
        text = ""
        if r.status_code < 500:
            text = temiz_metin(r.text or "")
        score = v77_official_candidate_score(final_url, firma_adi, text)
        if r.status_code < 400:
            score += 20
        elif r.status_code in [401, 403]:
            score += 5
        return {"url": final_url, "score": score, "text": text}
    except Exception:
        # Site timeout verse bile domain cok kuvvetliyse tamamen atma.
        return {"url": url, "score": v77_official_candidate_score(url, firma_adi, ""), "text": ""}


def v77_direct_official_site_bul(firma_adi):
    scored = []
    for url in v77_priority_domain_candidates(firma_adi)[:80]:
        root = v72_domain_root(url)
        # Brand-only generic domainleri once ele; aksi halde ada.com.tr gibi yanlislar doner.
        if root in V74_GENERIC_ROOTS and v74_expected_groups(firma_adi):
            continue
        s = v77_active_site_score(url, firma_adi)
        if s["score"] >= (70 if v74_expected_groups(firma_adi) else 42):
            scored.append(s)
        if len(scored) >= 4:
            break

    if scored:
        scored = sorted(scored, key=lambda x: x["score"], reverse=True)
        return scored[0]["url"]
    return ""


def firma_websitesi_bul(firma_adi):
    firma_adi_temiz = firma_adi_temizle(firma_adi)
    if not firma_adi_temiz:
        return ""

    cache_key = "v77:" + firma_adi_temiz.lower().strip()
    if cache_key in WEBSITE_CACHE:
        return WEBSITE_CACHE[cache_key]

    # Once deterministik resmi domainleri dene. Bu kisim Tersan/Cemre/RMK/Med/Yonca gibi
    # Google'da kolay bulunan ama skor yuzunden kacabilen firmalari toparlar.
    direct = v77_direct_official_site_bul(firma_adi_temiz)
    if direct:
        WEBSITE_CACHE[cache_key] = direct
        return direct

    web = V76_FIRMA_WEBSITE_BUL(firma_adi_temiz)
    if web:
        WEBSITE_CACHE[cache_key] = web
        return web

    # Son care: arama sonuclari icinden resmi domain puanlamasi.
    queries = [
        f'"{firma_adi_temiz}" official website',
        f'"{firma_adi_temiz}" website',
        f'"{firma_adi_temiz}" contact',
        f'{firma_adi_temiz} resmi web sitesi',
        f'{firma_adi_temiz} iletişim',
    ]
    scored = []
    for q in queries[:5]:
        for item in v76_search_result_items(q, limit=12):
            url = normalize_url(item.get("url", ""))
            if not url or v72_url_kotu_mu(url):
                continue
            score = v77_official_candidate_score(url, firma_adi_temiz, item.get("text", ""))
            score += v76_result_text_supports_company(item, firma_adi_temiz)
            if score >= (60 if v74_expected_groups(firma_adi_temiz) else 35):
                scored.append({"url": url, "score": score})

    if scored:
        scored = sorted(scored, key=lambda x: x["score"], reverse=True)
        WEBSITE_CACHE[cache_key] = scored[0]["url"]
        return scored[0]["url"]

    WEBSITE_CACHE[cache_key] = ""
    return ""


def v77_contact_search_queries(web_url, firma_adi):
    domain = domain_al(web_url).replace("www.", "")
    root = v72_domain_root(domain)
    firma = firma_adi_temizle(firma_adi)
    queries = [
        f'site:{domain} contact email phone',
        f'site:{domain} iletişim telefon e-posta',
        f'site:{domain} "{firma}"',
        f'"{firma}" "{domain}" email phone',
        f'"{firma}" "{domain}" iletişim',
        f'"{firma}" e-posta telefon',
        f'"{firma}" iletişim bilgileri',
        f'"{firma}" contact details',
        f'"{firma}" email',
        f'"{firma}" phone',
    ]
    if root:
        queries.extend([
            f'"{root}" email phone',
            f'"{root}" iletişim telefon',
        ])
    return list(dict.fromkeys(queries))


def v77_search_contact_fallback(web_url, firma_adi):
    mailler = []
    telefonlar = []
    contact_links = []
    web_root = v72_domain_root(web_url)
    profile = v74_company_profile(firma_adi)
    marka = profile.get("marka", "")

    for q in v77_contact_search_queries(web_url, firma_adi)[:10]:
        for item in v76_search_result_items(q, limit=14):
            url = normalize_url(item.get("url", ""))
            text = item.get("text", "")
            blob = text + " " + url

            m, t = v75_extract_contacts_from_blob(blob)
            for mail in m:
                try:
                    mail_root = v72_domain_root(mail.split("@", 1)[1])
                except Exception:
                    mail_root = ""
                if (
                    v74_mail_site_uyumu(mail, web_url, firma_adi)
                    or (web_root and mail_root and (web_root == mail_root or web_root in mail_root or mail_root in web_root))
                    or (marka and (marka in mail_root or marka in mail.split("@", 1)[0]))
                ):
                    mailler.append(mail)

            # Telefon icin firma/sayfa metninde marka veya domain gecmesi yeterli.
            low_blob = turkce_karakter_temizle(blob.lower())
            if marka and (marka in low_blob or web_root in low_blob):
                telefonlar.extend(t)

            if url and v72_same_site(url, web_url):
                low_url = turkce_karakter_temizle(url.lower())
                if any(w in low_url for w in list(V72_CONTACT_WORDS) + ["person", "people", "purchasing", "sales", "locations", "offices", "public/contact"]):
                    contact_links.append(url)

    for u in list(dict.fromkeys(contact_links))[:8]:
        data = sayfa_deep_contact_oku(u, referer=web_url)
        if data.get("mailler"):
            for mail in data["mailler"]:
                if v74_mail_site_uyumu(mail, web_url, firma_adi):
                    mailler.append(mail)
        if data.get("telefonlar"):
            telefonlar.extend(data["telefonlar"])

    return {
        "mailler": temiz_mail_listesi(mailler),
        "telefonlar": temiz_telefon_listesi(telefonlar),
        "links": list(dict.fromkeys(contact_links)),
    }


def websitesinden_iletisim_bul(web_url, firma_adi=""):
    sonuc = V76_WEBSITE_ILETISIM_BUL(web_url, firma_adi=firma_adi)

    mevcut_mail = [] if sonuc.get("eposta") in ["", None, "Bulunamadi"] else temiz_mail_listesi(str(sonuc.get("eposta", "")).split(","))
    mevcut_tel = [] if sonuc.get("telefon") in ["", None, "Bulunamadi"] else temiz_telefon_listesi(str(sonuc.get("telefon", "")).split(","))

    if mevcut_mail and mevcut_tel:
        sonuc["durum"] = str(sonuc.get("durum", "")).replace("V76", "V77")
        return sonuc

    fb = v77_search_contact_fallback(web_url, firma_adi)
    mailler = temiz_mail_listesi(mevcut_mail + fb.get("mailler", []))
    telefonlar = temiz_telefon_listesi(mevcut_tel + fb.get("telefonlar", []))

    if mailler:
        sonuc["eposta"] = ", ".join(mailler[:5])
    if telefonlar:
        sonuc["telefon"] = ", ".join(telefonlar[:5])
    if fb.get("links"):
        sonuc["kaynak"] = fb["links"][0]

    if sonuc["eposta"] != "Bulunamadi" and sonuc["telefon"] != "Bulunamadi":
        sonuc["durum"] = "Tamamlandi | V77 contact completion"
    elif sonuc["eposta"] != "Bulunamadi" or sonuc["telefon"] != "Bulunamadi":
        sonuc["durum"] = "Kismi tamamlandi | V77 contact completion"
    else:
        sonuc["durum"] = "Web bulundu, iletisim bulunamadi | V77 contact completion"

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
        time.sleep(random.uniform(0.5, 1.1))
        web = firma_websitesi_bul(firma_adi)

        if not web:
            sonuc["durum"] = "Web sitesi bulunamadi"
            return sonuc_guven_skorlari_ekle(sonuc, firma_adi)

        iletisim = websitesinden_iletisim_bul(web, firma_adi=firma_adi)
        sonuc.update(iletisim)
        sonuc["firma_adi"] = firma_adi
        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)
    except Exception as e:
        sonuc["durum"] = "Hata"
        sonuc["hata"] = str(e)
        logging.error(f"V77 derin bilgi hatasi: {firma_adi} - {str(e)}")
        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)


# ============================================================
# V78 FAST BALANCED ROUTER
# V77'nin agir arama/contact tamamlayicisini Dengeli moddan cikarir.
# Hedef: Dengeli mod seri sonuc uretecek; Derin mod eksikler icin agir tamamlayici calistiracak.
# ============================================================

V77_FIRMA_WEBSITE_BUL = firma_websitesi_bul
V77_WEBSITE_ILETISIM_BUL = websitesinden_iletisim_bul
V77_DERIN_BILGI_BUL = derin_bilgi_bul


def v78_light_direct_site_bul(firma_adi):
    """
    Dengeli mod icin kisa ve ucuz resmi domain denemesi.
    Yanlis pozitifleri azaltmak icin generic rootlari atlar, ama cok fazla sayfa gezmez.
    """
    try:
        candidates = []
        for url in v77_priority_domain_candidates(firma_adi)[:28]:
            root = v72_domain_root(url)
            if root in V74_GENERIC_ROOTS and v74_expected_groups(firma_adi):
                continue
            if url not in candidates:
                candidates.append(url)

        for url in candidates[:14]:
            try:
                r = guvenli_get(url, timeout=3, referer="https://www.google.com/")
                final_url = getattr(r, "url", url) or url
                if r.status_code >= 500:
                    continue
                text = temiz_metin((r.text or "")[:12000]) if r.status_code < 400 else ""
                score = v77_official_candidate_score(final_url, firma_adi, text)
                if score >= (72 if v74_expected_groups(firma_adi) else 45):
                    return final_url
            except Exception:
                continue
    except Exception:
        pass
    return ""


def firma_websitesi_bul(firma_adi):
    """
    V78:
    - Dengeli/Hizli: once ucuz direkt domain + V75/V76 hafif motor.
    - Derin: V77 agir arama-snippet motorunu kullan.
    """
    firma_adi_temiz = firma_adi_temizle(firma_adi)
    if not firma_adi_temiz:
        return ""

    cache_key = "v78:" + SCAN_MODE + ":" + firma_adi_temiz.lower().strip()
    if cache_key in WEBSITE_CACHE:
        return WEBSITE_CACHE[cache_key]

    if SCAN_MODE == "Derin Tarama":
        web = V77_FIRMA_WEBSITE_BUL(firma_adi_temiz)
        WEBSITE_CACHE[cache_key] = web
        return web

    direct = v78_light_direct_site_bul(firma_adi_temiz)
    if direct:
        WEBSITE_CACHE[cache_key] = direct
        return direct

    # V76 motoru V77'ye gore daha hafif; Dengeli modda bunu ana fallback yap.
    try:
        web = V76_FIRMA_WEBSITE_BUL(firma_adi_temiz)
    except Exception:
        web = ""

    WEBSITE_CACHE[cache_key] = web or ""
    return web or ""


def v78_fast_contact_paths(web_url):
    root = v75_root_url(web_url)
    parsed = urlparse(normalize_url(web_url))
    paths = [
        "", "/", "/contact", "/contact-us", "/contacts",
        "/iletisim", "/iletişim", "/tr/contact", "/tr/iletisim",
        "/tr/iletişim", "/en/contact", "/en/contact-us",
        "/kurumsal/iletisim", "/corporate/contact"
    ]

    parts = [p for p in parsed.path.split("/") if p]
    if parts and parts[0].lower() in ["tr", "en"]:
        lang = "/" + parts[0].lower()
        paths = ["", "/", lang + "/contact", lang + "/iletisim", lang + "/iletişim"] + paths

    urls = []
    for p in paths:
        u = normalize_url(root + p)
        if url_gecerli_mi(u) and u not in urls:
            urls.append(u)
    return urls[:10]


def websitesinden_iletisim_bul(web_url, firma_adi=""):
    """
    V78:
    Dengeli modda sadece ayni site icindeki en olasi contact sayfalari okunur.
    V77 arama-snippet completion sadece Derin Tarama'da calisir.
    """
    if SCAN_MODE == "Derin Tarama":
        return V77_WEBSITE_ILETISIM_BUL(web_url, firma_adi=firma_adi)

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

    mailler = []
    telefonlar = []
    kaynak = normalize_url(web_url)
    okunan = 0

    for idx, u in enumerate(v78_fast_contact_paths(web_url)):
        try:
            data = sayfa_deep_contact_oku(u, referer=web_url if idx else "https://www.google.com/")
            if not data.get("ok"):
                continue
            okunan += 1
            if data.get("mailler"):
                mailler.extend(data["mailler"])
                kaynak = u
            if data.get("telefonlar"):
                telefonlar.extend(data["telefonlar"])
                kaynak = u

            filtered_mail = v75_filter_mails_for_company(mailler, web_url, firma_adi)
            filtered_tel = temiz_telefon_listesi(telefonlar)
            if filtered_mail and filtered_tel:
                break
        except Exception:
            continue

    mailler = v75_filter_mails_for_company(mailler, web_url, firma_adi)
    telefonlar = temiz_telefon_listesi(telefonlar)

    if mailler:
        sonuc["eposta"] = ", ".join(mailler[:5])
    if telefonlar:
        sonuc["telefon"] = ", ".join(telefonlar[:5])

    sonuc["kaynak"] = kaynak
    if sonuc["eposta"] != "Bulunamadi" and sonuc["telefon"] != "Bulunamadi":
        sonuc["durum"] = f"Tamamlandi | V78 fast contact sayfa: {okunan}"
    elif sonuc["eposta"] != "Bulunamadi" or sonuc["telefon"] != "Bulunamadi":
        sonuc["durum"] = f"Kismi tamamlandi | V78 fast contact sayfa: {okunan}"
    else:
        sonuc["durum"] = f"Web bulundu, iletisim bulunamadi | V78 fast contact sayfa: {okunan}"

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
        time.sleep(random.uniform(0.4, 0.9))
        web = firma_websitesi_bul(firma_adi)
        if not web:
            sonuc["durum"] = "Web sitesi bulunamadi"
            return sonuc_guven_skorlari_ekle(sonuc, firma_adi)

        iletisim = websitesinden_iletisim_bul(web, firma_adi=firma_adi)
        sonuc.update(iletisim)
        sonuc["firma_adi"] = firma_adi
        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)
    except Exception as e:
        sonuc["durum"] = "Hata"
        sonuc["hata"] = str(e)
        logging.error(f"V78 derin bilgi hatasi: {firma_adi} - {str(e)}")
        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)


# ============================================================
# V79 UNIVERSAL CONTACT RESOLVER
# Sadece dogru web'i bulmak yetmez; sitelerin dinamik yapilarina gore
# iletisim bilgisini cok katmanli toplar:
# 1) Statik HTML + attribute/script/json
# 2) Site ici gercek contact linkleri
# 3) Hafif Playwright render
# 4) Arama snippet + ayni domain/firma uyumlu ucuncu kaynak sinyali
# ============================================================

V78_FIRMA_WEBSITE_BUL = firma_websitesi_bul
V78_WEBSITE_ILETISIM_BUL = websitesinden_iletisim_bul

V79_CONTACT_KEYWORDS = (
    "contact", "contact-us", "contacts", "iletisim", "iletişim", "bize-ulasin",
    "bize-ulaşın", "addresses", "address", "phones", "phone", "telefon",
    "e-posta", "email", "locations", "offices", "yerleske", "yerleşke",
    "purchasing", "sales", "marketing", "communication", "kurumsal/iletisim",
    "corporate/contact", "public/contact", "person", "people"
)

V79_CONTACT_PATHS = [
    "/", "/contact", "/contact/", "/contact-us", "/contact-us/", "/contacts", "/contacts/",
    "/iletisim", "/iletisim/", "/iletişim", "/iletişim/", "/bize-ulasin", "/bize-ulasin/",
    "/tr", "/tr/", "/tr/contact", "/tr/contact/", "/tr/contact-us", "/tr/contact-us/",
    "/tr/contacts", "/tr/contacts/", "/tr/iletisim", "/tr/iletisim/", "/tr/iletişim", "/tr/iletişim/",
    "/tr/kurumsal/iletisim", "/tr/kurumsal/iletisim/", "/tr/kurumsal/iletişim",
    "/en", "/en/", "/en/contact", "/en/contact/", "/en/contact-us", "/en/contact-us/",
    "/en/contacts", "/en/contacts/", "/en/corporate/contact", "/en/corporate/contact/",
    "/kurumsal/iletisim", "/kurumsal/iletisim/", "/corporate/contact", "/corporate/contact/",
    "/about/contact", "/about-us/contact", "/company/contact",
    "/locations", "/locations/", "/offices", "/offices/", "/address", "/addresses",
    "/sitemap.xml"
]


def v79_limits():
    if SCAN_MODE == "Derin Tarama":
        return {"static_pages": 24, "browser_pages": 4, "search_queries": 8, "timeout": 7}
    if SCAN_MODE == "Hızlı Tarama":
        return {"static_pages": 8, "browser_pages": 1, "search_queries": 2, "timeout": 4}
    return {"static_pages": 14, "browser_pages": 2, "search_queries": 4, "timeout": 5}


def v79_has_value(x):
    return str(x or "").strip() not in ["", "nan", "NaN", "Bulunamadi"]


def v79_base_url(web_url):
    u = normalize_url(web_url)
    p = urlparse(u)
    return f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else u


def v79_decode_blob(text):
    t = html_entity_temizle(str(text or ""))
    try:
        t = unquote(t)
    except Exception:
        pass
    replacements = {
        "\\u0040": "@", "\\u002e": ".", "\\x40": "@", "\\x2e": ".",
        "&#64;": "@", "&#x40;": "@", "&commat;": "@",
        "[at]": "@", "(at)": "@", "{at}": "@", " at ": "@",
        "[dot]": ".", "(dot)": ".", "{dot}": ".", " dot ": ".",
        "\u00a0": " ",
    }
    for a, b in replacements.items():
        t = re.sub(re.escape(a), b, t, flags=re.I)
    return t.replace("\\/", "/").replace("[email protected]", "")


def v79_html_blob(html):
    parts = [html or "", temiz_metin(html or ""), attribute_iceriklerini_topla(html or ""), js_json_iletisim_parcalari(html or "")]
    try:
        soup = BeautifulSoup(html or "", "html.parser")
        for tag in soup.find_all(True):
            for attr in ["href", "content", "data-email", "data-mail", "data-phone", "data-tel", "aria-label", "title", "alt", "value", "data-href", "data-url"]:
                val = tag.get(attr)
                if val:
                    parts.append(str(val))
        for script in soup.find_all("script"):
            txt = script.string or script.get_text(" ")
            if txt:
                parts.append(txt)
    except Exception:
        pass
    return v79_decode_blob(" ".join(parts))


def v79_extract_contacts(blob):
    blob = v79_decode_blob(blob)
    mailler = []
    telefonlar = []

    try:
        mailler.extend(cloudflare_mailleri_ayikla(blob))
    except Exception:
        pass

    mailler.extend(eposta_ayikla(blob))
    mailler.extend(mail_label_yakinindan_ayikla(blob))

    phone_patterns = [
        r"\+90[\s\-\.\(\)]{0,4}\d{3}[\s\-\.\)]{0,4}\d{3}[\s\-\.]{0,3}\d{2}[\s\-\.]{0,3}\d{2}",
        r"0[\s\-\.\(\)]{0,4}\d{3}[\s\-\.\)]{0,4}\d{3}[\s\-\.]{0,3}\d{2}[\s\-\.]{0,3}\d{2}",
        r"\+\d{1,3}[\s\-\.\(\)]{0,4}\d{2,4}[\s\-\.\)]{0,4}\d{3,4}[\s\-\.]{0,3}\d{2,4}[\s\-\.]{0,3}\d{2,4}",
    ]
    for p in phone_patterns:
        telefonlar.extend(re.findall(p, blob, flags=re.I))

    telefonlar.extend(telefon_label_yakinindan_ayikla(blob))
    telefonlar.extend(telefon_ayikla(blob))
    telefonlar.extend(whatsapp_telefonlari_ayikla(blob))

    return temiz_mail_listesi(mailler), temiz_telefon_listesi(telefonlar)


def v79_internal_contact_links(base_url, html):
    links = []
    try:
        soup = BeautifulSoup(html or "", "html.parser")
        for a in soup.find_all("a", href=True):
            text = turkce_karakter_temizle(temiz_metin(a.get_text(" ")).lower())
            href = normalize_url(a.get("href", ""), base_url=base_url)
            if not url_gecerli_mi(href) or not v72_same_site(href, base_url):
                continue
            low = turkce_karakter_temizle((href + " " + text).lower())
            score = 0
            for kw in V79_CONTACT_KEYWORDS:
                if kw in low:
                    score += 10
            if score > 0:
                links.append((score, href))

        # Script icinde /tr/contact gibi path'ler varsa yakala.
        raw = html or ""
        for m in re.findall(r"""["']((?:/[a-z]{2})?/(?:contact|contact-us|contacts|iletisim|iletişim|bize-ulasin|locations|offices|kurumsal/iletisim|corporate/contact)[^"']*)["']""", raw, flags=re.I):
            href = normalize_url(m, base_url=base_url)
            if url_gecerli_mi(href) and v72_same_site(href, base_url):
                links.append((80, href))
    except Exception:
        pass

    final = []
    seen = set()
    for _, href in sorted(links, key=lambda x: x[0], reverse=True):
        if href not in seen:
            seen.add(href)
            final.append(href)
    return final[:12]


def v79_candidate_contact_urls(web_url, home_html=""):
    base = v79_base_url(web_url)
    urls = [normalize_url(web_url), base + "/"]

    p = urlparse(normalize_url(web_url))
    parts = [x for x in p.path.split("/") if x]
    if parts and parts[0].lower() in ["tr", "en", "de", "fr"]:
        lang = "/" + parts[0].lower()
        for path in V79_CONTACT_PATHS:
            if path == "/" or path.startswith(lang + "/"):
                continue
            urls.append(base + lang + path)

    for path in V79_CONTACT_PATHS:
        urls.append(base + path)

    urls.extend(v79_internal_contact_links(base, home_html))

    try:
        urls.extend(contact_url_adaylari_uret(web_url))
    except Exception:
        pass

    final = []
    seen = set()
    for u in urls:
        u = normalize_url(u)
        if not url_gecerli_mi(u) or not v72_same_site(u, base):
            continue
        if u not in seen:
            seen.add(u)
            final.append(u)
    return final[:40]


def v79_fetch_contact_page(url, referer):
    result = {"ok": False, "html": "", "text": "", "mailler": [], "telefonlar": []}
    try:
        r = guvenli_get(url, timeout=v79_limits()["timeout"], referer=referer)
        if r.status_code >= 400:
            return result
        html = html_entity_temizle(r.text or "")
        blob = v79_html_blob(html)
        mailler, telefonlar = v79_extract_contacts(blob)
        result.update({
            "ok": True,
            "html": html,
            "text": temiz_metin(html),
            "mailler": mailler,
            "telefonlar": telefonlar,
        })
    except Exception:
        pass
    return result


def v79_browser_contact_pages(urls):
    result = {"mailler": [], "telefonlar": [], "ok": False}
    if not PLAYWRIGHT_AKTIF or not urls:
        return result

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            )
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121 Safari/537.36",
                viewport={"width": 1366, "height": 900},
                locale="tr-TR"
            )

            for url in urls[:v79_limits()["browser_pages"]]:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=22000)
                    page.wait_for_timeout(1800)
                    try:
                        page.evaluate("""
                            () => {
                                const words = ['kabul', 'accept', 'tamam', 'onay', 'allow'];
                                for (const el of Array.from(document.querySelectorAll('button, a'))) {
                                    const txt = (el.innerText || el.textContent || '').toLowerCase();
                                    if (words.some(w => txt.includes(w))) {
                                        try { el.click(); } catch(e) {}
                                    }
                                }
                            }
                        """)
                    except Exception:
                        pass
                    for _ in range(3):
                        try:
                            page.evaluate("window.scrollBy(0, 900)")
                        except Exception:
                            pass
                        page.wait_for_timeout(450)

                    html = page.content()
                    try:
                        text = page.inner_text("body")
                    except Exception:
                        text = ""
                    mailler, telefonlar = v79_extract_contacts(" ".join([html_entity_temizle(html), html_entity_temizle(text), v79_html_blob(html)]))
                    result["mailler"].extend(mailler)
                    result["telefonlar"].extend(telefonlar)
                    result["ok"] = True
                except Exception:
                    continue
            browser.close()
    except Exception as e:
        logging.warning(f"V79 browser contact hata: {str(e)}")

    result["mailler"] = temiz_mail_listesi(result["mailler"])
    result["telefonlar"] = temiz_telefon_listesi(result["telefonlar"])
    return result


def v79_filter_mails(mailler, web_url, firma_adi):
    cleaned = temiz_mail_listesi(mailler)
    if not cleaned:
        return []

    web_root = v72_domain_root(web_url)
    profile = v74_company_profile(firma_adi)
    marka = profile.get("marka", "")
    accepted = []

    for mail in cleaned:
        try:
            local, dom = mail.split("@", 1)
            mail_root = v72_domain_root(dom)
        except Exception:
            continue
        if v74_mail_site_uyumu(mail, web_url, firma_adi):
            accepted.append(mail)
        elif web_root and mail_root and (web_root == mail_root or web_root in mail_root or mail_root in web_root):
            accepted.append(mail)
        elif marka and (marka in mail_root or marka in local):
            accepted.append(mail)

    return temiz_mail_listesi(accepted)[:5]


def v79_search_contact_completion(web_url, firma_adi):
    domain = domain_al(web_url).replace("www.", "")
    firma = firma_adi_temizle(firma_adi)
    queries = [
        f'site:{domain} contact email phone',
        f'site:{domain} iletişim telefon e-posta',
        f'site:{domain} "{firma}"',
        f'"{firma}" "{domain}" email phone',
        f'"{firma}" "{domain}" iletişim',
        f'"{firma}" e-posta telefon',
        f'"{firma}" iletişim bilgileri',
        f'"{firma}" contact details',
    ]
    mailler, telefonlar, links = [], [], []
    profile = v74_company_profile(firma)
    marka = profile.get("marka", "")
    web_root = v72_domain_root(web_url)

    for q in queries[:v79_limits()["search_queries"]]:
        try:
            items = v76_search_result_items(q, limit=10)
        except Exception:
            items = []
        for item in items:
            url = normalize_url(item.get("url", ""))
            text = item.get("text", "")
            blob = " ".join([text, url])
            m, t = v79_extract_contacts(blob)

            mailler.extend(m)
            low = turkce_karakter_temizle(blob.lower())
            if (marka and marka in low) or (web_root and web_root in low) or v72_same_site(url, web_url):
                telefonlar.extend(t)

            if url and v72_same_site(url, web_url):
                low_url = turkce_karakter_temizle(url.lower())
                if any(k in low_url for k in V79_CONTACT_KEYWORDS):
                    links.append(url)

    for link in list(dict.fromkeys(links))[:5]:
        data = v79_fetch_contact_page(link, web_url)
        mailler.extend(data.get("mailler", []))
        telefonlar.extend(data.get("telefonlar", []))

    return {
        "mailler": v79_filter_mails(mailler, web_url, firma_adi),
        "telefonlar": temiz_telefon_listesi(telefonlar),
        "links": list(dict.fromkeys(links)),
    }


def websitesinden_iletisim_bul(web_url, firma_adi=""):
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
    mailler, telefonlar, kaynaklar = [], [], []
    okunan = 0

    home = v79_fetch_contact_page(web_url, "https://www.google.com/")
    if home.get("ok"):
        okunan += 1
        mailler.extend(home.get("mailler", []))
        telefonlar.extend(home.get("telefonlar", []))
        kaynaklar.append(web_url)

    urls = v79_candidate_contact_urls(web_url, home.get("html", ""))
    for u in urls[:v79_limits()["static_pages"]]:
        try:
            data = v79_fetch_contact_page(u, web_url)
            if not data.get("ok"):
                continue
            okunan += 1
            mailler.extend(data.get("mailler", []))
            telefonlar.extend(data.get("telefonlar", []))
            kaynaklar.append(u)
            if v79_filter_mails(mailler, web_url, firma_adi) and temiz_telefon_listesi(telefonlar):
                break
        except Exception:
            continue

    filtered_mail = v79_filter_mails(mailler, web_url, firma_adi)
    filtered_tel = temiz_telefon_listesi(telefonlar)

    # Statik yetmezse dynamic render.
    if (not filtered_mail or not filtered_tel) and PLAYWRIGHT_AKTIF:
        browser_data = v79_browser_contact_pages(urls)
        mailler.extend(browser_data.get("mailler", []))
        telefonlar.extend(browser_data.get("telefonlar", []))
        filtered_mail = v79_filter_mails(mailler, web_url, firma_adi)
        filtered_tel = temiz_telefon_listesi(telefonlar)

    # Hala eksikse arama destekli fallback.
    if not filtered_mail or not filtered_tel:
        search_data = v79_search_contact_completion(web_url, firma_adi)
        mailler.extend(search_data.get("mailler", []))
        telefonlar.extend(search_data.get("telefonlar", []))
        kaynaklar.extend(search_data.get("links", []))
        filtered_mail = v79_filter_mails(mailler, web_url, firma_adi)
        filtered_tel = temiz_telefon_listesi(telefonlar)

    if filtered_mail:
        sonuc["eposta"] = ", ".join(filtered_mail[:5])
    if filtered_tel:
        sonuc["telefon"] = ", ".join(filtered_tel[:5])
    sonuc["kaynak"] = list(dict.fromkeys(kaynaklar))[0] if kaynaklar else web_url

    if sonuc["eposta"] != "Bulunamadi" and sonuc["telefon"] != "Bulunamadi":
        sonuc["durum"] = f"Tamamlandi | V79 universal contact sayfa: {okunan}"
    elif sonuc["eposta"] != "Bulunamadi" or sonuc["telefon"] != "Bulunamadi":
        sonuc["durum"] = f"Kismi tamamlandi | V79 universal contact sayfa: {okunan}"
    else:
        sonuc["durum"] = f"Web bulundu, iletisim bulunamadi | V79 universal contact sayfa: {okunan}"

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
        time.sleep(random.uniform(0.4, 0.9))
        web = firma_websitesi_bul(firma_adi)
        if not web:
            sonuc["durum"] = "Web sitesi bulunamadi"
            return sonuc_guven_skorlari_ekle(sonuc, firma_adi)
        iletisim = websitesinden_iletisim_bul(web, firma_adi=firma_adi)
        sonuc.update(iletisim)
        sonuc["firma_adi"] = firma_adi
        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)
    except Exception as e:
        sonuc["durum"] = "Hata"
        sonuc["hata"] = str(e)
        logging.error(f"V79 derin bilgi hatasi: {firma_adi} - {str(e)}")
        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)


# ============================================================
# V80 DYNAMIC STRUCTURE CONTACT RESOLVER
# Problem: Bazi kurumsal sitelerde iletisim bilgisi /contact veya
# /iletisim yerine yerleskeler, lokasyonlar, ofisler, CDN/PDF veya
# JS/JSON icinde duruyor. V80 bu yapilari one alir.
# ============================================================

V79_WEBSITE_ILETISIM_BUL_FINAL = websitesinden_iletisim_bul

V80_CONTACT_KEYWORDS = tuple(dict.fromkeys(V79_CONTACT_KEYWORDS + (
    "yerleskeler", "yerleşkeler", "yerleskesi", "yerleşkesi", "yerleske", "yerleşke",
    "lokasyon", "lokasyonlar", "ofis", "ofisler", "sube", "şube", "subeler", "şubeler",
    "tesis", "facility", "facilities", "campus", "campuses", "branch", "branches",
    "headquarters", "hq", "adres", "adresler", "address", "addresses",
    "iletisim-bilgileri", "iletişim-bilgileri", "contact-information", "contact-details",
    "data", "api/file", "uploads", "docs", "pdf"
)))

V80_PRIORITY_CONTACT_PATHS = [
    "/", "/tr", "/tr/",
    "/tr/yerleskeler", "/tr/yerleskeler/", "/tr/yerleşkeler", "/tr/yerleşkeler/",
    "/yerleskeler", "/yerleskeler/", "/yerleşkeler", "/yerleşkeler/",
    "/tr/lokasyonlar", "/tr/lokasyonlar/", "/lokasyonlar", "/lokasyonlar/",
    "/tr/ofisler", "/tr/ofisler/", "/ofisler", "/ofisler/",
    "/tr/subeler", "/tr/subeler/", "/tr/şubeler", "/tr/şubeler/",
    "/tr/adresler", "/tr/adresler/", "/adresler", "/adresler/",
    "/tr/iletisim-bilgileri", "/tr/iletişim-bilgileri", "/iletisim-bilgileri", "/iletişim-bilgileri",
    "/tr/contact-information", "/contact-information", "/tr/contact-details", "/contact-details",
    "/locations", "/locations/", "/en/locations", "/en/locations/",
    "/offices", "/offices/", "/en/offices", "/en/offices/",
    "/branches", "/branches/", "/en/branches", "/en/branches/",
    "/contact", "/contact/", "/tr/contact", "/tr/contact/",
    "/iletisim", "/iletisim/", "/tr/iletisim", "/tr/iletisim/",
    "/iletişim", "/iletişim/", "/tr/iletişim", "/tr/iletişim/",
    "/contact-us", "/contact-us/", "/tr/contact-us", "/tr/contact-us/",
    "/kurumsal/iletisim", "/tr/kurumsal/iletisim", "/corporate/contact", "/en/corporate/contact",
    "/sitemap.xml", "/sitemap_index.xml"
]


def v80_limits():
    base = v79_limits().copy()
    if SCAN_MODE == "Derin Tarama":
        base.update({"static_pages": 38, "browser_pages": 5, "search_queries": 12, "assets": 14, "pdfs": 6, "sitemap": 24})
    elif SCAN_MODE == "Hızlı Tarama":
        base.update({"static_pages": 12, "browser_pages": 1, "search_queries": 3, "assets": 4, "pdfs": 2, "sitemap": 8})
    else:
        base.update({"static_pages": 26, "browser_pages": 2, "search_queries": 7, "assets": 8, "pdfs": 4, "sitemap": 16})
    return base


def v80_url_contact_score(url):
    low = turkce_karakter_temizle(str(url or "").lower())
    score = 0
    if any(x in low for x in ["yerleske", "yerleskeler", "locations", "offices", "branches", "lokasyon", "ofis", "sube", "adres"]):
        score += 130
    if any(x in low for x in ["contact-information", "contact-details", "iletisim-bilgileri"]):
        score += 120
    if any(x in low for x in ["contact", "iletisim", "bize-ulasin"]):
        score += 90
    if any(x in low for x in ["sitemap"]):
        score += 65
    if any(x in low for x in [".pdf", "/api/file/", "/uploads/", "/docs/"]):
        score += 45
    if any(x in low for x in ["form", "basvuru", "application", "newsletter", "ebulten"]):
        score -= 35
    if any(x in low for x in ["privacy", "gizlilik", "kvkk", "cookie", "cerez"]):
        score -= 25
    return score


def v80_same_brand_or_domain(url, web_url, firma_adi="", text=""):
    try:
        if v72_same_site(url, web_url):
            return True
    except Exception:
        pass

    profile = v74_company_profile(firma_adi)
    marka = profile.get("marka", "")
    web_root = v72_domain_root(web_url)
    url_root = v72_domain_root(url)
    blob = turkce_karakter_temizle(" ".join([str(url or ""), str(text or "")]).lower())

    if web_root and url_root and web_root == url_root:
        return True
    if marka and marka in blob:
        return True
    if web_root and web_root in blob:
        return True
    return False


def v80_sitemap_contact_urls(base_url, firma_adi=""):
    base = v79_base_url(base_url)
    adaylar = [base + "/sitemap.xml", base + "/sitemap_index.xml"]
    urls = []

    for sm in adaylar:
        try:
            r = guvenli_get(sm, timeout=min(v80_limits()["timeout"] + 2, 9), referer=base)
            if r.status_code >= 400:
                continue
            text = html_entity_temizle(r.text or "")
            found = re.findall(r"https?://[^<>\s\"']+", text, flags=re.I)
            for u in found:
                u = normalize_url(u.strip())
                if not v80_same_brand_or_domain(u, base_url, firma_adi):
                    continue
                low = turkce_karakter_temizle(u.lower())
                if any(k in low for k in V80_CONTACT_KEYWORDS):
                    urls.append(u)
        except Exception:
            continue

    final = []
    seen = set()
    for u in sorted(urls, key=v80_url_contact_score, reverse=True):
        if u not in seen:
            seen.add(u)
            final.append(u)
    return final[:v80_limits()["sitemap"]]


def v80_candidate_contact_urls(web_url, home_html="", firma_adi=""):
    base = v79_base_url(web_url)
    urls = []

    p = urlparse(normalize_url(web_url))
    parts = [x for x in p.path.split("/") if x]
    langs = []
    if parts and parts[0].lower() in ["tr", "en", "de", "fr", "es", "ar"]:
        langs.append("/" + parts[0].lower())
    langs.extend(["/tr", "/en", ""])

    for path in V80_PRIORITY_CONTACT_PATHS:
        if path.startswith("/tr/") or path in ["/tr", "/tr/"]:
            urls.append(base + path)
            continue
        if path.startswith("/en/") or path in ["/en", "/en/"]:
            urls.append(base + path)
            continue
        for lang in langs:
            if lang and path not in ["/", "/sitemap.xml", "/sitemap_index.xml"] and not path.startswith(lang + "/"):
                urls.append(base + lang + path)
        urls.append(base + path)

    urls.extend(v79_internal_contact_links(base, home_html))
    urls.extend(v80_sitemap_contact_urls(base, firma_adi))
    urls.extend(v79_candidate_contact_urls(web_url, home_html))

    final = []
    seen = set()
    for u in sorted(urls, key=v80_url_contact_score, reverse=True):
        u = normalize_url(u)
        if not url_gecerli_mi(u):
            continue
        if not v80_same_brand_or_domain(u, web_url, firma_adi):
            continue
        if u not in seen:
            seen.add(u)
            final.append(u)
    return final[:55]


def v80_extract_pdf_contacts(url, web_url, firma_adi=""):
    result = {"mailler": [], "telefonlar": [], "ok": False}
    try:
        r = guvenli_get(url, timeout=10, referer=web_url)
        if r.status_code >= 400:
            return result
        content_type = (r.headers.get("content-type", "") or "").lower()
        if ".pdf" not in url.lower() and "pdf" not in content_type:
            return result
        content = getattr(r, "content", b"") or b""
        if not content or len(content) > 12 * 1024 * 1024:
            return result

        texts = []
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            total = len(pdf.pages)
            page_indexes = list(dict.fromkeys(list(range(min(2, total))) + list(range(max(total - 3, 0), total))))
            for idx in page_indexes:
                try:
                    txt = pdf.pages[idx].extract_text() or ""
                    if txt:
                        texts.append(txt)
                except Exception:
                    continue

        blob = v79_decode_blob(" ".join(texts))
        if not v80_same_brand_or_domain(url, web_url, firma_adi, blob):
            return result
        m, t = v79_extract_contacts(blob)
        result.update({"mailler": m, "telefonlar": t, "ok": bool(m or t)})
    except Exception as e:
        logging.warning(f"V80 PDF contact hata: {url} - {str(e)}")
    return result


def v80_linked_asset_contacts(web_url, html, firma_adi=""):
    result = {"mailler": [], "telefonlar": [], "ok": False}
    base = v79_base_url(web_url)
    assets = []

    try:
        soup = BeautifulSoup(html or "", "html.parser")
        for tag in soup.find_all(["script", "link"]):
            src = tag.get("src") or tag.get("href") or ""
            if not src:
                continue
            u = normalize_url(src, base_url=base)
            low = u.lower()
            if not url_gecerli_mi(u) or not v80_same_brand_or_domain(u, web_url, firma_adi):
                continue
            if any(x in low for x in [".js", ".json", "_next", "_nuxt", "/assets/", "/static/", "/api/"]):
                assets.append(u)
    except Exception:
        pass

    for asset in list(dict.fromkeys(assets))[:v80_limits()["assets"]]:
        try:
            r = guvenli_get(asset, timeout=min(v80_limits()["timeout"] + 1, 8), referer=web_url)
            if r.status_code >= 400:
                continue
            blob = v79_decode_blob(r.text or "")
            if not blob:
                continue
            m, t = v79_extract_contacts(blob)
            result["mailler"].extend(m)
            result["telefonlar"].extend(t)
            result["ok"] = True
        except Exception:
            continue

    result["mailler"] = temiz_mail_listesi(result["mailler"])
    result["telefonlar"] = temiz_telefon_listesi(result["telefonlar"])
    return result


def v80_search_contact_completion(web_url, firma_adi):
    domain = domain_al(web_url).replace("www.", "")
    domain_root = v72_domain_root(web_url)
    firma = firma_adi_temizle(firma_adi)
    profile = v74_company_profile(firma)
    marka = profile.get("marka", "")
    queries = [
        f'site:{domain} yerleskeler telefon e-posta',
        f'site:{domain} locations phone email',
        f'site:{domain} contact information phone email',
        f'site:{domain} filetype:pdf "{firma}" phone email',
        f'site:{domain} filetype:pdf "{firma}" telefon e-posta',
        f'"{firma}" "{domain_root}" "e-posta" "telefon"',
        f'"{firma}" "{domain_root}" "email" "phone"',
        f'"{firma}" "P:" "F:" "@{domain_root}"',
        f'"{firma}" "T:" "@{domain_root}"',
        f'"{firma}" "marketing@{domain_root}"',
    ]

    if domain:
        queries.extend([
            f'site:wwwcdn.{domain} "{firma}" phone email',
            f'site:cdn.{domain} "{firma}" phone email',
            f'site:{domain}/uploads "{firma}" telefon',
            f'site:{domain}/docs "{firma}" email',
        ])

    mailler, telefonlar, links = [], [], []
    pdf_seen = set()

    for q in queries[:v80_limits()["search_queries"]]:
        try:
            items = v76_search_result_items(q, limit=12)
        except Exception:
            items = []

        for item in items:
            url = normalize_url(item.get("url", ""))
            text = item.get("text", "")
            if not url:
                continue

            if not v80_same_brand_or_domain(url, web_url, firma_adi, text):
                continue

            blob = " ".join([text, url])
            m, t = v79_extract_contacts(blob)
            mailler.extend(m)
            telefonlar.extend(t)

            low_url = turkce_karakter_temizle(url.lower())
            if any(k in low_url for k in V80_CONTACT_KEYWORDS):
                links.append(url)

            if (".pdf" in low_url or "/api/file/" in low_url or "/uploads/" in low_url) and url not in pdf_seen:
                pdf_seen.add(url)
                if len(pdf_seen) <= v80_limits()["pdfs"]:
                    pdata = v80_extract_pdf_contacts(url, web_url, firma_adi)
                    mailler.extend(pdata.get("mailler", []))
                    telefonlar.extend(pdata.get("telefonlar", []))

    for link in sorted(list(dict.fromkeys(links)), key=v80_url_contact_score, reverse=True)[:8]:
        if ".pdf" in link.lower():
            pdata = v80_extract_pdf_contacts(link, web_url, firma_adi)
            mailler.extend(pdata.get("mailler", []))
            telefonlar.extend(pdata.get("telefonlar", []))
        else:
            data = v79_fetch_contact_page(link, web_url)
            mailler.extend(data.get("mailler", []))
            telefonlar.extend(data.get("telefonlar", []))

    return {
        "mailler": v79_filter_mails(mailler, web_url, firma_adi),
        "telefonlar": temiz_telefon_listesi(telefonlar),
        "links": list(dict.fromkeys(links)),
    }


def websitesinden_iletisim_bul(web_url, firma_adi=""):
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
    mailler, telefonlar, kaynaklar, html_blobs = [], [], [], []
    okunan = 0

    home = v79_fetch_contact_page(web_url, "https://www.google.com/")
    if home.get("ok"):
        okunan += 1
        mailler.extend(home.get("mailler", []))
        telefonlar.extend(home.get("telefonlar", []))
        kaynaklar.append(web_url)
        html_blobs.append(home.get("html", ""))

    urls = v80_candidate_contact_urls(web_url, home.get("html", ""), firma_adi)
    for u in urls[:v80_limits()["static_pages"]]:
        try:
            if ".pdf" in u.lower():
                data = v80_extract_pdf_contacts(u, web_url, firma_adi)
                html = ""
            else:
                data = v79_fetch_contact_page(u, web_url)
                html = data.get("html", "")
            if not data.get("ok"):
                continue
            okunan += 1
            mailler.extend(data.get("mailler", []))
            telefonlar.extend(data.get("telefonlar", []))
            kaynaklar.append(u)
            if html:
                html_blobs.append(html)
            if v79_filter_mails(mailler, web_url, firma_adi) and temiz_telefon_listesi(telefonlar):
                break
        except Exception:
            continue

    filtered_mail = v79_filter_mails(mailler, web_url, firma_adi)
    filtered_tel = temiz_telefon_listesi(telefonlar)

    # SPA/Next/Nuxt sitelerinde veri JS veya JSON asset icinde kalabiliyor.
    if (not filtered_mail or not filtered_tel) and html_blobs:
        for html in html_blobs[:3]:
            asset_data = v80_linked_asset_contacts(web_url, html, firma_adi)
            mailler.extend(asset_data.get("mailler", []))
            telefonlar.extend(asset_data.get("telefonlar", []))
            filtered_mail = v79_filter_mails(mailler, web_url, firma_adi)
            filtered_tel = temiz_telefon_listesi(telefonlar)
            if filtered_mail and filtered_tel:
                break

    # Statik/asset yetmezse dinamik render.
    if (not filtered_mail or not filtered_tel) and PLAYWRIGHT_AKTIF:
        render_urls = sorted(urls, key=v80_url_contact_score, reverse=True)
        browser_data = v79_browser_contact_pages(render_urls)
        mailler.extend(browser_data.get("mailler", []))
        telefonlar.extend(browser_data.get("telefonlar", []))
        filtered_mail = v79_filter_mails(mailler, web_url, firma_adi)
        filtered_tel = temiz_telefon_listesi(telefonlar)

    # Hala eksikse arama + ayni marka/domain PDF/CDN kaynaklari.
    if not filtered_mail or not filtered_tel:
        search_data = v80_search_contact_completion(web_url, firma_adi)
        mailler.extend(search_data.get("mailler", []))
        telefonlar.extend(search_data.get("telefonlar", []))
        kaynaklar.extend(search_data.get("links", []))
        filtered_mail = v79_filter_mails(mailler, web_url, firma_adi)
        filtered_tel = temiz_telefon_listesi(telefonlar)

    if filtered_mail:
        sonuc["eposta"] = ", ".join(filtered_mail[:5])
    if filtered_tel:
        sonuc["telefon"] = ", ".join(filtered_tel[:5])
    sonuc["kaynak"] = list(dict.fromkeys(kaynaklar))[0] if kaynaklar else web_url

    if sonuc["eposta"] != "Bulunamadi" and sonuc["telefon"] != "Bulunamadi":
        sonuc["durum"] = f"Tamamlandi | V80 dynamic contact sayfa: {okunan}"
    elif sonuc["eposta"] != "Bulunamadi" or sonuc["telefon"] != "Bulunamadi":
        sonuc["durum"] = f"Kismi tamamlandi | V80 dynamic contact sayfa: {okunan}"
    else:
        sonuc["durum"] = f"Web bulundu, iletisim bulunamadi | V80 dynamic contact sayfa: {okunan}"

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
        time.sleep(random.uniform(0.35, 0.8))
        web = firma_websitesi_bul(firma_adi)
        if not web:
            sonuc["durum"] = "Web sitesi bulunamadi"
            return sonuc_guven_skorlari_ekle(sonuc, firma_adi)
        iletisim = websitesinden_iletisim_bul(web, firma_adi=firma_adi)
        sonuc.update(iletisim)
        sonuc["firma_adi"] = firma_adi
        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)
    except Exception as e:
        sonuc["durum"] = "Hata"
        sonuc["hata"] = str(e)
        logging.error(f"V80 derin bilgi hatasi: {firma_adi} - {str(e)}")
        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)


# ============================================================
# V81 STRUCTURE-AWARE OFFICIAL SITE + CONTACT RESOLVER
# Test sonucu: V79/V80 contact katmani bazi siteleri toparladi ama
# Dengeli mod resmi domain adaylarini marka-only domainlerde harciyordu.
# V81, resmi site bulmayi sektor yapisina gore yeniden siralar ve
# eksik contact icin legacy/subdomain/PDF/snippet katmanini genisletir.
# ============================================================

V80_FIRMA_WEBSITE_BUL_FINAL = firma_websitesi_bul
V80_WEBSITE_ILETISIM_BUL_FINAL = websitesinden_iletisim_bul
V80_TEMIZ_TELEFON_LISTESI = temiz_telefon_listesi

V81_BAD_RESULT_DOMAINS = {
    "wikipedia.org", "linkedin.com", "facebook.com", "instagram.com", "twitter.com", "x.com",
    "youtube.com", "crunchbase.com", "bloomberg.com", "dnb.com", "zoominfo.com",
    "tumisyeri.com", "cybo.com", "firmaekle.net", "superrehber.net", "alo118.com",
    "turkdenizcilik.com", "gmo.org.tr", "sasad.org.tr", "dredgepoint.org",
    "jsmea.or.jp", "thedeckmedia.com", "paluba.media", "maritimejournal.com",
}


def temiz_telefon_listesi(telefonlar):
    final = []
    seen_digits = set()

    for tel in telefonlar or []:
        tel_raw = html_entity_temizle(str(tel or "")).strip()
        if not tel_raw:
            continue
        if re.search(r"\d+\.\d+", tel_raw):
            continue

        tel_clean = tel_raw.replace("tel:", "")
        tel_clean = re.sub(r"\s+", " ", tel_clean).strip()
        digits = re.sub(r"\D", "", tel_clean)

        if len(digits) < 10 or len(digits) > 15:
            continue
        if len(set(digits)) <= 2:
            continue
        if re.search(r"(\d)\1{5,}", digits):
            continue

        # Turkiye numaralarinda alan kodu 1xx degildir; bu filtre 177/001 gibi
        # sayfa koordinati veya bozuk parcalari telefon sanmayi azaltir.
        if digits.startswith("90") and len(digits) == 12:
            area = digits[2:5]
            if area.startswith("1") or area.startswith("00"):
                continue
            norm = "+90 " + digits[2:5] + " " + digits[5:8] + " " + digits[8:10] + " " + digits[10:12]
        elif digits.startswith("0") and len(digits) == 11:
            area = digits[1:4]
            if area.startswith("1") or area.startswith("00"):
                continue
            norm = "+90 " + digits[1:4] + " " + digits[4:7] + " " + digits[7:9] + " " + digits[9:11]
        elif len(digits) == 10 and digits[0] in "2358":
            norm = "+90 " + digits[0:3] + " " + digits[3:6] + " " + digits[6:8] + " " + digits[8:10]
        elif digits.startswith("00") and len(digits) >= 12:
            norm = "+" + digits[2:]
        else:
            norm = tel_clean

        key = re.sub(r"\D", "", norm)[-10:]
        if key in seen_digits:
            continue
        seen_digits.add(key)
        final.append(norm)

    return final[:6]


def v81_add_root(weighted, root, weight):
    root = normalize_domain_token(str(root or "")).strip("-")
    if not root or len(root) < 3:
        return
    if root not in weighted or weight > weighted[root]:
        weighted[root] = weight


def v81_priority_roots(firma_adi):
    profile = v74_company_profile(firma_adi)
    tokens = profile.get("tokens", [])
    brand_tokens = profile.get("brand_tokens", []) or tokens[:1]
    groups = v74_expected_groups(firma_adi)
    weighted = {}

    brand1 = brand_tokens[0] if brand_tokens else ""
    brand2 = "".join(brand_tokens[:2]) if len(brand_tokens) >= 2 else ""
    brand2_dash = "-".join(brand_tokens[:2]) if len(brand_tokens) >= 2 else ""
    token2 = "".join(tokens[:2]) if len(tokens) >= 2 else ""
    token3 = "".join(tokens[:3]) if len(tokens) >= 3 else ""

    if "shipyard" in groups:
        bases = []
        for b in [brand2, brand2_dash, token2, brand1]:
            if b and b not in bases:
                bases.append(b)
        for b in bases:
            v81_add_root(weighted, b + "shipyard", 180)
            v81_add_root(weighted, b + "-shipyard", 178)
            v81_add_root(weighted, b + "shipyards", 172)
            v81_add_root(weighted, b + "tersane", 150)
        for b in [brand2, brand2_dash, token3, token2]:
            v81_add_root(weighted, b, 132)
        v81_add_root(weighted, brand1, 35)

    if "marine" in groups:
        bases = []
        for b in [brand2, brand2_dash, token2, brand1]:
            if b and b not in bases:
                bases.append(b)
        for b in bases:
            v81_add_root(weighted, b + "marine", 176)
            v81_add_root(weighted, b + "-marine", 174)
            v81_add_root(weighted, b + "maritime", 150)
        for b in [brand2, brand2_dash, token2]:
            v81_add_root(weighted, b, 128)
        v81_add_root(weighted, brand1, 30)

    if "holding" in groups:
        if brand1:
            v81_add_root(weighted, brand1 + "holding", 180)
            v81_add_root(weighted, brand1 + "-holding", 175)
            v81_add_root(weighted, brand1 + "group", 140)
            v81_add_root(weighted, brand1, 45)
        v81_add_root(weighted, token2, 160)

    if "classification" in groups or "loydu" in tokens:
        v81_add_root(weighted, "turkloydu", 190)
        v81_add_root(weighted, "turk-loydu", 185)

    for b, w in [(token3, 145), (token2, 132), (brand2, 120), (brand2_dash, 118), (brand1, 75)]:
        v81_add_root(weighted, b, w)

    return [r for r, _ in sorted(weighted.items(), key=lambda x: x[1], reverse=True)]


def v81_priority_domain_candidates(firma_adi):
    roots = v81_priority_roots(firma_adi)
    tlds = [".com", ".com.tr", ".org", ".net", ".tr", ".global"]
    paths = ["", "/", "/tr", "/tr/", "/en", "/en/"]
    adaylar = []
    for root in roots:
        for tld in tlds:
            for host in [f"https://www.{root}{tld}", f"https://{root}{tld}"]:
                for path in paths:
                    adaylar.append(host + path)
    return list(dict.fromkeys(adaylar))[:240]


def v81_is_bad_result_url(url):
    d = domain_al(url).replace("www.", "").lower()
    return any(d == bad or d.endswith("." + bad) for bad in V81_BAD_RESULT_DOMAINS)


def v81_official_score(url, firma_adi, text=""):
    if not url or v72_url_kotu_mu(url) or v81_is_bad_result_url(url):
        return -120
    root = v72_domain_root(url)
    roots = v81_priority_roots(firma_adi)
    score = v77_official_candidate_score(url, firma_adi, text)
    low_text = turkce_karakter_temizle(str(text or "").lower()[:30000])
    root_flat = root.replace("-", "")

    for idx, r in enumerate(roots[:12]):
        rf = r.replace("-", "")
        if root_flat == rf:
            score += 95 - min(idx * 4, 35)
            break
        if len(rf) >= 6 and (rf in root_flat or root_flat in rf):
            score += 62 - min(idx * 3, 25)
            break

    for group in v74_expected_groups(firma_adi):
        cfg = V74_SECTOR_GROUPS[group]
        if v74_text_has_any(low_text, cfg["needles"]):
            score += 28
        if v74_text_has_any(low_text, cfg["negative"]):
            score -= 85

    if any(x in low_text for x in ["official", "resmi", "contact", "iletisim", "iletişim", "shipyard", "tersane", "marine"]):
        score += 12
    return score


def v81_active_site_score(url, firma_adi):
    try:
        r = guvenli_get(url, timeout=min(v73_mode_limits()["site_timeout"], 5), referer="https://www.google.com/")
        final_url = normalize_url(getattr(r, "url", url) or url)
        text = temiz_metin((r.text or "")[:18000]) if r.status_code < 400 else ""
        score = v81_official_score(final_url, firma_adi, text)
        alive = r.status_code < 500
        if r.status_code < 400:
            score += 22
        elif r.status_code in [401, 403]:
            score += 8
        return {"url": final_url, "score": score, "alive": alive, "text": text}
    except Exception:
        return {"url": url, "score": v81_official_score(url, firma_adi, ""), "alive": False, "text": ""}


def v81_direct_official_site_bul(firma_adi):
    scored = []
    attempts = 0
    seen_urls = set()
    for url in v81_priority_domain_candidates(firma_adi):
        if url in seen_urls:
            continue
        seen_urls.add(url)
        root = v72_domain_root(url)

        # Marka tek basina generic ise ancak tum diger guclu adaylar bittikten sonra degerlendir.
        if root in V74_GENERIC_ROOTS and v74_expected_groups(firma_adi):
            continue

        attempts += 1
        if attempts > 90:
            break

        s = v81_active_site_score(url, firma_adi)
        threshold = 120 if v74_expected_groups(firma_adi) else 75
        if s["score"] >= threshold and (s["alive"] or s["score"] >= threshold + 45):
            scored.append(s)
        if len(scored) >= 5:
            break

    if scored:
        scored = sorted(scored, key=lambda x: x["score"], reverse=True)
        return scored[0]["url"]
    return ""


def v81_site_home_from_url(url):
    u = normalize_url(url)
    p = urlparse(u)
    if not p.scheme or not p.netloc:
        return u
    return f"{p.scheme}://{p.netloc}/"


def v81_search_official_site_bul(firma_adi):
    firma = firma_adi_temizle(firma_adi)
    profile = v74_company_profile(firma)
    roots = v81_priority_roots(firma)[:10]
    marka = profile.get("marka", "")
    groups = v74_expected_groups(firma)
    group_words = " ".join(groups)

    queries = [
        f'"{firma}" official website',
        f'"{firma}" contact',
        f'"{firma}" website',
        f'{firma} resmi web sitesi',
        f'{firma} iletişim',
    ]
    if group_words:
        queries.extend([
            f'"{firma}" {group_words} contact',
            f'{firma} {group_words} official',
        ])
    for root in roots[:5]:
        queries.append(f'"{firma}" "{root}"')
    if marka:
        queries.append(f'{marka} {" ".join(groups)} contact')

    scored = []
    deadline = time.time() + max(v73_mode_limits()["firma_cap"], 90)
    for q in list(dict.fromkeys(queries))[:10]:
        if time.time() > deadline:
            break
        try:
            items = v76_search_result_items(q, limit=12)
        except Exception:
            items = []
        for item in items:
            url = normalize_url(item.get("url", ""))
            if not url or v81_is_bad_result_url(url):
                continue
            score = v81_official_score(url, firma, item.get("text", ""))
            if score >= (105 if groups else 62):
                scored.append({"url": v81_site_home_from_url(url), "score": score, "text": item.get("text", "")})

    if not scored:
        return ""

    scored = sorted(scored, key=lambda x: x["score"], reverse=True)
    return scored[0]["url"]


def v81_web_reasonable(web_url, firma_adi):
    if not web_url or v81_is_bad_result_url(web_url):
        return False
    root = v72_domain_root(web_url)
    profile = v74_company_profile(firma_adi)
    brand = profile.get("marka", "")
    groups = v74_expected_groups(firma_adi)
    if groups and root in V74_GENERIC_ROOTS:
        return False
    if groups and brand and root == brand and root not in [r.replace("-", "") for r in v81_priority_roots(firma_adi)[:4]]:
        return False
    return v81_official_score(web_url, firma_adi, "") >= (55 if groups else 25)


def firma_websitesi_bul(firma_adi):
    firma_adi_temiz = firma_adi_temizle(firma_adi)
    if not firma_adi_temiz:
        return ""

    cache_key = "v81:" + SCAN_MODE + ":" + firma_adi_temiz.lower().strip()
    if cache_key in WEBSITE_CACHE:
        return WEBSITE_CACHE[cache_key]

    direct = v81_direct_official_site_bul(firma_adi_temiz)
    if direct:
        WEBSITE_CACHE[cache_key] = direct
        return direct

    searched = v81_search_official_site_bul(firma_adi_temiz)
    if searched:
        WEBSITE_CACHE[cache_key] = searched
        return searched

    try:
        previous = V80_FIRMA_WEBSITE_BUL_FINAL(firma_adi_temiz)
    except Exception:
        previous = ""

    if previous and v81_web_reasonable(previous, firma_adi_temiz):
        WEBSITE_CACHE[cache_key] = previous
        return previous

    WEBSITE_CACHE[cache_key] = previous or ""
    return previous or ""


def v81_extra_contact_urls(web_url, firma_adi="", home_html=""):
    base = v79_base_url(web_url)
    domain = domain_al(base).replace("www.", "")
    paths = [
        "/public/contact", "/public/contact/", "/contact", "/contact/", "/contacts", "/contacts/",
        "/contact-us", "/contact-us/", "/en/contact", "/en/contact/", "/en/contact-us", "/en/contact-us/",
        "/tr/contact", "/tr/contact/", "/tr/iletisim", "/tr/iletisim/", "/tr/iletişim", "/tr/iletişim/",
        "/iletisim", "/iletisim/", "/iletişim", "/iletişim/", "/bize-ulasin", "/bize-ulasin/",
        "/locations", "/locations/", "/offices", "/offices/", "/yerleskeler", "/tr/yerleskeler",
        "/adresler", "/tr/adresler"
    ]
    urls = []
    for path in paths:
        urls.append(base + path)

    if domain:
        for legacy in [f"https://old.{domain}", f"https://www.old.{domain}"]:
            for path in ["/contact", "/contact/", "/iletisim", "/iletisim/", "/contacts", "/contacts/"]:
                urls.append(legacy + path)

    try:
        urls.extend(v80_candidate_contact_urls(web_url, home_html, firma_adi))
    except Exception:
        pass

    final = []
    seen = set()
    for u in sorted(urls, key=v80_url_contact_score, reverse=True):
        u = normalize_url(u)
        if not url_gecerli_mi(u):
            continue
        if not v80_same_brand_or_domain(u, web_url, firma_adi):
            continue
        if u not in seen:
            seen.add(u)
            final.append(u)
    return final[:65]


def v81_search_contact_completion(web_url, firma_adi):
    domain = domain_al(web_url).replace("www.", "")
    domain_root = v72_domain_root(web_url)
    firma = firma_adi_temizle(firma_adi)
    roots = v81_priority_roots(firma)[:8]
    queries = [
        f'site:{domain} "{firma}" email phone',
        f'site:{domain} "{firma}" e-mail telefon',
        f'site:{domain} "{firma}" "T:" "E:"',
        f'site:{domain} "{firma}" filetype:pdf',
        f'"{firma}" "{domain_root}" "info@"',
        f'"{firma}" "{domain_root}" "Phone"',
        f'"{firma}" "{domain_root}" "E-mail"',
        f'"{firma}" contact details',
        f'"{firma}" iletişim bilgileri',
    ]
    for r in roots[:5]:
        queries.extend([
            f'"{firma}" "{r}" "email"',
            f'"{firma}" "{r}" "telefon"',
        ])
    if domain:
        queries.extend([
            f'site:old.{domain} "{firma}"',
            f'site:old.{domain} contact',
        ])

    mailler, telefonlar, links = [], [], []
    pdf_seen = set()

    for q in list(dict.fromkeys(queries))[:max(v80_limits()["search_queries"], 10)]:
        try:
            items = v76_search_result_items(q, limit=12)
        except Exception:
            items = []
        for item in items:
            url = normalize_url(item.get("url", ""))
            text = item.get("text", "")
            blob = " ".join([text, url])

            m, t = v79_extract_contacts(blob)
            accepted_m = v79_filter_mails(m, web_url, firma)
            if accepted_m:
                mailler.extend(accepted_m)
            if v80_same_brand_or_domain(url, web_url, firma, text) or accepted_m:
                telefonlar.extend(t)
                if url and not v81_is_bad_result_url(url):
                    links.append(url)

            low_url = url.lower()
            if (".pdf" in low_url or "/api/file/" in low_url or "/uploads/" in low_url or "/docs/" in low_url) and url not in pdf_seen:
                pdf_seen.add(url)
                if len(pdf_seen) <= v80_limits()["pdfs"] + 2:
                    pdata = v80_extract_pdf_contacts(url, web_url, firma)
                    mailler.extend(pdata.get("mailler", []))
                    telefonlar.extend(pdata.get("telefonlar", []))

    for link in sorted(list(dict.fromkeys(links)), key=v80_url_contact_score, reverse=True)[:10]:
        try:
            if ".pdf" in link.lower():
                pdata = v80_extract_pdf_contacts(link, web_url, firma)
                mailler.extend(pdata.get("mailler", []))
                telefonlar.extend(pdata.get("telefonlar", []))
            else:
                data = v79_fetch_contact_page(link, web_url)
                mailler.extend(data.get("mailler", []))
                telefonlar.extend(data.get("telefonlar", []))
        except Exception:
            continue

    return {
        "mailler": v79_filter_mails(mailler, web_url, firma),
        "telefonlar": temiz_telefon_listesi(telefonlar),
        "links": list(dict.fromkeys(links)),
    }


def websitesinden_iletisim_bul(web_url, firma_adi=""):
    sonuc = V80_WEBSITE_ILETISIM_BUL_FINAL(web_url, firma_adi=firma_adi)
    mevcut_mail = [] if sonuc.get("eposta") in ["", None, "Bulunamadi"] else temiz_mail_listesi(str(sonuc.get("eposta", "")).split(","))
    mevcut_tel = [] if sonuc.get("telefon") in ["", None, "Bulunamadi"] else temiz_telefon_listesi(str(sonuc.get("telefon", "")).split(","))

    if mevcut_mail and mevcut_tel:
        sonuc["telefon"] = ", ".join(mevcut_tel[:5])
        sonuc["eposta"] = ", ".join(mevcut_mail[:5])
        sonuc["durum"] = str(sonuc.get("durum", "")).replace("V80", "V81")
        return sonuc

    mailler = list(mevcut_mail)
    telefonlar = list(mevcut_tel)
    kaynaklar = [] if not sonuc.get("kaynak") else [sonuc.get("kaynak")]

    home_html = ""
    try:
        home = v79_fetch_contact_page(web_url, "https://www.google.com/")
        home_html = home.get("html", "")
    except Exception:
        pass

    for u in v81_extra_contact_urls(web_url, firma_adi, home_html)[:max(v80_limits()["static_pages"], 28)]:
        try:
            if ".pdf" in u.lower():
                data = v80_extract_pdf_contacts(u, web_url, firma_adi)
            else:
                data = v79_fetch_contact_page(u, web_url)
            if not data.get("ok"):
                continue
            mailler.extend(data.get("mailler", []))
            telefonlar.extend(data.get("telefonlar", []))
            kaynaklar.append(u)
            if v79_filter_mails(mailler, web_url, firma_adi) and temiz_telefon_listesi(telefonlar):
                break
        except Exception:
            continue

    filtered_mail = v79_filter_mails(mailler, web_url, firma_adi)
    filtered_tel = temiz_telefon_listesi(telefonlar)

    if not filtered_mail or not filtered_tel:
        search_data = v81_search_contact_completion(web_url, firma_adi)
        mailler.extend(search_data.get("mailler", []))
        telefonlar.extend(search_data.get("telefonlar", []))
        kaynaklar.extend(search_data.get("links", []))
        filtered_mail = v79_filter_mails(mailler, web_url, firma_adi)
        filtered_tel = temiz_telefon_listesi(telefonlar)

    if filtered_mail:
        sonuc["eposta"] = ", ".join(filtered_mail[:5])
    if filtered_tel:
        sonuc["telefon"] = ", ".join(filtered_tel[:5])
    if kaynaklar:
        sonuc["kaynak"] = list(dict.fromkeys(kaynaklar))[0]

    if sonuc["eposta"] != "Bulunamadi" and sonuc["telefon"] != "Bulunamadi":
        sonuc["durum"] = "Tamamlandi | V81 structure-aware contact"
    elif sonuc["eposta"] != "Bulunamadi" or sonuc["telefon"] != "Bulunamadi":
        sonuc["durum"] = "Kismi tamamlandi | V81 structure-aware contact"
    else:
        sonuc["durum"] = "Web bulundu, iletisim bulunamadi | V81 structure-aware contact"

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
        time.sleep(random.uniform(0.3, 0.75))
        web = firma_websitesi_bul(firma_adi)
        if not web:
            sonuc["durum"] = "Web sitesi bulunamadi"
            return sonuc_guven_skorlari_ekle(sonuc, firma_adi)

        iletisim = websitesinden_iletisim_bul(web, firma_adi=firma_adi)
        sonuc.update(iletisim)
        sonuc["firma_adi"] = firma_adi
        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)
    except Exception as e:
        sonuc["durum"] = "Hata"
        sonuc["hata"] = str(e)
        logging.error(f"V81 derin bilgi hatasi: {firma_adi} - {str(e)}")
        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)


# ============================================================
# V82 FALSE-DOMAIN GUARD + CLEAN SECTOR ROOTS
# V81 testinde gorulen hata: sektor kelimesi zaten kokte varken tekrar
# ekleniyordu: dearsanshipyardshipyard, medmarinemarine vb. V82 bunu
# engeller ve DNS/404 veren domainleri resmi site diye kabul etmez.
# ============================================================

V81_FIRMA_WEBSITE_BUL_FINAL = firma_websitesi_bul
V81_WEBSITE_ILETISIM_BUL_FINAL = websitesinden_iletisim_bul


def temiz_telefon_listesi(telefonlar):
    final = []
    seen_digits = set()

    for tel in telefonlar or []:
        tel_raw = html_entity_temizle(str(tel or "")).strip()
        if not tel_raw or re.search(r"\d+\.\d+", tel_raw):
            continue

        tel_clean = re.sub(r"\s+", " ", tel_raw.replace("tel:", "")).strip()
        digits = re.sub(r"\D", "", tel_clean)

        if len(digits) < 10 or len(digits) > 15:
            continue
        if len(set(digits)) <= 2 or re.search(r"(\d)\1{5,}", digits):
            continue

        if digits.startswith("90") and len(digits) == 12:
            area = digits[2:5]
            if area[0] not in "23458":
                continue
            norm = "+90 " + digits[2:5] + " " + digits[5:8] + " " + digits[8:10] + " " + digits[10:12]
        elif digits.startswith("0") and len(digits) == 11:
            area = digits[1:4]
            if area[0] not in "23458":
                continue
            norm = "+90 " + digits[1:4] + " " + digits[4:7] + " " + digits[7:9] + " " + digits[9:11]
        elif len(digits) == 10 and digits[0] in "23458":
            norm = "+90 " + digits[0:3] + " " + digits[3:6] + " " + digits[6:8] + " " + digits[8:10]
        elif digits.startswith("00") and len(digits) >= 12:
            norm = "+" + digits[2:]
        else:
            norm = tel_clean

        key = re.sub(r"\D", "", norm)[-10:]
        if key in seen_digits:
            continue
        seen_digits.add(key)
        final.append(norm)

    return final[:6]


def v82_sector_base_variants(profile):
    tokens = profile.get("tokens", [])
    brand_tokens = profile.get("brand_tokens", []) or tokens[:1]
    variants = []

    def add(x):
        x = normalize_domain_token(str(x or "")).strip("-")
        if x and len(x) >= 2 and x not in variants:
            variants.append(x)

    if brand_tokens:
        add(brand_tokens[0])
    if len(brand_tokens) >= 2:
        add(brand_tokens[0] + brand_tokens[1])
        add(brand_tokens[0] + "-" + brand_tokens[1])

    # token2 bazen tktuzla gibi markanin parcasi, bazen de dearsanshipyard
    # gibi zaten sektor eklenmis haldir. Sektorle bitiyorsa tekrar suffix alma.
    if len(tokens) >= 2:
        token2 = tokens[0] + tokens[1]
        if not re.search(r"(shipyard|shipyards|marine|maritime|holding|loydu|class)$", token2):
            add(token2)

    return variants


def v82_add_root(weighted, root, weight):
    root = normalize_domain_token(str(root or "")).strip("-")
    if not root or len(root) < 3:
        return
    # Bariz cift sektor eklerini tamamen ele.
    if re.search(r"(shipyardshipyard|shipyardshipyards|shipyardmarine|marinemarine|holdingholding|shipyardholding)$", root):
        return
    if root not in weighted or weight > weighted[root]:
        weighted[root] = weight


def v82_priority_roots(firma_adi):
    profile = v74_company_profile(firma_adi)
    tokens = profile.get("tokens", [])
    brand_tokens = profile.get("brand_tokens", []) or tokens[:1]
    groups = v74_expected_groups(firma_adi)
    bases = v82_sector_base_variants(profile)
    weighted = {}

    if "shipyard" in groups:
        for b in bases:
            v82_add_root(weighted, b + "shipyard", 190)
            v82_add_root(weighted, b + "-shipyard", 188)
            v82_add_root(weighted, b + "shipyards", 182)
            v82_add_root(weighted, b + "-shipyards", 180)
        for b in bases:
            # Sanmar, Tersan, Ceksan gibi dogru site yalniz marka domaini olabilir.
            v82_add_root(weighted, b, 150 if b not in V74_GENERIC_ROOTS else 55)

    if "marine" in groups:
        for b in bases:
            v82_add_root(weighted, b + "marine", 188)
            v82_add_root(weighted, b + "-marine", 186)
            v82_add_root(weighted, b + "maritime", 160)
            v82_add_root(weighted, b + "yachts", 154)
            v82_add_root(weighted, b + "yacht", 150)
        for b in bases:
            v82_add_root(weighted, b, 135 if b not in V74_GENERIC_ROOTS else 45)

    if "holding" in groups:
        b = brand_tokens[0] if brand_tokens else (tokens[0] if tokens else "")
        v82_add_root(weighted, b + "holding", 195)
        v82_add_root(weighted, b + "-holding", 190)
        v82_add_root(weighted, b + "group", 150)
        v82_add_root(weighted, b, 70)

    if "classification" in groups or "loydu" in tokens:
        v82_add_root(weighted, "turkloydu", 200)
        v82_add_root(weighted, "turk-loydu", 195)

    if len(tokens) >= 3:
        v82_add_root(weighted, "".join(tokens[:3]), 155)
    if len(tokens) >= 2:
        v82_add_root(weighted, "".join(tokens[:2]), 145)
    for b in bases:
        v82_add_root(weighted, b, 120 if b not in V74_GENERIC_ROOTS else 40)

    return [r for r, _ in sorted(weighted.items(), key=lambda x: x[1], reverse=True)]


def v82_priority_domain_candidates(firma_adi):
    roots = v82_priority_roots(firma_adi)
    tlds = [".com", ".com.tr", ".org", ".net", ".tr", ".global"]
    paths = ["", "/", "/tr", "/tr/", "/en", "/en/"]
    adaylar = []
    for root in roots:
        for tld in tlds:
            for host in [f"https://www.{root}{tld}", f"https://{root}{tld}"]:
                for path in paths:
                    adaylar.append(host + path)
    return list(dict.fromkeys(adaylar))[:260]


def v82_official_score(url, firma_adi, text=""):
    if not url or v72_url_kotu_mu(url) or v81_is_bad_result_url(url):
        return -120
    root = v72_domain_root(url)
    root_flat = root.replace("-", "")
    roots = v82_priority_roots(firma_adi)
    score = v77_official_candidate_score(url, firma_adi, text)
    low_text = turkce_karakter_temizle(str(text or "").lower()[:30000])

    for idx, r in enumerate(roots[:14]):
        rf = r.replace("-", "")
        if root_flat == rf:
            score += 105 - min(idx * 4, 40)
            break
        if len(rf) >= 6 and (rf in root_flat or root_flat in rf):
            score += 65 - min(idx * 3, 28)
            break

    for group in v74_expected_groups(firma_adi):
        cfg = V74_SECTOR_GROUPS[group]
        if v74_text_has_any(low_text, cfg["needles"]):
            score += 35
        if v74_text_has_any(low_text, cfg["negative"]):
            score -= 95

    return score


def v82_active_site_score(url, firma_adi):
    try:
        r = guvenli_get(url, timeout=min(v73_mode_limits()["site_timeout"], 6), referer="https://www.google.com/")
        final_url = normalize_url(getattr(r, "url", url) or url)
        status = int(getattr(r, "status_code", 0) or 0)
        text = temiz_metin((r.text or "")[:22000]) if status < 400 else ""
        alive = status < 400 or status in [401, 403]
        score = v82_official_score(final_url, firma_adi, text)
        if alive:
            score += 25
        if status == 404:
            score -= 120
        return {"url": final_url, "score": score, "alive": alive, "status": status, "text": text}
    except Exception:
        return {"url": url, "score": -120, "alive": False, "status": 0, "text": ""}


def v82_direct_official_site_bul(firma_adi):
    scored = []
    seen = set()
    attempts = 0
    for url in v82_priority_domain_candidates(firma_adi):
        if url in seen:
            continue
        seen.add(url)
        root = v72_domain_root(url)
        if root in V74_GENERIC_ROOTS and v74_expected_groups(firma_adi):
            continue
        attempts += 1
        if attempts > (140 if SCAN_MODE != "Hızlı Tarama" else 70):
            break

        s = v82_active_site_score(url, firma_adi)
        threshold = 118 if v74_expected_groups(firma_adi) else 70
        if s["alive"] and s["score"] >= threshold:
            scored.append(s)
        if len(scored) >= 4:
            break

    if scored:
        scored = sorted(scored, key=lambda x: x["score"], reverse=True)
        return v81_site_home_from_url(scored[0]["url"])
    return ""


def v82_search_official_site_bul(firma_adi):
    firma = firma_adi_temizle(firma_adi)
    groups = v74_expected_groups(firma)
    roots = v82_priority_roots(firma)[:8]
    queries = [
        f'"{firma}" official website',
        f'"{firma}" contact',
        f'"{firma}" iletişim',
        f'{firma} resmi web sitesi',
    ]
    if groups:
        queries.extend([
            f'"{firma}" {" ".join(groups)} contact',
            f'{firma} {" ".join(groups)} official website',
        ])
    for root in roots[:5]:
        queries.append(f'"{firma}" "{root}"')

    scored = []
    for q in list(dict.fromkeys(queries))[:10]:
        try:
            items = v76_search_result_items(q, limit=12)
        except Exception:
            items = []
        for item in items:
            url = normalize_url(item.get("url", ""))
            if not url or v81_is_bad_result_url(url):
                continue
            score = v82_official_score(url, firma, item.get("text", ""))
            if score >= (100 if groups else 58):
                scored.append({"url": v81_site_home_from_url(url), "score": score})

    if scored:
        scored = sorted(scored, key=lambda x: x["score"], reverse=True)
        return scored[0]["url"]
    return ""


def v82_web_reasonable(web_url, firma_adi):
    if not web_url or v81_is_bad_result_url(web_url):
        return False
    root = v72_domain_root(web_url)
    if root in V74_GENERIC_ROOTS and v74_expected_groups(firma_adi):
        return False
    if re.search(r"(shipyardshipyard|marinemarine|holdingholding)$", root.replace("-", "")):
        return False
    return v82_official_score(web_url, firma_adi, "") >= (50 if v74_expected_groups(firma_adi) else 22)


def firma_websitesi_bul(firma_adi):
    firma_adi_temiz = firma_adi_temizle(firma_adi)
    if not firma_adi_temiz:
        return ""

    cache_key = "v82:" + SCAN_MODE + ":" + firma_adi_temiz.lower().strip()
    if cache_key in WEBSITE_CACHE:
        return WEBSITE_CACHE[cache_key]

    direct = v82_direct_official_site_bul(firma_adi_temiz)
    if direct:
        WEBSITE_CACHE[cache_key] = direct
        return direct

    searched = v82_search_official_site_bul(firma_adi_temiz)
    if searched:
        WEBSITE_CACHE[cache_key] = searched
        return searched

    try:
        previous = V81_FIRMA_WEBSITE_BUL_FINAL(firma_adi_temiz)
    except Exception:
        previous = ""

    if previous and v82_web_reasonable(previous, firma_adi_temiz):
        WEBSITE_CACHE[cache_key] = previous
        return previous

    WEBSITE_CACHE[cache_key] = ""
    return ""


def v82_search_contact_completion(web_url, firma_adi):
    data = v81_search_contact_completion(web_url, firma_adi)
    # V81'in arama contact mantigini kullan, ama V82 telefon temizleyici ile son kez filtrele.
    return {
        "mailler": v79_filter_mails(data.get("mailler", []), web_url, firma_adi),
        "telefonlar": temiz_telefon_listesi(data.get("telefonlar", [])),
        "links": data.get("links", []),
    }


def websitesinden_iletisim_bul(web_url, firma_adi=""):
    sonuc = V81_WEBSITE_ILETISIM_BUL_FINAL(web_url, firma_adi=firma_adi)
    if sonuc.get("telefon") not in ["", None, "Bulunamadi"]:
        tel = temiz_telefon_listesi(str(sonuc.get("telefon", "")).split(","))
        sonuc["telefon"] = ", ".join(tel[:5]) if tel else "Bulunamadi"

    if sonuc.get("eposta") != "Bulunamadi" and sonuc.get("telefon") != "Bulunamadi":
        sonuc["durum"] = str(sonuc.get("durum", "")).replace("V81", "V82")
        return sonuc

    # Eksik kalanlarda V82 contact search tekrar temizlenmis sekilde devreye girsin.
    extra = v82_search_contact_completion(web_url, firma_adi)
    mailler = []
    telefonlar = []
    if sonuc.get("eposta") not in ["", None, "Bulunamadi"]:
        mailler.extend(str(sonuc.get("eposta", "")).split(","))
    if sonuc.get("telefon") not in ["", None, "Bulunamadi"]:
        telefonlar.extend(str(sonuc.get("telefon", "")).split(","))
    mailler.extend(extra.get("mailler", []))
    telefonlar.extend(extra.get("telefonlar", []))

    fm = v79_filter_mails(mailler, web_url, firma_adi)
    ft = temiz_telefon_listesi(telefonlar)
    if fm:
        sonuc["eposta"] = ", ".join(fm[:5])
    if ft:
        sonuc["telefon"] = ", ".join(ft[:5])
    if extra.get("links") and not sonuc.get("kaynak"):
        sonuc["kaynak"] = extra["links"][0]

    if sonuc["eposta"] != "Bulunamadi" and sonuc["telefon"] != "Bulunamadi":
        sonuc["durum"] = "Tamamlandi | V82 false-domain guarded contact"
    elif sonuc["eposta"] != "Bulunamadi" or sonuc["telefon"] != "Bulunamadi":
        sonuc["durum"] = "Kismi tamamlandi | V82 false-domain guarded contact"
    else:
        sonuc["durum"] = "Web bulundu, iletisim bulunamadi | V82 false-domain guarded contact"
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
        time.sleep(random.uniform(0.3, 0.75))
        web = firma_websitesi_bul(firma_adi)
        if not web:
            sonuc["durum"] = "Web sitesi bulunamadi"
            return sonuc_guven_skorlari_ekle(sonuc, firma_adi)
        iletisim = websitesinden_iletisim_bul(web, firma_adi=firma_adi)
        sonuc.update(iletisim)
        sonuc["firma_adi"] = firma_adi
        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)
    except Exception as e:
        sonuc["durum"] = "Hata"
        sonuc["hata"] = str(e)
        logging.error(f"V82 derin bilgi hatasi: {firma_adi} - {str(e)}")
        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)


# ============================================================
# V83 FAST WATCHDOG-SAFE ROUTER
# V82 dogruluk icin fazla aday denedigi icin Streamlit watchdog'a
# takilabiliyordu. V83 her firma icin kisa zaman butcesi uygular:
# - Domain basina tek ana sayfa denemesi
# - Dengeli modda hafif contact sayfalari
# - Arama fallback'i kisa ve sinirli
# ============================================================

V82_FIRMA_WEBSITE_BUL_FINAL = firma_websitesi_bul
V82_WEBSITE_ILETISIM_BUL_FINAL = websitesinden_iletisim_bul


def v83_limits():
    if SCAN_MODE == "Derin Tarama":
        return {"site_budget": 75, "max_hosts": 58, "site_timeout": 4, "contact_pages": 18, "contact_timeout": 5, "search_queries": 5}
    if SCAN_MODE == "Hızlı Tarama":
        return {"site_budget": 28, "max_hosts": 16, "site_timeout": 3, "contact_pages": 6, "contact_timeout": 3, "search_queries": 1}
    return {"site_budget": 45, "max_hosts": 32, "site_timeout": 3, "contact_pages": 10, "contact_timeout": 4, "search_queries": 3}


def v83_root_order(firma_adi):
    profile = v74_company_profile(firma_adi)
    tokens = profile.get("tokens", [])
    brand_tokens = profile.get("brand_tokens", []) or tokens[:1]
    groups = v74_expected_groups(firma_adi)
    roots = []

    def add(x):
        x = normalize_domain_token(str(x or "")).strip("-")
        if x and len(x) >= 3 and x not in roots:
            if not re.search(r"(shipyardshipyard|marinemarine|holdingholding)$", x):
                roots.append(x)

    brand1 = brand_tokens[0] if brand_tokens else ""
    brand2 = "".join(brand_tokens[:2]) if len(brand_tokens) >= 2 else ""
    token2 = "".join(tokens[:2]) if len(tokens) >= 2 else ""

    if "classification" in groups or "loydu" in tokens:
        add("turkloydu")
        add("turk-loydu")

    if "holding" in groups:
        add((brand1 or token2) + "holding")
        add((brand1 or token2) + "-holding")
        add(token2)
        add(brand1)

    if "marine" in groups:
        base = brand2 or token2 or brand1
        add(base + "marine")
        add(base + "-marine")
        add(base + "maritime")
        if base != brand1:
            add(brand1 + "marine")
            add(brand1 + "-marine")
        if brand1 not in V74_GENERIC_ROOTS:
            add(brand1)
        add(base)

    if "shipyard" in groups:
        base = brand2 or token2 or brand1
        if brand1 and brand1 not in V74_GENERIC_ROOTS and not brand2:
            # Dearsan/Sefine/Tersan/Sanmar/Cemre/Ceksan gibi siteler genellikle marka domainidir.
            add(brand1)
        add(base + "shipyard")
        add(base + "-shipyard")
        add(base + "shipyards")
        add(base + "-shipyards")
        if base != brand1:
            add(base)
            add(brand1 + "shipyard")
            add(brand1 + "-shipyard")
        if brand1 and brand1 not in V74_GENERIC_ROOTS:
            add(brand1)
        elif brand1:
            add(brand1 + "shipyard")

    if not groups:
        add(brand2)
        add(token2)
        add(brand1)

    # V82'nin iyi adaylarini sona ekle ama siralamayi sisirmeden.
    for r in v82_priority_roots(firma_adi)[:10]:
        add(r)

    return roots[:18]


def v83_tlds_for_root(root, firma_adi):
    tokens = v74_company_profile(firma_adi).get("tokens", [])
    if "loydu" in tokens or "classification" in v74_expected_groups(firma_adi):
        return [".org", ".com.tr", ".com", ".net", ".tr"]
    if root.endswith("holding"):
        return [".com", ".com.tr", ".net", ".tr"]
    if root in {"ares"}:
        return [".global", ".com", ".com.tr", ".net"]
    return [".com.tr", ".com", ".org", ".net", ".tr", ".global"]


def v83_host_candidates(firma_adi):
    adaylar = []
    for root in v83_root_order(firma_adi):
        for tld in v83_tlds_for_root(root, firma_adi):
            for host in [f"https://www.{root}{tld}/", f"https://{root}{tld}/"]:
                if host not in adaylar:
                    adaylar.append(host)
    return adaylar[:v83_limits()["max_hosts"]]


def v83_active_site_score(url, firma_adi):
    try:
        r = guvenli_get(url, timeout=v83_limits()["site_timeout"], referer="https://www.google.com/")
        status = int(getattr(r, "status_code", 0) or 0)
        final_url = normalize_url(getattr(r, "url", url) or url)
        if status == 404 or status >= 500:
            return {"url": final_url, "score": -120, "alive": False, "status": status}
        text = temiz_metin((r.text or "")[:18000]) if status < 400 else ""
        score = v82_official_score(final_url, firma_adi, text)
        if status < 400 or status in [401, 403]:
            score += 25
        if v81_is_bad_result_url(final_url):
            score -= 100
        return {"url": final_url, "score": score, "alive": status < 400 or status in [401, 403], "status": status}
    except Exception:
        return {"url": url, "score": -120, "alive": False, "status": 0}


def v83_search_official_site_bul(firma_adi, deadline):
    firma = firma_adi_temizle(firma_adi)
    groups = v74_expected_groups(firma)
    queries = [
        f'"{firma}" official website',
        f'"{firma}" contact',
        f'{firma} resmi web sitesi',
        f'{firma} iletişim',
    ]
    if groups:
        queries.append(f'"{firma}" {" ".join(groups)} contact')

    scored = []
    for q in list(dict.fromkeys(queries))[:v83_limits()["search_queries"]]:
        if time.time() > deadline:
            break
        try:
            items = v76_search_result_items(q, limit=8)
        except Exception:
            items = []
        for item in items:
            url = normalize_url(item.get("url", ""))
            if not url or v81_is_bad_result_url(url):
                continue
            score = v82_official_score(url, firma, item.get("text", ""))
            if score >= (88 if groups else 55):
                scored.append({"url": v81_site_home_from_url(url), "score": score})
    if scored:
        scored = sorted(scored, key=lambda x: x["score"], reverse=True)
        return scored[0]["url"]
    return ""


def firma_websitesi_bul(firma_adi):
    firma_adi_temiz = firma_adi_temizle(firma_adi)
    if not firma_adi_temiz:
        return ""

    cache_key = "v83:" + SCAN_MODE + ":" + firma_adi_temiz.lower().strip()
    if cache_key in WEBSITE_CACHE:
        return WEBSITE_CACHE[cache_key]

    deadline = time.time() + v83_limits()["site_budget"]
    scored = []
    for host in v83_host_candidates(firma_adi_temiz):
        if time.time() > deadline:
            break
        s = v83_active_site_score(host, firma_adi_temiz)
        if s.get("alive") and s.get("score", -120) >= (92 if v74_expected_groups(firma_adi_temiz) else 55):
            scored.append(s)
            if s.get("score", 0) >= 130:
                break

    if scored:
        scored = sorted(scored, key=lambda x: x.get("score", -120), reverse=True)
        web = v81_site_home_from_url(scored[0]["url"])
        WEBSITE_CACHE[cache_key] = web
        return web

    searched = v83_search_official_site_bul(firma_adi_temiz, deadline)
    if searched:
        WEBSITE_CACHE[cache_key] = searched
        return searched

    WEBSITE_CACHE[cache_key] = ""
    return ""


def v83_contact_urls(web_url, firma_adi="", home_html=""):
    base = v79_base_url(web_url)
    domain = domain_al(base).replace("www.", "")
    paths = [
        "/", "/contact", "/contact/", "/contacts", "/contacts/", "/contact-us", "/contact-us/",
        "/public/contact", "/public/contact/", "/iletisim", "/iletisim/", "/iletişim", "/iletişim/",
        "/tr/contact", "/tr/contact/", "/tr/iletisim", "/tr/iletisim/", "/tr/iletişim", "/tr/iletişim/",
        "/en/contact", "/en/contact/", "/en/contact-us", "/en/contact-us/",
        "/locations", "/locations/", "/offices", "/offices/", "/yerleskeler", "/tr/yerleskeler",
        "/adresler", "/tr/adresler",
    ]
    urls = [normalize_url(base + p) for p in paths]
    if domain:
        urls.extend([
            f"https://old.{domain}/contact/",
            f"https://old.{domain}/contacts/",
            f"https://old.{domain}/iletisim/",
        ])
    try:
        urls.extend(v79_internal_contact_links(base, home_html)[:8])
    except Exception:
        pass

    final = []
    seen = set()
    for u in sorted(urls, key=v80_url_contact_score, reverse=True):
        if not url_gecerli_mi(u) or u in seen:
            continue
        if v80_same_brand_or_domain(u, web_url, firma_adi):
            seen.add(u)
            final.append(u)
    return final[:v83_limits()["contact_pages"]]


def v83_light_search_contact(web_url, firma_adi):
    domain = domain_al(web_url).replace("www.", "")
    firma = firma_adi_temizle(firma_adi)
    queries = [
        f'site:{domain} "{firma}" email phone',
        f'site:{domain} "{firma}" telefon e-posta',
        f'"{firma}" "{domain}" contact',
    ]
    mailler, telefonlar, links = [], [], []
    for q in queries[:v83_limits()["search_queries"]]:
        try:
            items = v76_search_result_items(q, limit=8)
        except Exception:
            items = []
        for item in items:
            url = normalize_url(item.get("url", ""))
            blob = " ".join([item.get("text", ""), url])
            if not v80_same_brand_or_domain(url, web_url, firma_adi, blob):
                continue
            m, t = v79_extract_contacts(blob)
            mailler.extend(m)
            telefonlar.extend(t)
            if url and not v81_is_bad_result_url(url):
                links.append(url)
    return {
        "mailler": v79_filter_mails(mailler, web_url, firma_adi),
        "telefonlar": temiz_telefon_listesi(telefonlar),
        "links": list(dict.fromkeys(links)),
    }


def websitesinden_iletisim_bul(web_url, firma_adi=""):
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
    mailler, telefonlar, kaynaklar = [], [], []
    home_html = ""
    okunan = 0

    try:
        home = v79_fetch_contact_page(web_url, "https://www.google.com/")
        if home.get("ok"):
            okunan += 1
            home_html = home.get("html", "")
            mailler.extend(home.get("mailler", []))
            telefonlar.extend(home.get("telefonlar", []))
            kaynaklar.append(web_url)
    except Exception:
        pass

    for u in v83_contact_urls(web_url, firma_adi, home_html):
        try:
            data = v79_fetch_contact_page(u, web_url)
            if not data.get("ok"):
                continue
            okunan += 1
            mailler.extend(data.get("mailler", []))
            telefonlar.extend(data.get("telefonlar", []))
            kaynaklar.append(u)
            if v79_filter_mails(mailler, web_url, firma_adi) and temiz_telefon_listesi(telefonlar):
                break
        except Exception:
            continue

    filtered_mail = v79_filter_mails(mailler, web_url, firma_adi)
    filtered_tel = temiz_telefon_listesi(telefonlar)

    if not filtered_mail or not filtered_tel:
        extra = v83_light_search_contact(web_url, firma_adi)
        mailler.extend(extra.get("mailler", []))
        telefonlar.extend(extra.get("telefonlar", []))
        kaynaklar.extend(extra.get("links", []))
        filtered_mail = v79_filter_mails(mailler, web_url, firma_adi)
        filtered_tel = temiz_telefon_listesi(telefonlar)

    if filtered_mail:
        sonuc["eposta"] = ", ".join(filtered_mail[:5])
    if filtered_tel:
        sonuc["telefon"] = ", ".join(filtered_tel[:5])
    sonuc["kaynak"] = list(dict.fromkeys(kaynaklar))[0] if kaynaklar else web_url

    if sonuc["eposta"] != "Bulunamadi" and sonuc["telefon"] != "Bulunamadi":
        sonuc["durum"] = f"Tamamlandi | V83 fast contact sayfa: {okunan}"
    elif sonuc["eposta"] != "Bulunamadi" or sonuc["telefon"] != "Bulunamadi":
        sonuc["durum"] = f"Kismi tamamlandi | V83 fast contact sayfa: {okunan}"
    else:
        sonuc["durum"] = f"Web bulundu, iletisim bulunamadi | V83 fast contact sayfa: {okunan}"
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
        time.sleep(random.uniform(0.1, 0.35))
        web = firma_websitesi_bul(firma_adi)
        if not web:
            sonuc["durum"] = "Web sitesi bulunamadi"
            return sonuc_guven_skorlari_ekle(sonuc, firma_adi)
        iletisim = websitesinden_iletisim_bul(web, firma_adi=firma_adi)
        sonuc.update(iletisim)
        sonuc["firma_adi"] = firma_adi
        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)
    except Exception as e:
        sonuc["durum"] = "Hata"
        sonuc["hata"] = str(e)
        logging.error(f"V83 derin bilgi hatasi: {firma_adi} - {str(e)}")
        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)


# ============================================================
# V84 BEST-OF ENGINES + ARSIV HAFIZASI
# Tek motor her sitede ayni basariyi vermiyor. V84 yeni taramayi,
# onceki basarili arsiv kayitlari ve hafif alternatif motorlarla
# birlestirir; iyi bulunan veri sonraki guncellemede kaybolmaz.
# ============================================================

V83_FIRMA_WEBSITE_BUL_FINAL = firma_websitesi_bul
V83_WEBSITE_ILETISIM_BUL_FINAL = websitesinden_iletisim_bul

V84_EXTRA_GENERIC_ROOTS = set(V74_GENERIC_ROOTS) | {
    "besiktas", "gelibolu", "karadeniz", "ada", "hat", "yonca", "rmk"
}


def v84_has_value(x):
    return str(x or "").strip() not in ["", "nan", "NaN", "Bulunamadi", "None"]


def v84_base_result(firma_adi):
    return {
        "firma_adi": firma_adi,
        "web_adresi": "Bulunamadi",
        "telefon": "Bulunamadi",
        "eposta": "Bulunamadi",
        "kaynak": "",
        "durum": "",
        "hata": ""
    }


def v84_bad_web_shape(web_url):
    root = v72_domain_root(web_url)
    root_flat = root.replace("-", "")
    if not web_url or not url_gecerli_mi(normalize_url(web_url)):
        return True
    if v81_is_bad_result_url(web_url):
        return True
    if re.search(r"(shipyardshipyard|shipyardshipyards|marinemarine|holdingholding)$", root_flat):
        return True
    return False


def v84_fetch_short_text(web_url):
    cache_key = "v84_text:" + normalize_url(web_url)
    if cache_key in WEBSITE_CACHE:
        return WEBSITE_CACHE[cache_key]
    text = ""
    try:
        r = guvenli_get(web_url, timeout=4, referer="https://www.google.com/")
        if int(getattr(r, "status_code", 0) or 0) < 400:
            text = temiz_metin((r.text or "")[:26000])
    except Exception:
        text = ""
    WEBSITE_CACHE[cache_key] = text
    return text


def v84_sector_text_ok(web_url, firma_adi, text=""):
    groups = v74_expected_groups(firma_adi)
    if not groups:
        return True
    root = v72_domain_root(web_url)
    low_url = turkce_karakter_temizle(str(web_url or "").lower())
    root_flat = root.replace("-", "")
    for group in groups:
        cfg = V74_SECTOR_GROUPS[group]
        if any(r in root_flat or r in low_url for r in cfg["roots"]):
            return True
    if not text:
        text = v84_fetch_short_text(web_url)
    low_text = turkce_karakter_temizle(str(text or "").lower())
    return any(v74_text_has_any(low_text, V74_SECTOR_GROUPS[g]["needles"]) for g in groups)


def v84_web_plausible(web_url, firma_adi, text=""):
    if v84_bad_web_shape(web_url):
        return False
    root = v72_domain_root(web_url)
    groups = v74_expected_groups(firma_adi)
    profile = v74_company_profile(firma_adi)
    brand = profile.get("marka", "")
    root_flat = root.replace("-", "")

    if groups and root in V84_EXTRA_GENERIC_ROOTS:
        return v84_sector_text_ok(web_url, firma_adi, text)

    # Sektor firmasinda sadece marka domaini geldiginde sayfa metni sektoru desteklemeli.
    if groups and brand and root_flat == brand and not v84_sector_text_ok(web_url, firma_adi, text):
        return False

    score = v82_official_score(web_url, firma_adi, text or "")
    return score >= (35 if groups else 18)


def v84_contact_values_from_result(res):
    mails = []
    tels = []
    if v84_has_value(res.get("eposta")):
        mails = temiz_mail_listesi(str(res.get("eposta", "")).split(","))
    if v84_has_value(res.get("telefon")):
        tels = temiz_telefon_listesi(str(res.get("telefon", "")).split(","))
    return mails, tels


def v84_result_quality(res, firma_adi):
    if not res:
        return -999
    web = res.get("web_adresi", "")
    if not v84_has_value(web) or not v84_web_plausible(web, firma_adi):
        return -100
    mails, tels = v84_contact_values_from_result(res)
    score = 40
    if mails:
        score += 35
    if tels:
        score += 30
    try:
        score += min(int(res.get("genel_guven", 0) or 0), 100) / 4
    except Exception:
        pass
    if str(res.get("manuel_kontrol", "")) == "Hayır":
        score += 8
    return score


def v84_archive_best_result(firma_adi, require_complete=False):
    try:
        conn = db_baglan()
        df = pd.read_sql_query(
            """
            SELECT firma_adi, web_adresi, telefon, eposta, kaynak, durum, hata,
                   web_guven, mail_guven, telefon_guven, genel_guven,
                   manuel_kontrol, sirket_tipi, ulke_tahmini, ulke_guven, tarih
            FROM sonuclar
            WHERE LOWER(TRIM(firma_adi)) = LOWER(TRIM(?))
            ORDER BY id DESC
            LIMIT 80
            """,
            conn,
            params=(firma_adi,)
        )
        conn.close()
    except Exception:
        return None

    if df.empty:
        return None

    best = None
    best_score = -999
    for _, row in df.iterrows():
        res = {k: row.get(k, "") for k in df.columns}
        res["firma_adi"] = firma_adi
        web = res.get("web_adresi", "")
        if not v84_has_value(web) or not v84_web_plausible(web, firma_adi):
            continue
        mails, tels = v84_contact_values_from_result(res)
        if require_complete and not (mails and tels):
            continue
        score = v84_result_quality(res, firma_adi)
        if score > best_score:
            best_score = score
            best = res

    if best:
        best["durum"] = "Arsivden en iyi dogrulanmis kayit | " + str(best.get("durum", ""))
    return best


def v84_merge_result(primary, candidate, firma_adi, reason="merge"):
    if not candidate:
        return primary
    result = dict(primary or v84_base_result(firma_adi))
    cand = dict(candidate)
    cand_web = cand.get("web_adresi", "")
    cur_web = result.get("web_adresi", "")

    cand_quality = v84_result_quality(cand, firma_adi)
    cur_quality = v84_result_quality(result, firma_adi)

    if cand_quality > cur_quality + 12 and v84_has_value(cand_web):
        result.update({
            "web_adresi": cand_web,
            "kaynak": cand.get("kaynak", cand_web) or cand_web,
        })

    web_for_filter = result.get("web_adresi") if v84_has_value(result.get("web_adresi")) else cand_web
    cur_mails, cur_tels = v84_contact_values_from_result(result)
    cand_mails, cand_tels = v84_contact_values_from_result(cand)
    all_mails = v79_filter_mails(cur_mails + cand_mails, web_for_filter, firma_adi)
    all_tels = temiz_telefon_listesi(cur_tels + cand_tels)

    if all_mails:
        result["eposta"] = ", ".join(all_mails[:5])
    if all_tels:
        result["telefon"] = ", ".join(all_tels[:5])
    if not result.get("kaynak") and cand.get("kaynak"):
        result["kaynak"] = cand.get("kaynak")

    status_bits = [str(result.get("durum", "")).strip(), f"V84 {reason}"]
    result["durum"] = " | ".join([x for x in status_bits if x])
    result["firma_adi"] = firma_adi
    return result


def v84_site_candidates_from_engines(firma_adi):
    candidates = []

    def add(web, source):
        web = normalize_url(web)
        if web and v84_web_plausible(web, firma_adi):
            candidates.append({"web": web, "source": source, "score": v82_official_score(web, firma_adi, "")})

    try:
        add(V83_FIRMA_WEBSITE_BUL_FINAL(firma_adi), "v83")
    except Exception:
        pass

    # Kisa arama motoru: V83 bulamazsa veya eksik kalirsa, ama watchdog'u zorlamadan.
    try:
        searched = v83_search_official_site_bul(firma_adi, time.time() + 18)
        add(searched, "v83_search")
    except Exception:
        pass

    try:
        archive = v84_archive_best_result(firma_adi, require_complete=False)
        if archive:
            add(archive.get("web_adresi", ""), "archive")
    except Exception:
        pass

    final = []
    seen = set()
    for item in sorted(candidates, key=lambda x: x.get("score", 0), reverse=True):
        root = v72_domain_root(item["web"])
        if root in seen:
            continue
        seen.add(root)
        final.append(item)
    return final[:4]


def firma_websitesi_bul(firma_adi):
    firma_adi_temiz = firma_adi_temizle(firma_adi)
    if not firma_adi_temiz:
        return ""

    cache_key = "v84:" + SCAN_MODE + ":" + firma_adi_temiz.lower().strip()
    if cache_key in WEBSITE_CACHE:
        return WEBSITE_CACHE[cache_key]

    # Once tam ve dogrulanmis arsiv kaydi varsa onu koru; iyi veri kaybolmasin.
    archive_complete = v84_archive_best_result(firma_adi_temiz, require_complete=True)
    if archive_complete:
        web = normalize_url(archive_complete.get("web_adresi", ""))
        WEBSITE_CACHE[cache_key] = web
        return web

    candidates = v84_site_candidates_from_engines(firma_adi_temiz)
    if candidates:
        web = normalize_url(candidates[0]["web"])
        WEBSITE_CACHE[cache_key] = web
        return web

    WEBSITE_CACHE[cache_key] = ""
    return ""


def v84_contact_from_engines(web_url, firma_adi):
    # V83 hizli motor ana kaynaktir.
    result = V83_WEBSITE_ILETISIM_BUL_FINAL(web_url, firma_adi=firma_adi)

    # Eski basarili arsiv verisi varsa eksikleri doldur.
    archive = v84_archive_best_result(firma_adi, require_complete=False)
    if archive:
        result = v84_merge_result(result, archive, firma_adi, reason="arsiv hafizasi")

    mails, tels = v84_contact_values_from_result(result)
    if mails and tels:
        result["durum"] = str(result.get("durum", "")) + " | V84 tamam"
        return result

    # Yalniz eksik kalirsa V79 universal contact'i tek seferlik dene.
    try:
        alt = V79_WEBSITE_ILETISIM_BUL_FINAL(web_url, firma_adi=firma_adi)
        result = v84_merge_result(result, alt, firma_adi, reason="v79 tamamlayici")
    except Exception:
        pass

    mails, tels = v84_contact_values_from_result(result)
    if mails and tels:
        result["durum"] = str(result.get("durum", "")) + " | V84 tamam"
        return result

    # Son hafif arama fallback'i.
    try:
        extra = v83_light_search_contact(web_url, firma_adi)
        alt = {
            "firma_adi": firma_adi,
            "web_adresi": web_url,
            "telefon": ", ".join(extra.get("telefonlar", [])) if extra.get("telefonlar") else "Bulunamadi",
            "eposta": ", ".join(extra.get("mailler", [])) if extra.get("mailler") else "Bulunamadi",
            "kaynak": extra.get("links", [""])[0] if extra.get("links") else web_url,
            "durum": "V84 hafif arama tamamlayici"
        }
        result = v84_merge_result(result, alt, firma_adi, reason="arama tamamlayici")
    except Exception:
        pass

    mails, tels = v84_contact_values_from_result(result)
    if mails and tels:
        result["durum"] = "Tamamlandi | V84 best-of contact"
    elif mails or tels:
        result["durum"] = "Kismi tamamlandi | V84 best-of contact"
    else:
        result["durum"] = "Web bulundu, iletisim bulunamadi | V84 best-of contact"
    return result


def websitesinden_iletisim_bul(web_url, firma_adi=""):
    if not web_url:
        return {
            "web_adresi": "Bulunamadi",
            "telefon": "Bulunamadi",
            "eposta": "Bulunamadi",
            "kaynak": "",
            "durum": "Web sitesi bulunamadi",
            "hata": ""
        }
    return v84_contact_from_engines(normalize_url(web_url), firma_adi)


def derin_bilgi_bul(firma_adi):
    sonuc = v84_base_result(firma_adi)
    try:
        time.sleep(random.uniform(0.08, 0.25))

        archive_complete = v84_archive_best_result(firma_adi, require_complete=True)
        if archive_complete:
            archive_complete["firma_adi"] = firma_adi
            return sonuc_guven_skorlari_ekle(archive_complete, firma_adi)

        web = firma_websitesi_bul(firma_adi)
        if not web:
            archive_partial = v84_archive_best_result(firma_adi, require_complete=False)
            if archive_partial and v84_has_value(archive_partial.get("web_adresi")):
                web = archive_partial.get("web_adresi")
            else:
                sonuc["durum"] = "Web sitesi bulunamadi"
                return sonuc_guven_skorlari_ekle(sonuc, firma_adi)

        iletisim = websitesinden_iletisim_bul(web, firma_adi=firma_adi)
        sonuc.update(iletisim)
        sonuc["firma_adi"] = firma_adi

        archive_partial = v84_archive_best_result(firma_adi, require_complete=False)
        if archive_partial:
            sonuc = v84_merge_result(sonuc, archive_partial, firma_adi, reason="son kontrol arsiv")

        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)
    except Exception as e:
        sonuc["durum"] = "Hata"
        sonuc["hata"] = str(e)
        logging.error(f"V84 derin bilgi hatasi: {firma_adi} - {str(e)}")
        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)


# ============================================================
# V85 FULL-NAME INTENT GUARD
# Sorun: "Elkon Electric" gibi cok kelimeli firmalarda yalnizca
# ilk marka kelimesi gecen alakasiz domainler kabul ediliyordu.
# V85, ikinci/ayirt edici kelime domain, arama snippet'i veya
# sayfa metni tarafindan desteklenmeden tek kelime domaini kabul etmez.
# ============================================================

V84_FIRMA_WEBSITE_BUL_FINAL = firma_websitesi_bul
V84_WEBSITE_ILETISIM_BUL_FINAL = websitesinden_iletisim_bul

V85_QUALIFIER_SYNONYMS = {
    "electric": ["electric", "electrical", "elektrik", "elektroteknik", "power", "energy", "automation", "otomasyon"],
    "electrical": ["electric", "electrical", "elektrik", "elektroteknik", "power", "energy", "automation", "otomasyon"],
    "elektrik": ["electric", "electrical", "elektrik", "elektroteknik", "power", "energy", "automation", "otomasyon"],
    "automation": ["automation", "otomasyon", "control", "system integration", "systems integrator", "scada"],
    "otomasyon": ["automation", "otomasyon", "control", "system integration", "systems integrator", "scada"],
    "marine": ["marine", "maritime", "ship", "vessel", "denizcilik"],
    "shipyard": ["shipyard", "shipyards", "shipbuilding", "ship repair", "tersane", "gemi"],
    "shipyards": ["shipyard", "shipyards", "shipbuilding", "ship repair", "tersane", "gemi"],
    "holding": ["holding", "group", "investment", "energy"],
}


def v85_company_tokens(firma_adi):
    return v74_company_profile(firma_adi).get("tokens", [])


def v85_phrase_variants(firma_adi):
    clean = firma_adi_temizle(firma_adi)
    tokens = v85_company_tokens(clean)
    variants = [clean.lower()]
    if tokens:
        variants.append(" ".join(tokens))
        variants.append("".join(tokens[:2]))
        variants.append("-".join(tokens[:2]))
    return [turkce_karakter_temizle(v.lower()) for v in variants if v and len(v) >= 3]


def v85_qualifier_words(firma_adi):
    tokens = v85_company_tokens(firma_adi)
    if len(tokens) <= 1:
        return []
    # İlk kelime ana marka; geri kalan kelimeler ayirt edici sinyaldir.
    qualifiers = []
    for t in tokens[1:6]:
        if t not in qualifiers:
            qualifiers.append(t)
        for syn in V85_QUALIFIER_SYNONYMS.get(t, []):
            s = normalize_domain_token(syn)
            if s and s not in qualifiers:
                qualifiers.append(s)
    return qualifiers


def v85_text_has_qualifier(blob, firma_adi):
    low = turkce_karakter_temizle(str(blob or "").lower())
    compact = normalize_domain_token(low)
    for q in v85_qualifier_words(firma_adi):
        q_norm = normalize_domain_token(q)
        if not q_norm:
            continue
        if q_norm in compact or q.lower() in low:
            return True
    return False


def v85_full_name_supported(web_url, firma_adi, text=""):
    tokens = v85_company_tokens(firma_adi)
    if len(tokens) <= 1:
        return True

    root = v72_domain_root(web_url)
    root_flat = root.replace("-", "")
    url_blob = turkce_karakter_temizle(str(web_url or "").lower())
    text_blob = turkce_karakter_temizle(str(text or "").lower())
    combined = " ".join([url_blob, text_blob])

    first = tokens[0]
    second = tokens[1]
    joined2 = first + second

    if joined2 in root_flat or joined2 in normalize_domain_token(url_blob):
        return True
    if first in root_flat and second in root_flat:
        return True
    if any(v in combined for v in v85_phrase_variants(firma_adi)):
        return True
    if v85_text_has_qualifier(combined, firma_adi):
        return True
    return False


def v85_web_plausible(web_url, firma_adi, text=""):
    if not v84_web_plausible(web_url, firma_adi, text):
        return False

    tokens = v85_company_tokens(firma_adi)
    if len(tokens) <= 1:
        return True

    root = v72_domain_root(web_url)
    root_flat = root.replace("-", "")
    first = tokens[0]

    # Domain sadece ilk marka kelimesiyse ikinci kelime/saha niyeti mutlaka desteklenmeli.
    if root_flat == first or root_flat.startswith(first) and len(root_flat) <= len(first) + 3:
        if not text:
            text = v84_fetch_short_text(web_url)
        return v85_full_name_supported(web_url, firma_adi, text)

    # Kisa benzer domainler icin de ayirt edici kelimeyi ara.
    if first in root_flat and not v85_full_name_supported(web_url, firma_adi, text):
        if not text:
            text = v84_fetch_short_text(web_url)
        return v85_full_name_supported(web_url, firma_adi, text)

    return True


def v85_extract_urls_from_text(text):
    urls = []
    for m in re.findall(r"https?://[^\s<>\)\"']+", str(text or ""), flags=re.I):
        u = normalize_url(m.rstrip(".,;:"))
        if url_gecerli_mi(u) and not v81_is_bad_result_url(u):
            urls.append(v81_site_home_from_url(u))
    return list(dict.fromkeys(urls))


def v85_score_candidate(web_url, firma_adi, text="", source=""):
    if not v85_web_plausible(web_url, firma_adi, text):
        return -999
    score = v82_official_score(web_url, firma_adi, text)
    blob = turkce_karakter_temizle(" ".join([str(web_url or ""), str(text or ""), source]).lower())
    if any(v in blob for v in v85_phrase_variants(firma_adi)):
        score += 55
    if v85_text_has_qualifier(blob, firma_adi):
        score += 35
    root = v72_domain_root(web_url)
    tokens = v85_company_tokens(firma_adi)
    if len(tokens) >= 2 and root.replace("-", "") == tokens[0] and not v85_text_has_qualifier(blob, firma_adi):
        score -= 120
    return score


def v85_search_official_site_bul(firma_adi, seconds=22):
    firma = firma_adi_temizle(firma_adi)
    tokens = v85_company_tokens(firma)
    queries = [
        f'"{firma}" official website',
        f'"{firma}" contact',
        f'"{firma}" website',
        f'"{firma}" email phone',
        f'{firma} resmi web sitesi',
    ]
    if len(tokens) >= 2:
        queries.extend([
            f'"{tokens[0]} {tokens[1]}" official',
            f'"{tokens[0]} {tokens[1]}" contact',
            f'"{tokens[0]} {tokens[1]}" exhibitor',
        ])

    scored = []
    deadline = time.time() + seconds
    for q in list(dict.fromkeys(queries))[:6]:
        if time.time() > deadline:
            break
        try:
            items = v76_search_result_items(q, limit=10)
        except Exception:
            items = []
        for item in items:
            item_url = normalize_url(item.get("url", ""))
            item_text = item.get("text", "")
            candidates = []
            if item_url and not v81_is_bad_result_url(item_url):
                candidates.append(v81_site_home_from_url(item_url))
            candidates.extend(v85_extract_urls_from_text(item_text))

            for u in list(dict.fromkeys(candidates)):
                s = v85_score_candidate(u, firma, item_text, source=q)
                if s >= (80 if len(tokens) >= 2 else 45):
                    scored.append({"url": u, "score": s, "text": item_text})

    if scored:
        scored = sorted(scored, key=lambda x: x["score"], reverse=True)
        return scored[0]["url"]
    return ""


def v85_direct_name_domain_candidates(firma_adi):
    tokens = v85_company_tokens(firma_adi)
    if not tokens:
        return []

    first = tokens[0]
    second = tokens[1] if len(tokens) >= 2 else ""
    roots = []

    def add(root):
        root = str(root or "").strip("-")
        if root and root not in roots:
            roots.append(root)

    if second:
        add(first + second)
        add(first + "-" + second)
    add(first + "-tr")
    add(first + "tr")
    add(first)

    tlds = [".com", ".com.tr", ".net", ".org", ".global"]
    paths = ["/", "/tr", "/tr/", "/tr/iletisim", "/tr/iletisim/", "/contact", "/contact/"]

    urls = []
    for root in roots:
        for tld in tlds:
            for host in [f"https://www.{root}{tld}", f"https://{root}{tld}"]:
                for path in paths:
                    u = normalize_url(host + path)
                    if u not in urls:
                        urls.append(u)
    return urls[:70]


def v85_archive_best_result(firma_adi, require_complete=False):
    try:
        conn = db_baglan()
        df = pd.read_sql_query(
            """
            SELECT firma_adi, web_adresi, telefon, eposta, kaynak, durum, hata,
                   web_guven, mail_guven, telefon_guven, genel_guven,
                   manuel_kontrol, sirket_tipi, ulke_tahmini, ulke_guven, tarih
            FROM sonuclar
            WHERE LOWER(TRIM(firma_adi)) = LOWER(TRIM(?))
            ORDER BY id DESC
            LIMIT 80
            """,
            conn,
            params=(firma_adi,)
        )
        conn.close()
    except Exception:
        return None
    if df.empty:
        return None

    best, best_score = None, -999
    for _, row in df.iterrows():
        res = {k: row.get(k, "") for k in df.columns}
        res["firma_adi"] = firma_adi
        web = res.get("web_adresi", "")
        if not v84_has_value(web) or not v85_web_plausible(web, firma_adi):
            continue
        mails, tels = v84_contact_values_from_result(res)
        if require_complete and not (mails and tels):
            continue
        score = v84_result_quality(res, firma_adi) + v85_score_candidate(web, firma_adi)
        if score > best_score:
            best_score = score
            best = res
    if best:
        best["durum"] = "Arsivden V85 dogrulanmis kayit | " + str(best.get("durum", ""))
    return best


def v85_site_candidates_from_engines(firma_adi):
    candidates = []

    def add(web, source, text=""):
        web = normalize_url(web)
        if not web:
            return
        score = v85_score_candidate(web, firma_adi, text, source)
        if score > -200:
            candidates.append({"web": web, "source": source, "score": score})

    try:
        add(v85_search_official_site_bul(firma_adi, seconds=18), "v85_exact_search")
    except Exception:
        pass

    # Elkon Electric -> elkon-tr.com gibi arama sonucunda kolay gorunen ama
    # klasik firma+kategori domaininden farkli resmi yapilari yakala.
    direct_deadline = time.time() + 18
    for direct_url in v85_direct_name_domain_candidates(firma_adi):
        if time.time() > direct_deadline:
            break
        try:
            r = guvenli_get(direct_url, timeout=3, referer="https://www.google.com/")
            status = int(getattr(r, "status_code", 0) or 0)
            if status >= 500 or status == 404:
                continue
            final_url = normalize_url(getattr(r, "url", direct_url) or direct_url)
            text = temiz_metin((r.text or "")[:18000]) if status < 400 else ""
            add(final_url, "v85_direct_name", text)
        except Exception:
            continue

    try:
        add(V83_FIRMA_WEBSITE_BUL_FINAL(firma_adi), "v83")
    except Exception:
        pass

    try:
        add(v83_search_official_site_bul(firma_adi, time.time() + 12), "v83_search")
    except Exception:
        pass

    try:
        archive = v85_archive_best_result(firma_adi, require_complete=False)
        if archive:
            add(archive.get("web_adresi", ""), "archive")
    except Exception:
        pass

    final, seen = [], set()
    for item in sorted(candidates, key=lambda x: x["score"], reverse=True):
        root = v72_domain_root(item["web"])
        if not root or root in seen:
            continue
        seen.add(root)
        final.append(item)
    return final[:4]


def firma_websitesi_bul(firma_adi):
    firma_adi_temiz = firma_adi_temizle(firma_adi)
    if not firma_adi_temiz:
        return ""

    cache_key = "v85:" + SCAN_MODE + ":" + firma_adi_temiz.lower().strip()
    if cache_key in WEBSITE_CACHE:
        return WEBSITE_CACHE[cache_key]

    archive_complete = v85_archive_best_result(firma_adi_temiz, require_complete=True)
    if archive_complete:
        web = normalize_url(archive_complete.get("web_adresi", ""))
        WEBSITE_CACHE[cache_key] = web
        return web

    candidates = v85_site_candidates_from_engines(firma_adi_temiz)
    if candidates:
        web = normalize_url(candidates[0]["web"])
        WEBSITE_CACHE[cache_key] = web
        return web

    WEBSITE_CACHE[cache_key] = ""
    return ""


def v85_contact_from_engines(web_url, firma_adi):
    result = V84_WEBSITE_ILETISIM_BUL_FINAL(web_url, firma_adi=firma_adi)
    archive = v85_archive_best_result(firma_adi, require_complete=False)
    if archive:
        result = v84_merge_result(result, archive, firma_adi, reason="v85 arsiv hafizasi")
    result["durum"] = str(result.get("durum", "")) + " | V85 full-name guard"
    return result


def websitesinden_iletisim_bul(web_url, firma_adi=""):
    if not web_url:
        return {
            "web_adresi": "Bulunamadi",
            "telefon": "Bulunamadi",
            "eposta": "Bulunamadi",
            "kaynak": "",
            "durum": "Web sitesi bulunamadi",
            "hata": ""
        }
    return v85_contact_from_engines(normalize_url(web_url), firma_adi)


def derin_bilgi_bul(firma_adi):
    sonuc = v84_base_result(firma_adi)
    try:
        time.sleep(random.uniform(0.08, 0.22))
        archive_complete = v85_archive_best_result(firma_adi, require_complete=True)
        if archive_complete:
            archive_complete["firma_adi"] = firma_adi
            return sonuc_guven_skorlari_ekle(archive_complete, firma_adi)

        web = firma_websitesi_bul(firma_adi)
        if not web:
            sonuc["durum"] = "Web sitesi bulunamadi"
            return sonuc_guven_skorlari_ekle(sonuc, firma_adi)

        iletisim = websitesinden_iletisim_bul(web, firma_adi=firma_adi)
        sonuc.update(iletisim)
        sonuc["firma_adi"] = firma_adi
        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)
    except Exception as e:
        sonuc["durum"] = "Hata"
        sonuc["hata"] = str(e)
        logging.error(f"V85 derin bilgi hatasi: {firma_adi} - {str(e)}")
        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)


# ============================================================
# V86 SEARCH-RANK AUTHORITY
# Ana prensip: Firma adi tirnak icinde arandiginda arama motorunun ilk
# siralardaki sonucu en guclu sinyaldir. Domain tahmini, yalnizca bu
# sinyal yoksa devreye girer. Google CSE/SerpAPI/Bing key varsa kullanir;
# yoksa mevcut Bing/DDG HTML sonuc sirasi ile calisir.
# ============================================================

V85_FIRMA_WEBSITE_BUL_FINAL = firma_websitesi_bul
V85_WEBSITE_ILETISIM_BUL_FINAL = websitesinden_iletisim_bul

V86_DIRECTORY_HINTS = {
    "exhibitor", "exhibitors", "booked-exhibitors", "katilimci", "katılımcı",
    "fair", "fuar", "conference", "expo", "event", "directory", "firma-rehberi",
    "isfirmarehberi", "yellow", "kompass", "europages", "shippax", "marinedeal"
}


V86_BUSINESS_HINTS = {
    "electric": ["electric", "electrical", "elektrik", "elektronik", "power", "energy", "automation"],
    "electrik": ["electric", "electrical", "elektrik", "elektronik", "power", "energy", "automation"],
    "elektrik": ["electric", "electrical", "elektrik", "elektronik", "power", "energy", "automation"],
    "shipyard": ["shipyard", "shipbuilding", "marine", "maritime", "vessel", "yard", "tersane"],
    "ship": ["shipyard", "shipbuilding", "marine", "maritime", "vessel", "shipping", "tersane"],
    "marine": ["marine", "maritime", "ship", "vessel", "shipping", "deniz", "tersane"],
    "marin": ["marine", "maritime", "ship", "vessel", "shipping", "deniz", "tersane"],
    "defence": ["defence", "defense", "savunma", "aerospace", "aviation", "electronics"],
    "defense": ["defence", "defense", "savunma", "aerospace", "aviation", "electronics"],
    "savunma": ["defence", "defense", "savunma", "aerospace", "aviation", "electronics"],
    "aviation": ["aviation", "aerospace", "havacilik", "defence", "defense"],
    "software": ["software", "yazilim", "technology", "teknoloji", "automation"],
    "yazilim": ["software", "yazilim", "technology", "teknoloji", "automation"],
    "holding": ["holding", "group", "investment", "energy"],
}


def v86_secret(name, default=""):
    try:
        val = os.environ.get(name, "")
        if val:
            return val
    except Exception:
        pass
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return default


def v86_context_terms():
    ctx = turkce_karakter_temizle(str(globals().get("CURRENT_FUAR_ETIKETI", "") or "").lower())
    terms = []
    if any(x in ctx for x in ["smm", "ssm", "hamburg", "marin", "marine", "maritime", "ship", "deniz"]):
        terms.extend(["marine", "maritime", "shipbuilding", "exhibitor"])
    if any(x in ctx for x in ["beauty", "cosmetic", "kozmetik"]):
        terms.extend(["cosmetic", "beauty", "exhibitor"])
    return list(dict.fromkeys(terms))


def v86_business_terms(firma_adi):
    blob = turkce_karakter_temizle(str(firma_adi or "").lower())
    terms = []

    for key, values in V86_BUSINESS_HINTS.items():
        if key in blob:
            terms.extend(values)

    for token in v85_company_tokens(firma_adi)[1:4]:
        if len(token) >= 4:
            terms.append(token)

    terms.extend(v86_context_terms())
    return list(dict.fromkeys(turkce_karakter_temizle(str(t).lower()) for t in terms if str(t).strip()))[:14]


def v86_search_authority_limits():
    mode = turkce_karakter_temizle(str(globals().get("SCAN_MODE", "") or "").lower())
    if "hizli" in mode:
        return {"seconds": 10, "queries": 4, "items": 5}
    if "derin" in mode:
        return {"seconds": 38, "queries": 9, "items": 10}
    return {"seconds": 20, "queries": 6, "items": 8}


def v86_google_cse_items(query, limit=8):
    key = v86_secret("GOOGLE_CSE_API_KEY") or v86_secret("GOOGLE_API_KEY")
    cx = v86_secret("GOOGLE_CSE_ID") or v86_secret("GOOGLE_CX") or v86_secret("GOOGLE_SEARCH_ENGINE_ID")
    if not key or not cx:
        return []
    try:
        r = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={"key": key, "cx": cx, "q": query, "num": min(max(int(limit), 1), 10)},
            timeout=7,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        if r.status_code >= 400:
            return []
        data = r.json()
        items = []
        for idx, item in enumerate(data.get("items", [])[:limit], start=1):
            link = normalize_url(item.get("link", ""))
            if not link:
                continue
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            items.append({
                "url": link,
                "title": title,
                "text": temiz_metin(" ".join([title, snippet])),
                "rank": idx,
                "engine": "google_cse"
            })
        return items
    except Exception as e:
        logging.warning(f"V86 Google CSE arama hatasi: {query} - {str(e)}")
        return []


def v86_serpapi_items(query, limit=8):
    key = v86_secret("SERPAPI_KEY")
    if not key:
        return []
    try:
        r = requests.get(
            "https://serpapi.com/search.json",
            params={"engine": "google", "q": query, "api_key": key, "num": min(max(int(limit), 1), 10)},
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        if r.status_code >= 400:
            return []
        data = r.json()
        items = []
        for idx, item in enumerate(data.get("organic_results", [])[:limit], start=1):
            link = normalize_url(item.get("link", ""))
            if not link:
                continue
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            items.append({
                "url": link,
                "title": title,
                "text": temiz_metin(" ".join([title, snippet])),
                "rank": idx,
                "engine": "serpapi_google"
            })
        return items
    except Exception as e:
        logging.warning(f"V86 SerpAPI arama hatasi: {query} - {str(e)}")
        return []


def v86_ranked_search_items(query, limit=8):
    items = v86_google_cse_items(query, limit=limit)
    if not items:
        items = v86_serpapi_items(query, limit=limit)
    if not items:
        try:
            fallback = v76_search_result_items(query, limit=limit)
        except Exception:
            fallback = []
        items = []
        for idx, item in enumerate(fallback[:limit], start=1):
            items.append({
                "url": normalize_url(item.get("url", "")),
                "title": "",
                "text": item.get("text", ""),
                "rank": idx,
                "engine": "bing_ddg"
            })
    return [x for x in items if x.get("url")]


def v86_item_candidate_urls(item):
    urls = []
    primary = normalize_url(item.get("url", ""))
    if primary and not v81_is_bad_result_url(primary):
        urls.append(v81_site_home_from_url(primary))

    # Arama sonucu bir fuar/dizin sayfasi olabilir; snippet icindeki resmi URL daha degerlidir.
    blob = " ".join([item.get("title", ""), item.get("text", ""), item.get("url", "")])
    urls.extend(v85_extract_urls_from_text(blob))

    final = []
    seen = set()
    for u in urls:
        u = normalize_url(u)
        if not u or v81_is_bad_result_url(u):
            continue
        root = v72_domain_root(u)
        if not root or root in seen:
            continue
        seen.add(root)
        final.append(u)
    return final[:5]


def v86_item_is_directory(item):
    blob = turkce_karakter_temizle(" ".join([item.get("url", ""), item.get("title", ""), item.get("text", "")]).lower())
    return any(x in blob for x in V86_DIRECTORY_HINTS)


def v86_search_rank_candidate_score(url, item, firma_adi, query):
    rank = int(item.get("rank", 9) or 9)
    evidence_blob = turkce_karakter_temizle(" ".join([
        str(url or ""),
        item.get("url", ""),
        item.get("title", ""),
        item.get("text", "")
    ]).lower())
    tokens = v85_company_tokens(firma_adi)

    score = max(0, 165 - (rank - 1) * 22)

    if str(item.get("engine", "")).startswith(("google", "serpapi_google")):
        score += 35
        if rank <= 3:
            score += 35

    if any(v in evidence_blob for v in v85_phrase_variants(firma_adi)):
        score += 95

    if tokens:
        token_hits = sum(1 for t in tokens[:5] if t in evidence_blob or normalize_domain_token(t) in normalize_domain_token(evidence_blob))
        score += token_hits * 24

    business_terms = v86_business_terms(firma_adi)
    if business_terms:
        business_hits = sum(1 for t in business_terms if t in evidence_blob)
        score += min(business_hits, 3) * 28
        if len(tokens) >= 2 and business_hits == 0:
            score -= 45

    if len(tokens) >= 2:
        if not v85_full_name_supported(url, firma_adi, item.get("text", "")):
            score -= 170
        else:
            score += 70

    if v85_text_has_qualifier(evidence_blob, firma_adi):
        score += 45

    if v86_item_is_directory(item) and url != v81_site_home_from_url(item.get("url", "")):
        # Fuar/dizin sonucunun icindeki resmi URL'yi yakaladiysak iyi sinyal.
        score += 45
    elif v86_item_is_directory(item):
        score -= 55

    if any(x in evidence_blob for x in ["official", "resmi", "website", "web site", "contact", "iletisim", "iletişim"]):
        score += 20

    if not v85_web_plausible(url, firma_adi, item.get("text", "")):
        score -= 150

    return score


def v86_search_rank_authority_site_bul(firma_adi, seconds=28):
    firma = firma_adi_temizle(firma_adi)
    if not firma:
        return ""

    limits = v86_search_authority_limits()
    tokens = v85_company_tokens(firma)
    queries = [
        f'"{firma}" official website',
        f'"{firma}" contact',
        f'"{firma}" website',
        f'"{firma}"',
    ]

    for ctx in v86_context_terms():
        queries.insert(0, f'"{firma}" {ctx} official website')
        queries.insert(1, f'"{firma}" {ctx} contact')

    for term in v86_business_terms(firma)[:4]:
        queries.append(f'"{firma}" {term} official website')
        queries.append(f'"{firma}" {term} contact')

    if len(tokens) >= 2:
        queries.extend([
            f'"{tokens[0]} {tokens[1]}" official website',
            f'"{tokens[0]} {tokens[1]}" contact',
        ])

    deadline = time.time() + seconds
    scored = []
    for q in list(dict.fromkeys(queries))[:limits["queries"]]:
        if time.time() > deadline:
            break
        items = v86_ranked_search_items(q, limit=limits["items"])
        for item in items:
            for u in v86_item_candidate_urls(item):
                s = v86_search_rank_candidate_score(u, item, firma, q)
                if s >= (150 if len(tokens) >= 2 else 95):
                    scored.append({"url": u, "score": s, "rank": item.get("rank", 9), "engine": item.get("engine", "")})

    if not scored:
        return ""

    scored = sorted(scored, key=lambda x: (x["score"], -int(x.get("rank", 9))), reverse=True)
    return v81_site_home_from_url(scored[0]["url"])


def firma_websitesi_bul(firma_adi):
    firma_adi_temiz = firma_adi_temizle(firma_adi)
    if not firma_adi_temiz:
        return ""

    cache_key = "v86:" + SCAN_MODE + ":" + firma_adi_temiz.lower().strip()
    if cache_key in WEBSITE_CACHE:
        return WEBSITE_CACHE[cache_key]

    archive_complete = v85_archive_best_result(firma_adi_temiz, require_complete=True)
    if archive_complete:
        web = normalize_url(archive_complete.get("web_adresi", ""))
        WEBSITE_CACHE[cache_key] = web
        return web

    hinted_web = url_website_hint_getir(firma_adi_temiz)
    if hinted_web and v85_web_plausible(hinted_web, firma_adi_temiz):
        WEBSITE_CACHE[cache_key] = hinted_web
        return hinted_web

    ranked = v86_search_rank_authority_site_bul(
        firma_adi_temiz,
        seconds=v86_search_authority_limits()["seconds"]
    )
    if ranked:
        WEBSITE_CACHE[cache_key] = ranked
        return ranked

    try:
        web = V85_FIRMA_WEBSITE_BUL_FINAL(firma_adi_temiz)
    except Exception:
        web = ""

    if web and v85_web_plausible(web, firma_adi_temiz):
        WEBSITE_CACHE[cache_key] = web
        return web

    WEBSITE_CACHE[cache_key] = ""
    return ""


def websitesinden_iletisim_bul(web_url, firma_adi=""):
    return V85_WEBSITE_ILETISIM_BUL_FINAL(web_url, firma_adi=firma_adi)


def derin_bilgi_bul(firma_adi):
    sonuc = v84_base_result(firma_adi)
    try:
        time.sleep(random.uniform(0.06, 0.18))
        web = firma_websitesi_bul(firma_adi)
        if not web:
            sonuc["durum"] = "Web sitesi bulunamadi"
            return sonuc_guven_skorlari_ekle(sonuc, firma_adi)

        iletisim = websitesinden_iletisim_bul(web, firma_adi=firma_adi)
        sonuc.update(iletisim)
        sonuc["firma_adi"] = firma_adi
        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)
    except Exception as e:
        sonuc["durum"] = "Hata"
        sonuc["hata"] = str(e)
        logging.error(f"V86 derin bilgi hatasi: {firma_adi} - {str(e)}")
        return sonuc_guven_skorlari_ekle(sonuc, firma_adi)


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
        st.session_state["auth_last_activity"] = 0.0
        st.rerun()

    st.header("⚙️ Tarama Ayarlari")

    if PLAYWRIGHT_AKTIF:
        st.success("Playwright aktif: JS sayfalari okunabilir.")
    else:
        st.warning("Playwright pasif: Sadece statik HTML okunur.")

    fuar_etiketi = st.text_input("Fuar Etiketi", value="Genel_Liste")
    globals()["CURRENT_FUAR_ETIKETI"] = fuar_etiketi

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
                    kuyruga_firma_ekle(fuar_etiketi, firmalar)

                if adet > 0:
                    st.success(f"✅ {adet} firma havuza aktarıldı.")
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
    st.subheader("📄 PDF Katılımcı Kataloğu Analiz")
    pdf_file = st.file_uploader("Katılımcı listesi / katalog PDF'i yükleyin", type=["pdf"])

    if pdf_file:
        try:
            with st.spinner("PDF okunuyor..."):
                pdf_firmalar = pdf_firmalari_oku(pdf_file)

            st.info(f"PDF içinde {len(pdf_firmalar)} olası firma adı bulundu.")

            if pdf_firmalar:
                st.dataframe(pd.DataFrame({"Firma Adi": pdf_firmalar}), use_container_width=True)

            if st.button("📥 PDF Firmalarını Havuza Aktar", use_container_width=True):
                adet = listeye_ekle(pdf_firmalar, listeyi_sifirla=listeyi_sifirla)
                kuyruga_firma_ekle(fuar_etiketi, pdf_firmalar)
                st.success(f"✅ {adet} firma havuza aktarıldı.")
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
                kuyruga_firma_ekle(fuar_etiketi, excel_firmalar)
                st.success(f"✅ {adet} firma havuza aktarıldı.")
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
            kuyruga_firma_ekle(fuar_etiketi, manuel_firmalar)
            st.success(f"✅ {adet} firma havuza aktarıldı.")
            st.rerun()


# ============================================================
# ISLEM HAVUZU
# ============================================================

st.divider()
st.subheader(f"📋 Islem Havuzu: {len(st.session_state['ana_liste'])} Firma")

try:
    kuyruk_ozet = kuyruk_ozeti_getir(fuar_etiketi)
    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Kuyruk Bekleyen", kuyruk_ozet.get("Bekliyor", 0))
    q2.metric("Kuyruk İşleniyor", kuyruk_ozet.get("İşleniyor", 0))
    q3.metric("Kuyruk Tamamlandı", kuyruk_ozet.get("Tamamlandı", 0))
    q4.metric("Kuyruk Hata", kuyruk_ozet.get("Hata", 0))

    c_devam, c_tarama, c_yansit, c_sifirla = st.columns([1, 1, 1, 1])

    with c_devam:
        if st.button("🔁 Kaldığı Yerden Havuzu Güncelle", use_container_width=True):
            kurtarilan = kuyruk_takilanlari_bekliyora_al(fuar_etiketi, dakika=2)
            adet_devam = kuyruk_bekleyenleri_havuza_yansit(fuar_etiketi)
            st.success(f"{adet_devam} bekleyen firma işlem havuzuna yansıtıldı. {kurtarilan} takılı iş tekrar Bekliyor durumuna alındı.")
            st.rerun()

    with c_tarama:
        if st.button("▶️ Kuyruktan Sonraki Paketi Tara", use_container_width=True):
            kuyruk_takilanlari_bekliyora_al(fuar_etiketi, dakika=2)
            st.session_state["force_queue_run"] = True
            st.rerun()

    with c_yansit:
        if st.button("📌 Havuzu Kuyrukla Senkronize Et", use_container_width=True):
            sync = kuyruk_havuz_senkronize_et(fuar_etiketi, st.session_state.get("ana_liste", []))
            st.success(
                f"Havuz senkronize edildi. Havuz: {sync['toplam']} firma | "
                f"Yeni eklenen: {sync['yeni']} | "
                f"Takılıdan kurtarılan: {sync['kurtarilan']} | "
                f"Kuyruk bekleyen: {sync['bekleyen']}"
            )
            st.rerun()

    with c_sifirla:
        with st.expander("🧹 Kuyruk İşlemleri"):
            if st.button("Takılı İşleniyor Kayıtlarını Bekliyor Yap"):
                adet_k = kuyruk_takilanlari_bekliyora_al(fuar_etiketi, dakika=0)
                st.success(f"{adet_k} takılı kayıt tekrar Bekliyor durumuna alındı.")
                st.rerun()

            if st.button("Bu fuar kuyruğunu sıfırla"):
                kuyruk_sifirla(fuar_etiketi)
                st.success("Kuyruk sıfırlandı.")
                st.rerun()
except Exception as e:
    st.warning(f"Kuyruk özeti gösterilemedi: {str(e)}")


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

    tara = st.button("⚡ KUYRUKTAN BU PAKETİ TARA VE ARŞİVE KAYDET", use_container_width=True)

    if tara or st.session_state.get("force_queue_run", False):
        st.session_state["force_queue_run"] = False
        # Önce mevcut havuzu kalıcı kuyruğa yaz.
        # Böylece sistem 139 firma bulduysa 139'u da kaybolmadan bekleyen iş olur.
        tum_firmalar = st.session_state["ana_liste"]
        kuyruga_firma_ekle(fuar_etiketi, tum_firmalar)

        # Kesinti nedeniyle İşleniyor durumunda takılı kalanları tekrar Bekliyor yap.
        kuyruk_takilanlari_bekliyora_al(fuar_etiketi, dakika=2)

        # İşlenecek paket artık session'dan değil, kalıcı kuyruktan alınır.
        paket_firmalar = kuyruk_bekleyen_firmalari_getir(
            fuar_etiketi,
            limit=paket_boyutu,
            sadece_islenmemis=sadece_islenmemis
        )

        toplam_kalan = len(kuyruk_bekleyen_firmalari_getir(
            fuar_etiketi,
            limit=10000,
            sadece_islenmemis=sadece_islenmemis
        ))

        if not paket_firmalar:
            st.success("✅ Bu fuar etiketi için işlem bekleyen firma kalmadı.")
            st.stop()

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

        kuyruk_toplu_durum_guncelle(fuar_etiketi, paket_firmalar, "İşleniyor")

        status_area.info(
            f"🚀 {SCAN_MODE} başladı. Bu pakette {toplam_firma} firma işlenecek. "
            f"Kalıcı kuyrukta bekleyen toplam: {toplam_kalan}. Paralel işlem: {max_workers}."
        )

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(derin_bilgi_bul, firma): firma for firma in paket_firmalar}
            pending = set(futures.keys())
            tamamlanan_sayi = 0
            son_ilerleme = time.time()

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
                        **Bekleyen thread:** {len(pending)} &nbsp;&nbsp; | &nbsp;&nbsp;
                        **Geçen:** {sure_formatla(gecen)}
                        """
                    )
                    status_area.info(
                        f"🔎 Arka planda {max_workers} firma aynı anda taranıyor. Sonuç geldikçe ara kayıt yapılacak."
                    )

                    # 4 dakikadan uzun hiç ilerleme yoksa bu paketi durdur, kalanları tekrar Bekliyor yap
                    if time.time() - son_ilerleme > 240:
                        for fut in list(pending):
                            firma_pending = futures.get(fut, "")
                            if firma_pending:
                                kuyruk_durum_guncelle(fuar_etiketi, firma_pending, "Bekliyor", "Watchdog: işlem çok uzun sürdü, tekrar kuyruğa alındı")
                        st.warning("⚠️ Uzun süre ilerleme olmadığı için kalan işler tekrar bekleyen kuyruğa alındı. Kaldığı yerden devam edebilirsin.")
                        break

                    continue

                son_ilerleme = time.time()

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

                    try:
                        kalite = enrichment_kalite_etiketi(res)
                        if res.get("durum"):
                            res["durum"] = f"{res.get('durum')} | Kalite: {kalite}"
                    except Exception:
                        pass

                    kayitlar.append(res)

                    try:
                        verileri_toplu_kaydet([res])
                        kuyruk_durum_guncelle(fuar_etiketi, firma, "Tamamlandı")
                    except Exception as e:
                        kuyruk_durum_guncelle(fuar_etiketi, firma, "Hata", str(e))
                        hata_kaydet(f"Ara kayıt hatası: {str(e)}")

                    if res.get("durum") and "Tamamlandi" in res.get("durum"):
                        basarili += 1
                    elif "bulunamadi" in res.get("durum", "").lower():
                        web_bulunamadi += 1
                    elif "Hata" in res.get("durum", ""):
                        hata_sayisi += 1

                    oran = tamamlanan_sayi / toplam_firma
                    gecen = time.time() - baslangic_tarama
                    tahmini_toplam = gecen / tamamlanan_sayi * toplam_firma if tamamlanan_sayi else 0
                    kalan = max(tahmini_toplam - gecen, 0)

                    progress_bar.progress(oran)
                    status_area.info(
                        f"İşleniyor: {tamamlanan_sayi}/{toplam_firma} | Son tamamlanan firma: {firma}"
                    )

                    kalan_kuyruk = kuyruk_ozeti_getir(fuar_etiketi).get("Bekliyor", 0)

                    metrik_area.markdown(
                        f"""
                        **Mod:** {SCAN_MODE} &nbsp;&nbsp; | &nbsp;&nbsp;
                        **Bu paket:** {tamamlanan_sayi}/{toplam_firma} &nbsp;&nbsp; | &nbsp;&nbsp;
                        **Kuyrukta kalan:** {kalan_kuyruk} &nbsp;&nbsp; | &nbsp;&nbsp;
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
        kuyruk_ozet_final = kuyruk_ozeti_getir(fuar_etiketi)
        kalan_sonraki = kuyruk_ozet_final.get("Bekliyor", 0) + kuyruk_ozet_final.get("Hata", 0)

        st.session_state["son_islem_ozeti"] = (
            f"Paket tamamlandı. Bu paket: {len(kayitlar)} | "
            f"Başarılı: {basarili} | "
            f"Web bulunamadı: {web_bulunamadi} | "
            f"Hata: {hata_sayisi} | "
            f"Kuyrukta kalan: {kalan_sonraki}"
        )

        st.success("✅ Paket tamamlandı ve sonuçlar arşive ara kayıt olarak işlendi.")
        st.info(st.session_state["son_islem_ozeti"])

        # İşlenenleri görsel havuzdan çıkar ama kalanları kalıcı kuyrukta tut
        islenen_set = set([f.lower().strip() for f in paket_firmalar if f])
        st.session_state["ana_liste"] = [
            f for f in st.session_state["ana_liste"]
            if f.lower().strip() not in islenen_set
        ]

        if kalan_sonraki > 0:
            st.warning(f"📦 Bu paket bitti. Kuyrukta yaklaşık {kalan_sonraki} firma kaldı. Devam etmek için 'Kuyruktan Sonraki Paketi Tara' butonuna bas.")
        else:
            st.success("🎉 Kalıcı kuyruktaki tüm firmalar tamamlandı.")

        st.rerun()

else:
    st.info("Henuz islem havuzunda firma yok. URL, PDF, Excel veya manuel giristen firma ekleyebilirsin.")


# ============================================================
# ARSIV
# ============================================================

st.divider()
st.subheader("🗄️ Araştırma Klasörleri / Kalıcı Arşiv")

st.caption("Her fuar etiketi ayrı bir araştırma klasörü gibi gösterilir. Buradan tamamlanan işleri, eksikleri ve manuel kontrol gerekenleri görebilirsin.")

df_klasorler = arsiv_klasor_ozeti_getir()

if not df_klasorler.empty:
    # Oran kolonları
    df_klasorler_goster = df_klasorler.copy()
    for col in ["toplam_kayit", "web_bulunan", "mail_bulunan", "telefon_bulunan", "yuksek_guven", "orta_guven", "dusuk_guven", "manuel_kontrol"]:
        if col in df_klasorler_goster.columns:
            df_klasorler_goster[col] = pd.to_numeric(df_klasorler_goster[col], errors="coerce").fillna(0).astype(int)

    df_klasorler_goster["web_orani"] = ((df_klasorler_goster["web_bulunan"] / df_klasorler_goster["toplam_kayit"]) * 100).round(1)
    df_klasorler_goster["mail_orani"] = ((df_klasorler_goster["mail_bulunan"] / df_klasorler_goster["toplam_kayit"]) * 100).round(1)
    df_klasorler_goster["telefon_orani"] = ((df_klasorler_goster["telefon_bulunan"] / df_klasorler_goster["toplam_kayit"]) * 100).round(1)

    st.dataframe(
        df_klasorler_goster,
        use_container_width=True,
        height=260
    )

    klasor_listesi = df_klasorler["fuar_etiketi"].dropna().astype(str).tolist()
    secili_klasor = st.selectbox("📁 İncelenecek araştırma klasörü", klasor_listesi)

    df_detay = arsiv_klasor_detay_getir(secili_klasor)

    if not df_detay.empty:
        toplam = len(df_detay)
        web_bulunan = int(((df_detay["web_adresi"].fillna("") != "") & (df_detay["web_adresi"].fillna("") != "Bulunamadi")).sum())
        mail_bulunan = int(((df_detay["eposta"].fillna("") != "") & (df_detay["eposta"].fillna("") != "Bulunamadi")).sum())
        tel_bulunan = int(((df_detay["telefon"].fillna("") != "") & (df_detay["telefon"].fillna("") != "Bulunamadi")).sum())
        manuel = int((df_detay["manuel_kontrol"].fillna("") == "Evet").sum()) if "manuel_kontrol" in df_detay.columns else 0

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Toplam Firma", toplam)
        c2.metric("Web Bulunan", web_bulunan)
        c3.metric("Mail Bulunan", mail_bulunan)
        c4.metric("Telefon Bulunan", tel_bulunan)
        c5.metric("Manuel Kontrol", manuel)

        if "sirket_tipi" in df_detay.columns:
            y1, y2, y3 = st.columns(3)
            y1.metric("Yerli Firma", int((df_detay["sirket_tipi"].fillna("") == "Yerli").sum()))
            y2.metric("Yabancı Firma", int((df_detay["sirket_tipi"].fillna("") == "Yabancı").sum()))
            y3.metric("Belirsiz", int((df_detay["sirket_tipi"].fillna("") == "Belirsiz").sum()))

        st.markdown("### 📌 Klasör Detayı")

        filtre = st.selectbox(
            "Filtre",
            ["Tümü", "Yerli firmalar", "Yabancı firmalar", "Belirsiz ülke/tip", "Web bulunamayanlar", "Mail/telefon eksik", "Düşük güven", "Manuel kontrol gerekenler"],
            index=0
        )

        df_goster = df_detay.copy()

        if filtre == "Yerli firmalar":
            df_goster = df_goster[df_goster["sirket_tipi"].fillna("") == "Yerli"]
        elif filtre == "Yabancı firmalar":
            df_goster = df_goster[df_goster["sirket_tipi"].fillna("") == "Yabancı"]
        elif filtre == "Belirsiz ülke/tip":
            df_goster = df_goster[df_goster["sirket_tipi"].fillna("").isin(["", "Belirsiz"])]
        elif filtre == "Web bulunamayanlar":
            df_goster = df_goster[df_goster["web_adresi"].fillna("").isin(["", "Bulunamadi"])]
        elif filtre == "Mail/telefon eksik":
            df_goster = df_goster[
                df_goster["eposta"].fillna("").isin(["", "Bulunamadi"]) |
                df_goster["telefon"].fillna("").isin(["", "Bulunamadi"])
            ]
        elif filtre == "Düşük güven":
            df_goster = df_goster[pd.to_numeric(df_goster["genel_guven"], errors="coerce").fillna(0) < 45]
        elif filtre == "Manuel kontrol gerekenler":
            df_goster = df_goster[df_goster["manuel_kontrol"].fillna("") == "Evet"]

        st.dataframe(df_goster, use_container_width=True, height=420)

        st.markdown("### 🔁 Eksikleri Tekrar Havuza Al")

        b1, b2, b3, b4 = st.columns(4)

        with b1:
            if st.button("Web bulunamayanları tekrar tara", use_container_width=True):
                adet = arsiv_eksikleri_havuza_al(secili_klasor, "web")
                st.success(f"{adet} firma tekrar işlem havuzuna alındı.")
                st.rerun()

        with b2:
            if st.button("Mail/telefon eksikleri tekrar tara", use_container_width=True):
                adet = arsiv_eksikleri_havuza_al(secili_klasor, "mail_tel")
                st.success(f"{adet} firma tekrar işlem havuzuna alındı.")
                st.rerun()

        with b3:
            if st.button("Düşük güvenlileri tekrar tara", use_container_width=True):
                adet = arsiv_eksikleri_havuza_al(secili_klasor, "dusuk_guven")
                st.success(f"{adet} firma tekrar işlem havuzuna alındı.")
                st.rerun()

        with b4:
            if st.button("Manuel kontrol gerekenleri havuza al", use_container_width=True):
                adet = arsiv_eksikleri_havuza_al(secili_klasor, "manuel")
                st.success(f"{adet} firma tekrar işlem havuzuna alındı.")
                st.rerun()

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df_goster.to_excel(writer, index=False, sheet_name="Arsiv Detay")

        st.download_button(
            label="📥 Seçili klasörü Excel indir",
            data=output.getvalue(),
            file_name=f"{secili_klasor}_arsiv_detay.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

        st.markdown("### 🗑️ Arşiv Temizleme")

        st.warning("Silme işlemleri kalıcıdır. Test kayıtlarını temizlemek için kullan.")

        del_col1, del_col2 = st.columns(2)

        with del_col1:
            with st.expander("🗑️ Seçili araştırma klasörünü komple sil"):
                st.caption("Bu işlem seçili fuar etiketine ait tüm arşiv kayıtlarını ve işlem kuyruğunu siler.")
                onay_klasor = st.checkbox(
                    f"'{secili_klasor}' klasörünü silmeyi onaylıyorum",
                    key=f"delete_folder_confirm_{secili_klasor}"
                )

                if st.button("Klasörü Kalıcı Olarak Sil", use_container_width=True, disabled=not onay_klasor):
                    ok = arsiv_klasor_sil(secili_klasor, kuyruk_dahil=True)
                    if ok:
                        st.success(f"'{secili_klasor}' araştırma klasörü silindi.")
                        st.rerun()
                    else:
                        st.error("Klasör silinirken hata oluştu.")

        with del_col2:
            with st.expander("🧹 Şu an filtrede görünen kayıtları sil"):
                st.caption("Örneğin sadece 'Düşük güven' filtresindekileri ya da 'Web bulunamayanlar' listesini temizleyebilirsin.")
                filtre_sayisi = len(df_goster)
                st.write(f"Şu an filtrede görünen kayıt sayısı: **{filtre_sayisi}**")

                onay_filtre = st.checkbox(
                    f"Filtrede görünen {filtre_sayisi} kaydı silmeyi onaylıyorum",
                    key=f"delete_filtered_confirm_{secili_klasor}_{filtre}"
                )

                if st.button("Filtrede Görünenleri Sil", use_container_width=True, disabled=(not onay_filtre or filtre_sayisi == 0)):
                    silinen = arsiv_filtreli_kayitlari_sil(secili_klasor, df_goster["firma_adi"].dropna().astype(str).tolist())
                    st.success(f"{silinen} kayıt silindi.")
                    st.rerun()


else:
    st.info("Henüz arşiv klasörü oluşmadı. Bir araştırma çalıştırıp sonuçları kaydettiğinde burada görünecek.")



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
    Perge Mimarlık & Squarexpo iş birliği ile geliştirildi ❤️ Fuar Müşteri Otomasyonu V3.1
</div>
""", unsafe_allow_html=True)

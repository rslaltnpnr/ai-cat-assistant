"""
AI Kedi Asistani
-----------------
Windows masaustunde duran, seffaf arka planli, surklenebilir bir kedi
karakteri. Cift tiklaninca acilan konusma balonundan soru sorulur;
ekran goruntusu alinip Google Gemini Flash modeline gonderilir ve
yanit balonda gosterilir.

Calistirmak icin:
    pip install -r requirements.txt
    python main.py

Dosyanin en altinda PyInstaller ile tek dosya (.exe) yapma adimlari
yer alir.
"""

import base64
import hmac
import http.server
import ipaddress
import json
import math
import os
import random
import socket
import socketserver
import ssl
import struct
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from collections import deque
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlparse

from PyQt6.QtCore import (
    QEasingCurve,
    QObject,
    QPoint,
    QPointF,
    QPropertyAnimation,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QBrush,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


# --------------------------------------------------------------------------
# Yol yardimcilari (PyInstaller ile tek dosya .exe icinde de calisir)
# --------------------------------------------------------------------------

def base_dir():
    """config.json gibi yazilabilir dosyalarin duracagi klasor."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(relative_path):
    """assets gibi PyInstaller ile pakete gomulen salt-okunur dosyalar."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)


CONFIG_PATH = os.path.join(base_dir(), "config.json")
HISTORY_PATH = os.path.join(base_dir(), "chat_history.json")
ACCESS_LOG_PATH = os.path.join(base_dir(), "remote_access.log")
SCREENSHOT_HISTORY_PATH = os.path.join(base_dir(), "screenshot_history.json")
MAX_SCREENSHOT_HISTORY_ENTRIES = 50

NOTIFICATION_LOG_PATH = os.path.join(base_dir(), "notifications.json")
ASSETS_DIR = resource_path("assets")
MAX_HISTORY_ENTRIES = 200
ACCESS_LOG_MAX_BYTES = 512 * 1024
MAX_NOTIFICATION_ENTRIES = 50
ACCESS_LOG_DISPLAY_LINES = 50
# "Baglam farkindaliği": her soruda modele gonderilen onceki soru-cevap
# sayisi - fazla yuksek olursa istek boyutu (ve maliyeti) gereksiz buyur,
# fazla dusuk olursa "ona gore" gibi takip sorulari baglamini kaybeder.
CONTEXT_HISTORY_TURNS = 5


# --------------------------------------------------------------------------
# Coken durumda log tutma + otomatik yeniden baslatma
# --------------------------------------------------------------------------

CRASH_LOG_PATH = os.path.join(base_dir(), "crash.log")
CRASH_MARKER_PATH = os.path.join(base_dir(), ".last_crash")
MIN_RESTART_INTERVAL_SECONDS = 10  # bundan kisa arayla ust uste cokerse
# yeniden baslatmayi durdurur (baslangicta patlayan bir hatanin sonsuz
# dongude bilgisayari yormasini onlemek icin)


def _restart_command():
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, os.path.abspath(__file__)]


def _log_crash(exc_type, exc_value, exc_tb):
    try:
        with open(CRASH_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n--- {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
    except OSError:
        pass


def _should_auto_restart():
    now = time.time()
    last = None
    try:
        with open(CRASH_MARKER_PATH, "r", encoding="utf-8") as f:
            last = float(f.read().strip())
    except (OSError, ValueError):
        pass
    try:
        with open(CRASH_MARKER_PATH, "w", encoding="utf-8") as f:
            f.write(str(now))
    except OSError:
        pass
    return last is None or (now - last) > MIN_RESTART_INTERVAL_SECONDS


def install_crash_handler():
    """
    Beklenmeyen bir hata GUI thread'inden disari sizarsa (PyQt6 normalde
    bunu yakalayip sys.excepthook'a yonlendirir) traceback'i crash.log'a
    yazar ve uygulamayi kendini yeniden baslatarak kurtarmaya calisir.
    Cok kisa arayla ust uste cokerse (baslangic hatasi dongusu) tekrar
    baslatmaz - kullanici crash.log'u inceleyip sorunu gormelidir.
    """

    def handle_exception(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        _log_crash(exc_type, exc_value, exc_tb)
        if _should_auto_restart():
            try:
                subprocess.Popen(_restart_command(), close_fds=True)
            except OSError:
                pass
        os._exit(1)

    sys.excepthook = handle_exception

SLEEP_AFTER_MS = 3 * 60 * 1000  # 3 dakika hareketsizlikten sonra uyku
REVERT_TO_NORMAL_MS = 4000  # smile/fear gosterildikten sonra norm'a donus

FALLBACK_MODEL = "gemini-3.6-flash"
OVERLOAD_RETRY_DELAYS = (2, 4)  # saniye; ana modelde 503 aldiginda bekleme sureleri

# Google'in kullanimdan kaldirdigi/eskimis model adlari: config.json'da
# bunlardan biri kayitliysa otomatik olarak guncel varsayilana tasinir.
DEPRECATED_MODELS = {"gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.0-pro"}

STATE_FILES = {
    "norm": "fuff_norm.png",
    "zzz": "fuff_zzz.png",
    "smile": "fuff_smile.png",
    "stern": "fuff_stern.png",
    "fear": "fuff_fear.png",
}

# "norm" durumunda kedi statik durmak yerine gercekten yuruyormus gibi
# bu kare dizisini dondurur (bkz. CatCharacter._load_walk_frames). Dosyalar
# yoksa (henuz eklenmemis/ozel bir skin'de bulunmuyorsa) sessizce statik
# "norm" gorseline geri duser - mevcut skin'leri bozmaz.
WALK_FRAME_PATTERN = "fuff_walk_{:03d}.png"
WALK_FRAME_MAX_COUNT = 60
WALK_FRAME_INTERVAL_MS = 90

# Kedi "norm" durumundayken (yuruyus animasyonu varsa) olduğu yerde saymak
# yerine ekran uzerinde gercekten dolasir - bkz. CatCharacter._roam_move.
# Mobil surumdeki RoamingCat ile ayni mantik: rastgele bir hedefe, mesafeyle
# orantili bir surede yumusak gecis yapip biraz bekler, tekrar dener.
ROAM_MIN_DELAY_MS = 2000
ROAM_MAX_DELAY_MS = 6000
ROAM_MS_PER_PIXEL = 6
ROAM_MIN_DURATION_MS = 600
ROAM_MAX_DURATION_MS = 3500

REMOTE_SERVER_PORT = 8765
REMOTE_MAX_FAILED_ATTEMPTS = 5
REMOTE_LOCKOUT_SECONDS = 60

# "Canli Kontrol" sekmesi (bkz. RemoteLiveControlServer) REST komut
# sunucusundan (REMOTE_SERVER_PORT) AYRI bir portta calisir - HTTP degil,
# ozel/hafif bir TLS soket protokolu kullanir (surekli video karesi +
# gercek zamanli fare/klavye olaylari icin). Telefon tarafi bu portu
# ayrica eslestirmez; sabit REMOTE_SERVER_PORT + 1 kuralini kullanir
# (bkz. mobil taraftaki ayni sabit), boylece mevcut eslesmis
# bilgisayarlar (QR/PIN ile zaten kaydedilmis) yeniden eslestirilmeden
# bu portu da kullanabilir.
REMOTE_LIVE_PORT = REMOTE_SERVER_PORT + 1
REMOTE_LIVE_FRAME_INTERVAL_SECONDS = 1 / 12  # ~12 kare/saniye
REMOTE_LIVE_JPEG_QUALITY = 55
REMOTE_LIVE_MAX_FRAME_WIDTH = 960
REMOTE_LIVE_MOUSE_BUTTONS = frozenset({"left", "right", "middle"})
REMOTE_LIVE_SPECIAL_KEY_NAMES = frozenset(
    {
        "enter",
        "backspace",
        "delete",
        "tab",
        "esc",
        "space",
        "up",
        "down",
        "left",
        "right",
        "home",
        "end",
        "shift",
        "ctrl",
        "alt",
        "caps_lock",
        "page_up",
        "page_down",
    }
)

APP_VERSION = "1.8.0"
GITHUB_REPO = "rslaltnpnr/ai-cat-assistant"
UPDATE_CHECK_TIMEOUT_SECONDS = 5
UPDATE_DOWNLOAD_TIMEOUT_SECONDS = 60
# release-desktop.yml release'e bu adlarla dosya yukler - degistirilirse
# ikisi de birlikte guncellenmeli.
UPDATE_ASSET_NAME = "AI-Kedi-Asistani.exe"
UPDATE_CHECKSUM_ASSET_NAME = "AI-Kedi-Asistani.exe.sha256"

DEFAULT_CONFIG = {
    "character_name": "Fuff",
    "gemini_api_key": "",
    "scale_percent": 100,
    "model_name": "gemini-flash-latest",
    "skin": "Varsayilan",
    "pos_x": None,
    "pos_y": None,
    "remote_pin": None,
    "gemini_request_date": None,
    "gemini_request_count": 0,
    "theme_mode": "dark",
    "auto_backup_enabled": True,
    "auto_backup_last": None,
    "context_aware_enabled": True,
    "personality": "Varsayilan",
    "auto_theme_enabled": False,
    "auto_theme_day_start": "07:00",
    "auto_theme_night_start": "19:00",
}

# "Ayarlari Disa/Ice Aktar" ile paylasilabilen kisisellestirme ayarlari -
# _export_backup/_import_backup'taki tam yedeklemenin aksine, gizli
# bilgi (gemini_api_key, remote_pin) ya da makineye ozgu durum
# (pos_x/pos_y, auto_backup_last, gemini_request_date/count) icermez,
# boylece baskalariyla guvenle paylasilabilir.
PROFILE_EXPORT_KEYS = [
    "character_name",
    "scale_percent",
    "model_name",
    "skin",
    "personality",
    "theme_mode",
    "auto_backup_enabled",
    "context_aware_enabled",
    "auto_theme_enabled",
    "auto_theme_day_start",
    "auto_theme_night_start",
]

AUTO_BACKUP_PREFIX = "otomatik-yedek-"
AUTO_BACKUP_INTERVAL_DAYS = 1
AUTO_BACKUP_MAX_COUNT = 7
# Zamanlayici her calistiginda "bir gun gecti mi" kontrol edilir - bu
# yuzden interval_days'ten cok daha sik calisabilir (dakikalarda bir),
# gercek yedekleme yine de gunde bir kereyle sinirli kalir.
AUTO_BACKUP_CHECK_INTERVAL_MS = 60 * 60 * 1000

# --------------------------------------------------------------------------
# Kural motoru / otomasyon: "config.json"'daki "automation_rules" listesi
# (bilerek DEFAULT_CONFIG'e eklenmedi - orada bir liste, dict(DEFAULT_CONFIG)
# ile alinan sig kopyalar arasinda paylasilan degisebilir bir varsayilan
# olurdu; bkz. CatCharacter._automation_rules()) kullanicinin tanimladigi
# tetikleyici -> eylem kurallarini tutar. Her kural bir dict:
#   {"id", "name", "trigger_type", "trigger_value", "action_type",
#    "action_value", "enabled", "last_fired"}
AUTOMATION_TICK_INTERVAL_MS = 30 * 1000
AUTOMATION_TRIGGER_LABELS = {
    "time_daily": "Her gun belirli bir saatte",
    "idle_minutes": "N dakika hareketsiz kalinca",
}
AUTOMATION_ACTION_LABELS = {
    "lock": "Bilgisayari kilitle",
    "sleep": "Uyku moduna al",
    "notify": "Bildirim goster",
    "open_url": "Bir baglanti ac",
}

# Konusma balonu ve gecmis paneli gibi yari-seffaf panellerin renk paleti.
# Mobil uygulamadaki ThemeMode.light/dark tercihiyle ayni fikirde -
# "theme_mode" config anahtari yedek alma/geri yukleme ile diger tum
# ayarlar gibi tasinir, boylece iki uygulamada da tutarli bir tercih
# saklanir (gercek bir canli senkron degil, ayri ayri saklanan ayni tur
# tercih).
THEME_PALETTES = {
    "dark": {
        "panel_bg": "rgba(30, 30, 40, 220)",
        "border": "rgba(255, 255, 255, 60)",
        "text": "white",
        "text_muted": "rgba(255, 255, 255, 140)",
        "input_bg": "rgba(255, 255, 255, 30)",
        "input_border": "rgba(255, 255, 255, 80)",
        "textedit_bg": "rgba(255, 255, 255, 15)",
    },
    "light": {
        "panel_bg": "rgba(245, 245, 250, 235)",
        "border": "rgba(0, 0, 0, 40)",
        "text": "#202028",
        "text_muted": "rgba(30, 30, 40, 140)",
        "input_bg": "rgba(0, 0, 0, 18)",
        "input_border": "rgba(0, 0, 0, 60)",
        "textedit_bg": "rgba(0, 0, 0, 10)",
    },
}


def panel_stylesheet(object_name, theme_mode):
    """[object_name] nesne adiyla iliskilendirilmis yari-seffaf bir panel
    (ChatBubble/ChatHistoryDialog) icin, [theme_mode] ("dark"/"light")
    paletine gore QSS dondurur. Ikisi de neredeyse ayni QSS blogunu
    kullandigi icin buraya cikarildi."""
    p = THEME_PALETTES.get(theme_mode, THEME_PALETTES["dark"])
    return f"""
        #{object_name} {{
            background-color: {p['panel_bg']};
            border-radius: 16px;
            border: 1px solid {p['border']};
        }}
        QLabel {{ color: {p['text']}; }}
        QLineEdit {{
            background-color: {p['input_bg']};
            border: 1px solid {p['input_border']};
            border-radius: 8px;
            padding: 6px;
            color: {p['text']};
        }}
        QPushButton {{
            background-color: rgba(90, 170, 255, 220);
            border: none;
            border-radius: 8px;
            padding: 6px 10px;
            color: white;
            font-weight: bold;
        }}
        QPushButton:hover {{ background-color: rgba(120, 190, 255, 230); }}
        QTextEdit {{
            background-color: {p['textedit_bg']};
            border: none;
            border-radius: 8px;
            color: {p['text']};
            padding: 6px;
        }}
    """


# --------------------------------------------------------------------------
# Ayar yonetimi (config.json)
# --------------------------------------------------------------------------

class ConfigManager:
    def __init__(self, path):
        self.path = path
        self.data = dict(DEFAULT_CONFIG)
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data.update(json.load(f))
            except (json.JSONDecodeError, OSError):
                pass
            self._migrate_deprecated_model()
        else:
            self.save()
        self._ensure_remote_pin()

    def _migrate_deprecated_model(self):
        if self.data.get("model_name") in DEPRECATED_MODELS:
            self.data["model_name"] = DEFAULT_CONFIG["model_name"]
            self.save()

    def _ensure_remote_pin(self):
        if not self.data.get("remote_pin"):
            self.data["remote_pin"] = f"{random.randint(0, 999999):06d}"
            self.save()

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def register_gemini_request(self):
        """Gunluk soru sayacini bir arttirir (gun degistiyse once sifirlar)
        ve yeni degeri dondurur - kullaniciya gunde kac istek gonderdigini
        gostermek icin (Gemini ucretsiz kotasi gunluktur)."""
        today = datetime.now().strftime("%Y-%m-%d")
        if self.data.get("gemini_request_date") != today:
            self.data["gemini_request_date"] = today
            self.data["gemini_request_count"] = 0
        self.data["gemini_request_count"] += 1
        self.save()
        return self.data["gemini_request_count"]

    def gemini_request_count_today(self):
        today = datetime.now().strftime("%Y-%m-%d")
        if self.data.get("gemini_request_date") != today:
            return 0
        return self.data.get("gemini_request_count", 0)


# --------------------------------------------------------------------------
# Sohbet gecmisi (chat_history.json)
# --------------------------------------------------------------------------

class ChatHistoryManager:
    def __init__(self, path):
        self.path = path
        self.entries = []
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.entries = json.load(f)
            except (json.JSONDecodeError, OSError):
                self.entries = []

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.entries, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def add(self, question, answer, is_error=False):
        self.entries.append(
            {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "question": question,
                "answer": answer,
                "is_error": is_error,
                "favorite": False,
            }
        )
        if len(self.entries) > MAX_HISTORY_ENTRIES:
            self.entries = self.entries[-MAX_HISTORY_ENTRIES:]
        self.save()

    def clear(self):
        self.entries = []
        self.save()


# --------------------------------------------------------------------------
# Bildirim gecmisi (notifications.json)
# --------------------------------------------------------------------------

class NotificationLog:
    """Sistem tepsisi (ya da tepsi yoksa mesaj kutusu) araciligiyla
    kullaniciya gosterilen her bildirimin (hatirlatici kuruldu/ates aldi,
    guncelleme mevcut vb.) kalici bir kaydi - "Bildirim Gecmisi" menu
    eylemiyle gorulebilir. Windows'un kendi Eylem Merkezi'nden farkli
    olarak, uygulama yeniden baslatilsa da (Eylem Merkezi bildirim
    kapatilinca kaybolabilir) burada kalir."""

    def __init__(self, path):
        self.path = path
        self.entries = []
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.entries = json.load(f)
            except (json.JSONDecodeError, OSError):
                self.entries = []

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.entries, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def add(self, title, message):
        self.entries.append(
            {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "title": title,
                "message": message,
            }
        )
        if len(self.entries) > MAX_NOTIFICATION_ENTRIES:
            self.entries = self.entries[-MAX_NOTIFICATION_ENTRIES:]
        self.save()

    def clear(self):
        self.entries = []
        self.save()


class ScreenshotHistoryLog(NotificationLog):
    """Telefonun /screenshot ile istedigi her ekran goruntusunun ne zaman
    alindiginin kalici bir kaydi - "Ekran Goruntusu Gecmisi" menu
    eylemiyle gorulebilir. Gorselin kendisini SAKLAMAZ (bkz.
    capture_screenshot_jpeg_base64 - goruntu yalnizca istek anlik olarak
    telefona gonderilir); yalnizca zaman damgasi ve kim istedigi
    (add()'in source parametresi) tutulur, boylece bu ozellik hicbir yeni
    gizlilik/depolama riski eklemez."""

    def add(self, source):
        self.entries.append(
            {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "source": source,
            }
        )
        if len(self.entries) > MAX_SCREENSHOT_HISTORY_ENTRIES:
            self.entries = self.entries[-MAX_SCREENSHOT_HISTORY_ENTRIES:]
        self.save()


def format_screenshot_history(entries):
    """[entries] listesini (en yeni en ustte) okunabilir duz metne
    cevirir - Ekran Goruntusu Gecmisi penceresinde gosterilir."""
    lines = []
    for entry in reversed(entries):
        lines.append(f"[{entry.get('time', '')}] {entry.get('source', '')}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Sifreli not defteri (secure_notepad.dat)
# --------------------------------------------------------------------------

SECURE_NOTEPAD_PATH = os.path.join(base_dir(), "secure_notepad.dat")
# Mobil suruumundeki SecureNotepadService ile ayni gerekce: OWASP
# PBKDF2-HMAC-SHA256 onerisi 600k+ ama bu, yerel hizlandirma olmadan
# kilit acmayi rahatsiz edici derecede yavaslatabilir; 200k, kaba
# kuvveti pahali kilarken yine de makul bir sure icinde kalir.
SECURE_NOTEPAD_PBKDF2_ITERATIONS = 200000


class WrongPasswordError(Exception):
    """unlock()'a girilen sifre, saklanan tuzla turetilen anahtarla
    eslesmedigini (AES-GCM'in kimlik dogrulama etiketi tutmadigini)
    belirtir."""


class SecureNotepadService:
    """Notlari, kullanicinin belirledigi bir sifreden PBKDF2-HMAC-SHA256
    ile turetilen bir anahtarla AES-256-GCM ile sifreleyip cihazda
    (config.json'dan ayri, secure_notepad.dat dosyasinda) saklayan
    servis - mobil suruumundeki SecureNotepadService ile ayni tasarim.
    Butun not listesi TEK bir sifreli blok olarak tutulur.

    Sifre hicbir zaman diskte saklanmaz; her kilit acmada saklanan
    tuzdan yeniden turetilir ve dogrulugu AES-GCM'in kendi kimlik
    dogrulama etiketiyle sinanir - decrypt yanlis anahtarda
    cryptography.exceptions.InvalidTag firlatir, bu WrongPasswordError'a
    cevrilir. Sifre unutulursa notlar KURTARILAMAZ - bkz. reset()."""

    def __init__(self, path=SECURE_NOTEPAD_PATH, pbkdf2_iterations=SECURE_NOTEPAD_PBKDF2_ITERATIONS):
        self.path = path
        self.pbkdf2_iterations = pbkdf2_iterations

    def is_set_up(self):
        return os.path.exists(self.path)

    def _derive_key(self, password, salt):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self.pbkdf2_iterations,
        )
        return kdf.derive(password.encode("utf-8"))

    def set_up(self, password):
        """Ilk kurulum: yeni bir tuz uretir, [password]'dan bir anahtar
        turetir ve bos bir not listesini sifreleyip kaydeder. Dondurulen
        anahtar, oturum boyunca save() cagrilarinda sifreyi tekrar
        girmeden kullanilabilir."""
        salt = os.urandom(16)
        key = self._derive_key(password, salt)
        self._write_notes(salt, key, [])
        return key

    def unlock(self, password):
        """[password] dogruysa (anahtar, salt) cifti ile notlari
        dondurur; yanlissa WrongPasswordError firlatir. Defter henuz
        kurulmadiysa (bkz. is_set_up()) FileNotFoundError firlatir."""
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        salt = base64.b64decode(data["salt"])
        key = self._derive_key(password, salt)
        nonce_and_ciphertext = base64.b64decode(data["blob"])
        nonce, ciphertext = nonce_and_ciphertext[:12], nonce_and_ciphertext[12:]
        try:
            plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
        except InvalidTag:
            raise WrongPasswordError() from None
        notes = json.loads(plaintext.decode("utf-8"))
        return key, notes

    def save(self, key, notes):
        """[notes]'u onceden turetilmis [key] ile yeniden sifreleyip
        kaydeder - her cagrida YENI bir rastgele nonce kullanilir
        (AES-GCM'de ayni anahtarla nonce tekrari kritik bir guvenlik
        zafiyetidir)."""
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        salt = base64.b64decode(data["salt"])
        self._write_notes(salt, key, notes)

    def _write_notes(self, salt, key, notes):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = os.urandom(12)
        plaintext = json.dumps(notes, ensure_ascii=False).encode("utf-8")
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
        data = {
            "salt": base64.b64encode(salt).decode("ascii"),
            "blob": base64.b64encode(nonce + ciphertext).decode("ascii"),
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def reset(self):
        """Not defterini ve tum notlari kalici olarak siler. Sifre
        unutulduysa tek secenek budur: anahtar yalnizca sifreden
        turetilir ve hicbir yerde saklanmaz, bu yuzden "sifremi
        unuttum" akisi kriptografik olarak imkansizdir."""
        try:
            os.remove(self.path)
        except OSError:
            pass


def format_notifications(entries):
    """[entries] listesini (en yeni en ustte) okunabilir duz metne
    cevirir - Bildirim Gecmisi penceresinde gosterilir."""
    lines = []
    for entry in reversed(entries):
        lines.append(f"[{entry.get('time', '')}] {entry.get('title', '')}")
        lines.append(entry.get("message", ""))
        lines.append("")
    return "\n".join(lines)


def compute_usage_stats(
    history_entries, notifications, automation_rules, custom_commands,
    recent_connections, now,
):
    """Uygulamanin cihazdaki mevcut verilerinden (sohbet gecmisi,
    bildirimler, otomasyon kurallari, ozel komutlar, son baglanan
    cihazlar) bir "Kullanım İstatistikleri" anlik goruntusu hesaplar -
    hicbir yeni veri saklamaz, her cagrildiginda yeniden hesaplar
    (mobil suruumundeki UsageStatsService.compute() ile ayni fikirde).
    [history_entries]'teki "time" alani ChatHistoryManager.add()'in
    urettigi "%Y-%m-%d %H:%M" bicimindedir; ayristirilamayan (bozuk)
    kayitlar sessizce atlanir."""
    week_ago = now - timedelta(days=7)
    questions_today = 0
    questions_this_week = 0
    error_count = 0
    favorite_count = 0
    first_question_at = None
    for entry in history_entries:
        try:
            entry_time = datetime.strptime(entry.get("time", ""), "%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            continue
        if entry_time.date() == now.date():
            questions_today += 1
        if entry_time >= week_ago:
            questions_this_week += 1
        if entry.get("is_error"):
            error_count += 1
        if entry.get("favorite"):
            favorite_count += 1
        if first_question_at is None or entry_time < first_question_at:
            first_question_at = entry_time

    return {
        "total_questions": len(history_entries),
        "questions_today": questions_today,
        "questions_this_week": questions_this_week,
        "error_count": error_count,
        "favorite_count": favorite_count,
        "notification_count": len(notifications),
        "automation_rule_count": len(automation_rules),
        "custom_command_count": len(custom_commands),
        "connected_device_count": len(recent_connections),
        "first_question_at": first_question_at,
    }


def format_usage_stats(stats):
    """[compute_usage_stats]'in sonucunu okunabilir duz metne cevirir -
    Kullanım İstatistikleri penceresinde gosterilir."""
    first_question = (
        stats["first_question_at"].strftime("%Y-%m-%d")
        if stats["first_question_at"]
        else "-"
    )
    lines = [
        f"Toplam soru: {stats['total_questions']}",
        f"Bugün sorulan: {stats['questions_today']}",
        f"Bu hafta sorulan: {stats['questions_this_week']}",
        f"Favori kayıt: {stats['favorite_count']}",
        f"Hatalı yanıt: {stats['error_count']}",
        f"Bildirim: {stats['notification_count']}",
        f"Otomasyon kuralı: {stats['automation_rule_count']}",
        f"Özel komut: {stats['custom_command_count']}",
        f"Bağlanan cihaz: {stats['connected_device_count']}",
        f"İlk soru tarihi: {first_question}",
    ]
    return "\n".join(lines)


def merge_history_entries(existing_entries, new_entries):
    """[new_entries] icindeki (telefondan gelen) kayitlari [existing_entries]
    listesine yerinde (in-place) ekler; (time, question, answer) ucluesu
    zaten varsa atlar. Alan uzunluklari HISTORY_ENTRY_MAX_FIELD_LENGTH ile
    sinirlanir. time ya da question bossa kayit atlanir. Eklenen kayit
    sayisini dondurur."""
    existing_keys = {
        (e.get("time"), e.get("question"), e.get("answer")) for e in existing_entries
    }
    added = 0
    for entry in new_entries:
        if not isinstance(entry, dict):
            continue
        entry_time = str(entry.get("time", ""))[:64]
        question = str(entry.get("question", ""))[:HISTORY_ENTRY_MAX_FIELD_LENGTH]
        answer = str(entry.get("answer", ""))[:HISTORY_ENTRY_MAX_FIELD_LENGTH]
        if not entry_time or not question:
            continue
        key = (entry_time, question, answer)
        if key in existing_keys:
            continue
        existing_keys.add(key)
        existing_entries.append(
            {
                "time": entry_time,
                "question": question,
                "answer": answer,
                "is_error": bool(entry.get("is_error", False)),
            }
        )
        added += 1
    return added


def select_context_turns(entries, enabled, max_turns=CONTEXT_HISTORY_TURNS):
    """"Baglam farkindaligi" icin GeminiWorker'a gonderilecek onceki
    soru-cevaplari secer: [enabled] False ise (kullanici kapatmis) hic
    baglam gonderilmez; aksi halde hatali olmayan (is_error=False) son
    [max_turns] kayit, {"question", "answer"} sozlukleri olarak, en
    eskiden en yeniye siralanmis dondurulur."""
    if not enabled:
        return []
    successful = [e for e in entries if not e.get("is_error")]
    recent = successful[-max_turns:] if max_turns > 0 else []
    return [{"question": e["question"], "answer": e["answer"]} for e in recent]


def format_relative_time(occurred_at, now):
    """[occurred_at], record_connection'in urettigi "last_seen" gibi
    "YYYY-MM-DD HH:MM" bicimindeki bir zaman dizesi; [now] bir datetime.
    Insan-okunur goreli sure dondurur ("az once", "5 dakika once", "3
    saat once", "2 gun once") - "Bağlantılar İçin Son Kullanım
    Göstergesi" bunu mutlak zaman damgasinin yanina ekler. Ayristirilamayan
    bir deger oldugu gibi geri dondurulur."""
    try:
        dt = datetime.strptime(occurred_at, "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return str(occurred_at)
    delta_seconds = (now - dt).total_seconds()
    if delta_seconds < 60:
        return "az once"
    minutes = int(delta_seconds // 60)
    if minutes < 60:
        return f"{minutes} dakika once"
    hours = int(minutes // 60)
    if hours < 24:
        return f"{hours} saat once"
    days = int(hours // 24)
    return f"{days} gun once"


def format_recent_connections(connections, now):
    """[connections] (RemoteCommandServer.recent_connections - IP -> bkz.
    record_connection) icin okunabilir bir ozet uretir - "Uzaktan Kumanda"
    penceresinde gosterilir. Her satirda mutlak zaman damgasinin yaninda
    format_relative_time ile goreli bir "son kullanim" gostergesi de yer
    alir (orn. "5 dakika once")."""
    if not connections:
        return "Son baglanan cihaz yok."
    rows = sorted(connections.items(), key=lambda kv: kv[1]["last_seen_epoch"], reverse=True)
    lines = ["Son baglanan cihazlar:"]
    for conn_ip, conn in rows[:10]:
        relative = format_relative_time(conn.get("last_seen", ""), now)
        lines.append(
            f"  {conn_ip} - son gorulme {conn['last_seen']} ({relative}) "
            f"({conn['last_endpoint']}, {conn['count']} istek)"
        )
    return "\n".join(lines)


def record_connection(recent_connections, client_ip, endpoint, now_epoch, max_connections):
    """[recent_connections] (IP -> {"count", "last_seen_epoch", "last_seen",
    "last_endpoint"}) sozlugunu [client_ip]'den basariyla dogrulanmis bir
    istek icin yerinde gunceller. Sozluk [max_connections] farkli IP'yi
    asarsa, guncellenen IP zaten iclerinde degilse en eski gorulen IP
    cikarilir (basit bir LRU). RemoteCommandServer.run() ve testler
    tarafindan paylasilir."""
    if client_ip not in recent_connections and len(recent_connections) >= max_connections:
        oldest_ip = min(recent_connections, key=lambda ip: recent_connections[ip]["last_seen_epoch"])
        recent_connections.pop(oldest_ip, None)
    conn = recent_connections.setdefault(client_ip, {"count": 0})
    conn["count"] += 1
    conn["last_seen_epoch"] = now_epoch
    conn["last_seen"] = datetime.fromtimestamp(now_epoch).strftime("%Y-%m-%d %H:%M")
    conn["last_endpoint"] = endpoint


def auto_backup_dir():
    return os.path.join(base_dir(), "backups")


def should_run_auto_backup(last_backup_str, now, interval_days=AUTO_BACKUP_INTERVAL_DAYS):
    """[last_backup_str] config'te saklanan en son otomatik yedek zamaninin
    ISO 8601 dizesi - bos/gecersizse (hic yedek alinmamis ya da bozuk
    kayit) hemen True doner. [now] bir datetime. Son yedekten bu yana
    [interval_days] gun ya da daha fazla gecmisse True doner."""
    if not last_backup_str:
        return True
    try:
        last = datetime.fromisoformat(last_backup_str)
    except (ValueError, TypeError):
        return True
    return (now - last) >= timedelta(days=interval_days)


def parse_hh_mm(text):
    """[text]'i "SS:DD" saat bicimine ayristirir (orn. "9:5" de kabul
    edilir, "09:05"e normallestirilir). Gecersizse (iki parca degilse,
    sayi degilse ya da araliğin disindaysa) None doner."""
    parts = str(text).strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


def resolve_auto_theme_mode(now, day_start="07:00", night_start="19:00"):
    """[now] (bir datetime) icin "light" mi "dark" mi kullanilmasi
    gerektigini dondurur - [day_start]'ta gunduz temasina, [night_start]'ta
    gece temasina gecilir. Ikisi de "SS:DD" bicimindedir (parse_hh_mm ile
    dogrulanir, gecersizse varsayilana duser). "HH:MM" bicimindeki
    dizeler sozluksel olarak da saat sirasina gore karsilastirilabildigi
    icin datetime nesnesine cevirmeye gerek yok."""
    day_start = parse_hh_mm(day_start) or "07:00"
    night_start = parse_hh_mm(night_start) or "19:00"
    current = now.strftime("%H:%M")
    if day_start <= night_start:
        return "light" if day_start <= current < night_start else "dark"
    # gunduz araligi gece yarisini gecer (orn. gunduz baslangici gece
    # baslangicindan sonra) - nadiren kullanilir ama tutarli olmali.
    return "light" if current >= day_start or current < night_start else "dark"


def should_fire_rule(rule, now, idle_seconds):
    """[rule] bir otomasyon kuralidir (bkz. AUTOMATION_TRIGGER_LABELS/
    AUTOMATION_ACTION_LABELS anahtarlari). [now] bir datetime,
    [idle_seconds] kullanicinin ne kadar suredir hareketsiz oldugu
    (saniye). Kural devre disiyse (enabled False) her zaman False doner.

    "time_daily": saat [trigger_value]'ya ("SS:DD") ulasildiginda VE bugun
    henuz ateslenmediyse True doner - boylece dakikada bir kontrol edilse
    de gunde sadece bir kez ateslenir.

    "idle_minutes": [idle_seconds], [trigger_value] dakikayi astiginda VE
    en son ateslemeden bu yana en az o kadar zaman gectiyse True doner -
    boylece surekli hareketsizlikte her kontrolde yeniden ateslenmez."""
    if not rule.get("enabled", True):
        return False
    trigger_type = rule.get("trigger_type")
    last_fired = rule.get("last_fired")
    last_fired_dt = None
    if last_fired:
        try:
            last_fired_dt = datetime.fromisoformat(last_fired)
        except (ValueError, TypeError):
            last_fired_dt = None

    if trigger_type == "time_daily":
        if now.strftime("%H:%M") != str(rule.get("trigger_value", "")):
            return False
        return last_fired_dt is None or last_fired_dt.date() != now.date()

    if trigger_type == "idle_minutes":
        try:
            threshold_minutes = float(rule.get("trigger_value", 0))
        except (TypeError, ValueError):
            return False
        if threshold_minutes <= 0 or idle_seconds < threshold_minutes * 60:
            return False
        return last_fired_dt is None or (now - last_fired_dt) >= timedelta(
            minutes=threshold_minutes
        )

    return False


def describe_automation_rule(rule):
    """[rule]'u tek satirlik okunabilir bir ozete cevirir - orn.
    '"Ise gec kalma" - Her gun belirli bir saatte (18:00) -> Bildirim
    goster [devre disi]'."""
    trigger_type = rule.get("trigger_type")
    trigger_label = AUTOMATION_TRIGGER_LABELS.get(trigger_type, trigger_type or "?")
    trigger_value = rule.get("trigger_value", "")
    if trigger_type == "idle_minutes":
        trigger_desc = f"{trigger_label} ({trigger_value} dk)"
    else:
        trigger_desc = f"{trigger_label} ({trigger_value})"
    action_label = AUTOMATION_ACTION_LABELS.get(
        rule.get("action_type"), rule.get("action_type") or "?"
    )
    action_value = rule.get("action_value")
    action_desc = f"{action_label}: {action_value}" if action_value else action_label
    suffix = "" if rule.get("enabled", True) else " [devre disi]"
    return f'"{rule.get("name", "")}" - {trigger_desc} -> {action_desc}{suffix}'


def format_automation_rules(rules):
    """[rules] listesini, her satiri numaralanmis okunabilir duz metne
    cevirir - Otomasyon Kurallari penceresinde gosterilir."""
    lines = []
    for i, rule in enumerate(rules, start=1):
        lines.append(f"{i}. {describe_automation_rule(rule)}")
    return "\n".join(lines)


def build_settings_profile(config_data):
    """[config_data] (ConfigManager.data) icinden yalnizca PROFILE_EXPORT_
    KEYS'teki (gizli/makineye ozgu olmayan) anahtarlari alan bir dict
    dondurur - "Ayarlari Disa Aktar" bunu oldugu gibi JSON'a yazar."""
    return {key: config_data[key] for key in PROFILE_EXPORT_KEYS if key in config_data}


def apply_settings_profile(config, profile_data):
    """[profile_data] (build_settings_profile ile uretilmis ya da elle
    yazilmis bir dict) icindeki PROFILE_EXPORT_KEYS anahtarlarini
    [config]'e (bir ConfigManager) yazar, geri kalanini yok sayar - boylece
    baska bir surumden ya da elle duzenlenmis, bilinmeyen ekstra anahtar
    iceren bir dosya bile guvenle ice aktarilabilir. Uygulanan anahtarlarin
    listesini dondurur."""
    applied = []
    if not isinstance(profile_data, dict):
        return applied
    for key in PROFILE_EXPORT_KEYS:
        if key in profile_data:
            config.set(key, profile_data[key])
            applied.append(key)
    return applied


def prune_old_backups(directory, keep_count):
    """[directory] icinde AUTO_BACKUP_PREFIX ile baslayan dosyalari isme
    gore (bu da zaman damgasi anlamina gelir) sıralayip en yeni
    [keep_count] tanesini tutar, gerisini siler. [directory] yoksa
    sessizce hicbir sey yapmaz."""
    if not os.path.isdir(directory):
        return
    files = sorted(
        f
        for f in os.listdir(directory)
        if f.startswith(AUTO_BACKUP_PREFIX) and f.endswith(".json")
    )
    stale = files[:-keep_count] if keep_count > 0 else files
    for old_file in stale:
        try:
            os.remove(os.path.join(directory, old_file))
        except OSError:
            pass


def format_access_log_line(timestamp_str, client_ip, event, detail=""):
    """Erisim gunlugune eklenecek tek satirlik, sekme-ayrimli bir kayit
    uretir. [event] orn. "istek" ya da "gecersiz-pin"; [detail] orn.
    istenen uc nokta - verilmezse atlanir."""
    line = f"{timestamp_str}\t{client_ip}\t{event}"
    if detail:
        line += f"\t{detail}"
    return line


def append_access_log(path, line, max_bytes=ACCESS_LOG_MAX_BYTES):
    """[line]'i [path]'in sonuna yeni bir satir olarak ekler. Dosya
    [max_bytes]'i asarsa, en eski yarisi atilarak basit bir boyut-tabanli
    donme (rotasyon) yapilir. G/C hatalarinda sessizce vazgecer - erisim
    gunlugu asla ana islevi (uzaktan kumandayi) bozmamalidir."""
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        if os.path.getsize(path) > max_bytes:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines[len(lines) // 2 :])
    except OSError:
        pass


def tail_access_log(path, max_lines=ACCESS_LOG_DISPLAY_LINES):
    """[path]'teki son [max_lines] satiri (en yeni en altta) dondurur.
    Dosya yoksa ya da okunamazsa bos liste doner."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return []
    return [line.rstrip("\n") for line in lines[-max_lines:]]


def format_history_entries(entries):
    """[entries] listesini (en yeni en ustte) okunabilir duz metne cevirir -
    hem ChatHistoryDialog'un ekran gorunumu hem de disa aktarma (.txt)
    ayni bicimi kullanir."""
    lines = []
    for entry in reversed(entries):
        marker = "⚠" if entry.get("is_error") else "\U0001F431"
        lines.append(f"[{entry.get('time', '')}]")
        lines.append(f"Sen: {entry.get('question', '')}")
        lines.append(f"{marker} {entry.get('answer', '')}")
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Gorsel yukleme (assets eksikse basit bir yer tutucu cizilir)
# --------------------------------------------------------------------------

def discover_skins():
    """
    assets/ altindaki her alt klasoru ayri bir "skin" olarak sunar
    (fuff_norm.png vb. dosyalari icermesi beklenir). Kok dizindeki
    gorseller her zaman "Varsayilan" adiyla erisilebilir kalir, boylece
    yeni skin klasorleri eklemek mevcut kurulumu bozmaz.
    """
    skins = {"Varsayilan": ASSETS_DIR}
    if os.path.isdir(ASSETS_DIR):
        for name in sorted(os.listdir(ASSETS_DIR)):
            full_path = os.path.join(ASSETS_DIR, name)
            if os.path.isdir(full_path):
                skins[name] = full_path
    return skins


def make_placeholder_pixmap(size=96, color=QColor(90, 170, 255), label=""):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QBrush(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(4, 4, size - 8, size - 8)
    painter.setPen(QPen(QColor(255, 255, 255)))
    font = QFont()
    font.setPointSize(10)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, label)
    painter.end()
    return pixmap


def load_pixmap(skin_dir, filename, placeholder_label=""):
    path = os.path.join(skin_dir, filename)
    if os.path.exists(path):
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            return pixmap
    return make_placeholder_pixmap(label=placeholder_label)


def build_pairing_qr_pixmap(ip, port, pin, fingerprint, box_size=6):
    """[build_pairing_uri]'i kodlayan bir QR kodu QPixmap olarak uretir.
    "qrcode" kutuphanesi kurulu degilse ya da beklenmedik bir hata
    olursa None doner - QR tamamen opsiyoneldir, metin bilgisi
    (IP/Port/PIN) zaten yeterlidir, bu yuzden eksikligi uygulamanin
    calismasini engellememeli."""
    try:
        import qrcode
    except ImportError:
        return None
    try:
        import io

        img = qrcode.make(
            build_pairing_uri(ip, port, pin, fingerprint), box_size=box_size, border=2
        )
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(buffer.getvalue(), "PNG")
        return pixmap if not pixmap.isNull() else None
    except Exception:
        return None


# --------------------------------------------------------------------------
# Uzaktan kumanda (telefon uygulamasindan yerel ag uzerinden komut)
# --------------------------------------------------------------------------

def get_local_ip():
    """Telefonun bu bilgisayara baglanacagi yerel ag IP'si (internete
    paket gondermeden, sadece isletim sistemine hangi arayuzun
    kullanilacagini sordurarak bulunur)."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return "127.0.0.1"


PAIRING_URI_SCHEME = "aikedi"


def build_pairing_uri(ip, port, pin, fingerprint):
    """Uzaktan kumanda bilgi penceresindeki QR koda gomulecek URI'yi
    olusturur - mobil uygulama bunu (kamerayla) tarayip IP/Port/PIN/
    sertifika parmak izi alanlarini elle yazmadan doldurur. urlencode
    kullanilir cunku parmak izi iki nokta ust uste (:) iceriyor ve bu
    URI icinde ozel anlam tasir."""
    query = urlencode({"ip": ip, "port": port, "pin": pin, "fp": fingerprint})
    return f"{PAIRING_URI_SCHEME}://pair?{query}"


REMOTE_CERT_PATH = os.path.join(base_dir(), "remote_cert.pem")
REMOTE_KEY_PATH = os.path.join(base_dir(), "remote_key.pem")


def _generate_self_signed_cert():
    import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AI Kedi Asistani Uzaktan Kumanda")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .sign(key, hashes.SHA256())
    )

    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    with open(REMOTE_KEY_PATH, "wb") as f:
        f.write(key_pem)
    with open(REMOTE_CERT_PATH, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))


def ensure_remote_tls_cert():
    """
    Uzaktan kumanda sunucusu icin kendinden imzali bir TLS sertifikasi/
    anahtari yoksa uretir; boylece PIN ve komutlar ag uzerinde duz metin
    degil sifreli gider (baskasi ayni Wi-Fi'de paketleri dinleyemez).
    Sertifika bir Yetkili Kurum tarafindan imzali olmadigindan telefon
    tarafi "ilk baglantida guven" (TOFU) modeliyle parmak izini sabitler.
    """
    if os.path.exists(REMOTE_CERT_PATH) and os.path.exists(REMOTE_KEY_PATH):
        return True
    try:
        _generate_self_signed_cert()
        return True
    except Exception:
        return False


def get_cert_fingerprint():
    """Sertifikanin SHA-256 parmak izini 'AA:BB:...' biciminde dondurur."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes

        with open(REMOTE_CERT_PATH, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
        digest = cert.fingerprint(hashes.SHA256()).hex()
        return ":".join(digest[i : i + 2] for i in range(0, len(digest), 2)).upper()
    except Exception:
        return None


def is_url_safe_to_open(url):
    """
    PIN sizarsa bile telefon uzerinden bilgisayarin yerel agindaki
    router/IoT/localhost panellerine yonlendirme (SSRF benzeri kotuye
    kullanim) yapilamamasi icin: yalnizca genel (ozel olmayan) IP'lere
    cozumlenen http(s) adreslerine izin verilir.

    Not: Bu, hedef host adini simdi cozup kontrol eder; gelismis bir
    saldirgan DNS rebinding ile bu kontrolden sonra farkli bir IP'ye
    yonlendirebilir - webbrowser.open() tarayiciya devrettigi icin bu
    katmanda tam engellenemez. Buradaki amac, PIN'i ele geciren birinin
    dogrudan "http://192.168.1.1/..." gibi bariz yerel adresler
    yazmasini engellemektir.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    hostname = parsed.hostname
    if not hostname or hostname.lower() == "localhost":
        return False
    try:
        infos = socket.getaddrinfo(hostname, None)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        raw_addr = info[4][0].split("%")[0]
        try:
            ip_obj = ipaddress.ip_address(raw_addr)
        except ValueError:
            return False
        if (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_reserved
            or ip_obj.is_multicast
            or ip_obj.is_unspecified
        ):
            return False
    return True


def validate_custom_command(name, url):
    """"Özel Komutlar" menusune eklenmeden once [name]/[url] ciftini
    dogrular (bkz. CatCharacter._add_custom_command). Sorun yoksa None,
    varsa kullaniciya aynen gosterilecek bir hata metni dondurur. Ayni
    is_url_safe_to_open() kontrolu otomasyon kurallarindaki open_url
    adiminda da kullanilir - buradaki gerekce de aynidir (PIN sizmasa
    bile yerel ag adreslerine yonlendirme yapilamamasi)."""
    if not name.strip():
        return "Bir isim yaz."
    if not url.strip():
        return "Bir bağlantı yaz."
    if not is_url_safe_to_open(url.strip()):
        return "Bu bağlantı açılamaz (yalnızca genel http(s) adreslerine izin verilir)."
    return None


MEDIA_KEY_NAMES = {
    "play_pause": "play/pause media",
    "next": "next track",
    "prev": "previous track",
    "vol_up": "volume up",
    "vol_down": "volume down",
    "mute": "volume mute",
}

POWER_ACTIONS = ("sleep", "lock")

CLIPBOARD_ACTIONS = ("push", "pull")
CLIPBOARD_MAX_LENGTH = 100_000

# Telefondan /history/import ile tek seferde ice aktarilabilecek en fazla
# kayit sayisi ve soru/cevap basina en fazla karakter (PIN'i ele geciren
# birinin sohbet gecmisini sisirmesini/asiri bellek kullanimini
# engellemek icin).
HISTORY_IMPORT_MAX_ENTRIES = 500
HISTORY_ENTRY_MAX_FIELD_LENGTH = 20_000


def get_clipboard_text():
    try:
        return QApplication.clipboard().text()
    except Exception:
        return ""


def set_clipboard_text(text):
    try:
        QApplication.clipboard().setText(text)
        return True
    except Exception:
        return False


def handle_media_action(action):
    """Windows'ta medya tuslarini simule eder (keyboard kutuphanesi
    araciligiyla - global kisayol icin de kullanilan ayni kutuphane)."""
    if sys.platform != "win32":
        return False
    key = MEDIA_KEY_NAMES.get(action)
    if key is None:
        return False
    try:
        import keyboard

        keyboard.send(key)
        return True
    except Exception:
        return False


def handle_power_action(action):
    """Windows'ta bilgisayari kilitler ya da uyku moduna alir."""
    if sys.platform != "win32" or action not in POWER_ACTIONS:
        return False
    try:
        import ctypes

        if action == "lock":
            ctypes.windll.user32.LockWorkStation()
            return True
        # action == "sleep": hibernate degil normal uyku, zorla, uyanma
        # olaylarini devre disi birakma.
        ctypes.windll.powrprof.SetSuspendState(False, True, False)
        return True
    except Exception:
        return False


def capture_screenshot_jpeg_base64(max_width=1280, quality=70):
    """Ekran goruntusunu alip kucultup JPEG olarak base64 dondurur -
    telefona makul boyutta bir onizleme gondermek icin."""
    import base64
    import io

    import mss
    from PIL import Image

    with mss.mss() as sct:
        monitor = sct.monitors[0]
        shot = sct.grab(monitor)
    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, max(1, int(img.height * ratio))))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=quality)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def live_coords_to_pixels(norm_x, norm_y, screen_width, screen_height):
    """"Canli Kontrol" sekmesinden gelen (0..1 arasi normallestirilmis)
    x/y konumunu gercek ekran piksel konumuna cevirir - telefon tarafinin
    bilgisayarin tam cozunurlugunu onceden bilmesine gerek kalmaz,
    gosterdigi goruntudeki orani (dokunulan noktanin goruntu genisligine/
    yuksekligine orani) yeterlidir. Sinirlarin disina tasan degerler
    ekrana kirpilir (orn. goruntunun kenarindaki bir surukleme)."""
    x = min(max(norm_x, 0.0), 1.0) * screen_width
    y = min(max(norm_y, 0.0), 1.0) * screen_height
    return int(x), int(y)


def normalize_live_key_name(name):
    """Telefondan gelen tus adini normallestirir: bos/None ise None,
    bilinen bir ozel tus adiysa (REMOTE_LIVE_SPECIAL_KEY_NAMES, kucuk
    harfe cevrilmis) kendisi, tek karakterli bir harf/rakam/sembolse
    oldugu gibi, diger (taninmayan, coklu karakterli) adlar icin None
    doner (yoksayilir - yanlislikla rastgele bir komutun bir tusa
    esitlenmesini onlemek icin). pynput'a KASITLI olarak bagimli degildir
    (yalnizca dize/kume islemleri) - boylece testte pynput kurulu
    olmasa/calisamasa bile (orn. ekransiz CI) test edilebilir; gercek
    pynput Key/KeyCode nesnesine cevirme, pynput'un zaten import edildigi
    cagiran yerde (RemoteLiveControlServer) yapilir."""
    if not name:
        return None
    lowered = name.lower()
    if lowered in REMOTE_LIVE_SPECIAL_KEY_NAMES:
        return lowered
    if len(name) == 1:
        return name
    return None


def normalize_live_mouse_button(name):
    """Telefondan gelen fare tusu adini dogrular - bilinmeyen/bos bir
    deger icin (dokunmatik ekranda "sol tik" en dogal varsayilan
    oldugundan) sessizce "left"e duser."""
    lowered = str(name or "").lower()
    return lowered if lowered in REMOTE_LIVE_MOUSE_BUTTONS else "left"


REMOTE_FILE_TELEPORT_DIR_NAME = "AI Kedi Asistani - Telefondan Gelenler"
REMOTE_FILE_TELEPORT_MAX_BYTES = 25 * 1024 * 1024  # 25 MB


def received_files_dir():
    """Telefondan "Dosya Teleport" ile gonderilen dosyalarin kaydedildigi
    sabit klasor - her seferinde nereye kaydedilecegi sorulmaz/secilmez,
    hep ayni yer kullanilir. Kullanicinin ev dizininde, yoksa olusturulur."""
    directory = os.path.join(os.path.expanduser("~"), REMOTE_FILE_TELEPORT_DIR_NAME)
    os.makedirs(directory, exist_ok=True)
    return directory


def sanitize_teleport_filename(name):
    """Telefondan gelen dosya adini guvenli hale getirir: yol bilesenlerini
    (orn. "../gizli/dosya" ya da "C:\\Windows\\..") atar - boylece kotu
    niyetli/bozuk bir istemci hedef klasorun disina yazamaz. Sonuc bossa
    (orn. sadece "." ya da ".." gonderilmisse) "dosya" varsayilan adi
    kullanilir."""
    base = os.path.basename(str(name or "").strip().replace("\\", "/"))
    base = base.strip().lstrip(".")
    return base or "dosya"


def unique_teleport_destination(directory, filename):
    """Ayni adli bir dosya zaten varsa uzerine yazmak yerine " (2)", " (3)"
    gibi bir sayac ekleyerek benzersiz bir hedef yol uretir - boylece
    telefondan arka arkaya gonderilen ayni isimli dosyalar birbirinin
    uzerine yazilmaz."""
    root, ext = os.path.splitext(filename)
    candidate = os.path.join(directory, filename)
    counter = 2
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f"{root} ({counter}){ext}")
        counter += 1
    return candidate


# --------------------------------------------------------------------------
# "Kediyle Gönder": Windows Gezgini sag tik menusunden dogrudan telefona
# dosya gonderme
# --------------------------------------------------------------------------

SEND_WITH_CAT_ARG = "--send-file"
# Yalnizca 127.0.0.1'den erisilebilir (disaridan ULASILAMAZ) - sag tikla
# baslatilan IKINCI bir surecin, zaten calisan ASIL surece dosya yolunu
# iletmesi icindir; PIN/TLS gerekmez cunku zaten ayni makinede olmayan
# hicbir surec bu porta baglanamaz.
SEND_WITH_CAT_IPC_PORT = REMOTE_SERVER_PORT + 2
SEND_WITH_CAT_MENU_KEY = r"Software\Classes\*\shell\AIKediAsistaniGonder"
SEND_WITH_CAT_MENU_LABEL = "Kediyle Gönder"
SEND_WITH_CAT_MAX_PENDING = 5


def parse_send_file_arg(argv):
    """argv icinde '--send-file <yol>' varsa yolu, yoksa None doner -
    Windows Gezgini sag tik menusunden "%1" (tiklanan dosyanin tam yolu)
    ile baslatildiginda kullanilir."""
    for i, arg in enumerate(argv):
        if arg == SEND_WITH_CAT_ARG and i + 1 < len(argv):
            return argv[i + 1]
    return None


def send_with_cat_command_line(exe_path):
    """Kayit defterine yazilacak komut satirini uretir - Windows Gezgini
    "%1" yerine sag tiklanan dosyanin tam yolunu koyar."""
    return f'"{exe_path}" {SEND_WITH_CAT_ARG} "%1"'


def register_send_with_cat_context_menu():
    """Windows Gezgini'nde herhangi bir dosyaya sag tiklaninca "Kediyle
    Gönder" secenegini ekler - HKEY_CURRENT_USER altina yazdigi icin ADMIN
    GEREKTIRMEZ. Idempotent: her baslangicta calisir, otomatik guncelleme
    sonrasi exe'nin yeri degismis olsa bile komut satirini gunceller.
    Yalnizca paketlenmis (frozen) .exe icin calisir - `python main.py` ile
    gelistirme ortaminda calistirmanin dogru bir komut satiri uretmesi
    mumkun olmadigi icin sessizce atlanir."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    try:
        import winreg

        command = send_with_cat_command_line(sys.executable)
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, SEND_WITH_CAT_MENU_KEY)
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, SEND_WITH_CAT_MENU_LABEL)
        winreg.CloseKey(key)
        cmd_key = winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, SEND_WITH_CAT_MENU_KEY + r"\command"
        )
        winreg.SetValueEx(cmd_key, "", 0, winreg.REG_SZ, command)
        winreg.CloseKey(cmd_key)
    except OSError:
        pass  # kayit defterine yazilamadi - sessizce vazgec, uygulama normal calisir


def send_file_to_running_instance(file_path):
    """Zaten calisan bir kopya varsa (IPC portu dolu/dinleniyor), dosya
    yolunu ona iletir ve True doner - cagiran taraf (main()) bu durumda
    yeni bir GUI baslatmadan hemen cikmalidir. Baglanti kurulamazsa (henuz
    calisan bir kopya yok) False doner - cagiran taraf bu surecin kendisi
    "asil" kopya olacak sekilde devam eder."""
    try:
        with socket.create_connection(
            ("127.0.0.1", SEND_WITH_CAT_IPC_PORT), timeout=2
        ) as sock:
            sock.sendall(file_path.encode("utf-8") + b"\n")
        return True
    except OSError:
        return False


class SendWithCatIpcServer(QThread):
    """"Kediyle Gönder" sag tik menusunden ikinci bir surecin gonderdigi
    dosya yollarini dinler (bkz. send_file_to_running_instance). Sadece
    127.0.0.1'e baglanir - agdan ERISILEMEZ, bu yuzden PIN/TLS gerekmez."""

    file_path_received = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._server = None

    def run(self):
        signal = self.file_path_received

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                try:
                    line = self.rfile.readline(4096).decode("utf-8", errors="ignore").strip()
                except (OSError, UnicodeDecodeError):
                    return
                if line:
                    signal.emit(line)

        try:
            self._server = socketserver.ThreadingTCPServer(
                ("127.0.0.1", SEND_WITH_CAT_IPC_PORT), Handler
            )
        except OSError:
            return  # port zaten kullanimda - baska bir asil kopya calisiyor olmali
        self._server.daemon_threads = True
        try:
            self._server.serve_forever()
        except OSError:
            pass

    def stop(self):
        if self._server is not None:
            self._server.shutdown()


class RemoteCommandServer(QThread):
    """
    Telefon uygulamasindan gelen komutlari alan basit bir yerel HTTP
    sunucusu. Sadece ayni Wi-Fi agindan erisim beklenir; PIN eslesmezse
    istek reddedilir. Uc noktalar:
      POST /open       {"pin", "url"}    - taraycida bir baglanti acar
      POST /media      {"pin", "action"} - medya tuslarini simule eder
      POST /power      {"pin", "action"} - kilitler / uyku moduna alir
      POST /screenshot {"pin"}           - kucultulmus bir ekran goruntusu dondurur
      POST /history    {"pin"}               - sohbet gecmisini dondurur (telefona ice aktarmak icin)
      POST /history/import {"pin", "entries"} - telefondaki yeni kayitlari sohbet gecmisine ekler (iki yonlu senkron)
      POST /alerts     {"pin", "since_id"}   - since_id'den sonraki hata/uyari bildirimlerini dondurur
      POST /clipboard  {"pin", "action", "text"} - "push": panoyu text'e ayarlar, "pull": panoyu dondurur
      POST /file       {"pin", "filename", "content_base64"} - "Dosya Teleport": dosyayi
        received_files_dir() sabit klasorune kaydeder (ayni adda dosya varsa " (2)" vb.
        ekler, uzerine yazmaz)
      POST /file/pending {"pin"} - "Kediyle Gönder" ile kuyruga alinan (bkz.
        queue_outbound_file) dosyalari dondurur VE kuyruktan siler (her dosya
        yalnizca bir kez teslim edilir)
    Gecerli bir /open, /media ya da /power istegi geldiginde ilgili sinyal
    (ana/GUI thread'ine Qt tarafindan otomatik kuyruklanir) yayinlanir.
    """

    command_received = pyqtSignal(str)
    media_command_received = pyqtSignal(str)
    power_command_received = pyqtSignal(str)
    file_received = pyqtSignal(str)

    MAX_ALERTS = 50

    MAX_RECENT_CONNECTIONS = 20

    def __init__(self, config: ConfigManager, history: ChatHistoryManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.history = history
        self._httpd = None
        # Telefonun yokladigi (poll) hata/uyari kuyrugu - deque kullanilir
        # cunku Handler thread'i bu listeyi (yeniden atama degil, sadece
        # append/otomatik-trim ile) referans olarak paylasir.
        self.alerts = deque(maxlen=self.MAX_ALERTS)
        self._next_alert_id = 1
        # "Kediyle Gönder" ile kuyruga alinan, telefonun bir sonraki
        # /file/pending yoklamasinda alacagi dosyalar - alerts ile ayni
        # capraz-thread paylasim deseni (bkz. queue_outbound_file).
        self.pending_outbound_files = deque(maxlen=SEND_WITH_CAT_MAX_PENDING)
        # IP -> {"last_seen", "last_endpoint", "count"} - PIN'i basariyla
        # dogrulamis en son istemciler (kalici bir "oturum" kavrami yok,
        # her istek kendi basina PIN ile dogrulanir - bu yuzden "aktif
        # oturumlari sonlandirmak" burada PIN'i yenilemek anlamina gelir,
        # bkz. _show_remote_info). Sadece son MAX_RECENT_CONNECTIONS farkli
        # IP tutulur.
        self.recent_connections = {}
        # CatCharacter.__init__ tarafindan start()'tan once atanir; testler
        # (ve teorik olarak baska cagiranlar) icin varsayilan None guvenli -
        # bkz. run()'daki None kontrolu.
        self.screenshot_history = None

    def add_alert(self, message):
        """Ana/GUI thread'inden cagrilir (orn. bir Gemini hatasi olustugunda);
        telefon /alerts ile bir sonraki yoklamasinda bunu gorur."""
        self.alerts.append(
            {
                "id": self._next_alert_id,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "message": str(message),
            }
        )
        self._next_alert_id += 1

    def queue_outbound_file(self, filename, content_b64):
        """Ana/GUI thread'inden (CatCharacter.queue_outbound_file uzerinden,
        "Kediyle Gönder" sag tik menusuyle) cagrilir - telefon bir sonraki
        /file/pending yoklamasinda bu dosyayi alir."""
        self.pending_outbound_files.append(
            {"filename": filename, "content_base64": content_b64}
        )

    def run(self):
        config = self.config
        history = self.history
        alerts = self.alerts
        pending_outbound_files = self.pending_outbound_files
        recent_connections = self.recent_connections
        screenshot_history = self.screenshot_history
        open_signal = self.command_received
        media_signal = self.media_command_received
        power_signal = self.power_command_received
        file_signal = self.file_received
        # IP -> {"count": basarisiz deneme sayisi, "blocked_until": epoch}
        # Kaba kuvvetle PIN denemeyi yavaslatmak icin bellek ici, basit bir
        # kilitlenme mekanizmasi (kalici loglama yapilmiyor).
        failed_attempts = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format_str, *args):
                pass  # konsolu HTTP erisim loglariyla kirletme

            def _send_json(self, status, payload):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                if self.path not in (
                    "/open",
                    "/media",
                    "/power",
                    "/screenshot",
                    "/history",
                    "/history/import",
                    "/automation",
                    "/alerts",
                    "/clipboard",
                    "/file",
                    "/file/pending",
                ):
                    self._send_json(404, {"error": "bulunamadi"})
                    return

                client_ip = self.client_address[0]
                record = failed_attempts.get(client_ip)
                if record and time.time() < record["blocked_until"]:
                    remaining = int(record["blocked_until"] - time.time())
                    self._send_json(
                        429,
                        {"error": f"cok fazla yanlis deneme, {remaining} saniye sonra tekrar deneyin"},
                    )
                    return

                try:
                    length = int(self.headers.get("Content-Length", 0))
                    data = json.loads(self.rfile.read(length))
                except (ValueError, TypeError, json.JSONDecodeError):
                    self._send_json(400, {"error": "gecersiz istek govdesi"})
                    return

                submitted_pin = str(data.get("pin", ""))
                expected_pin = str(config.get("remote_pin"))
                if not hmac.compare_digest(submitted_pin, expected_pin):
                    record = failed_attempts.setdefault(client_ip, {"count": 0, "blocked_until": 0.0})
                    record["count"] += 1
                    if record["count"] >= REMOTE_MAX_FAILED_ATTEMPTS:
                        record["blocked_until"] = time.time() + REMOTE_LOCKOUT_SECONDS
                        record["count"] = 0
                    append_access_log(
                        ACCESS_LOG_PATH,
                        format_access_log_line(
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            client_ip,
                            "gecersiz-pin",
                            self.path,
                        ),
                    )
                    self._send_json(401, {"error": "gecersiz pin"})
                    return

                failed_attempts.pop(client_ip, None)
                record_connection(
                    recent_connections,
                    client_ip,
                    self.path,
                    time.time(),
                    RemoteCommandServer.MAX_RECENT_CONNECTIONS,
                )
                append_access_log(
                    ACCESS_LOG_PATH,
                    format_access_log_line(
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), client_ip, "istek", self.path
                    ),
                )

                if self.path == "/open":
                    url = str(data.get("url", "")).strip()
                    if not is_url_safe_to_open(url):
                        self._send_json(400, {"error": "gecersiz veya guvensiz url"})
                        return
                    open_signal.emit(url)
                    self._send_json(200, {"status": "ok"})
                    return

                if self.path == "/media":
                    action = str(data.get("action", ""))
                    if action not in MEDIA_KEY_NAMES:
                        self._send_json(400, {"error": "gecersiz eylem"})
                        return
                    media_signal.emit(action)
                    self._send_json(200, {"status": "ok"})
                    return

                if self.path == "/power":
                    action = str(data.get("action", ""))
                    if action not in POWER_ACTIONS:
                        self._send_json(400, {"error": "gecersiz eylem"})
                        return
                    power_signal.emit(action)
                    self._send_json(200, {"status": "ok"})
                    return

                if self.path == "/screenshot":
                    try:
                        image_b64 = capture_screenshot_jpeg_base64()
                    except Exception as exc:
                        self._send_json(500, {"error": f"ekran goruntusu alinamadi: {exc}"})
                        return
                    if screenshot_history is not None:
                        screenshot_history.add(f"Telefon ({self.client_address[0]})")
                    self._send_json(200, {"status": "ok", "image_base64": image_b64})
                    return

                if self.path == "/history":
                    self._send_json(200, {"status": "ok", "entries": history.entries})
                    return

                if self.path == "/automation":
                    self._send_json(200, {"status": "ok", "rules": config.get("automation_rules") or []})
                    return

                if self.path == "/history/import":
                    entries = data.get("entries")
                    if not isinstance(entries, list):
                        self._send_json(400, {"error": "gecersiz govde"})
                        return
                    if len(entries) > HISTORY_IMPORT_MAX_ENTRIES:
                        self._send_json(400, {"error": "cok fazla kayit"})
                        return
                    added = merge_history_entries(history.entries, entries)
                    if added:
                        if len(history.entries) > MAX_HISTORY_ENTRIES:
                            history.entries = history.entries[-MAX_HISTORY_ENTRIES:]
                        history.save()
                    self._send_json(200, {"status": "ok", "added": added})
                    return

                if self.path == "/clipboard":
                    action = str(data.get("action", ""))
                    if action not in CLIPBOARD_ACTIONS:
                        self._send_json(400, {"error": "gecersiz eylem"})
                        return
                    if action == "push":
                        text = str(data.get("text", ""))
                        if len(text) > CLIPBOARD_MAX_LENGTH:
                            self._send_json(400, {"error": "metin cok uzun"})
                            return
                        if not set_clipboard_text(text):
                            self._send_json(500, {"error": "panoya yazilamadi"})
                            return
                        self._send_json(200, {"status": "ok"})
                        return
                    # action == "pull"
                    self._send_json(200, {"status": "ok", "text": get_clipboard_text()})
                    return

                if self.path == "/file":
                    filename = sanitize_teleport_filename(data.get("filename"))
                    content_b64 = data.get("content_base64")
                    if not isinstance(content_b64, str) or not content_b64:
                        self._send_json(400, {"error": "dosya icerigi eksik"})
                        return
                    try:
                        content = base64.b64decode(content_b64, validate=True)
                    except (ValueError, TypeError):
                        self._send_json(400, {"error": "dosya icerigi cozulemedi"})
                        return
                    if len(content) > REMOTE_FILE_TELEPORT_MAX_BYTES:
                        self._send_json(400, {"error": "dosya cok buyuk (en fazla 25 MB)"})
                        return
                    try:
                        destination = unique_teleport_destination(received_files_dir(), filename)
                        with open(destination, "wb") as f:
                            f.write(content)
                    except OSError as exc:
                        self._send_json(500, {"error": f"dosya kaydedilemedi: {exc}"})
                        return
                    saved_name = os.path.basename(destination)
                    file_signal.emit(saved_name)
                    self._send_json(200, {"status": "ok", "saved_as": saved_name})
                    return

                if self.path == "/file/pending":
                    files = []
                    while pending_outbound_files:
                        files.append(pending_outbound_files.popleft())
                    self._send_json(200, {"status": "ok", "files": files})
                    return

                # self.path == "/alerts"
                try:
                    since_id = int(data.get("since_id", 0))
                except (TypeError, ValueError):
                    since_id = 0
                new_alerts = [dict(a) for a in alerts if a["id"] > since_id]
                self._send_json(200, {"status": "ok", "alerts": new_alerts})

        if not ensure_remote_tls_cert():
            return  # sertifika olusturulamadi - uzaktan kumanda olmadan devam et

        # "0.0.0.0": yalnizca yerel ag arayuzune degil, TUM aglara
        # (Tailscale gibi sanal arayuzler dahil) baglanti kabul eder -
        # tek bir arayuze (orn. get_local_ip()'in dondurdugu Wi-Fi IP'si)
        # baglanirsak, o arayuzden gelmeyen istekler (orn. Tailscale
        # uzerinden gelen) sessizce reddedilir; PIN + TLS + sertifika
        # dogrulamasi zaten kim baglanirsa baglansin ayni korumayi saglar,
        # bu yuzden tum arayuzlerde dinlemek yeni bir guvenlik riski
        # eklemez.
        try:
            self._httpd = http.server.ThreadingHTTPServer(("0.0.0.0", REMOTE_SERVER_PORT), Handler)
        except OSError:
            return

        try:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(REMOTE_CERT_PATH, REMOTE_KEY_PATH)
            self._httpd.socket = ssl_context.wrap_socket(self._httpd.socket, server_side=True)
        except (ssl.SSLError, OSError):
            self._httpd.server_close()
            self._httpd = None
            return

        self._httpd.daemon_threads = True
        try:
            self._httpd.serve_forever()
        except OSError:
            pass  # sunucu kapatildi vb.

    def stop(self):
        if self._httpd is not None:
            self._httpd.shutdown()


class RemoteLiveControlServer(QThread):
    """
    "Ekranda Gez" balonundaki/uygulamadaki "Canlı Kontrol" sekmesi icin:
    telefona surekli (~12 kare/saniye) JPEG video kareleri gonderen VE
    telefondan gelen fare/klavye olaylarini GERCEK ZAMANLI olarak bu
    bilgisayara uygulayan, REST komut sunucusundan (RemoteCommandServer,
    REMOTE_SERVER_PORT) AYRI, hafif bir TLS soket sunucusu
    (REMOTE_LIVE_PORT). HTTP kullanmaz - ozel, basit bir protokol:

      1) Istemci TLS ile baglanir, ilk satir olarak PIN'i (\\n ile
         bitmis duz metin) gonderir.
      2) PIN dogruysa sunucu "OK\\n" yazar, aksi halde "ERR\\n" yazip
         baglantiyi kapatir (ayni marka/kilitlenme korumasi -
         REMOTE_MAX_FAILED_ATTEMPTS/REMOTE_LOCKOUT_SECONDS - REST
         sunucusuyla aynidir, ama ayri bir failed_attempts sozlugunde
         izlenir).
      3) Baglanti kabul edildikten sonra sunucu SUREKLI video karesi
         yazar: 4 bayt buyuk-endian uzunluk + o kadar JPEG bayti,
         tekrar tekrar (ayri bir yazici thread'inde).
      4) Es zamanli olarak (ayni soket, aksi yonde) istemciden gelen
         satirlari (her biri tek bir JSON komutu, \\n ile ayrilmis) okuyup
         fare/klavye olarak bu bilgisayara uygular (bkz. _apply_command).

    Ayni TLS sertifikasini (REMOTE_CERT_PATH/REMOTE_KEY_PATH) kullanir,
    bu yuzden telefonun REST sunucusu icin zaten kaydettigi parmak izi
    (TOFU) bu port icin de gecerlidir - ayrica bir eslestirme/QR
    gerekmez; telefon tarafi bu portu REMOTE_SERVER_PORT + 1 olarak
    sabit turetir.

    Baglanti kopunca (telefon "Canlı Kontrol" sekmesini kapatinca ya da
    ag koptugunda) o an basili olan TUM klavye tuslari birakilir
    (_release_all_pressed) - aksi halde uzaktaki telefon bir tusu basili
    birakip baglantiyi koparirsa bilgisayarda o tus fiziksel olarak
    "yapisik" kalirdi.
    """

    session_started = pyqtSignal()
    session_ended = pyqtSignal()

    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self._server = None

    def run(self):
        config = self.config
        started_signal = self.session_started
        ended_signal = self.session_ended
        # IP -> {"count", "blocked_until"} - REST sunucusundaki
        # failed_attempts ile ayni fikir, ama bu tamamen ayri bir
        # sunucu/port oldugu icin ayri bir sozluk.
        failed_attempts = {}

        import pynput.keyboard
        import pynput.mouse

        def resolve_key(normalized):
            if normalized in REMOTE_LIVE_SPECIAL_KEY_NAMES:
                return getattr(pynput.keyboard.Key, normalized, None)
            return pynput.keyboard.KeyCode.from_char(normalized)

        def resolve_button(name):
            return {
                "left": pynput.mouse.Button.left,
                "right": pynput.mouse.Button.right,
                "middle": pynput.mouse.Button.middle,
            }[normalize_live_mouse_button(name)]

        class ConnectionHandler(socketserver.StreamRequestHandler):
            # Tek bir yanlis PIN satirindan cok daha fazlasini okumaya
            # kalkip belleği sisirmesin diye - gecerli bir PIN cok daha
            # kisadir.
            def _read_pin_line(self):
                raw = self.rfile.readline(128)
                return raw.decode("utf-8", "replace").strip()

            def handle(self):
                client_ip = self.client_address[0]
                record = failed_attempts.get(client_ip)
                if record and time.time() < record["blocked_until"]:
                    try:
                        self.wfile.write(b"ERR\n")
                    except OSError:
                        pass
                    return

                try:
                    submitted_pin = self._read_pin_line()
                except OSError:
                    return
                expected_pin = str(config.get("remote_pin"))
                if not hmac.compare_digest(submitted_pin, expected_pin):
                    rec = failed_attempts.setdefault(client_ip, {"count": 0, "blocked_until": 0.0})
                    rec["count"] += 1
                    if rec["count"] >= REMOTE_MAX_FAILED_ATTEMPTS:
                        rec["blocked_until"] = time.time() + REMOTE_LOCKOUT_SECONDS
                        rec["count"] = 0
                    try:
                        self.wfile.write(b"ERR\n")
                    except OSError:
                        pass
                    return
                failed_attempts.pop(client_ip, None)

                try:
                    self.wfile.write(b"OK\n")
                    self.wfile.flush()
                except OSError:
                    return

                import io

                import mss
                from PIL import Image

                with mss.mss() as sct:
                    monitor = sct.monitors[0]
                screen_width, screen_height = monitor["width"], monitor["height"]

                stop_flag = threading.Event()
                pressed_keys = set()

                def release_all_pressed():
                    for key in list(pressed_keys):
                        try:
                            keyboard.release(key)
                        except Exception:
                            pass
                    pressed_keys.clear()

                def video_loop():
                    try:
                        with mss.mss() as sct:
                            while not stop_flag.is_set():
                                start = time.monotonic()
                                try:
                                    shot = sct.grab(monitor)
                                    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                                    if img.width > REMOTE_LIVE_MAX_FRAME_WIDTH:
                                        ratio = REMOTE_LIVE_MAX_FRAME_WIDTH / img.width
                                        img = img.resize(
                                            (
                                                REMOTE_LIVE_MAX_FRAME_WIDTH,
                                                max(1, int(img.height * ratio)),
                                            )
                                        )
                                    buffer = io.BytesIO()
                                    img.save(buffer, format="JPEG", quality=REMOTE_LIVE_JPEG_QUALITY)
                                    data = buffer.getvalue()
                                    self.wfile.write(struct.pack(">I", len(data)))
                                    self.wfile.write(data)
                                    self.wfile.flush()
                                except (OSError, BrokenPipeError):
                                    stop_flag.set()
                                    return
                                elapsed = time.monotonic() - start
                                remaining = REMOTE_LIVE_FRAME_INTERVAL_SECONDS - elapsed
                                if remaining > 0:
                                    time.sleep(remaining)
                    finally:
                        stop_flag.set()

                mouse = pynput.mouse.Controller()
                keyboard = pynput.keyboard.Controller()

                video_thread = threading.Thread(target=video_loop, daemon=True)
                video_thread.start()
                started_signal.emit()

                try:
                    while not stop_flag.is_set():
                        raw_line = self.rfile.readline(4096)
                        if not raw_line:
                            break
                        try:
                            cmd = json.loads(raw_line)
                        except (ValueError, TypeError):
                            continue
                        if not isinstance(cmd, dict):
                            continue
                        self._apply(cmd, mouse, keyboard, pressed_keys, screen_width, screen_height)
                except OSError:
                    pass
                finally:
                    stop_flag.set()
                    release_all_pressed()
                    ended_signal.emit()

            def _apply(self, cmd, mouse, keyboard, pressed_keys, screen_width, screen_height):
                kind = cmd.get("t")
                try:
                    if kind == "mv":
                        x, y = live_coords_to_pixels(
                            float(cmd.get("x", 0)), float(cmd.get("y", 0)), screen_width, screen_height
                        )
                        mouse.position = (x, y)
                    elif kind == "down":
                        mouse.press(resolve_button(cmd.get("b")))
                    elif kind == "up":
                        mouse.release(resolve_button(cmd.get("b")))
                    elif kind == "click":
                        mouse.click(resolve_button(cmd.get("b")), max(1, int(cmd.get("n", 1))))
                    elif kind == "scroll":
                        mouse.scroll(0, float(cmd.get("dy", 0)))
                    elif kind == "kd":
                        normalized = normalize_live_key_name(str(cmd.get("k", "")))
                        if normalized is not None:
                            key = resolve_key(normalized)
                            keyboard.press(key)
                            pressed_keys.add(key)
                    elif kind == "ku":
                        normalized = normalize_live_key_name(str(cmd.get("k", "")))
                        if normalized is not None:
                            key = resolve_key(normalized)
                            keyboard.release(key)
                            pressed_keys.discard(key)
                    elif kind == "text":
                        keyboard.type(str(cmd.get("s", ""))[:2000])
                except Exception:
                    pass  # tek bir hatali komut tum oturumu koparmasin

        if not ensure_remote_tls_cert():
            return

        try:
            self._server = socketserver.ThreadingTCPServer(("0.0.0.0", REMOTE_LIVE_PORT), ConnectionHandler)
        except OSError:
            return
        self._server.daemon_threads = True
        self._server.allow_reuse_address = True

        try:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(REMOTE_CERT_PATH, REMOTE_KEY_PATH)
            self._server.socket = ssl_context.wrap_socket(self._server.socket, server_side=True)
        except (ssl.SSLError, OSError):
            self._server.server_close()
            self._server = None
            return

        try:
            self._server.serve_forever()
        except OSError:
            pass

    def stop(self):
        if self._server is not None:
            self._server.shutdown()


# --------------------------------------------------------------------------
# Guncelleme kontrolu (GitHub Releases)
# --------------------------------------------------------------------------

def _parse_version(text):
    """'v1.2.0' -> (1, 2, 0) gibi karsilastirilabilir bir tuple uretir;
    ayristirilamayan parcalar 0 sayilir."""
    text = text.strip()
    if text.lower().startswith("v"):
        text = text[1:]
    parts = []
    for piece in text.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer_version(remote_version, local_version):
    try:
        return _parse_version(remote_version) > _parse_version(local_version)
    except (ValueError, TypeError, AttributeError):
        return False


def find_release_with_asset(releases, asset_name):
    """[releases] listesinde (GitHub Releases API'sinin dondugu sirayla, en
    yeniden eskiye) taslak/on-surum olmayan ve icinde [asset_name] adinda
    bir dosya olan ilk release'i doner - yoksa None. Bu repoda masaustu ve
    mobil uygulamalarin release'leri ayni listede karistigi icin gerekli
    (bkz. UpdateCheckWorker.run)."""
    for release in releases or []:
        if release.get("draft") or release.get("prerelease"):
            continue
        asset_names = {
            str(asset.get("name", "")) for asset in release.get("assets", []) or []
        }
        if asset_name in asset_names:
            return release
    return None


class UpdateCheckWorker(QThread):
    """
    GitHub Releases API'sinden en son surumu sorar. Henuz hic release
    yayinlanmamissa (404) ya da ag erisimi yoksa sessizce hicbir sey
    yapmaz - bu, mevcut kurulumu bozmayan, tamamen opsiyonel bir kontrol.
    """

    # tag_name, html_url, exe_download_url (bulunamazsa bos), checksum_download_url (bulunamazsa bos)
    update_available = pyqtSignal(str, str, str, str)
    check_finished = pyqtSignal(bool, str)  # basarili mi, hata mesaji (varsa)

    def run(self):
        try:
            import urllib.error
            import urllib.request

            # /releases/latest doner reponun en son yayinlanan release'i -
            # ama bu repo'da masaustu ve mobil uygulamalar release'leri
            # paylasir, bu yuzden "en son" bazen diger uygulamaninki olabilir.
            # Bunun yerine listeyi (en yeniden eskiye) tarayip icinde bizim
            # exe'mizin oldugu ilk release'i buluyoruz.
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=10"
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "ai-kedi-asistani-update-check",
                },
            )
            with urllib.request.urlopen(req, timeout=UPDATE_CHECK_TIMEOUT_SECONDS) as resp:
                releases = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                self.check_finished.emit(True, "")  # henuz release yayinlanmamis
            else:
                self.check_finished.emit(False, f"HTTP {exc.code}")
            return
        except Exception as exc:
            self.check_finished.emit(False, str(exc))
            return

        data = find_release_with_asset(releases, UPDATE_ASSET_NAME)
        if data is None:
            self.check_finished.emit(True, "")  # bu uygulamaya ait release yok
            return

        tag = str(data.get("tag_name", "")).strip()
        html_url = str(data.get("html_url", "")).strip()
        if tag and is_newer_version(tag, APP_VERSION):
            download_url = ""
            checksum_url = ""
            for asset in data.get("assets", []) or []:
                name = str(asset.get("name", ""))
                asset_url = str(asset.get("browser_download_url", ""))
                if name == UPDATE_ASSET_NAME:
                    download_url = asset_url
                elif name == UPDATE_CHECKSUM_ASSET_NAME:
                    checksum_url = asset_url
            self.update_available.emit(tag, html_url, download_url, checksum_url)
        self.check_finished.emit(True, "")


class UpdateDownloadWorker(QThread):
    """
    Bir GitHub Release'inden yeni surum exe'sini indirir, varsa esliginde
    gelen SHA-256 dosyasiyla dogrular. Yalnizca PyInstaller ile derlenmis
    (frozen) halde anlamlidir - kaynaktan calisirken degistirilecek bir
    exe yoktur.
    """

    progress = pyqtSignal(int)  # 0-100 (toplam boyut bilinmiyorsa hic yayinlanmaz)
    finished_ok = pyqtSignal(str)  # indirilen dosyanin tam yolu
    finished_error = pyqtSignal(str)

    def __init__(self, download_url, checksum_url, parent=None):
        super().__init__(parent)
        self.download_url = download_url
        self.checksum_url = checksum_url

    def run(self):
        import hashlib
        import urllib.request

        target_path = os.path.join(base_dir(), "AI-Kedi-Asistani-new.exe")
        try:
            req = urllib.request.Request(
                self.download_url, headers={"User-Agent": "ai-kedi-asistani-update"}
            )
            digest = hashlib.sha256()
            with urllib.request.urlopen(req, timeout=UPDATE_DOWNLOAD_TIMEOUT_SECONDS) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                with open(target_path, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        digest.update(chunk)
                        downloaded += len(chunk)
                        if total:
                            self.progress.emit(int(downloaded * 100 / total))
        except Exception as exc:
            try:
                os.remove(target_path)
            except OSError:
                pass
            self.finished_error.emit(f"Indirme basarisiz: {exc}")
            return

        if self.checksum_url:
            try:
                checksum_req = urllib.request.Request(
                    self.checksum_url, headers={"User-Agent": "ai-kedi-asistani-update"}
                )
                with urllib.request.urlopen(
                    checksum_req, timeout=UPDATE_CHECK_TIMEOUT_SECONDS
                ) as resp:
                    expected = resp.read().decode("utf-8").strip().split()[0].lower()
                if expected != digest.hexdigest().lower():
                    os.remove(target_path)
                    self.finished_error.emit(
                        "Indirilen dosyanin bütünlük dogrulamasi basarisiz oldu "
                        "(SHA-256 uyusmuyor); guvenlik icin silindi."
                    )
                    return
            except Exception as exc:
                try:
                    os.remove(target_path)
                except OSError:
                    pass
                self.finished_error.emit(f"Bütünlük dogrulamasi yapilamadi: {exc}")
                return

        self.finished_ok.emit(target_path)


def apply_update_and_restart(new_exe_path):
    """
    Calisan exe'yi indirilen yeni surumle degistirip yeniden baslatir.
    Windows'ta calisan bir exe kendi uzerine yazilamadigindan, mevcut
    surecin (PID) tam olarak kapanmasini bekleyen kucuk bir .bat betigi
    olusturup arka planda calistirir, sonra uygulamayi kapatir.
    Yalnizca PyInstaller ile derlenmis (frozen) halde calisir.
    """
    if not getattr(sys, "frozen", False):
        return False
    if sys.platform != "win32":
        return False

    current_exe = sys.executable
    pid = os.getpid()
    updater_script = os.path.join(base_dir(), "_ai_kedi_update.bat")
    script = (
        "@echo off\r\n"
        ":wait\r\n"
        f'tasklist /FI "PID eq {pid}" | find "{pid}" >nul\r\n'
        "if not errorlevel 1 (\r\n"
        "    timeout /t 1 /nobreak >nul\r\n"
        "    goto wait\r\n"
        ")\r\n"
        f'move /Y "{new_exe_path}" "{current_exe}" >nul\r\n'
        f'start "" "{current_exe}"\r\n'
        'del "%~f0"\r\n'
    )
    try:
        with open(updater_script, "w", encoding="utf-8") as f:
            f.write(script)
        subprocess.Popen(
            ["cmd", "/c", updater_script],
            creationflags=subprocess.CREATE_NO_WINDOW,
            close_fds=True,
        )
    except OSError:
        return False

    QApplication.instance().quit()
    return True


# --------------------------------------------------------------------------
# Windows ile otomatik baslatma (baslangic klasoru yerine Run registry anahtari)
# --------------------------------------------------------------------------

AUTOSTART_VALUE_NAME = "AI Kedi Asistani"


def _autostart_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" "{os.path.abspath(__file__)}"'


def is_autostart_enabled():
    if sys.platform != "win32":
        return False
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ
        )
        try:
            value, _ = winreg.QueryValueEx(key, AUTOSTART_VALUE_NAME)
            return value == _autostart_command()
        finally:
            winreg.CloseKey(key)
    except OSError:
        return False


def set_autostart(enabled):
    if sys.platform != "win32":
        return
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE
        )
        try:
            if enabled:
                winreg.SetValueEx(key, AUTOSTART_VALUE_NAME, 0, winreg.REG_SZ, _autostart_command())
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_VALUE_NAME)
                except FileNotFoundError:
                    pass
        finally:
            winreg.CloseKey(key)
    except OSError:
        pass


# --------------------------------------------------------------------------
# Genel (uygulama odakta olmasa da calisan) klavye kisayolu
# --------------------------------------------------------------------------

HOTKEY_COMBO = "ctrl+shift+k"


class HotkeySignal(QObject):
    """
    keyboard kutuphanesi kendi arka plan thread'inde calisir; bu QObject
    Qt'nin sinyal/slot mekanizmasiyla tetiklemeyi ana/GUI thread'ine
    guvenli sekilde tasir.
    """

    triggered = pyqtSignal()


def register_global_hotkey(callback):
    """
    HOTKEY_COMBO tuş bileşimini global olarak dinler ve tetiklendiginde
    callback'i (Qt ana thread'inde) cagirir. Platform desteklemiyorsa ya
    da kayit basarisiz olursa (izin, cakisma vb.) sessizce hicbir sey
    yapmaz - uygulama bu ozellik olmadan da calismaya devam eder.
    """
    signal_holder = HotkeySignal()
    signal_holder.triggered.connect(callback)
    try:
        import keyboard

        keyboard.add_hotkey(HOTKEY_COMBO, signal_holder.triggered.emit)
    except Exception:
        return None
    return signal_holder  # referansi canli tutmak icin cagirana dondurulur


# "Kisilik" sag tik menusunden hizlica secilir; her biri persona metnine
# eklenen kisa bir ton tarifi - kedinin kimligini (isim) degil, nasil
# konustugunu degistirir. Anahtarlar menude gorundugu sirayla tutulur.
PERSONALITY_PRESETS = {
    "Varsayilan": "Kisa, samimi ve yardimsever konus.",
    "Sakaci": "Esprili ve nese dolu konus, uygun oldugunda kucuk sakalar yap.",
    "Ciddi": "Kisa, dogrudan ve profesyonel konus, gereksiz sohbetten kacin.",
    "Nazik": "Cok kibar, sabirli ve tesvik edici bir dille konus.",
    "Enerjik": "Cosku dolu, hareketli ve motive edici bir dille konus.",
}


def build_persona_prompt(character_name, personality):
    """GeminiWorker'in Gemini'ye gonderdigi system_instruction'ini
    uretir - kimlik (character_name, her zaman sabit) ile ton
    (PERSONALITY_PRESETS[personality], kullanicinin sectigi) ayri
    tutulur, boylece kisilik degistirmek asistanin kim oldugunu degil
    yalnizca nasil konustugunu etkiler. Bilinmeyen bir personality
    "Varsayilan"a duser."""
    tone = PERSONALITY_PRESETS.get(personality, PERSONALITY_PRESETS["Varsayilan"])
    return (
        f"Senin adin '{character_name}'. Kullanicinin masaustunde yasayan, "
        "onun ekranini gorebilen sevimli bir kedi yapay zeka asistanisin. "
        "Kendini her zaman bu isimle tanit; Google tarafindan gelistirilmis "
        "bir dil modeli oldugunu veya hangi sirkete/modele ait oldugunu "
        f"asla soyleme. {tone}"
    )


# --------------------------------------------------------------------------
# Ekran goruntusu + Gemini istegini arka planda yapan thread
# --------------------------------------------------------------------------

class GeminiWorker(QThread):
    finished_ok = pyqtSignal(str)
    finished_error = pyqtSignal(str)

    def __init__(
        self,
        api_key,
        model_name,
        question,
        character_name,
        personality="Varsayilan",
        history_context=None,
        parent=None,
    ):
        super().__init__(parent)
        self.api_key = api_key
        self.model_name = model_name
        self.question = question
        self.character_name = character_name
        self.personality = personality
        # Onceki soru-cevaplar (bkz. CONTEXT_HISTORY_TURNS) - "ona gore",
        # "bir de sunu" gibi takip sorularinin baglamini korumak icin
        # modele ayri konusma turleri olarak gonderilir.
        self.history_context = history_context or []

    def run(self):
        try:
            import mss
            import mss.tools

            with mss.mss() as sct:
                monitor = sct.monitors[0]  # tum sanal masaustu
                shot = sct.grab(monitor)
                png_bytes = mss.tools.to_png(shot.rgb, shot.size)
        except Exception as exc:
            self.finished_error.emit(f"Ekran goruntusu alinamadi: {exc}")
            return

        try:
            from google import genai
            from google.genai import types
        except ImportError:
            self.finished_error.emit(
                "google-genai kutuphanesi kurulu degil. "
                "'pip install google-genai' calistirin."
            )
            return

        persona = build_persona_prompt(self.character_name, self.personality)
        # Onceki turler sadece metin olarak (ekran goruntusu her seferinde
        # yeniden gonderilir, o an gecerli olan tek goruntu budur) - boylece
        # model "bahsettigim..." gibi bir onceki soruya gonderme yapan
        # takip sorularinda neyin kastedildigini hatirlayabilir.
        contents = []
        for turn in self.history_context:
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=turn["question"])],
                )
            )
            contents.append(
                types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=turn["answer"])],
                )
            )
        contents.append(
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=self.question),
                    types.Part.from_bytes(data=png_bytes, mime_type="image/png"),
                ],
            )
        )
        gen_config = types.GenerateContentConfig(system_instruction=persona)

        try:
            client = genai.Client(api_key=self.api_key)
            try:
                response = self._generate_with_retry(client, self.model_name, contents, gen_config)
            except Exception as primary_exc:
                should_try_fallback = self.model_name != FALLBACK_MODEL and (
                    self._is_overload_error(primary_exc) or self._is_model_retired_error(primary_exc)
                )
                if should_try_fallback:
                    try:
                        response = self._generate_with_retry(
                            client, FALLBACK_MODEL, contents, gen_config, retry_delays=(2,)
                        )
                    except Exception:
                        raise primary_exc
                else:
                    raise
            text = (response.text or "").strip() or "(Bos yanit dondu)"
            self.finished_ok.emit(text)
        except Exception as exc:
            self.finished_error.emit(f"Gemini API hatasi: {exc}")

    @staticmethod
    def _is_overload_error(exc):
        text = str(exc).lower()
        return "503" in text or "unavailable" in text or "overloaded" in text

    @staticmethod
    def _is_model_retired_error(exc):
        text = str(exc).lower()
        return "404" in text or "not_found" in text or "no longer available" in text

    def _generate_with_retry(self, client, model_name, contents, gen_config, retry_delays=OVERLOAD_RETRY_DELAYS):
        attempts = len(retry_delays) + 1
        for attempt in range(attempts):
            try:
                return client.models.generate_content(
                    model=model_name, contents=contents, config=gen_config
                )
            except Exception as exc:
                is_last_attempt = attempt == attempts - 1
                if is_last_attempt or not self._is_overload_error(exc):
                    raise
                time.sleep(retry_delays[attempt])


DEFAULT_QUICK_QUESTIONS = [
    "Ekranimda su an ne var, ozetler misin?",
    "Bu hata mesaji ne anlama geliyor?",
    "Bu kod parcasini aciklar misin?",
    "Burada nasil devam etmeliyim?",
    "Bunu daha verimli nasil yaparim?",
    "Bu metni ozetler misin?",
]


# --------------------------------------------------------------------------
# Pati izi loading animasyonu
# --------------------------------------------------------------------------

class PawLoadingIndicator(QWidget):
    """Kedi "dusunurken" gosterilen, art arda parlayan pati izlerinden
    olusan hafif bir loading animasyonu. Disaridan gorsel dosyasi
    gerektirmez - tamami QPainter ile cizilir."""

    PAW_COUNT = 4
    TICK_MS = 40
    PHASE_STEP = 0.16
    PHASE_OFFSET = 0.9

    def __init__(self, color="#5AAAFF", parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def start(self):
        self._phase = 0.0
        self._timer.start(self.TICK_MS)
        self.show()

    def stop(self):
        self._timer.stop()
        self.hide()

    def _tick(self):
        self._phase += self.PHASE_STEP
        self.update()

    def _draw_paw(self, painter, cx, cy, scale, opacity):
        color = QColor(self._color)
        color.setAlphaF(max(0.0, min(1.0, opacity)))
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx, cy + 5 * scale), 9 * scale, 7 * scale)
        for dx, dy in ((-8, -6), (-3, -10), (3, -10), (8, -6)):
            painter.drawEllipse(
                QPointF(cx + dx * scale, cy + dy * scale), 4 * scale, 5.5 * scale
            )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        spacing = self.width() / (self.PAW_COUNT + 1)
        cy = self.height() / 2
        for i in range(self.PAW_COUNT):
            wave = (math.sin(self._phase - i * self.PHASE_OFFSET) + 1) / 2
            self._draw_paw(
                painter,
                spacing * (i + 1),
                cy,
                scale=0.75 + 0.35 * wave,
                opacity=0.25 + 0.75 * wave,
            )


# --------------------------------------------------------------------------
# Konusma balonu
# --------------------------------------------------------------------------

class ChatBubble(QWidget):
    ask_requested = pyqtSignal(str)

    def __init__(self, character_name, theme_mode="dark"):
        super().__init__()
        self.theme_mode = theme_mode
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(320, 250)
        self._build_ui(character_name)

    def _build_ui(self, character_name):
        palette = THEME_PALETTES.get(self.theme_mode, THEME_PALETTES["dark"])
        container = QWidget(self)
        container.setGeometry(0, 0, self.width(), self.height())
        container.setObjectName("bubble")
        container.setStyleSheet(panel_stylesheet("bubble", self.theme_mode))

        layout = QVBoxLayout(container)
        layout.setContentsMargins(14, 12, 14, 12)

        header = QHBoxLayout()
        title = QPushButton(f"\U0001F431 {character_name}")
        title.setEnabled(False)
        title.setStyleSheet(
            f"background: transparent; color: {palette['text']}; font-weight: bold; "
            "font-size: 13px; text-align: left; border: none; padding: 0;"
        )
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(
            "background-color: rgba(255, 80, 80, 180); border-radius: 11px; padding: 0;"
        )
        close_btn.clicked.connect(self.close)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(close_btn)
        layout.addLayout(header)

        self.response_area = QTextEdit()
        self.response_area.setReadOnly(True)
        self.response_area.setPlaceholderText("Bana ekraninda ne oldugunu sor...")
        layout.addWidget(self.response_area, 1)

        self.paw_loading = PawLoadingIndicator(parent=container)
        self.paw_loading.setFixedHeight(32)
        layout.addWidget(self.paw_loading)

        self.quick_questions_box = QComboBox()
        self.quick_questions_box.addItem("Hazir sorular...")
        self.quick_questions_box.addItems(DEFAULT_QUICK_QUESTIONS)
        self.quick_questions_box.currentIndexChanged.connect(
            self._on_quick_question_selected
        )
        layout.addWidget(self.quick_questions_box)

        input_row = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Bir soru yaz...")
        self.input_field.returnPressed.connect(self._on_ask)
        self.ask_button = QPushButton("Sor / Fikir Ver")
        self.ask_button.clicked.connect(self._on_ask)
        input_row.addWidget(self.input_field, 1)
        input_row.addWidget(self.ask_button)
        layout.addLayout(input_row)

        self.request_count_label = QPushButton("")
        self.request_count_label.setEnabled(False)
        self.request_count_label.setStyleSheet(
            f"background: transparent; color: {palette['text_muted']}; "
            "font-size: 10px; text-align: left; border: none; padding: 0;"
        )
        layout.addWidget(self.request_count_label)

    def set_request_count(self, count):
        self.request_count_label.setText(f"Bugun gonderilen istek: {count}")

    def _on_ask(self):
        text = self.input_field.text().strip()
        if not text:
            return
        self.ask_requested.emit(text)

    def _on_quick_question_selected(self, index):
        if index <= 0:
            return
        self.input_field.setText(self.quick_questions_box.itemText(index))
        self.input_field.setFocus()
        self.quick_questions_box.setCurrentIndex(0)

    def show_thinking(self):
        self.ask_button.setEnabled(False)
        self.response_area.setPlainText("Dusunuyor...")
        self.paw_loading.start()

    def show_response(self, text):
        self.ask_button.setEnabled(True)
        self.paw_loading.stop()
        self.response_area.setPlainText(text)

    def show_error(self, text):
        self.ask_button.setEnabled(True)
        self.paw_loading.stop()
        self.response_area.setPlainText(f"⚠ {text}")


# --------------------------------------------------------------------------
# Sohbet gecmisi paneli
# --------------------------------------------------------------------------

class ChatHistoryDialog(QWidget):
    def __init__(self, history: ChatHistoryManager, character_name, theme_mode="dark"):
        super().__init__()
        self.history = history
        self.theme_mode = theme_mode
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(360, 420)
        self._build_ui(character_name)
        self.refresh()

    def _build_ui(self, character_name):
        palette = THEME_PALETTES.get(self.theme_mode, THEME_PALETTES["dark"])
        container = QWidget(self)
        container.setGeometry(0, 0, self.width(), self.height())
        container.setObjectName("historyPanel")
        container.setStyleSheet(panel_stylesheet("historyPanel", self.theme_mode))

        layout = QVBoxLayout(container)
        layout.setContentsMargins(14, 12, 14, 12)

        header = QHBoxLayout()
        title = QPushButton(f"\U0001F553 {character_name} - Sohbet Gecmisi")
        title.setEnabled(False)
        title.setStyleSheet(
            f"background: transparent; color: {palette['text']}; font-weight: bold; "
            "font-size: 13px; text-align: left; border: none; padding: 0;"
        )
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(
            "background-color: rgba(255, 80, 80, 180); border-radius: 11px; padding: 0;"
        )
        close_btn.clicked.connect(self.close)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(close_btn)
        layout.addLayout(header)

        search_row = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Gecmiste ara...")
        self.search_box.textChanged.connect(self.refresh)
        search_row.addWidget(self.search_box, 1)
        self.favorites_btn = QPushButton("★")
        self.favorites_btn.setCheckable(True)
        self.favorites_btn.setFixedSize(30, 30)
        self.favorites_btn.setToolTip("Sadece favoriler")
        self.favorites_btn.toggled.connect(self.refresh)
        search_row.addWidget(self.favorites_btn)
        layout.addLayout(search_row)

        self.list_area = QScrollArea()
        self.list_area.setWidgetResizable(True)
        self.list_area.setFrameShape(QFrame.Shape.NoFrame)
        self.list_area.setStyleSheet("background: transparent; border: none;")
        self.list_container = QWidget()
        self.list_container.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.addStretch()
        self.list_area.setWidget(self.list_container)
        layout.addWidget(self.list_area, 1)

        footer = QHBoxLayout()
        export_btn = QPushButton("Disa Aktar...")
        export_btn.clicked.connect(self._on_export)
        footer.addWidget(export_btn)
        footer.addStretch()
        clear_btn = QPushButton("Gecmisi Temizle")
        clear_btn.clicked.connect(self._on_clear)
        footer.addWidget(clear_btn)
        layout.addLayout(footer)

    def _visible_entries(self):
        query = self.search_box.text().strip().lower()
        entries = self.history.entries
        if query:
            entries = [
                e
                for e in entries
                if query in str(e.get("question", "")).lower()
                or query in str(e.get("answer", "")).lower()
            ]
        if self.favorites_btn.isChecked():
            entries = [e for e in entries if e.get("favorite")]
        return entries

    def refresh(self):
        while self.list_layout.count() > 1:  # son eleman hep addStretch()
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not self.history.entries:
            self.list_layout.insertWidget(0, self._make_message_label("Henuz bir sohbet gecmisi yok."))
            return
        entries = self._visible_entries()
        if not entries:
            self.list_layout.insertWidget(0, self._make_message_label("Eslesen kayit bulunamadi."))
            return
        for i, entry in enumerate(reversed(entries)):  # en yeni en ustte
            row = self._make_entry_row(entry)
            self.list_layout.insertWidget(i, row)

    def _make_message_label(self, text):
        palette = THEME_PALETTES.get(self.theme_mode, THEME_PALETTES["dark"])
        label = QLabel(text)
        label.setStyleSheet(f"color: {palette['text_muted']}; border: none; padding: 8px;")
        return label

    def _make_entry_row(self, entry):
        palette = THEME_PALETTES.get(self.theme_mode, THEME_PALETTES["dark"])
        row = QWidget()
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(4, 6, 4, 6)
        row_layout.setSpacing(2)

        header = QHBoxLayout()
        time_label = QLabel(f"[{entry.get('time', '')}]")
        time_label.setStyleSheet(f"color: {palette['text_muted']}; font-size: 10px; border: none;")
        header.addWidget(time_label)
        header.addStretch()
        star_btn = QPushButton("★" if entry.get("favorite") else "☆")
        star_btn.setFixedSize(22, 20)
        star_btn.setStyleSheet(
            f"background: transparent; border: none; color: {palette['text']}; font-size: 13px; padding: 0;"
        )
        star_btn.clicked.connect(lambda: self._toggle_favorite(entry))
        header.addWidget(star_btn)
        row_layout.addLayout(header)

        q_label = QLabel(f"Sen: {entry.get('question', '')}")
        q_label.setWordWrap(True)
        q_label.setStyleSheet(f"color: {palette['text_muted']}; font-size: 12px; border: none;")
        row_layout.addWidget(q_label)

        marker = "⚠" if entry.get("is_error") else "\U0001F431"
        a_label = QLabel(f"{marker} {entry.get('answer', '')}")
        a_label.setWordWrap(True)
        a_label.setStyleSheet(f"color: {palette['text']}; font-size: 12px; border: none;")
        row_layout.addWidget(a_label)

        return row

    def _toggle_favorite(self, entry):
        entry["favorite"] = not entry.get("favorite", False)
        self.history.save()
        self.refresh()

    def _on_clear(self):
        self.history.clear()
        self.refresh()

    def _on_export(self):
        entries = self._visible_entries()
        if not entries:
            QMessageBox.information(self, "Disa Aktar", "Aktarilacak bir kayit yok.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Sohbet Gecmisini Disa Aktar", "sohbet-gecmisi.txt", "Metin Dosyalari (*.txt)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(format_history_entries(entries))
        except OSError as exc:
            QMessageBox.warning(self, "Disa Aktarilamadi", f"Dosya yazilamadi: {exc}")


class SecureNotepadDialog(QDialog):
    """Sifreli not defteri penceresi - kullanicinin belirledigi bir
    sifreyle korunan, yalnizca bu bilgisayarda saklanan bir not listesi
    (bkz. SecureNotepadService; mobil suruumundeki SecureNotepadSheet
    ile ayni tasarim). Uc sayfa arasinda (kurulum/kilitli/acik) bir
    QStackedWidget ile gecis yapar; turetilen anahtar yalnizca bu
    pencere acikken bellekte tutulur."""

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self.key = None
        self.notes = []

        self.setWindowTitle("Şifreli Not Defteri")
        self.resize(420, 480)

        outer = QVBoxLayout(self)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)

        self.setup_page = self._build_setup_page()
        self.locked_page = self._build_locked_page()
        self.unlocked_page = self._build_unlocked_page()
        self.stack.addWidget(self.setup_page)
        self.stack.addWidget(self.locked_page)
        self.stack.addWidget(self.unlocked_page)

        self.stack.setCurrentWidget(
            self.locked_page if self.service.is_set_up() else self.setup_page
        )

    def _build_setup_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        info = QLabel(
            "Notlarınız yalnızca bu bilgisayarda, bu şifreyle şifreli "
            "olarak saklanır. Bu şifreyi unutursanız notlarınızı "
            "kurtarmanın bir yolu yoktur."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.setup_password = QLineEdit()
        self.setup_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.setup_password.setPlaceholderText("Yeni şifre")
        layout.addWidget(self.setup_password)

        self.setup_confirm = QLineEdit()
        self.setup_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.setup_confirm.setPlaceholderText("Şifreyi tekrar yaz")
        self.setup_confirm.returnPressed.connect(self._handle_setup)
        layout.addWidget(self.setup_confirm)

        self.setup_error = QLabel("")
        self.setup_error.setStyleSheet("color: #d1453a;")
        layout.addWidget(self.setup_error)

        setup_button = QPushButton("Not Defterini Kur")
        setup_button.clicked.connect(self._handle_setup)
        layout.addWidget(setup_button)
        layout.addStretch()
        return page

    def _handle_setup(self):
        password = self.setup_password.text()
        confirm = self.setup_confirm.text()
        if len(password) < 4:
            self.setup_error.setText("Şifre en az 4 karakter olmalı.")
            return
        if password != confirm:
            self.setup_error.setText("Şifreler eşleşmiyor.")
            return
        self.key = self.service.set_up(password)
        self.notes = []
        self.setup_password.clear()
        self.setup_confirm.clear()
        self.setup_error.setText("")
        self._refresh_notes_list()
        self.stack.setCurrentWidget(self.unlocked_page)

    def _build_locked_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.unlock_password = QLineEdit()
        self.unlock_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.unlock_password.setPlaceholderText("Şifre")
        self.unlock_password.returnPressed.connect(self._handle_unlock)
        layout.addWidget(self.unlock_password)

        self.unlock_error = QLabel("")
        self.unlock_error.setStyleSheet("color: #d1453a;")
        layout.addWidget(self.unlock_error)

        unlock_button = QPushButton("Kilidi Aç")
        unlock_button.clicked.connect(self._handle_unlock)
        layout.addWidget(unlock_button)

        forgot_button = QPushButton("Şifremi unuttum (tüm notları sil)")
        forgot_button.clicked.connect(self._handle_reset)
        layout.addWidget(forgot_button)
        layout.addStretch()
        return page

    def _handle_unlock(self):
        try:
            key, notes = self.service.unlock(self.unlock_password.text())
        except WrongPasswordError:
            self.unlock_error.setText("Yanlış şifre.")
            return
        self.key = key
        self.notes = notes
        self.unlock_password.clear()
        self.unlock_error.setText("")
        self._refresh_notes_list()
        self.stack.setCurrentWidget(self.unlocked_page)

    def _handle_reset(self):
        confirmed = QMessageBox.question(
            self,
            "Not Defterini Sıfırla",
            "Şifre kriptografik olarak kurtarılamaz - devam ederseniz TÜM "
            "notlar kalıcı olarak silinir ve yeni bir şifreyle sıfırdan "
            "başlarsınız.\n\nDevam edilsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        self.service.reset()
        self.unlock_password.clear()
        self.unlock_error.setText("")
        self.stack.setCurrentWidget(self.setup_page)

    def _build_unlocked_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        button_row = QHBoxLayout()
        add_button = QPushButton("Yeni Not")
        add_button.clicked.connect(lambda: self._edit_note(None))
        lock_button = QPushButton("Kilitle")
        lock_button.clicked.connect(self._handle_lock)
        button_row.addWidget(add_button)
        button_row.addStretch()
        button_row.addWidget(lock_button)
        layout.addLayout(button_row)

        self.notes_list = QListWidget()
        self.notes_list.itemDoubleClicked.connect(self._on_note_double_clicked)
        layout.addWidget(self.notes_list)

        delete_button = QPushButton("Seçili Notu Sil")
        delete_button.clicked.connect(self._delete_selected_note)
        layout.addWidget(delete_button)
        return page

    def _handle_lock(self):
        self.key = None
        self.notes = []
        self.stack.setCurrentWidget(self.locked_page)

    def _refresh_notes_list(self):
        self.notes_list.clear()
        for note in sorted(
            self.notes, key=lambda n: n.get("updated_at", ""), reverse=True
        ):
            item = QListWidgetItem(note.get("title") or "(başlıksız)")
            item.setData(Qt.ItemDataRole.UserRole, note.get("id"))
            self.notes_list.addItem(item)

    def _on_note_double_clicked(self, item):
        note_id = item.data(Qt.ItemDataRole.UserRole)
        note = next((n for n in self.notes if n.get("id") == note_id), None)
        if note is not None:
            self._edit_note(note)

    def _edit_note(self, existing):
        dialog = QDialog(self)
        dialog.setWindowTitle("Yeni Not" if existing is None else "Notu Düzenle")
        layout = QVBoxLayout(dialog)

        title_field = QLineEdit(existing.get("title", "") if existing else "")
        title_field.setPlaceholderText("Başlık")
        layout.addWidget(title_field)

        body_field = QTextEdit(existing.get("body", "") if existing else "")
        layout.addWidget(body_field)

        button_row = QHBoxLayout()
        cancel_button = QPushButton("İptal")
        save_button = QPushButton("Kaydet")
        button_row.addWidget(cancel_button)
        button_row.addWidget(save_button)
        layout.addLayout(button_row)
        cancel_button.clicked.connect(dialog.reject)
        save_button.clicked.connect(dialog.accept)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        title = title_field.text().strip()
        body = body_field.toPlainText().strip()
        if not title and not body:
            return

        now_iso = datetime.now().isoformat()
        if existing is None:
            self.notes.append(
                {
                    "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                    "title": title,
                    "body": body,
                    "updated_at": now_iso,
                }
            )
        else:
            for note in self.notes:
                if note.get("id") == existing.get("id"):
                    note["title"] = title
                    note["body"] = body
                    note["updated_at"] = now_iso
                    break
        self.service.save(self.key, self.notes)
        self._refresh_notes_list()

    def _delete_selected_note(self):
        item = self.notes_list.currentItem()
        if item is None:
            return
        note_id = item.data(Qt.ItemDataRole.UserRole)
        self.notes = [n for n in self.notes if n.get("id") != note_id]
        self.service.save(self.key, self.notes)
        self._refresh_notes_list()


# --------------------------------------------------------------------------
# Masaustu kedi karakteri
# --------------------------------------------------------------------------

class CatCharacter(QWidget):
    SPRITE_BASE_SIZE = 110

    def __init__(self, config: ConfigManager):
        super().__init__()
        self.config = config

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

        self.scale_factor = self.config.get("scale_percent") / 100.0
        self.pixmaps = {}
        self.walk_frames = []
        self._walk_frame_index = 0
        self.walk_anim_timer = QTimer(self)
        self.walk_anim_timer.timeout.connect(self._advance_walk_frame)
        self._load_pixmaps()

        self.state = "norm"
        self.current_pixmap = None
        self._dragging = False
        self._drag_offset = QPoint()
        self._facing_left = True  # yuruyus gorselleri varsayilan olarak sola bakiyor
        self._roam_animation = None
        self.roam_timer = QTimer(self)
        self.roam_timer.setSingleShot(True)
        self.roam_timer.timeout.connect(self._roam_move)
        self.last_activity = time.monotonic()
        self.bubble = None
        self.worker = None
        self.history = ChatHistoryManager(HISTORY_PATH)
        self.notifications = NotificationLog(NOTIFICATION_LOG_PATH)
        self.secure_notepad_service = SecureNotepadService()
        self.screenshot_history = ScreenshotHistoryLog(SCREENSHOT_HISTORY_PATH)
        self.history_dialog = None
        self._pending_question = None

        self._position_window()
        self._set_state("norm")
        self._schedule_roam()

        self.sleep_check_timer = QTimer(self)
        self.sleep_check_timer.timeout.connect(self._check_sleep)
        self.sleep_check_timer.start(5000)

        self.auto_backup_timer = QTimer(self)
        self.auto_backup_timer.timeout.connect(self._maybe_auto_backup)
        self.auto_backup_timer.start(AUTO_BACKUP_CHECK_INTERVAL_MS)
        self._maybe_auto_backup()

        self.automation_timer = QTimer(self)
        self.automation_timer.timeout.connect(self._run_automation_tick)
        self.automation_timer.start(AUTOMATION_TICK_INTERVAL_MS)

        self.revert_timer = QTimer(self)
        self.revert_timer.setSingleShot(True)
        self.revert_timer.timeout.connect(lambda: self._set_state("norm"))

        # Tekrarlayan hatirlaticilarin QTimer'lari - uygulama kapanana kadar
        # (kalici bir depolama yok, tek seferlik hatirlaticilar gibi) burada
        # tutulur, boylece "Tekrarlayan Hatirlaticilari Durdur" hepsini
        # birden stop() edebilir.
        self._repeating_reminder_timers = []

        self.remote_server = RemoteCommandServer(self.config, self.history, self)
        self.remote_server.screenshot_history = self.screenshot_history
        self.remote_server.command_received.connect(self._on_remote_command)
        self.remote_server.media_command_received.connect(self._on_media_command)
        self.remote_server.power_command_received.connect(self._on_power_command)
        self.remote_server.file_received.connect(self._on_file_received)
        self.remote_server.start()

        self.live_control_server = RemoteLiveControlServer(self.config, self)
        self.live_control_server.session_started.connect(self._on_live_control_started)
        self.live_control_server.session_ended.connect(self._on_live_control_ended)
        self.live_control_server.start()

        register_send_with_cat_context_menu()
        self.send_with_cat_ipc_server = SendWithCatIpcServer(self)
        self.send_with_cat_ipc_server.file_path_received.connect(self.queue_outbound_file)
        self.send_with_cat_ipc_server.start()

        self._hotkey_signal = register_global_hotkey(self._open_bubble)

        self.tray_icon = None
        self._setup_tray_icon()

        self.update_worker = None
        self._update_check_manual = False
        self._last_update_info = None
        self._update_download_worker = None
        QTimer.singleShot(3000, lambda: self._check_for_updates(manual=False))

    # -- gorsel yukleme / olcekleme -------------------------------------

    def _load_pixmaps(self):
        skins = discover_skins()
        skin_dir = skins.get(self.config.get("skin"), ASSETS_DIR)
        for state, filename in STATE_FILES.items():
            raw = load_pixmap(skin_dir, filename, state)
            self.pixmaps[state] = raw.scaled(
                max(24, int(self.SPRITE_BASE_SIZE * self.scale_factor)),
                max(24, int(self.SPRITE_BASE_SIZE * self.scale_factor)),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self.walk_frames = self._load_walk_frames(skin_dir)

    def _load_walk_frames(self, skin_dir):
        """"norm" durumunda oynatilacak yuruyus kare dizisini yukler.
        Dosyalar (fuff_walk_000.png, fuff_walk_001.png, ...) bulunamazsa
        bos liste doner - bu durumda CatCharacter statik "norm" gorseline
        geri duser, mevcut/eksik skin'leri bozmaz."""
        frames = []
        size = max(24, int(self.SPRITE_BASE_SIZE * self.scale_factor))
        for i in range(WALK_FRAME_MAX_COUNT):
            path = os.path.join(skin_dir, WALK_FRAME_PATTERN.format(i))
            if not os.path.isfile(path):
                break
            raw = QPixmap(path)
            if raw.isNull():
                break
            frames.append(
                raw.scaled(
                    size,
                    size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        return frames

    def _position_window(self):
        screen = QApplication.primaryScreen().availableGeometry()
        w = self.pixmaps["norm"].width()
        h = self.pixmaps["norm"].height()

        saved_x = self.config.get("pos_x")
        saved_y = self.config.get("pos_y")
        if saved_x is not None and saved_y is not None:
            x = min(max(saved_x, screen.left()), screen.right() - w)
            y = min(max(saved_y, screen.top()), screen.bottom() - h)
        else:
            x = screen.right() - w - 40
            y = screen.bottom() - h - 20

        self.move(x, y)

    def _set_state(self, state):
        was_norm = self.state == "norm"
        self.state = state
        if state == "norm" and self.walk_frames:
            self._walk_frame_index = 0
            self.current_pixmap = self.walk_frames[0]
            self.setFixedSize(self.current_pixmap.size())
            if not self.walk_anim_timer.isActive():
                self.walk_anim_timer.start(WALK_FRAME_INTERVAL_MS)
            if not was_norm:
                self._schedule_roam()
        else:
            self.walk_anim_timer.stop()
            if self._roam_animation is not None:
                self._roam_animation.stop()
                self._roam_animation = None
            self.roam_timer.stop()
            pixmap = self.pixmaps.get(state, self.pixmaps["norm"])
            self.current_pixmap = pixmap
            self.setFixedSize(pixmap.size())
        self.update()

    def _advance_walk_frame(self):
        if not self.walk_frames:
            return
        self._walk_frame_index = (self._walk_frame_index + 1) % len(self.walk_frames)
        self.current_pixmap = self.walk_frames[self._walk_frame_index]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self.current_pixmap:
            # Yuruyus gorselleri varsayilan olarak sola bakiyor; saga
            # dogru dolasirken yatayda aynalanir.
            if self.state == "norm" and not self._facing_left:
                painter.translate(self.width(), 0)
                painter.scale(-1, 1)
            painter.drawPixmap(0, 0, self.current_pixmap)

    # -- dolasma (roaming) --------------------------------------------------

    def _schedule_roam(self):
        if not self.walk_frames:
            return
        delay = random.randint(ROAM_MIN_DELAY_MS, ROAM_MAX_DELAY_MS)
        self.roam_timer.start(delay)

    def _roam_move(self):
        if self.state != "norm" or self._dragging:
            self._schedule_roam()
            return
        if self.bubble is not None and self.bubble.isVisible():
            self._schedule_roam()
            return

        screen = QApplication.primaryScreen().availableGeometry()
        max_x = max(screen.left(), screen.right() - self.width())
        max_y = max(screen.top(), screen.bottom() - self.height())
        if max_x <= screen.left() or max_y <= screen.top():
            self._schedule_roam()
            return

        target_x = random.randint(screen.left(), max_x)
        target_y = random.randint(screen.top(), max_y)
        self._facing_left = target_x <= self.x()

        distance = ((target_x - self.x()) ** 2 + (target_y - self.y()) ** 2) ** 0.5
        duration = int(
            min(max(distance * ROAM_MS_PER_PIXEL, ROAM_MIN_DURATION_MS), ROAM_MAX_DURATION_MS)
        )

        self._roam_animation = QPropertyAnimation(self, b"pos")
        self._roam_animation.setDuration(duration)
        self._roam_animation.setStartValue(self.pos())
        self._roam_animation.setEndValue(QPoint(target_x, target_y))
        self._roam_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._roam_animation.finished.connect(self._on_roam_finished)
        self._roam_animation.start()

    def _on_roam_finished(self):
        self._roam_animation = None
        self.config.set("pos_x", self.x())
        self.config.set("pos_y", self.y())
        self._schedule_roam()

    # -- uyku modu ----------------------------------------------------------

    def _register_activity(self):
        self.last_activity = time.monotonic()
        if self.state == "zzz":
            self._set_state("norm")

    def _check_sleep(self):
        if self.state in ("stern",) or self._dragging:
            return
        if self.state == "zzz":
            return
        idle_ms = (time.monotonic() - self.last_activity) * 1000
        if idle_ms >= SLEEP_AFTER_MS:
            self.revert_timer.stop()
            self._set_state("zzz")

    # -- surukleme --------------------------------------------------------

    def mousePressEvent(self, event):
        self._register_activity()
        if event.button() == Qt.MouseButton.LeftButton:
            if self._roam_animation is not None:
                self._roam_animation.stop()
                self._roam_animation = None
            self.roam_timer.stop()
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self.config.set("pos_x", self.x())
            self.config.set("pos_y", self.y())
            self._schedule_roam()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._register_activity()
            self._open_bubble()
        super().mouseDoubleClickEvent(event)

    # -- konusma balonu -----------------------------------------------------

    def _open_bubble(self):
        if self.bubble is None:
            self.bubble = ChatBubble(
                self.config.get("character_name"), self.config.get("theme_mode")
            )
            self.bubble.ask_requested.connect(self._handle_question)
            self.bubble.set_request_count(self.config.gemini_request_count_today())

        bubble_x = self.x() + self.width() // 2 - self.bubble.width() // 2
        bubble_y = self.y() - self.bubble.height() - 10

        screen = QApplication.primaryScreen().availableGeometry()
        bubble_x = max(screen.left(), min(bubble_x, screen.right() - self.bubble.width()))
        bubble_y = max(screen.top(), bubble_y)

        self.bubble.move(bubble_x, bubble_y)
        self.bubble.show()
        self.bubble.raise_()
        self.bubble.activateWindow()

    def _open_history(self):
        if self.history_dialog is None:
            self.history_dialog = ChatHistoryDialog(
                self.history,
                self.config.get("character_name"),
                self.config.get("theme_mode"),
            )
        self.history_dialog.refresh()

        panel_x = self.x() + self.width() // 2 - self.history_dialog.width() // 2
        panel_y = self.y() - self.history_dialog.height() - 10

        screen = QApplication.primaryScreen().availableGeometry()
        panel_x = max(screen.left(), min(panel_x, screen.right() - self.history_dialog.width()))
        panel_y = max(screen.top(), panel_y)

        self.history_dialog.move(panel_x, panel_y)
        self.history_dialog.show()
        self.history_dialog.raise_()
        self.history_dialog.activateWindow()

    def _handle_question(self, question):
        api_key = self.config.get("gemini_api_key")
        if not api_key:
            self.bubble.show_error("Once sag tik menusunden Gemini API Key ayarini girin.")
            return

        self._register_activity()
        self.revert_timer.stop()
        self._set_state("stern")
        self.bubble.show_thinking()
        self.bubble.set_request_count(self.config.register_gemini_request())
        self._pending_question = question

        self.worker = GeminiWorker(
            api_key,
            self.config.get("model_name"),
            question,
            self.config.get("character_name"),
            personality=self.config.get("personality"),
            history_context=self._recent_context(),
        )
        self.worker.finished_ok.connect(self._on_answer)
        self.worker.finished_error.connect(self._on_answer_error)
        self.worker.start()

    def _recent_context(self):
        return select_context_turns(
            self.history.entries, self.config.get("context_aware_enabled")
        )

    def _on_answer(self, text):
        self._set_state("smile")
        self.revert_timer.start(REVERT_TO_NORMAL_MS)
        if self.bubble:
            self.bubble.show_response(text)
        self._log_history(text, is_error=False)

    def _on_answer_error(self, text):
        self._set_state("fear")
        self.revert_timer.start(REVERT_TO_NORMAL_MS)
        if self.bubble:
            self.bubble.show_error(text)
        self._log_history(text, is_error=True)
        self.remote_server.add_alert(text)

    def _log_history(self, answer, is_error):
        if self._pending_question is None:
            return
        self.history.add(self._pending_question, answer, is_error=is_error)
        self._pending_question = None
        if self.history_dialog is not None:
            self.history_dialog.refresh()

    # -- uzaktan kumanda ------------------------------------------------------

    def _on_remote_command(self, url):
        webbrowser.open(url)
        self._register_activity()
        self.revert_timer.stop()
        self._set_state("smile")
        self.revert_timer.start(REVERT_TO_NORMAL_MS)

    def _on_media_command(self, action):
        handle_media_action(action)
        self._register_activity()
        self.revert_timer.stop()
        self._set_state("smile")
        self.revert_timer.start(REVERT_TO_NORMAL_MS)

    def _on_power_command(self, action):
        handle_power_action(action)

    def _on_file_received(self, filename):
        """Telefondan "Dosya Teleport" ile bir dosya geldiginde - bilgisayarin
        basinda biri varsa acik bir bildirim gosterir (sessiz/gizli calismaz)."""
        if self.tray_icon is not None:
            self.tray_icon.showMessage(
                "Dosya Alındı",
                f'"{filename}" telefondan alındı ve '
                f'"{REMOTE_FILE_TELEPORT_DIR_NAME}" klasörüne kaydedildi.',
                QSystemTrayIcon.MessageIcon.Information,
                4000,
            )

    def queue_outbound_file(self, path):
        """"Kediyle Gönder" (Windows Gezgini sag tik menusu ya da ayni
        surecteki SendWithCatIpcServer) ile cagrilir - dosyayi okuyup
        RemoteCommandServer'daki kuyruga ekler, telefon bir sonraki
        /file/pending yoklamasinda alir. Bilgisayarin basinda biri varsa
        acik bir bildirimle bilgilendirilir (sessiz/gizli calismaz)."""
        filename = os.path.basename(path)
        if not os.path.isfile(path):
            self._notify_send_with_cat_failure(filename, "dosya bulunamadı")
            return
        try:
            if os.path.getsize(path) > REMOTE_FILE_TELEPORT_MAX_BYTES:
                self._notify_send_with_cat_failure(filename, "dosya çok büyük (en fazla 25 MB)")
                return
            with open(path, "rb") as f:
                content_b64 = base64.b64encode(f.read()).decode("ascii")
        except OSError as exc:
            self._notify_send_with_cat_failure(filename, str(exc))
            return
        self.remote_server.queue_outbound_file(filename, content_b64)
        if self.tray_icon is not None:
            self.tray_icon.showMessage(
                "Kediyle Gönder",
                f'"{filename}" telefonunuza gönderilmek üzere kuyruğa alındı - '
                "telefon bir sonraki kontrolünde indirecek.",
                QSystemTrayIcon.MessageIcon.Information,
                4000,
            )

    def _notify_send_with_cat_failure(self, filename, reason):
        if self.tray_icon is not None:
            self.tray_icon.showMessage(
                "Kediyle Gönder",
                f'"{filename}" gönderilemedi: {reason}.',
                QSystemTrayIcon.MessageIcon.Warning,
                5000,
            )

    def _on_live_control_started(self):
        """Telefon "Canlı Kontrol" sekmesini acip baglaninca - bilgisayarin
        basinda biri varsa fare/klavyenin uzaktan kullanildigini bilsin
        diye acik bir bildirim gosterir (sessiz/gizli calismaz)."""
        if self.tray_icon is not None:
            self.tray_icon.showMessage(
                "Canlı Kontrol Başladı",
                "Telefon bu bilgisayarı fare/klavye ile uzaktan kontrol ediyor.",
                QSystemTrayIcon.MessageIcon.Warning,
                5000,
            )

    def _on_live_control_ended(self):
        if self.tray_icon is not None:
            self.tray_icon.showMessage(
                "Canlı Kontrol Bitti",
                "Telefonun uzaktan kontrol bağlantısı kapandı.",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )

    def _show_remote_info(self):
        self._register_activity()
        ip = get_local_ip()
        pin = self.config.get("remote_pin")
        fingerprint = get_cert_fingerprint()
        fingerprint_line = (
            f"Sertifika Parmak Izi (SHA-256): {fingerprint}\n"
            if fingerprint
            else ""
        )
        qr_pixmap = build_pairing_qr_pixmap(ip, REMOTE_SERVER_PORT, pin, fingerprint)
        qr_hint = (
            "ya da asagidaki QR kodu telefonda \"QR ile Ekle\" ile "
            "tarayin - alanlar otomatik dolar. "
            if qr_pixmap is not None
            else ""
        )

        dialog = QDialog(self)
        dialog.setWindowTitle("Uzaktan Kumanda")
        layout = QVBoxLayout(dialog)

        text_label = QLabel(
            "Telefon uygulamasindaki \"Bilgisayari Kumanda Et\" bolumune "
            f"bu bilgileri girin (ikisi de ayni Wi-Fi agina bagli olmali), "
            f"{qr_hint}"
            "Baglanti HTTPS (TLS) ile sifrelenir; telefon ilk baglantida "
            "asagidaki parmak izini kaydedip sonraki baglantilarda dogrular:\n\n"
            f"IP Adresi: {ip}\n"
            f"Port: {REMOTE_SERVER_PORT}\n"
            f"PIN: {pin}\n"
            f"{fingerprint_line}"
            "\nAyni Wi-Fi agindaysaniz yukaridaki IP'yi kullanin. Farkli "
            "bir agdaysaniz (evden uzaktayken) her iki cihaza da Tailscale "
            "kurup, buraya bu bilgisayarin Tailscale IP'sini (100.x.x.x, "
            "Tailscale uygulamasindan gorulebilir) girin - geri kalan her "
            "sey (PIN, sertifika dogrulamasi) ayni sekilde calisir.\n"
            f"\n{self._recent_connections_text()}"
        )
        text_label.setWordWrap(True)
        layout.addWidget(text_label)

        if qr_pixmap is not None:
            qr_label = QLabel()
            qr_label.setPixmap(qr_pixmap)
            qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(qr_label)

        button_row = QHBoxLayout()
        regen_button = QPushButton("PIN'i Yenile")
        close_button = QPushButton("Kapat")
        button_row.addWidget(regen_button)
        button_row.addStretch()
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        regenerated = {"value": False}

        def on_regen():
            regenerated["value"] = True
            dialog.accept()

        regen_button.clicked.connect(on_regen)
        close_button.clicked.connect(dialog.accept)

        dialog.exec()
        if regenerated["value"]:
            self.config.set("remote_pin", f"{random.randint(0, 999999):06d}")
            # Yeni PIN'i bilmeyen eski baglantilar artik dogrulanamaz -
            # "aktif oturumlari sonlandirma" karsiligi budur (bkz. sinif
            # docstring'i); listeyi de bu yuzden temizliyoruz.
            self.remote_server.recent_connections.clear()
            self._show_remote_info()

    def _recent_connections_text(self):
        return format_recent_connections(self.remote_server.recent_connections, datetime.now())

    def _show_access_log(self):
        self._register_activity()
        lines = tail_access_log(ACCESS_LOG_PATH)
        if not lines:
            text = (
                "Henuz bir erisim kaydi yok. Telefon uygulamasindan bir "
                "istek geldiginde burada gorunecek."
            )
        else:
            text = (
                f"Son {len(lines)} kayit (zaman, IP, olay, uc nokta):\n\n"
                + "\n".join(lines)
            )
        box = QMessageBox(self)
        box.setWindowTitle("Erisim Gunlugu")
        box.setText(text)
        box.exec()

    def _show_notification_history(self):
        self._register_activity()
        if not self.notifications.entries:
            text = "Henuz bir bildirim yok."
        else:
            text = format_notifications(self.notifications.entries)
        box = QMessageBox(self)
        box.setWindowTitle("Bildirim Gecmisi")
        box.setText(text)
        clear_button = box.addButton("Temizle", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() == clear_button:
            self.notifications.clear()

    def _show_screenshot_history(self):
        self._register_activity()
        if not self.screenshot_history.entries:
            text = "Henuz alinan bir ekran goruntusu yok."
        else:
            text = format_screenshot_history(self.screenshot_history.entries)
        box = QMessageBox(self)
        box.setWindowTitle("Ekran Goruntusu Gecmisi")
        box.setText(text)
        clear_button = box.addButton("Temizle", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() == clear_button:
            self.screenshot_history.clear()

    def _show_usage_stats(self):
        self._register_activity()
        stats = compute_usage_stats(
            self.history.entries,
            self.notifications.entries,
            self._automation_rules(),
            self._custom_commands(),
            self.remote_server.recent_connections,
            datetime.now(),
        )
        box = QMessageBox(self)
        box.setWindowTitle("Kullanım İstatistikleri")
        box.setText(format_usage_stats(stats))
        box.exec()

    def _show_secure_notepad(self):
        self._register_activity()
        dialog = SecureNotepadDialog(self.secure_notepad_service, self)
        dialog.exec()


    # -- hatirlatici --------------------------------------------------------

    def _create_reminder(self):
        self._register_activity()
        minutes, ok = QInputDialog.getInt(
            self, "Hatirlatici Kur", "Kac dakika sonra hatirlatilsin?", 5, 1, 1440
        )
        if not ok:
            return
        text, ok = QInputDialog.getText(
            self, "Hatirlatici Kur", "Hatirlatma mesaji (bos birakabilirsiniz):"
        )
        if not ok:
            return
        text = text.strip() or "Hatirlatma zamani!"

        repeat = QMessageBox.question(
            self,
            "Hatirlatici Kur",
            f"Bu hatirlatici her {minutes} dakikada bir tekrarlansin mi?\n"
            "(Hayir derseniz yalnizca bir kez hatirlatilir.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

        interval_ms = minutes * 60 * 1000
        if repeat:
            timer = QTimer(self)
            timer.timeout.connect(lambda: self._fire_reminder(text))
            timer.start(interval_ms)
            self._repeating_reminder_timers.append(timer)
            confirm_message = f"Her {minutes} dakikada bir tekrarlanacak."
        else:
            QTimer.singleShot(interval_ms, lambda: self._fire_reminder(text))
            confirm_message = f"{minutes} dakika sonra hatirlatilacaksiniz."

        if self.tray_icon is not None:
            self.tray_icon.showMessage(
                "Hatirlatici Kuruldu",
                confirm_message,
                QSystemTrayIcon.MessageIcon.Information,
                4000,
            )
        else:
            QMessageBox.information(self, "Hatirlatici Kuruldu", confirm_message)
        self.notifications.add("Hatirlatici Kuruldu", confirm_message)

    def _stop_repeating_reminders(self):
        self._register_activity()
        if not self._repeating_reminder_timers:
            QMessageBox.information(self, "Tekrarlayan Hatirlaticilar", "Aktif tekrarlayan hatirlatici yok.")
            return
        count = len(self._repeating_reminder_timers)
        for timer in self._repeating_reminder_timers:
            timer.stop()
        self._repeating_reminder_timers = []
        QMessageBox.information(
            self, "Tekrarlayan Hatirlaticilar", f"{count} tekrarlayan hatirlatici durduruldu."
        )

    def _fire_reminder(self, text):
        self._register_activity()
        self.revert_timer.stop()
        self._set_state("smile")
        self.revert_timer.start(REVERT_TO_NORMAL_MS)
        reminder_title = f"{self.config.get('character_name')} Hatirlatiyor"
        if self.tray_icon is not None:
            self.tray_icon.showMessage(
                reminder_title,
                text,
                QSystemTrayIcon.MessageIcon.Information,
                10000,
            )
        else:
            QMessageBox.information(self, "Hatirlatma", text)
        self.notifications.add(reminder_title, text)

    # -- kural motoru / otomasyon --------------------------------------------

    def _automation_rules(self):
        """config'teki "automation_rules" listesinin bir kopyasini dondurur
        (DEFAULT_CONFIG'te bilerek yok - bkz. o tanimin yanindaki yorum);
        cagiran bunu diledigi gibi degistirip config.set() ile geri
        yazabilir, dogrudan config.data'yi mutasyona ugratmadan."""
        return list(self.config.get("automation_rules") or [])

    def _run_automation_tick(self):
        """automation_timer'in her tetiklenisinde (bkz. AUTOMATION_TICK_
        INTERVAL_MS) cagrilir; ateslenmesi gereken kural varsa eylemini
        calistirir ve last_fired'ini gunceller (bkz. should_fire_rule)."""
        now = datetime.now()
        idle_seconds = time.monotonic() - self.last_activity
        rules = self._automation_rules()
        changed = False
        for rule in rules:
            if should_fire_rule(rule, now, idle_seconds):
                self._perform_automation_action(rule)
                rule["last_fired"] = now.isoformat()
                changed = True
        if changed:
            self.config.set("automation_rules", rules)
        self._apply_auto_theme_if_enabled(now)

    def _apply_auto_theme_if_enabled(self, now):
        if not self.config.get("auto_theme_enabled"):
            return
        desired_mode = resolve_auto_theme_mode(
            now,
            self.config.get("auto_theme_day_start"),
            self.config.get("auto_theme_night_start"),
        )
        if desired_mode != self.config.get("theme_mode"):
            self.config.set("theme_mode", desired_mode)
            if self.bubble is not None:
                self.bubble.close()
                self.bubble = None
            if self.history_dialog is not None:
                self.history_dialog.close()
                self.history_dialog = None

    def _perform_automation_action(self, rule):
        action_type = rule.get("action_type")
        rule_name = rule.get("name", "")
        if action_type == "lock":
            handle_power_action("lock")
        elif action_type == "sleep":
            handle_power_action("sleep")
        elif action_type == "notify":
            title = f"Otomasyon: {rule_name}" if rule_name else "Otomasyon"
            message = str(rule.get("action_value") or "Kural calisti.")
            if self.tray_icon is not None:
                self.tray_icon.showMessage(
                    title, message, QSystemTrayIcon.MessageIcon.Information, 8000
                )
            else:
                QMessageBox.information(self, title, message)
            self.notifications.add(title, message)
        elif action_type == "open_url":
            url = str(rule.get("action_value") or "")
            if is_url_safe_to_open(url):
                webbrowser.open(url)

    def _show_automation_rules(self):
        self._register_activity()
        rules = self._automation_rules()
        text = format_automation_rules(rules) if rules else "Henuz bir otomasyon kurali yok."
        box = QMessageBox(self)
        box.setWindowTitle("Otomasyon Kurallari")
        box.setText(text)
        add_button = box.addButton("Yeni Kural Ekle...", QMessageBox.ButtonRole.ActionRole)
        delete_button = (
            box.addButton("Kural Sil...", QMessageBox.ButtonRole.ActionRole)
            if rules
            else None
        )
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        clicked = box.clickedButton()
        if clicked == add_button:
            self._create_automation_rule()
        elif delete_button is not None and clicked == delete_button:
            self._delete_automation_rule()

    def _create_automation_rule(self):
        self._register_activity()
        name, ok = QInputDialog.getText(self, "Yeni Otomasyon Kurali", "Kural adi:")
        if not ok or not name.strip():
            return

        trigger_keys = list(AUTOMATION_TRIGGER_LABELS.keys())
        trigger_labels = list(AUTOMATION_TRIGGER_LABELS.values())
        trigger_label, ok = QInputDialog.getItem(
            self, "Yeni Otomasyon Kurali", "Ne zaman calissin?", trigger_labels, 0, False
        )
        if not ok:
            return
        trigger_type = trigger_keys[trigger_labels.index(trigger_label)]

        if trigger_type == "time_daily":
            time_text, ok = QInputDialog.getText(
                self, "Yeni Otomasyon Kurali", "Saat (SS:DD, orn. 18:30):", text="18:00"
            )
            if not ok:
                return
            trigger_value = parse_hh_mm(time_text)
            if trigger_value is None:
                QMessageBox.warning(
                    self, "Gecersiz Saat", "Saat SS:DD bicimimde olmali (orn. 09:30)."
                )
                return
        else:
            minutes, ok = QInputDialog.getInt(
                self,
                "Yeni Otomasyon Kurali",
                "Kac dakika hareketsizlikten sonra?",
                30,
                1,
                1440,
            )
            if not ok:
                return
            trigger_value = minutes

        action_keys = list(AUTOMATION_ACTION_LABELS.keys())
        action_labels = list(AUTOMATION_ACTION_LABELS.values())
        action_label, ok = QInputDialog.getItem(
            self, "Yeni Otomasyon Kurali", "Ne yapsin?", action_labels, 0, False
        )
        if not ok:
            return
        action_type = action_keys[action_labels.index(action_label)]

        action_value = ""
        if action_type == "notify":
            action_value, ok = QInputDialog.getText(
                self, "Yeni Otomasyon Kurali", "Bildirim mesaji:", text=name.strip()
            )
            if not ok:
                return
            action_value = action_value.strip()
        elif action_type == "open_url":
            action_value, ok = QInputDialog.getText(
                self, "Yeni Otomasyon Kurali", "Acilacak baglanti (https://...):"
            )
            if not ok or not action_value.strip():
                return
            action_value = action_value.strip()
            if not is_url_safe_to_open(action_value):
                QMessageBox.warning(
                    self,
                    "Gecersiz Baglanti",
                    "Bu baglanti acilamaz (yalnizca genel http(s) adreslerine izin verilir).",
                )
                return

        rule = {
            "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
            "name": name.strip(),
            "trigger_type": trigger_type,
            "trigger_value": trigger_value,
            "action_type": action_type,
            "action_value": action_value,
            "enabled": True,
            "last_fired": None,
        }
        rules = self._automation_rules()
        rules.append(rule)
        self.config.set("automation_rules", rules)
        QMessageBox.information(
            self, "Kural Eklendi", f'"{rule["name"]}" kurali eklendi.'
        )

    def _delete_automation_rule(self):
        self._register_activity()
        rules = self._automation_rules()
        if not rules:
            return
        descriptions = [describe_automation_rule(r) for r in rules]
        choice, ok = QInputDialog.getItem(
            self, "Kural Sil", "Silinecek kural:", descriptions, 0, False
        )
        if not ok:
            return
        del rules[descriptions.index(choice)]
        self.config.set("automation_rules", rules)

    # -- ozel komutlar (komut genisletme sistemi) ----------------------------

    def _custom_commands(self):
        """config'teki "custom_commands" listesinin bir kopyasini dondurur
        (DEFAULT_CONFIG'te bilerek yok - bkz. automation_rules'un yanindaki
        yorumdaki ayni gerekce: dict(DEFAULT_CONFIG) sig kopyasi, bir liste
        icin ConfigManager ornekleri arasinda paylasilan degisebilir bir
        varsayilan olurdu)."""
        return list(self.config.get("custom_commands") or [])

    def _run_custom_command(self, url):
        self._register_activity()
        if is_url_safe_to_open(url):
            webbrowser.open(url)

    def _add_custom_command(self):
        """"Özel Komutlar" menusune yeni bir baglanti-acma kisayolu ekler -
        makrolardan (mobil) ve otomasyon kurallarindan (bkz. yukarida)
        farkli olarak burada tetikleyici yok, dogrudan menuden tek
        tiklamayla calistirilir; kod calistirmaz, yalnizca bir URL acar
        (bkz. validate_custom_command/is_url_safe_to_open)."""
        self._register_activity()
        name, ok = QInputDialog.getText(self, "Özel Komut Ekle", "Komut adı:")
        if not ok:
            return
        url, ok = QInputDialog.getText(
            self, "Özel Komut Ekle", "Açılacak bağlantı (https://...):"
        )
        if not ok:
            return
        error = validate_custom_command(name, url)
        if error is not None:
            QMessageBox.warning(self, "Eklenemedi", error)
            return
        commands = self._custom_commands()
        commands.append(
            {
                "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                "name": name.strip(),
                "url": url.strip(),
            }
        )
        self.config.set("custom_commands", commands)
        QMessageBox.information(
            self, "Komut Eklendi", f'"{name.strip()}" komutu eklendi.'
        )

    def _delete_custom_command(self):
        self._register_activity()
        commands = self._custom_commands()
        if not commands:
            return
        names = [c.get("name", "") for c in commands]
        choice, ok = QInputDialog.getItem(
            self, "Komut Sil", "Silinecek komut:", names, 0, False
        )
        if not ok:
            return
        del commands[names.index(choice)]
        self.config.set("custom_commands", commands)

    # -- yedekleme / geri yukleme -------------------------------------------

    def _maybe_auto_backup(self):
        """auto_backup_timer'in her tetiklenisinde (ayrica uygulama acilista
        da bir kez) cagrilir; sessizce hicbir sey yapmayabilir - gercek
        yedekleme sadece ayar acikken ve son yedekten bu yana yeterli
        zaman gectiyse gerceklesir (bkz. should_run_auto_backup)."""
        if not self.config.get("auto_backup_enabled"):
            return
        now = datetime.now()
        if not should_run_auto_backup(self.config.get("auto_backup_last"), now):
            return
        self._run_auto_backup(now)

    def _run_auto_backup(self, now):
        directory = auto_backup_dir()
        backup = {"config": self.config.data, "history": self.history.entries}
        filename = f"{AUTO_BACKUP_PREFIX}{now.strftime('%Y-%m-%d-%H%M%S')}.json"
        try:
            os.makedirs(directory, exist_ok=True)
            with open(os.path.join(directory, filename), "w", encoding="utf-8") as f:
                json.dump(backup, f, ensure_ascii=False, indent=2)
            prune_old_backups(directory, AUTO_BACKUP_MAX_COUNT)
        except OSError:
            return
        self.config.set("auto_backup_last", now.isoformat())

    def _toggle_auto_backup(self, checked):
        self.config.set("auto_backup_enabled", checked)
        if checked:
            self._maybe_auto_backup()

    def _toggle_context_aware(self, checked):
        self.config.set("context_aware_enabled", checked)

    def _export_backup(self):
        self._register_activity()
        path, _ = QFileDialog.getSaveFileName(
            self, "Yedek Al", "ai-kedi-asistani-yedek.json", "JSON Dosyalari (*.json)"
        )
        if not path:
            return
        backup = {
            "config": self.config.data,
            "history": self.history.entries,
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(backup, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            QMessageBox.warning(self, "Yedek Alinamadi", f"Yedek kaydedilemedi: {exc}")
            return
        QMessageBox.information(
            self,
            "Yedek Alindi",
            f"Yedek kaydedildi:\n{path}\n\n"
            "Not: Bu dosya Gemini API anahtarinizi ve uzaktan kumanda PIN'inizi "
            "duz metin olarak icerir - baskalariyla paylasmayin.",
        )

    def _import_backup(self):
        self._register_activity()
        path, _ = QFileDialog.getOpenFileName(
            self, "Yedekten Geri Yukle", "", "JSON Dosyalari (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                backup = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "Geri Yukleme Basarisiz", f"Dosya okunamadi: {exc}")
            return
        if not isinstance(backup, dict):
            QMessageBox.warning(self, "Geri Yukleme Basarisiz", "Gecersiz yedek dosyasi.")
            return

        confirm = QMessageBox.question(
            self,
            "Geri Yukleme Onayi",
            "Mevcut ayarlar ve sohbet gecmisi bu yedekle degistirilecek. Devam edilsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        config_data = backup.get("config")
        if isinstance(config_data, dict):
            self.config.data.update(config_data)
            self.config.save()
        history_data = backup.get("history")
        if isinstance(history_data, list):
            self.history.entries = history_data
            self.history.save()
            if self.history_dialog is not None:
                self.history_dialog.refresh()

        QMessageBox.information(
            self,
            "Geri Yuklendi",
            "Yedek geri yuklendi. Degisikliklerin tam olarak yansimasi icin "
            "uygulamayi yeniden baslatmaniz onerilir.",
        )

    def _export_settings_profile(self):
        self._register_activity()
        path, _ = QFileDialog.getSaveFileName(
            self, "Ayarlari Disa Aktar", "ai-kedi-asistani-profil.json", "JSON Dosyalari (*.json)"
        )
        if not path:
            return
        profile = build_settings_profile(self.config.data)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(profile, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            QMessageBox.warning(self, "Disa Aktarilamadi", f"Dosya kaydedilemedi: {exc}")
            return
        QMessageBox.information(
            self,
            "Ayarlar Disa Aktarildi",
            f"Ayarlar kaydedildi:\n{path}\n\n"
            "Bu dosya API anahtarinizi ya da PIN'inizi icermez, baskalariyla "
            "paylasabilirsiniz.",
        )

    def _import_settings_profile(self):
        self._register_activity()
        path, _ = QFileDialog.getOpenFileName(
            self, "Ayarlari Ice Aktar", "", "JSON Dosyalari (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                profile_data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "Ice Aktarma Basarisiz", f"Dosya okunamadi: {exc}")
            return
        applied = apply_settings_profile(self.config, profile_data)
        if not applied:
            QMessageBox.warning(self, "Ice Aktarma Basarisiz", "Dosyada taninan bir ayar bulunamadi.")
            return
        QMessageBox.information(
            self,
            "Ayarlar Ice Aktarildi",
            f"{len(applied)} ayar guncellendi. Degisikliklerin tam olarak yansimasi "
            "icin uygulamayi yeniden baslatmaniz onerilir.",
        )

    # -- hakkinda -------------------------------------------------------

    def _show_about(self):
        self._register_activity()
        QMessageBox.about(
            self,
            "Hakkinda",
            f"<b>AI Kedi Asistani</b><br>"
            f"Surum {APP_VERSION}<br><br>"
            "Google Gemini destekli, masaustunde gezinen bir kedi asistani.<br><br>"
            f'<a href="https://github.com/{GITHUB_REPO}">GitHub deposu</a>',
        )

    # -- guncelleme kontrolu ----------------------------------------------

    def _check_for_updates(self, manual=False):
        if self.update_worker is not None and self.update_worker.isRunning():
            return
        self._update_check_manual = manual
        self._last_update_info = None
        self.update_worker = UpdateCheckWorker(self)
        self.update_worker.update_available.connect(self._on_update_available)
        self.update_worker.check_finished.connect(self._on_update_check_finished)
        self.update_worker.start()

    def _on_update_available(self, tag, html_url, download_url, checksum_url):
        self._last_update_info = (tag, html_url, download_url, checksum_url)
        if not self._update_check_manual and self.tray_icon is not None:
            update_message = f"AI Kedi Asistani {tag} yayinlandi. Detaylar icin tiklayin."
            self.tray_icon.showMessage(
                "Yeni surum mevcut",
                update_message,
                QSystemTrayIcon.MessageIcon.Information,
                8000,
            )
            self.notifications.add("Yeni surum mevcut", update_message)

    def _on_update_check_finished(self, success, error_message):
        if not self._update_check_manual:
            return
        if not success:
            QMessageBox.warning(
                self, "Guncelleme Kontrolu", f"Guncelleme kontrol edilemedi: {error_message}"
            )
            return
        if self._last_update_info is not None:
            self._offer_update(*self._last_update_info)
        else:
            QMessageBox.information(
                self, "Guncelleme Kontrolu", f"Kullandiginiz surum guncel ({APP_VERSION})."
            )

    def _on_tray_message_clicked(self):
        if self._last_update_info is not None:
            self._offer_update(*self._last_update_info)

    def _offer_update(self, tag, html_url, download_url, checksum_url):
        can_auto_update = getattr(sys, "frozen", False) and sys.platform == "win32" and download_url

        box = QMessageBox(self)
        box.setWindowTitle("Guncelleme Mevcut")
        if can_auto_update:
            box.setText(
                f"Yeni surum mevcut: {tag} (su an: {APP_VERSION})\n\n"
                "Otomatik olarak indirilip kurulsun mu? Uygulama kisa sureligine "
                "kapanip yeniden acilacak."
            )
            download_btn = box.addButton("Simdi Indir ve Kur", QMessageBox.ButtonRole.AcceptRole)
        else:
            box.setText(
                f"Yeni surum mevcut: {tag} (su an: {APP_VERSION})\n\n"
                f"{html_url}\n\n"
                "(Otomatik guncelleme yalnizca derlenmis .exe surumunde "
                "calisir; kaynak koddan calistiriyorsaniz elle indirin.)"
            )
            download_btn = None
        box.addButton("Daha Sonra", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if download_btn is not None and box.clickedButton() == download_btn:
            self._start_update_download(download_url, checksum_url)

    def _start_update_download(self, download_url, checksum_url):
        progress = QProgressDialog("Guncelleme indiriliyor...", "Iptal", 0, 100, self)
        progress.setWindowTitle("Guncelleniyor")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)

        worker = UpdateDownloadWorker(download_url, checksum_url, self)
        self._update_download_worker = worker  # referansi canli tut

        worker.progress.connect(progress.setValue)
        progress.canceled.connect(worker.terminate)

        def on_ok(path):
            progress.close()
            restart_box = QMessageBox(self)
            restart_box.setWindowTitle("Guncelleme Indirildi")
            restart_box.setText(
                "Guncelleme indirildi ve dogrulandi. Simdi yeniden baslatilsin mi?"
            )
            restart_btn = restart_box.addButton("Simdi Yeniden Baslat", QMessageBox.ButtonRole.AcceptRole)
            restart_box.addButton("Daha Sonra", QMessageBox.ButtonRole.RejectRole)
            restart_box.exec()
            if restart_box.clickedButton() == restart_btn:
                if not apply_update_and_restart(path):
                    QMessageBox.warning(
                        self, "Guncelleme", "Guncelleme uygulanamadi; elle indirip kurmayi deneyin."
                    )

        def on_error(message):
            progress.close()
            QMessageBox.warning(self, "Guncelleme", message)

        worker.finished_ok.connect(on_ok)
        worker.finished_error.connect(on_error)
        worker.start()

    # -- sistem tepsisi -------------------------------------------------------

    def _setup_tray_icon(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray_icon = QSystemTrayIcon(QIcon(self.pixmaps["norm"]), self)
        self.tray_icon.setToolTip(self.config.get("character_name"))

        tray_menu = QMenu()
        show_action = QAction("Goster", self)
        show_action.triggered.connect(self._restore_from_tray)
        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        exit_action = QAction("Cikis", self)
        exit_action.triggered.connect(QApplication.instance().quit)
        tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.messageClicked.connect(self._on_tray_message_clicked)
        self.tray_icon.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._restore_from_tray()

    def _restore_from_tray(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _toggle_autostart(self, checked):
        set_autostart(checked)

    def _toggle_theme(self, checked):
        self.config.set("theme_mode", "light" if checked else "dark")
        # Acik konuşma balonu/gecmis panelini kapat - bir sonraki acilista
        # yeni temayla yeniden olusturulacaklar (bkz. _open_bubble/_open_history).
        if self.bubble is not None:
            self.bubble.close()
            self.bubble = None
        if self.history_dialog is not None:
            self.history_dialog.close()
            self.history_dialog = None

    def _toggle_auto_theme(self, checked):
        self.config.set("auto_theme_enabled", checked)
        if checked:
            self._apply_auto_theme_if_enabled(datetime.now())

    # -- sag tik menusu -----------------------------------------------------

    def contextMenuEvent(self, event):
        self._register_activity()
        menu = QMenu(self)
        menu.setStyleSheet(
            """
            QMenu { background-color: #202028; color: white; border: 1px solid #444; }
            QMenu::item { padding: 6px 20px; }
            QMenu::item:selected { background-color: #3a6cf6; }
            """
        )

        size_menu = menu.addMenu("Boyut Degistir")
        size_group = QActionGroup(self)
        size_group.setExclusive(True)
        for percent in (50, 75, 100, 150):
            action = QAction(f"%{percent}", self)
            action.setCheckable(True)
            action.setChecked(self.config.get("scale_percent") == percent)
            action.triggered.connect(lambda checked, p=percent: self._set_scale(p))
            size_group.addAction(action)
            size_menu.addAction(action)

        skins = discover_skins()
        if len(skins) > 1:
            skin_menu = menu.addMenu("Kedi Skin'i")
            skin_group = QActionGroup(self)
            skin_group.setExclusive(True)
            current_skin = self.config.get("skin")
            for skin_name in skins:
                action = QAction(skin_name, self)
                action.setCheckable(True)
                action.setChecked(skin_name == current_skin)
                action.triggered.connect(lambda checked, s=skin_name: self._set_skin(s))
                skin_group.addAction(action)
                skin_menu.addAction(action)

        personality_menu = menu.addMenu("Kisilik")
        personality_group = QActionGroup(self)
        personality_group.setExclusive(True)
        current_personality = self.config.get("personality")
        for personality_name in PERSONALITY_PRESETS:
            action = QAction(personality_name, self)
            action.setCheckable(True)
            action.setChecked(personality_name == current_personality)
            action.triggered.connect(
                lambda checked, p=personality_name: self._set_personality(p)
            )
            personality_group.addAction(action)
            personality_menu.addAction(action)

        rename_action = QAction("Kediye Isim Ver", self)
        rename_action.triggered.connect(self._rename_character)
        menu.addAction(rename_action)

        history_action = QAction("Sohbet Gecmisi", self)
        history_action.triggered.connect(self._open_history)
        menu.addAction(history_action)

        api_key_action = QAction("Gemini API Key Ayarlari", self)
        api_key_action.triggered.connect(self._set_api_key)
        menu.addAction(api_key_action)

        remote_action = QAction("Uzaktan Kumanda Bilgisi", self)
        remote_action.triggered.connect(self._show_remote_info)
        menu.addAction(remote_action)

        access_log_action = QAction("Erisim Gunlugu", self)
        access_log_action.triggered.connect(self._show_access_log)
        menu.addAction(access_log_action)

        notification_history_action = QAction("Bildirim Gecmisi", self)
        notification_history_action.triggered.connect(self._show_notification_history)
        menu.addAction(notification_history_action)

        screenshot_history_action = QAction("Ekran Goruntusu Gecmisi", self)
        screenshot_history_action.triggered.connect(self._show_screenshot_history)
        menu.addAction(screenshot_history_action)

        usage_stats_action = QAction("Kullanım İstatistikleri", self)
        usage_stats_action.triggered.connect(self._show_usage_stats)
        menu.addAction(usage_stats_action)

        secure_notepad_action = QAction("Şifreli Not Defteri", self)
        secure_notepad_action.triggered.connect(self._show_secure_notepad)
        menu.addAction(secure_notepad_action)


        reminder_action = QAction("Hatirlatici Kur", self)
        reminder_action.triggered.connect(self._create_reminder)
        menu.addAction(reminder_action)

        if self._repeating_reminder_timers:
            stop_reminders_action = QAction("Tekrarlayan Hatirlaticilari Durdur", self)
            stop_reminders_action.triggered.connect(self._stop_repeating_reminders)
            menu.addAction(stop_reminders_action)

        automation_action = QAction("Otomasyon Kurallari...", self)
        automation_action.triggered.connect(self._show_automation_rules)
        menu.addAction(automation_action)

        custom_commands = self._custom_commands()
        custom_menu = menu.addMenu("Özel Komutlar")
        if not custom_commands:
            empty_action = QAction("(henüz komut yok)", self)
            empty_action.setEnabled(False)
            custom_menu.addAction(empty_action)
        else:
            for command in custom_commands:
                command_action = QAction(command.get("name", ""), self)
                command_action.triggered.connect(
                    lambda checked, url=command.get("url", ""): self._run_custom_command(url)
                )
                custom_menu.addAction(command_action)
            custom_menu.addSeparator()
        add_command_action = QAction("Komut Ekle...", self)
        add_command_action.triggered.connect(self._add_custom_command)
        custom_menu.addAction(add_command_action)
        if custom_commands:
            delete_command_action = QAction("Komut Sil...", self)
            delete_command_action.triggered.connect(self._delete_custom_command)
            custom_menu.addAction(delete_command_action)

        autostart_action = QAction("Windows ile Baslat", self)
        autostart_action.setCheckable(True)
        autostart_action.setChecked(is_autostart_enabled())
        autostart_action.toggled.connect(self._toggle_autostart)
        menu.addAction(autostart_action)

        light_theme_action = QAction("Acik Tema", self)
        light_theme_action.setCheckable(True)
        light_theme_action.setChecked(self.config.get("theme_mode") == "light")
        light_theme_action.toggled.connect(self._toggle_theme)
        menu.addAction(light_theme_action)

        auto_theme_action = QAction("Otomatik Gece/Gunduz Temasi", self)
        auto_theme_action.setCheckable(True)
        auto_theme_action.setChecked(bool(self.config.get("auto_theme_enabled")))
        auto_theme_action.toggled.connect(self._toggle_auto_theme)
        menu.addAction(auto_theme_action)

        update_action = QAction("Guncellemeleri Kontrol Et", self)
        update_action.triggered.connect(lambda: self._check_for_updates(manual=True))
        menu.addAction(update_action)

        menu.addSeparator()

        backup_action = QAction("Yedek Al...", self)
        backup_action.triggered.connect(self._export_backup)
        menu.addAction(backup_action)

        restore_action = QAction("Yedekten Geri Yukle...", self)
        restore_action.triggered.connect(self._import_backup)
        menu.addAction(restore_action)

        export_profile_action = QAction("Ayarlari Disa Aktar...", self)
        export_profile_action.triggered.connect(self._export_settings_profile)
        menu.addAction(export_profile_action)

        import_profile_action = QAction("Ayarlari Ice Aktar...", self)
        import_profile_action.triggered.connect(self._import_settings_profile)
        menu.addAction(import_profile_action)

        auto_backup_action = QAction("Otomatik Yedekleme (Gunluk)", self)
        auto_backup_action.setCheckable(True)
        auto_backup_action.setChecked(self.config.get("auto_backup_enabled"))
        auto_backup_action.toggled.connect(self._toggle_auto_backup)
        menu.addAction(auto_backup_action)

        context_aware_action = QAction("Onceki Sohbeti Hatirla (Baglam)", self)
        context_aware_action.setCheckable(True)
        context_aware_action.setChecked(self.config.get("context_aware_enabled"))
        context_aware_action.toggled.connect(self._toggle_context_aware)
        menu.addAction(context_aware_action)

        menu.addSeparator()

        about_action = QAction("Hakkinda", self)
        about_action.triggered.connect(self._show_about)
        menu.addAction(about_action)

        menu.addSeparator()
        exit_action = QAction("Cikis", self)
        exit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(exit_action)

        menu.exec(event.globalPos())

    def _set_scale(self, percent):
        self.config.set("scale_percent", percent)
        self.scale_factor = percent / 100.0
        old_x, old_y = self.x(), self.y()

        self._load_pixmaps()
        self._set_state(self.state)

        screen = QApplication.primaryScreen().availableGeometry()
        new_x = min(max(old_x, screen.left()), screen.right() - self.width())
        new_y = min(max(old_y, screen.top()), screen.bottom() - self.height())
        self.move(new_x, new_y)
        self.config.set("pos_x", new_x)
        self.config.set("pos_y", new_y)

    def _set_skin(self, skin_name):
        self.config.set("skin", skin_name)
        old_x, old_y = self.x(), self.y()

        self._load_pixmaps()
        self._set_state(self.state)

        screen = QApplication.primaryScreen().availableGeometry()
        new_x = min(max(old_x, screen.left()), screen.right() - self.width())
        new_y = min(max(old_y, screen.top()), screen.bottom() - self.height())
        self.move(new_x, new_y)
        self.config.set("pos_x", new_x)
        self.config.set("pos_y", new_y)

    def _set_personality(self, personality_name):
        self._register_activity()
        self.config.set("personality", personality_name)

    def _rename_character(self):
        current = self.config.get("character_name")
        name, ok = QInputDialog.getText(self, "Kediye Isim Ver", "Yeni isim:", text=current)
        if ok and name.strip():
            self.config.set("character_name", name.strip())
            self.bubble = None  # yeni isimle yeniden olusturulsun
            self.history_dialog = None  # yeni isimle yeniden olusturulsun

    def _set_api_key(self):
        current = self.config.get("gemini_api_key")
        key, ok = QInputDialog.getText(
            self,
            "Gemini API Key Ayarlari",
            "API anahtarinizi girin:",
            QLineEdit.EchoMode.Password,
            current,
        )
        if ok:
            self.config.set("gemini_api_key", key.strip())


# --------------------------------------------------------------------------
# Giris noktasi
# --------------------------------------------------------------------------

def main():
    install_crash_handler()

    # Windows Gezgini sag tik menusunden "Kediyle Gönder" ile baslatildiysa
    # ve uygulama ZATEN calisiyorsa, dosya yolunu o calisan kopyaya iletip
    # burada hemen cikilir - ikinci bir GUI/simge acilmaz.
    send_file_path = parse_send_file_arg(sys.argv)
    if send_file_path and send_file_to_running_instance(send_file_path):
        return

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    config = ConfigManager(CONFIG_PATH)
    cat = CatCharacter(config)
    cat.show()

    if send_file_path:
        cat.queue_outbound_file(send_file_path)

    app.aboutToQuit.connect(cat.remote_server.stop)
    app.aboutToQuit.connect(cat.live_control_server.stop)
    app.aboutToQuit.connect(cat.send_with_cat_ipc_server.stop)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()


# ==========================================================================
# PyInstaller ile tek dosya (.exe) yapma adimlari (Windows)
# ==========================================================================
#
# 1) Sanal ortam olusturup bagimliliklari kurun:
#
#       python -m venv venv
#       venv\Scripts\activate
#       pip install -r requirements.txt
#       pip install pyinstaller
#
# 2) "assets" klasorunun bu dosyayla (main.py) ayni klasorde oldugundan
#    emin olun (fuff_norm.png, fuff_zzz.png, fuff_smile.png,
#    fuff_stern.png, fuff_fear.png).
#
# 3) Proje klasorunde asagidaki komutu calistirin. --add-data ile assets
#    klasoru exe'nin icine gomulur (Windows'ta kaynak ve hedef ";" ile
#    ayrilir):
#
#       pyinstaller --onefile --windowed --name "AI-Kedi-Asistani" ^
#           --add-data "assets;assets" main.py
#
#    Ozel bir uygulama simgesi eklemek isterseniz (icon.ico dosyasi ile):
#
#       pyinstaller --onefile --windowed --name "AI-Kedi-Asistani" ^
#           --add-data "assets;assets" --icon "icon.ico" main.py
#
# 4) Derleme bitince exe dosyasi "dist\AI-Kedi-Asistani.exe" altinda
#    olusur. config.json, exe ilk calistirildiginda exe ile ayni klasorde
#    otomatik olarak olusturulur (API anahtari ve pozisyon orada saklanir).
#
# 5) --windowed bayragi konsol penceresini gizler. Hata ayiklarken
#    gecici olarak bu bayragi kaldirip konsolu gorebilirsiniz.
#
# Not: --onefile modunda uygulama her acildiginda assets klasorunu gecici
# bir klasore (sys._MEIPASS) acar; koddaki resource_path() fonksiyonu bunu
# otomatik olarak yonetir, ek bir islem yapmaniza gerek yoktur.
# ==========================================================================

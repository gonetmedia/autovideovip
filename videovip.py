import streamlit as st
import os
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import cv2
import numpy as np
import tempfile
import zipfile
from pathlib import Path
import platform
import requests
from urllib.parse import urlparse
import logging
import hashlib
import sqlite3

# --- Kullanıcı Yetkilendirme ---

def create_usertable():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS userstable(username TEXT, password TEXT, approved INTEGER DEFAULT 0)')
    conn.commit()
    conn.close()

def add_userdata(username, password):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    approved_status = 1 if username.lower() == "admin" else 0
    c.execute('INSERT INTO userstable(username,password, approved) VALUES (?,?,?)', (username, password, approved_status))
    conn.commit()
    conn.close()

def login_user(username, password):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT * FROM userstable WHERE username =? AND password = ?', (username, hash_password(password)))
    data = c.fetchall()
    conn.close()
    return data

def check_user_approved(username):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT approved FROM userstable WHERE username =?', (username,))
    approved = c.fetchone()
    conn.close()
    return approved[0] if approved else 0

def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def show_signup_form():
    st.subheader("Kayıt Ol")
    new_user = st.text_input("Kullanıcı Adı")
    new_password = st.text_input("Şifre", type='password')

    if st.button("Kayıt Ol"):
        create_usertable()
        hashed_new_password = hash_password(new_password)
        add_userdata(new_user, hashed_new_password)
        st.success("Başarıyla kayıt oldunuz. Admin onayını bekleyin.")

def show_login_form():
    st.subheader("Giriş Yap")
    username = st.text_input("Kullanıcı Adı")
    password = st.text_input("Şifre", type='password')

    if st.button("Giriş"):
        create_usertable()
        result = login_user(username, password)

        if result:
            if check_user_approved(username):
                # Oturum açma durumunu sakla
                st.session_state["logged_in"] = True
                st.session_state["username"] = username
                st.session_state["is_admin"] = (username.lower() == "admin")  # Kullanıcının admin olup olmadığını kontrol et
                st.success("Giriş başarılı!")
            else:
                st.warning("Hesabınız henüz admin tarafından onaylanmadı.")
        else:
            st.warning("Yanlış kullanıcı adı veya şifre")

def show_logout_button():
    if st.button("Çıkış Yap"):
        # Kullanıcının oturumunu sonlandır
        st.session_state.clear()  # Tüm oturum durumunu temizle
        st.success("Çıkış yapıldı!")

def show_admin_panel():
    st.title("Admin Paneli")
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT username, approved FROM userstable')
    users = c.fetchall()
    conn.close()

    if users:
        users_df = pd.DataFrame(users, columns=["Kullanıcı Adı", "Onay Durumu"])
        st.write(users_df)

        selected_user = st.selectbox("Onaylanacak veya Deaktif Edilecek Kullanıcı Seçin", users_df["Kullanıcı Adı"])
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Kullanıcıyı Onayla"):
                conn = sqlite3.connect('users.db')
                c = conn.cursor()
                c.execute('UPDATE userstable SET approved = 1 WHERE username = ?', (selected_user,))
                conn.commit()
                conn.close()
                st.success(f"{selected_user} onaylandı!")

        with col2:
            if st.button("Kullanıcıyı Deaktif Et"):
                conn = sqlite3.connect('users.db')
                c = conn.cursor()
                c.execute('UPDATE userstable SET approved = 0 WHERE username = ?', (selected_user,))
                conn.commit()
                conn.close()
                st.success(f"{selected_user} deaktive edildi!")

    else:
        st.info("Henüz kayıtlı kullanıcı yok.")

# --- Video İşleme Fonksiyonları ---

def download_video(url, temp_dir):
    try:
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise ValueError("Geçersiz URL formatı")
        
        video_filename = f"temp_video_{os.path.basename(parsed_url.path)}"
        if not video_filename.endswith(('.mp4', '.avi', '.mov', '.mkv')):
            video_filename += '.mp4'

        temp_path = os.path.join(temp_dir, video_filename)

        response = requests.get(url, stream=True)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024 
        progress_bar = st.progress(0)

        with open(temp_path, 'wb') as file:
            downloaded = 0
            for data in response.iter_content(block_size):
                file.write(data)
                downloaded += len(data)
                if total_size:
                    progress = int(100 * downloaded / total_size)
                    progress_bar.progress(progress / 100)

        return temp_path
    except requests.exceptions.RequestException as e:
        st.error(f"Video indirme hatası: {str(e)}")
        return None
    except Exception as e:
        st.error(f"Beklenmeyen hata: {str(e)}")
        return None

def is_url(path):
    try:
        result = urlparse(path)
        return all([result.scheme, result.netloc])
    except:
        return False

def hex_to_bgr(hex_color):
    hex_color = hex_color.lstrip('#')
    rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    return (rgb[2], rgb[1], rgb[0])

def wrap_text(text, font, max_width):
    lines = []
    words = text.split(" ")
    current_line = ""
    for word in words:
        test_line = current_line + (" " if current_line else "") + word
        bbox = font.getbbox(test_line)
        text_width = bbox[2] - bbox[0]
        if text_width <= max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines

def draw_text_with_pillow(frame, text, x, y, font_size, font_path, text_color, box_color):
    pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_image)

    try:
        font = ImageFont.truetype(font_path, font_size)
    except Exception as e:
        st.error(f"Font dosyası açılamadı: {e}")
        return frame

    max_width = VIDEO_WIDTH_9_16 - 2 * TEXT_MARGIN_X
    lines = wrap_text(text, font, max_width)
    line_height = font.getbbox("A")[3] + LINE_SPACING
    total_text_height = len(lines) * line_height - LINE_SPACING

    background_top = y - total_text_height - 30
    background_bottom = y + 30
    background_left = TEXT_MARGIN_X - 10
    background_right = VIDEO_WIDTH_9_16 - TEXT_MARGIN_X + 10

    bg_color_rgb = (box_color[2], box_color[1], box_color[0])
    text_color_rgb = (text_color[2], text_color[1], text_color[0])

    draw.rectangle([(background_left, background_top), (background_right, background_bottom)], fill=bg_color_rgb)

    for i, line in enumerate(lines):
        line_y = y - total_text_height + i * line_height
        draw.text((x, line_y), line, font=font, fill=text_color_rgb)

    return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

def process_video(title, description, input_video_path, output_video_path, logo_path, font_path, title_font_size, desc_font_size, text_color, box_color, top_bar_height, bottom_bar_height):
    global VIDEO_WIDTH_9_16, VIDEO_HEIGHT_9_16, FPS, TITLE_DISPLAY_TIME, GAP_DURATION
    global TEXT_MARGIN_X, TEXT_POSITION_Y, LINE_SPACING, LOGO_WIDTH, LOGO_HEIGHT, LOGO_TOP_MARGIN

    cap = cv2.VideoCapture(input_video_path)
    if not cap.isOpened():
        st.error(f"Video açılamadı: {input_video_path}")
        return

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_video_path, fourcc, FPS, (VIDEO_WIDTH_9_16, VIDEO_HEIGHT_9_16))

    logo = None
    if logo_path:
        try:
            logo = cv2.imread(str(logo_path), cv2.IMREAD_UNCHANGED)
            logo = cv2.resize(logo, (LOGO_WIDTH, LOGO_HEIGHT), interpolation=cv2.INTER_AREA)
        except Exception as e:
            st.warning(f"Logo yüklenirken hata oluştu: {e}")

    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        output_frame = np.full((VIDEO_HEIGHT_9_16, VIDEO_WIDTH_9_16, 3), hex_to_bgr(BACKGROUND_COLOR), dtype=np.uint8)

        cap_height, cap_width = frame.shape[:2]
        if cap_width / cap_height > VIDEO_WIDTH_9_16 / VIDEO_HEIGHT_9_16:
            new_width = VIDEO_WIDTH_9_16
            new_height = int(new_width * (cap_height / cap_width))
        else:
            new_height = VIDEO_HEIGHT_9_16
            new_width = int(new_height * (cap_width / cap_height))

        resized_frame = cv2.resize(frame, (new_width, new_height))

        x_offset = (VIDEO_WIDTH_9_16 - new_width) // 2
        y_offset = (VIDEO_HEIGHT_9_16 - new_height) // 2
        output_frame[y_offset:y_offset + new_height, x_offset:x_offset + new_width] = resized_frame

        if frame_count < FPS * TITLE_DISPLAY_TIME:
            output_frame = draw_text_with_pillow(output_frame, title, TEXT_MARGIN_X, TEXT_POSITION_Y, title_font_size, font_path, text_color, box_color)
        elif FPS * (TITLE_DISPLAY_TIME + GAP_DURATION) <= frame_count:
            output_frame = draw_text_with_pillow(output_frame, description, TEXT_MARGIN_X, TEXT_POSITION_Y, desc_font_size, font_path, text_color, box_color)

        output_frame[:top_bar_height, :] = hex_to_bgr(BAR_COLOR)
        output_frame[-bottom_bar_height:, :] = hex_to_bgr(BAR_COLOR)

        if logo is not None:
            logo_x = (VIDEO_WIDTH_9_16 - LOGO_WIDTH) // 2
            logo_y = LOGO_TOP_MARGIN
            output_frame[logo_y:logo_y + LOGO_HEIGHT, logo_x:logo_x + LOGO_WIDTH] = logo

        out.write(output_frame)
        frame_count += 1

    cap.release()
    out.release()

def process_videos_from_csv(df, temp_dir, output_zip_path, **kwargs):
    for index, row in df.iterrows():
        title = row["title"]
        description = row["description"]
        input_video_path = row["input_video_path"]

        st.write(f"Video işleniyor -> {title}")

        if is_url(input_video_path):
            st.info(f"Online video indiriliyor: {input_video_path}")
            temp_video_input = download_video(input_video_path, temp_dir)
            if not temp_video_input:
                st.error(f"Video indirilemedi: {input_video_path}")
                continue
            input_video_path = temp_video_input
        elif not os.path.exists(input_video_path):
            st.error(f"Yerel video bulunamadı: {input_video_path}")
            continue

        output_video_path = os.path.join(temp_dir, f"output_video_{index + 1}.mp4")

        try:
            process_video(
                title=title,
                description=description,
                input_video_path=input_video_path,
                output_video_path=output_video_path,
                logo_path=kwargs.get("logo_path"),
                font_path=kwargs.get("font_path"),
                title_font_size=kwargs.get("title_font_size"),
                desc_font_size=kwargs.get("desc_font_size"),
                text_color=kwargs.get("text_color"),
                box_color=kwargs.get("box_color"),
                top_bar_height=kwargs.get("top_bar_height"),
                bottom_bar_height=kwargs.get("bottom_bar_height"),
            )

            if not os.path.exists(output_video_path):
                st.error(f"Çıktı dosyası oluşturulamadı: {output_video_path}")
                continue

            st.success(f"Video başarıyla işlendi: {output_video_path}")

            with zipfile.ZipFile(output_zip_path, 'a') as zipf:
                zipf.write(output_video_path, arcname=os.path.basename(output_video_path))

        except Exception as e:
            st.error(f"Video işleme hatası: {str(e)}")
            continue

# --- Font Yönetimi Fonksiyonları ---

def find_system_font():
    system_font_paths = {
        'Windows': [
            'C:/Windows/Fonts',
            str(Path.home() / "AppData/Local/Microsoft/Windows/Fonts")
        ],
        'Darwin': [
            '/System/Library/Fonts',
            '/Library/Fonts',
            str(Path.home() / "Library/Fonts")
        ],
        'Linux': [
            '/usr/share/fonts',
            '/usr/local/share/fonts',
            str(Path.home() / ".local/share/fonts")
        ]
    }

    system = platform.system()
    if system in system_font_paths:
        for font_dir in system_font_paths[system]:
            if os.path.exists(font_dir):
                for root, _, files in os.walk(font_dir):
                    if 'arial.ttf' in [f.lower() for f in files]:
                        return os.path.join(root, 'arial.ttf')
    return None

def validate_font(font_path):
    try:
        ImageFont.truetype(font_path, 40)
        return True
    except Exception:
        return False

def setup_font():
    uploaded_font = st.sidebar.file_uploader("Font Yükle (TTF/OTF)", type=["ttf", "otf"])

    if uploaded_font:
        try:
            temp_font = tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_font.name).suffix)
            temp_font.write(uploaded_font.getvalue())
            temp_font.close()

            if validate_font(temp_font.name):
                st.sidebar.success("Font başarıyla yüklendi!")
                return temp_font.name
            else:
                os.unlink(temp_font.name)
                st.sidebar.error("Geçersiz font dosyası!")
        except Exception as e:
            st.sidebar.error(f"Font yükleme hatası: {str(e)}")

    default_font = find_system_font()
    if default_font:
        st.sidebar.info("Varsayılan sistem fontu (Arial) kullanılıyor")
        return default_font

    try:
        from PIL import ImageFont
        default_font = ImageFont.load_default()
        st.sidebar.info("PIL varsayılan fontu kullanılıyor")
        return default_font
    except Exception as e:
        st.sidebar.error(f"Varsayılan font yüklenemedi: {str(e)}")
        return None

# --- Streamlit Uygulaması ---

# Logging ayarları
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    st.title("Video İşleme Uygulaması")

    # Streamlit yan panelini ekleme
    st.sidebar.header("Kullanıcı Girişi ve Ayarlar")

    global VIDEO_WIDTH_9_16, VIDEO_HEIGHT_9_16, FPS, TITLE_DISPLAY_TIME, GAP_DURATION
    global TEXT_MARGIN_X, TEXT_POSITION_Y, LINE_SPACING, LOGO_WIDTH, LOGO_HEIGHT, LOGO_TOP_MARGIN
    global BACKGROUND_COLOR, BAR_COLOR

    VIDEO_WIDTH_9_16 = 1080
    VIDEO_HEIGHT_9_16 = 1920
    FPS = 30
    TITLE_DISPLAY_TIME = 8
    GAP_DURATION = 2
    TEXT_MARGIN_X = 15
    TEXT_POSITION_Y = VIDEO_HEIGHT_9_16 - 310
    LINE_SPACING = 20
    LOGO_WIDTH = 150
    LOGO_HEIGHT = 150
    LOGO_TOP_MARGIN = 80

    # Kullanıcı giriş durumu kontrolü
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    # Giriş yapmamışsa giriş veya kayıt ol formunu göster
    if not st.session_state["logged_in"]:
        login_choice = st.radio("İşlem Seçin:", ("Giriş Yap", "Kayıt Ol"))
        if login_choice == "Giriş Yap":
            show_login_form()
        elif login_choice == "Kayıt Ol":
            show_signup_form()
    else:
        show_logout_button()

        if st.session_state["username"].lower() == "admin":
            show_admin_panel()
        else:
            # Normal kullanıcı işlemleri
            uploaded_csv = st.sidebar.file_uploader("CSV Dosyası Yükle", type=["csv"])
            uploaded_logo = st.sidebar.file_uploader("Logo Yükle (PNG)", type=["png"])

            if uploaded_logo:
                temp_logo = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                temp_logo.write(uploaded_logo.getvalue())
                logo_path = temp_logo.name
            else:
                logo_path = None

            font_path = setup_font()
            if not font_path:
                st.error("Font sistemi başlatılamadı!")
                return

            st.sidebar.subheader("Font Boyutları")
            title_font_size = st.sidebar.slider("Başlık Font Boyutu", 20, 100, 45)
            desc_font_size = st.sidebar.slider("Açıklama Font Boyutu", 15, 80, 30)

            st.sidebar.subheader("Renk Ayarları")
            BACKGROUND_COLOR = st.sidebar.color_picker("Arka Plan Rengi", "#00345B")
            text_color_hex = st.sidebar.color_picker("Yazı Rengi", "#FFFFFF")
            box_color_hex = st.sidebar.color_picker("Metin Kutusu Rengi", "#A3D4F7")
            BAR_COLOR = st.sidebar.color_picker("Çubuk Rengi", "#194E8A")

            st.sidebar.subheader("Çubuk Ayarları")
            col1, col2 = st.sidebar.columns(2)
            top_bar_height = col1.number_input("Üst Çubuk Yüksekliği", 10, 800, 150)
            bottom_bar_height = col2.number_input("Alt Çubuk Yüksekliği", 10, 800, 150)

            if uploaded_csv is not None:
                df = pd.read_csv(uploaded_csv)
                st.write("CSV Dosyası Yüklendi:", df)
                
                if st.button("Videoları İşle"):
                    with tempfile.TemporaryDirectory() as temp_dir:
                        output_zip_path = os.path.join(temp_dir, "output_videos.zip")
                        try:
                            process_videos_from_csv(
                                df=df,
                                temp_dir=temp_dir,
                                output_zip_path=output_zip_path,
                                logo_path=logo_path,
                                font_path=font_path,
                                title_font_size=title_font_size,
                                desc_font_size=desc_font_size,
                                text_color=hex_to_bgr(text_color_hex),
                                box_color=hex_to_bgr(box_color_hex),
                                top_bar_height=top_bar_height,
                                bottom_bar_height=bottom_bar_height
                            )

                            st.success("Tüm videolar işlendi!")

                            if os.path.exists(output_zip_path):
                                with open(output_zip_path, "rb") as f:
                                    st.download_button("İndir ZIP Dosyası", f, file_name="output_videos.zip", mime="application/zip")

                        except Exception as e:
                            st.error(f"İşlem sırasında hata oluştu: {str(e)}")
                            logger.error(f"İşlem hatası: {str(e)}")

    # Geçici dosyayı temizleme işlemi
    if 'temp_logo' in locals():
        try:
            os.unlink(temp_logo.name)
        except Exception as e:
            logger.error(f"Geçici dosya temizleme hatası: {str(e)}")

if __name__ == "__main__":
    main()

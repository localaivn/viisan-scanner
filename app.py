import streamlit as st
import subprocess
import os
from datetime import datetime
import time
import socket
import base64
from openai import OpenAI
from docx import Document as DocxDocument
from docx.shared import Pt
import cv2

# ─── Config ───────────────────────────────────────────────
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip

LOCAL_IP       = get_local_ip()
MJPEG_URL      = f"http://{LOCAL_IP}:8080"
DEVICE         = "/dev/video0"
CAPTURE_WIDTH  = 3264
CAPTURE_HEIGHT = 2448
SAVE_DIR       = "captures"
OCR_MAX_WIDTH  = 1600
OCR_MAX_HEIGHT = 1200
CSS_FILE       = "static/style.css"

os.makedirs(SAVE_DIR, exist_ok=True)

# ─── Page config ──────────────────────────────────────────
st.set_page_config(page_title="Scanner Preview and OCR", page_icon="📷", layout="wide")

# ─── Load CSS từ file ─────────────────────────────────────
def load_css(path: str):
    with open(path, "r") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_css(CSS_FILE)

# ─── Session state ────────────────────────────────────────
if "captured_file" not in st.session_state:
    st.session_state.captured_file = None
if "ocr_text" not in st.session_state:
    st.session_state.ocr_text = None

# ─── Header ───────────────────────────────────────────────
st.markdown("""
<div class="app-header">
    <span class="app-header-icon">📷</span>
    <h1>Scanner Preview &amp; OCR</h1>
    <span class="live-badge"><span class="live-dot"></span>LIVE</span>
</div>
""", unsafe_allow_html=True)

# ─── Layout chính ─────────────────────────────────────────
col_preview, col_ctrl = st.columns([3, 1], gap="medium")

with col_preview:
    st.markdown(f"""
    <div class="preview-box">
        <img src="{MJPEG_URL}" alt="Live Preview">
    </div>
    <div class="preview-info">
        🌐 <code>{MJPEG_URL}</code> &nbsp;|&nbsp; 📹 <code>{DEVICE}</code>
    </div>
    """, unsafe_allow_html=True)

with col_ctrl:
    # ── Thông số ──
    st.markdown(f"""
    <div class="info-card">
        📐 Capture: <b>{CAPTURE_WIDTH} × {CAPTURE_HEIGHT}</b> px<br>
        🔍 OCR input: <b>{OCR_MAX_WIDTH} × {OCR_MAX_HEIGHT}</b> px<br>
        💾 Save: <b>{SAVE_DIR}/</b>
    </div>
    """, unsafe_allow_html=True)

    # ── Exposure ──
    exposure = st.slider(
        "☀️ Exposure", min_value=100, max_value=20000,
        value=12000, step=100, help="Cao hơn = sáng hơn"
    )

    # ── API Key ──
    api_key = st.text_input(
        "🔑 DashScope API Key", type="password", placeholder="sk-..."
    )

    st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)

    # ── Nút Capture ──
    capture_btn = st.button("📸 Capture Full Resolution")

    # ── Nút Download ảnh ──
    if st.session_state.captured_file and os.path.exists(st.session_state.captured_file):
        fname = os.path.basename(st.session_state.captured_file)
        with open(st.session_state.captured_file, "rb") as f:
            st.download_button(
                f"⬇️ {fname}", f,
                file_name=fname, mime="image/jpeg"
            )

    # ── Nút OCR ──
    ocr_disabled = (
        st.session_state.captured_file is None or
        not os.path.exists(st.session_state.captured_file or "")
    )
    ocr_btn = st.button("🔍 Run OCR → .docx", disabled=ocr_disabled)

    # ── OCR result + Download docx ──
    if st.session_state.ocr_text:
        st.markdown("<div style='margin-top:4px'></div>", unsafe_allow_html=True)
        edited_text = st.text_area(
            "📄 OCR Result",
            value=st.session_state.ocr_text,
            height=340,
        )

        base_name = os.path.splitext(
            os.path.basename(st.session_state.captured_file)
        )[0]
        docx_path = f"{SAVE_DIR}/{base_name}_ocr.docx"

        doc = DocxDocument()
        doc.add_heading("OCR Result", level=1)
        doc.add_paragraph(f"Source: {os.path.basename(st.session_state.captured_file)}")
        doc.add_paragraph(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        doc.add_paragraph("")
        for line in edited_text.split("\n"):
            para = doc.add_paragraph(line)
            para.style.font.size = Pt(12)
        doc.save(docx_path)

        with open(docx_path, "rb") as f:
            st.download_button(
                "⬇️ Download .docx", f,
                file_name=os.path.basename(docx_path),
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )

    # ── Footer ──
    st.markdown("""
    <div class="footer">
        Scanner Preview v1.2 &nbsp;|&nbsp;
        <a href="https://ttaisolutions.com" target="_blank">TTAI Solutions Software</a>
    </div>
    """, unsafe_allow_html=True)

# ─── Capture logic ────────────────────────────────────────
if capture_btn:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"{SAVE_DIR}/capture_{timestamp}.jpg"

    prog = st.progress(0, text="Stopping MJPEG service...")
    subprocess.run(["sudo", "systemctl", "stop", "mjpeg-server.service"],
                   capture_output=True)
    time.sleep(0.3)

    prog.progress(20, text="Setting exposure...")
    subprocess.run(["v4l2-ctl", "-d", DEVICE, "--set-ctrl=exposure_auto=1"],
                   capture_output=True)
    subprocess.run(["v4l2-ctl", "-d", DEVICE,
                    f"--set-ctrl=exposure_absolute={exposure}"],
                   capture_output=True)

    prog.progress(40, text="Waiting sensor stabilize...")
    time.sleep(1.0)

    prog.progress(60, text="Capturing...")
    result = subprocess.run([
        "ffmpeg", "-y",
        "-f", "v4l2", "-framerate", "3",
        "-input_format", "mjpeg",
        "-video_size", f"{CAPTURE_WIDTH}x{CAPTURE_HEIGHT}",
        "-i", DEVICE,
        "-vf", "transpose=1",
        "-frames:v", "3", "-update", "1",
        "-q:v", "2", filename
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    prog.progress(85, text="Restarting MJPEG service...")
    subprocess.run(["sudo", "systemctl", "start", "mjpeg-server.service"],
                   capture_output=True)

    prog.progress(100, text="Done!")
    time.sleep(0.3)
    prog.empty()

    if result.returncode == 0 and os.path.exists(filename):
        st.session_state.captured_file = filename
        st.session_state.ocr_text = None
        st.success(f"✅ Saved: `{os.path.basename(filename)}`")
        st.rerun()
    else:
        st.error("❌ Capture failed!")
        with st.expander("FFmpeg log"):
            st.code(result.stderr.decode(), language="bash")

# ─── OCR logic ────────────────────────────────────────────
if ocr_btn:
    if not api_key:
        st.warning("⚠️ Nhập API Key trước khi chạy OCR.")
    else:
        with st.spinner("🔄 Resizing image..."):
            img = cv2.imread(st.session_state.captured_file)
            h, w = img.shape[:2]
            scale = min(OCR_MAX_WIDTH / w, OCR_MAX_HEIGHT / h, 1.0)
            if scale < 1.0:
                img = cv2.resize(img, (int(w * scale), int(h * scale)),
                                 interpolation=cv2.INTER_AREA)
            _, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            img_b64 = base64.b64encode(buf.tobytes()).decode()

        with st.spinner("🤖 Running OCR..."):
            try:
                client = OpenAI(
                    api_key=api_key,
                    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
                )
                resp = client.chat.completions.create(
                    model="qwen-vl-ocr",
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                                "min_pixels": 100 * 100,
                                "max_pixels": OCR_MAX_WIDTH * OCR_MAX_HEIGHT
                            },
                            {
                                "type": "text",
                                "text": "Read all the text in this image. Output the text exactly as it appears, preserving layout and line breaks."
                            }
                        ]
                    }],
                    max_tokens=4096
                )
                st.session_state.ocr_text = resp.choices[0].message.content
                st.rerun()
            except Exception as e:
                st.error(f"❌ OCR failed: {e}")

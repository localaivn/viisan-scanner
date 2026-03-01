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

os.makedirs(SAVE_DIR, exist_ok=True)

# ─── Page config ──────────────────────────────────────────
st.set_page_config(page_title="Scanner Preview", page_icon="📷", layout="wide")

# ─── CSS ──────────────────────────────────────────────────
st.markdown("""
<style>
    /* Ẩn header/footer mặc định của Streamlit */
    #MainMenu, header, footer { visibility: hidden; }

    /* Giảm padding mặc định */
    .block-container {
        padding-top: 10px !important;
        padding-bottom: 0px !important;
        padding-left: 24px !important;
        padding-right: 24px !important;
    }

    /* App header */
    .app-header {
        display: flex; align-items: center; gap: 10px;
        padding: 4px 0 6px 0;
        border-bottom: 2px solid #e0e0e0;
        margin-bottom: 10px;
    }
    .app-header h1 { font-size: 1.2rem; margin: 0; color: #1a1a2e; }

    .live-badge {
        display: inline-flex; align-items: center; gap: 5px;
        background: #ff4b4b; color: white;
        font-size: 0.7rem; font-weight: 700;
        padding: 2px 8px; border-radius: 20px; letter-spacing: 1px;
    }
    .live-dot {
        width: 7px; height: 7px; background: white;
        border-radius: 50%; animation: blink 1s infinite;
    }
    @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.2} }

    /* Preview box */
    .preview-box {
        background: #0d0d0d; border-radius: 10px; padding: 6px;
        text-align: center; box-shadow: 0 3px 12px rgba(0,0,0,0.3);
    }
    .preview-box img { border-radius: 6px; width: 100%; height: 100%; object-fit: contain; }

    /* Info nhỏ dưới preview */
    .info-small {
        font-size: 0.72rem; color: #888; margin-top: 4px; text-align: center;
    }

    /* Card thông tin bên phải */
    .info-card {
        background: #f8f9fa; border-left: 3px solid #4a90d9;
        border-radius: 6px; padding: 7px 10px;
        font-size: 0.78rem; color: #444; margin-bottom: 8px;
    }

    /* Buttons */
    div[data-testid="stButton"] > button {
        width: 100%;
        background: linear-gradient(135deg, #1a73e8, #0d47a1);
        color: white; font-size: 0.88rem; font-weight: 600;
        padding: 8px 0; border: none; border-radius: 8px;
        cursor: pointer; transition: opacity 0.2s;
        margin-bottom: 2px;
    }
    div[data-testid="stButton"] > button:hover { opacity: 0.85; }
    div[data-testid="stButton"] > button:disabled {
        background: #b0bec5 !important; cursor: not-allowed;
    }

    /* Slider label nhỏ lại */
    .stSlider label { font-size: 0.82rem !important; }

    /* Input label */
    .stTextInput label { font-size: 0.82rem !important; }

    /* OCR textarea */
    .stTextArea textarea {
        font-size: 0.85rem;
        font-family: 'Segoe UI', sans-serif;
        line-height: 1.6;
    }

    /* Download button */
    div[data-testid="stDownloadButton"] > button {
        width: 100%;
        background: linear-gradient(135deg, #2e7d32, #1b5e20);
        color: white; font-size: 0.88rem; font-weight: 600;
        padding: 8px 0; border: none; border-radius: 8px;
    }

    /* Footer */
    .footer {
        text-align: center; color: #bbb; font-size: 0.68rem;
        padding-top: 4px; border-top: 1px solid #eee; margin-top: 6px;
    }
</style>
""", unsafe_allow_html=True)

# ─── Session state ────────────────────────────────────────
if "captured_file" not in st.session_state:
    st.session_state.captured_file = None
if "ocr_text" not in st.session_state:
    st.session_state.ocr_text = None

# ─── Header ───────────────────────────────────────────────
st.markdown("""
<div class="app-header">
    <span style="font-size:1.5rem;">📷</span>
    <h1>Scanner Preview &amp; Capture</h1>
    <span class="live-badge"><span class="live-dot"></span>LIVE</span>
</div>
""", unsafe_allow_html=True)

# ─── Layout chính: preview | controls ─────────────────────
col_preview, col_ctrl = st.columns([3, 1], gap="medium")

with col_preview:
    # Preview chiếm toàn bộ chiều cao còn lại (~780px sau header)
    st.markdown(f"""
    <div class="preview-box" style="height: 780px;">
        <img src="{MJPEG_URL}" alt="Live Preview" style="max-height:768px;">
    </div>
    <div class="info-small">
        🌐 <code>{MJPEG_URL}</code> &nbsp;|&nbsp; 📹 <code>{DEVICE}</code>
    </div>
    """, unsafe_allow_html=True)

with col_ctrl:
    # ── Thông số ──
    st.markdown(f"""
    <div class="info-card">
        📐 <b>{CAPTURE_WIDTH} × {CAPTURE_HEIGHT}</b> px<br>
        🔍 OCR: <b>{OCR_MAX_WIDTH} × {OCR_MAX_HEIGHT}</b> px<br>
        💾 <b>{SAVE_DIR}/</b>
    </div>
    """, unsafe_allow_html=True)

    # ── Exposure ──
    exposure = st.slider(
        "☀️ Exposure", min_value=100, max_value=20000,
        value=12000, step=100, help="Cao hơn = sáng hơn"
    )

    # ── API Key ──
    api_key = st.text_input(
        "🔑 API Key", type="password", placeholder="sk-..."
    )

    st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)

    # ── Nút Capture ──
    capture_btn = st.button("📸 Capture Full Resolution")

    # ── Nút Download ảnh (chỉ hiện khi có file) ──
    if st.session_state.captured_file and os.path.exists(st.session_state.captured_file):
        fname = os.path.basename(st.session_state.captured_file)
        with open(st.session_state.captured_file, "rb") as f:
            st.download_button(
                f"⬇️ Download  {fname}",
                f, file_name=fname, mime="image/jpeg"
            )

    # ── Nút OCR ──
    ocr_disabled = (
        st.session_state.captured_file is None or
        not os.path.exists(st.session_state.captured_file or "")
    )
    ocr_btn = st.button("🔍 Run OCR → .docx", disabled=ocr_disabled)

    # ── OCR result + Download docx ──
    if st.session_state.ocr_text:
        st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)
        edited_text = st.text_area(
            "📄 OCR Result",
            value=st.session_state.ocr_text,
            height=340,
        )

        # Build docx
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
    <div class="footer">Scanner Preview v1.2 &nbsp;|&nbsp; TTAI Solutions</div>
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
                    model="qwen-vl-ocr-2025-11-20",
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

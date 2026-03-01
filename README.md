# Viisan Scanner

A lightweight camera-scanner application for Linux devices that combines:

- **Live camera preview** over MJPEG (`mjpeg_server.py`)
- **Capture at full scanner resolution** from a USB camera (`app.py`)
- **OCR extraction** through DashScope-compatible OpenAI API
- **Export OCR text to `.docx`** for editing and download

The UI is built with **Streamlit**, and camera access is done with **OpenCV + V4L2 + FFmpeg**.

---

## 1) How the codebase is organized

- `app.py`  
  Main Streamlit app. Handles UI, live preview embedding, camera capture workflow, OCR call, and `.docx` export.
- `mjpeg_server.py`  
  Local MJPEG streaming server that continuously reads frames from `/dev/video0` and serves them at `http://<host-ip>:8080`.
- `static/style.css`  
  Custom styling for Streamlit widgets and layout.
- `requirements.txt`  
  Python dependencies for both the UI app and streaming server.
- `mjpeg-server.service`  
  Systemd unit file example for running the MJPEG streamer in production.

---

## 2) Runtime architecture

At runtime, you typically run **two processes**:

1. `mjpeg_server.py` keeps `/dev/video0` open for low-latency live preview (`:8080`).
2. `app.py` shows the web UI (`:8501` by default).

When user clicks **Capture Full Resolution** in the Streamlit app:

1. The app stops the MJPEG service (`systemctl stop mjpeg-server.service`) so capture can take exclusive camera access.
2. Exposure is set with `v4l2-ctl`.
3. Frame(s) are captured at full resolution via `ffmpeg` and saved into `captures/`.
4. MJPEG service is started again (`systemctl start mjpeg-server.service`).
5. Optional OCR step resizes image and sends it to DashScope-compatible endpoint.

---

## 3) Prerequisites

### OS / Hardware

- Linux machine with a camera exposed as `/dev/video0`
- User permissions to access video device (often via `video` group)

### System packages

Install required system tools:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg v4l-utils
```

> OpenCV camera access in this project uses the V4L2 backend (`cv2.CAP_V4L2`).

### Python version

- Python 3.9+ recommended

---

## 4) Install project dependencies

From repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 5) Development mode

Development mode is best when actively changing code.

### Step A: start MJPEG server manually

```bash
source .venv/bin/activate
python mjpeg_server.py
```

- Stream URL: `http://<host-ip>:8080`
- Health check: `http://<host-ip>:8080/health`

### Step B: start Streamlit app in another terminal

```bash
source .venv/bin/activate
streamlit run app.py
```

Default Streamlit URL:

- `http://localhost:8501`

### Dev notes

- Ensure your user can run these commands (used by `app.py`):
  - `sudo systemctl stop mjpeg-server.service`
  - `sudo systemctl start mjpeg-server.service`
  - `v4l2-ctl ...`
  - `ffmpeg ...`
- If you run MJPEG manually (not systemd), capture buttons may fail when trying to control `mjpeg-server.service`.

---

## 6) Production mode (systemd)

Production setup keeps MJPEG streamer as a background service and runs Streamlit persistently.

## 6.1 Configure paths/user

The provided `mjpeg-server.service` uses:

- `User=admin`
- `WorkingDirectory=/home/admin/viisan-scanner`
- `ExecStart=/usr/bin/python3 /home/admin/viisan-scanner/mjpeg_server.py`

Update these values to match your machine if needed.

## 6.2 Install MJPEG service

```bash
sudo cp mjpeg-server.service /etc/systemd/system/mjpeg-server.service
sudo systemctl daemon-reload
sudo systemctl enable mjpeg-server.service
sudo systemctl start mjpeg-server.service
sudo systemctl status mjpeg-server.service
```

## 6.3 Run Streamlit as a service (recommended)

Create `/etc/systemd/system/viisan-scanner.service`:

```ini
[Unit]
Description=Viisan Scanner Streamlit App
After=network.target mjpeg-server.service

[Service]
Type=simple
User=admin
WorkingDirectory=/home/admin/viisan-scanner
Environment="PATH=/home/admin/viisan-scanner/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/home/admin/viisan-scanner/.venv/bin/streamlit run app.py --server.address 0.0.0.0 --server.port 8501
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
```

Then enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable viisan-scanner.service
sudo systemctl start viisan-scanner.service
sudo systemctl status viisan-scanner.service
```

---

## 7) OCR configuration

In the app UI:

1. Enter **DashScope API Key** in the key field.
2. Capture an image.
3. Click **Run OCR → .docx**.

Implementation details:

- Uses OpenAI Python SDK with custom `base_url`:
  - `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`
- Model configured in code:
  - `qwen-vl-ocr-2025-11-20`

---

## 8) Common troubleshooting

### No live preview

- Verify streamer is running:
  ```bash
  systemctl status mjpeg-server.service
  ```
- Check health endpoint:
  ```bash
  curl http://127.0.0.1:8080/health
  ```
- Confirm camera device exists:
  ```bash
  ls /dev/video0
  ```

### Capture fails

- Ensure app user has permission for:
  - `sudo systemctl` calls
  - `v4l2-ctl`
  - `ffmpeg`
- Check Streamlit error expander for FFmpeg stderr output.

### OCR fails

- Confirm API key is valid.
- Verify network access to DashScope endpoint.
- Reduce OCR image max size if responses timeout (adjust constants in `app.py`).

---

## 9) Useful commands

```bash
# Restart both services
sudo systemctl restart mjpeg-server.service
sudo systemctl restart viisan-scanner.service

# View logs
journalctl -u mjpeg-server.service -f
journalctl -u viisan-scanner.service -f

# Stop services
sudo systemctl stop viisan-scanner.service
sudo systemctl stop mjpeg-server.service
```

---

## 10) Security and ops notes

- The app currently asks for API key in the UI (not persisted by default).
- Consider restricting network exposure:
  - Bind Streamlit behind reverse proxy/auth
  - Firewall ports `8080` and `8501`
- For unattended production, configure passwordless sudo for only required `systemctl` commands or refactor capture flow to avoid sudo.


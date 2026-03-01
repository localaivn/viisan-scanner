import cv2
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ─── Config ───────────────────────────────────────────────
DEVICE       = "/dev/video0"
WIDTH        = 1920
HEIGHT       = 1080
FPS          = 30
JPEG_QUALITY = 75
PORT         = 8080

# ─── Camera init ──────────────────────────────────────────
def open_camera():
    cap = cv2.VideoCapture(DEVICE, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    return cap

print(f"[MJPEG] Opening camera: {DEVICE}")
cap = open_camera()

if not cap.isOpened():
    print("[MJPEG] ERROR: Cannot open camera")
    exit(1)

print(f"[MJPEG] Camera OK — "
      f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
      f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} "
      f"@ {int(cap.get(cv2.CAP_PROP_FPS))}fps")

# ─── Shared frame ─────────────────────────────────────────
output_frame = None
lock         = threading.Lock()

# ─── Capture thread ───────────────────────────────────────
def capture_loop():
    global output_frame, cap
    print("[MJPEG] Capture thread started")
    frame_count = 0
    t0 = time.time()

    while True:
        ret, frame = cap.read()

        # Auto-reconnect nếu camera bị mất
        if not ret:
            print("[MJPEG] Frame read failed — reconnecting...")
            cap.release()
            time.sleep(1.0)
            cap = open_camera()
            continue

        # Rotate 90° CW để khớp với hướng capture
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)

        ret, jpeg = cv2.imencode(
            '.jpg', frame,
            [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
        )
        if not ret:
            continue

        with lock:
            output_frame = jpeg.tobytes()

        # Log FPS mỗi 5 giây
        frame_count += 1
        elapsed = time.time() - t0
        if elapsed >= 5.0:
            print(f"[MJPEG] Streaming {frame_count / elapsed:.1f} fps")
            frame_count = 0
            t0 = time.time()

threading.Thread(target=capture_loop, daemon=True).start()

# ─── HTTP Handler ─────────────────────────────────────────
class MJPEGHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        # Chỉ log kết nối mới, bỏ spam request log
        pass

    def do_GET(self):
        if self.path == "/":
            self._stream()
        elif self.path == "/health":
            self._health()
        else:
            self.send_error(404)

    def _stream(self):
        print(f"[MJPEG] Client connected: {self.client_address[0]}")
        self.send_response(200)
        self.send_header('Content-Type',
                         'multipart/x-mixed-replace; boundary=frame')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        try:
            while True:
                with lock:
                    if output_frame is None:
                        time.sleep(0.01)
                        continue
                    frame = output_frame

                self.wfile.write(
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n'
                    b'Content-Length: ' + str(len(frame)).encode() + b'\r\n\r\n'
                    + frame + b'\r\n'
                )
                time.sleep(1 / FPS)

        except (BrokenPipeError, ConnectionResetError):
            print(f"[MJPEG] Client disconnected: {self.client_address[0]}")
        except Exception as e:
            print(f"[MJPEG] Stream error: {e}")

    def _health(self):
        """Endpoint kiểm tra server còn sống không."""
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')

# ─── Start server ─────────────────────────────────────────
print(f"[MJPEG] Server running → http://0.0.0.0:{PORT}")
server = ThreadingHTTPServer(('0.0.0.0', PORT), MJPEGHandler)
server.serve_forever()

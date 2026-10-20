"""Kho Đề Toán — ứng dụng PC.

Mở phần mềm trong cửa sổ riêng (không cần trình duyệt, không có cửa sổ đen).
Máy chủ nội bộ chạy ngầm trên 127.0.0.1, chỉ máy này truy cập được.
Dữ liệu: Documents\\KhoDeToan (hoặc thư mục du_lieu đặt cạnh file .exe nếu có — bản "mang đi").
"""
import json, os, socket, sys, threading, time, traceback, urllib.request
from pathlib import Path

APP_NAME = 'Kho Đề Toán'
BASE = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
portable = BASE / 'du_lieu'
if os.environ.get('KHODE_DATA'):
    DATA = Path(os.environ['KHODE_DATA'])
else:
    DATA = portable if portable.is_dir() else Path.home() / 'Documents' / 'KhoDeToan'
DATA.mkdir(parents=True, exist_ok=True)
os.environ.setdefault('KHODE_DATA', str(DATA))
LOG = DATA / 'nhat_ky.txt'

def log(msg):
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + msg + '\n')
    except OSError:
        pass

# --------------------------------------------------------------- chỉ cho chạy 1 cửa sổ
_lock = socket.socket()
try:
    _lock.bind(('127.0.0.1', 47615))
except OSError:
    import ctypes  # đã có một cửa sổ đang mở
    if sys.platform == 'win32':
        ctypes.windll.user32.MessageBoxW(0, 'Kho Đề Toán đang mở rồi. Hãy tìm cửa sổ trên thanh tác vụ.', APP_NAME, 0x40)
    sys.exit(0)

import uvicorn  # noqa: E402
import webview  # noqa: E402
from app.main import app  # noqa: E402

def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

PORT = free_port()
URL = f'http://127.0.0.1:{PORT}'

def serve():
    try:
        uvicorn.run(app, host='127.0.0.1', port=PORT, log_level='warning', log_config=None)
    except Exception:
        log('Lỗi máy chủ:\n' + traceback.format_exc())

class Api:
    """Các hàm trang web gọi được qua window.pywebview.api.*"""

    def __init__(self):
        self.window = None

    def save(self, path, method='GET', body=None, name='file'):
        """Tải dữ liệu từ máy chủ nội bộ rồi hỏi nơi lưu bằng hộp thoại Windows."""
        try:
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(URL + path, data=data, method=method,
                                         headers={'Content-Type': 'application/json'} if data else {})
            with urllib.request.urlopen(req, timeout=600) as r:
                blob = r.read()
                cd = r.headers.get('Content-Disposition') or ''
                if 'filename="' in cd:
                    name = cd.split('filename="', 1)[1].split('"', 1)[0]
        except urllib.error.HTTPError as e:
            try:
                return {'ok': False, 'status': e.code, 'body': json.loads(e.read().decode('utf-8'))}
            except Exception:
                return {'ok': False, 'status': e.code, 'error': str(e)}
        except Exception as e:
            log('Lỗi tải: ' + traceback.format_exc())
            return {'ok': False, 'error': str(e)}
        ext = Path(name).suffix.lstrip('.').lower() or 'bin'
        kinds = {'docx': 'Tài liệu Word (*.docx)', 'zip': 'Tệp nén (*.zip)', 'db': 'Bản sao lưu kho (*.db)'}
        last = getattr(self, 'last_dir', str(Path.home() / 'Documents'))
        res = self.window.create_file_dialog(webview.SAVE_DIALOG, directory=last, save_filename=name,
                                             file_types=(kinds.get(ext, f'Tệp (*.{ext})'), 'Tất cả (*.*)'))
        if not res:
            return {'ok': False, 'cancel': True}
        dest = res if isinstance(res, str) else res[0]
        if not Path(dest).suffix:
            dest += '.' + ext
        Path(dest).write_bytes(blob)
        self.last_dir = str(Path(dest).parent)
        return {'ok': True, 'path': dest}

    def open_path(self, p):
        """Mở file (Word) hoặc thư mục bằng chương trình mặc định của Windows."""
        try:
            if sys.platform == 'win32':
                os.startfile(p)  # noqa
            return True
        except OSError as e:
            return str(e)

    def reveal(self, p):
        """Mở thư mục chứa file và chọn sẵn file đó."""
        try:
            if sys.platform == 'win32':
                import subprocess
                subprocess.Popen(['explorer', '/select,', str(p)])
            return True
        except OSError as e:
            return str(e)

    def data_dir(self):
        return str(DATA)

def wait_ready():
    for _ in range(200):
        try:
            urllib.request.urlopen(URL + '/api/settings', timeout=1)
            return True
        except Exception:
            time.sleep(0.05)
    return False

def main():
    log(f'Khởi động, dữ liệu: {DATA}')
    threading.Thread(target=serve, daemon=True).start()
    if not wait_ready():
        log('Máy chủ không khởi động được')
    api = Api()
    win = webview.create_window(APP_NAME, URL, js_api=api, width=1400, height=880, min_size=(980, 640),
                                maximized=True, background_color='#F4F5F9', text_select=True)
    api.window = win
    webview.start(private_mode=False, storage_path=str(DATA / '.webview'))

if __name__ == '__main__':
    try:
        main()
    except Exception:
        log('Lỗi:\n' + traceback.format_exc())
        raise

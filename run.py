"""Khởi động Kho Đề Toán: chạy máy chủ trên máy này rồi mở trình duyệt.

- Chạy trên máy cá nhân: python run.py  (hoặc bấm đúp KhoDeToan.exe)
- Chạy làm máy chủ cho nhiều máy trong mạng: python run.py --mang
"""
import os, socket, sys, threading, time, webbrowser
from pathlib import Path

BASE = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
os.environ.setdefault('KHODE_DATA', str(BASE / 'du_lieu'))

import uvicorn  # noqa: E402
from app.main import app  # noqa: E402

def free_port(start=8765):
    for port in range(start, start + 50):
        with socket.socket() as s:
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    return start

def main():
    lan = '--mang' in sys.argv
    port = free_port()
    host = '0.0.0.0' if lan else '127.0.0.1'
    url = f'http://127.0.0.1:{port}'
    print('=' * 60)
    print(' KHO ĐỀ TOÁN đang chạy tại', url)
    if lan:
        try:
            ip = socket.gethostbyname(socket.gethostname())
            print(f' Máy khác trong mạng mở: http://{ip}:{port}')
        except OSError:
            pass
    print(' Dữ liệu lưu tại:', os.environ['KHODE_DATA'])
    print(' Đóng cửa sổ này để tắt phần mềm.')
    print('=' * 60)
    threading.Thread(target=lambda: (time.sleep(1.2), webbrowser.open(url)), daemon=True).start()
    uvicorn.run(app, host=host, port=port, log_level='warning')

if __name__ == '__main__':
    main()

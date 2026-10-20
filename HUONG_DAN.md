# Kho Đề Toán — bản 1

Phần mềm lưu câu hỏi Toán (giữ nguyên công thức và hình của Word), lọc theo chuyên đề và mức độ, tạo đề theo ma trận 4 phần rồi xuất ra Word.

## Chạy trên máy Windows

**Cách 1 — file .exe (khi đã đóng gói):** bấm đúp `KhoDeToan.exe`. Phần mềm tự mở trong trình duyệt. Dữ liệu lưu ở thư mục `du_lieu` cạnh file .exe.

**Cách 2 — chạy từ mã nguồn:**
1. Cài Python 3.11 trở lên tại python.org (khi cài, tick ô *Add python.exe to PATH*).
2. Bấm đúp `chay_tren_windows.bat`. Lần đầu mất 1–2 phút để cài thư viện, các lần sau mở ngay.

Đóng cửa sổ đen là tắt phần mềm.

## Dùng chung cho nhiều máy

- **Trong cùng mạng ở trung tâm:** trên một máy, chạy `python run.py --mang`. Máy khác mở trình duyệt vào địa chỉ hiện trên cửa sổ (dạng `http://192.168.x.x:8765`).
- **Qua Internet:** đưa thư mục này lên một máy chủ thuê (VPS), chạy giống trên. Nên thêm đăng nhập trước khi mở ra Internet (bản sau).

## Sao lưu

Toàn bộ kho nằm trong thư mục `du_lieu`:
- `kho.db`: câu hỏi và hình;
- `de_da_tao/`: các đề đã tạo.

Copy thư mục này là sao lưu xong.

## Mẫu file nhập

```
[6.C1.B1] [M2] [TN]
Câu 1. Nội dung câu hỏi …
A. …    B. …    C. …    D. …       ← gạch chân chữ cái đáp án đúng
Lời giải
Nội dung lời giải …
```

- **Mã chuyên đề:** mã của thư mục trong cây chuyên đề, ví dụ `6.C1.B1` (Toán 6 › Chương I › Bài 1) hoặc `6.C1.B1.D1` (một dạng thầy tự thêm). Di chuột vào thư mục để xem mã. Không ghi mã cũng được: chọn chuyên đề lúc nhập.
- **Mức độ:** M1 Nhận biết · M2 Thông hiểu · M3 Vận dụng · M4 Vận dụng cao.
- **Dạng câu:**
  - `TN`: trắc nghiệm ABCD.
  - `ĐS`: đúng/sai, các ý a) b) c) d); gạch chân chữ cái của ý đúng.
  - `TLN`: trả lời ngắn; thêm dòng `Đáp án: …`.
  - `TL`: tự luận. Câu có nhiều ý a), b), c)… được tách thành từng câu riêng (phần đề chung chép vào mỗi câu), mỗi ý có chuyên đề và mức độ riêng. Khi xuất lại cả đề, các ý tự gộp về một câu như cũ.

## Cây thư mục

Có hai cây, chọn ở ô phía trên cây mục lục:
- **Chuyên đề (Toán 6–9):** dựng sẵn theo sách Kết nối tri thức. Thêm, đổi tên, xoá, kéo thả, đưa lên/xuống ngay trong phần mềm: di chuột vào thư mục sẽ hiện các nút ＋ ✎ ↑ ↓ ✕, hoặc bấm “+ Thư mục”.
- **Tổng hợp đề thi:** mỗi đề nhập vào được giữ nguyên thành một đề (đủ câu, đúng thứ tự). Xem, tải lại file Word, chọn cả đề để trộn mã. Khi nhập liệu, chọn “Lưu mỗi file thành một đề”.

Xoá thư mục không xoá câu hỏi bên trong: câu được chuyển lên thư mục cha.

## Đóng gói thành .exe

Đưa thư mục lên GitHub. Mỗi lần đẩy code, GitHub tự build `KhoDeToan.exe` (tab Actions → bản build mới nhất → Artifacts).

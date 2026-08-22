# 📬 eMail Assistant v1.5 (VNPT AI Assistant)

> **Ứng dụng trợ lý email tự động thông minh: Quản lý & Tóm tắt Chuỗi Hội Thoại Email (Email Threads), Tự động gợi ý & Phím tắt Tab cho Senders, Quét đa nguồn Microsoft Outlook và Đa tài khoản Webmail (IMAP), Tóm tắt nội dung bằng AI (Offline / Online), Hiển thị thông báo nổi trên Desktop và Tương tác phản hồi 2 chiều qua Telegram.**

---

## 🌟 Tính năng mới nổi bật trong phiên bản v1.5

- 👥 **Gợi Ý Người Gửi Thông Minh (Contacts & Senders Autocomplete) + Phím Tắt `Tab`:**
  - **Tự động gom liên hệ:** Trích xuất tức thời danh bạ và người gửi gần đây từ Outlook, CSDL SQLite Threads và Cache tóm tắt với bộ nhớ đệm tốc độ cao (`data/contacts_cache.json`).
  - **Tìm kiếm tức thì:** Tìm kiếm linh hoạt theo Tên, Email, Username tiếng Việt Unicode NFC không phân biệt hoa thường.
  - **Phím tắt `Tab` tiện lợi:** Chỉ cần gõ vài ký tự và nhấn phím `Tab`, ứng dụng sẽ tự động chọn và điền ngay email phù hợp vào Rule.
  - **Hiển thị tinh gọn:** Tự động chuẩn hóa về địa chỉ email gọn gàng (vd: `nanhduc@vnpt.vn`), không bị dài dòng.
- ⚡ **Hệ Thống Rule 3 Cột Độc Lập Hoàn Toàn (Independent Rules Architecture):**
  - **Cơ chế OR linh hoạt:** Hoạt động độc lập giữa 3 cột **Folders**, **Senders**, **Keywords**.
  - **Tự động quét toàn bộ hòm thư:** Khi cột Folders để trống, ứng dụng sẽ tự động duyệt xuyên suốt qua **tất cả các thư mục mail & thư mục con** để tìm kiếm chính xác email từ `👤 Senders` hoặc chứa `🔑 Keywords`.
  - **Tìm kiếm nhanh thư mục (Fast Folders Search):** Ô tìm kiếm lọc tức thì cây thư mục, tự động làm sạch ô tìm kiếm sau khi tick chọn thư mục.
- 🗑️ **Đồng Bộ Xóa Trực Tiếp Vào Thùng Rác (Direct Trash Sync):**
  - Khi bấm nút `🗑️ Xóa` trên từng Email hoặc Thread, ứng dụng sẽ gửi lệnh chuyển trực tiếp email đó vào thư mục **Thùng rác (Deleted Items / Trash)** trên máy chủ Outlook và Webmail IMAP.
  - Hỗ trợ mở trực tiếp email mới nhất của chuỗi Thread bằng 1 click.
- 🎨 **Chuẩn Hóa Giao Diện & Typography Hiện Đại:**
  - **Đồng bộ Typography:** Tiêu đề và nội dung tóm tắt trang **Emails** đồng bộ chuẩn 100% font chữ với trang **Threads** (`Segoe UI 12 Bold` cho tiêu đề, `Segoe UI 11` với hộp thoại co giãn tự động theo độ dài tóm tắt).
  - **Nút xóa `[✕]` vuông vắn tinh tế:** Kích thước cố định `22x22px` viền đỏ mảnh (`border_width=1`), nền trong suốt, không bao giờ bị text dài đè biến dạng.
  - **Phong cách Outline Transparent:** Đồng bộ các nút thao tác chính (*Lưu cấu hình*, *Xem thông báo*, *Bắt đầu/Dừng theo dõi*, *Làm mới*, *Sắp xếp*) sang phong cách viền mảnh thanh lịch chuẩn nhận diện VNPT.
- 🧵 **Quản Lý & Tóm Tắt Chuỗi Hội Thoại Email (Email Threads - SQLite Độc Lập):**
  - **Cơ sở dữ liệu độc lập (`data/threads.db`):** Sử dụng SQLite chuyên biệt cho luồng Thread, hoàn toàn không ảnh hưởng đến các luồng xử lý email cũ.
  - **Thuật toán Chuẩn hóa Tiêu đề (Subject Normalization):** Tự động bóc tách các tiền tố rác (`Re:`, `Fwd:`, `Tr:`,...) và thẻ tag vuông doanh nghiệp (`[NOC]`, `[Khẩn]`, `[VNPT]`,...) để gom nhóm chính xác các email phản hồi vào cùng một Thread.
  - **Tóm tắt Cuốn chiếu Tự động 100% (Rolling AI Summarization):** Tự động tổng hợp `[Bản tóm tắt cũ]` + `[Email phản hồi mới]` để đưa ra báo cáo diễn biến sự cố, trạng thái và action items mới nhất.
  - **Định tuyến thông báo thông minh:** Email thuộc chuỗi chỉ bắn duy nhất 1 thông báo tổng hợp của toàn bộ Thread (kèm số lượng thư và tóm tắt cuốn chiếu mới nhất) thay vì bắn lẻ tẻ từng email con.
- 📊 **Giao diện Modern SaaS Dashboard chuẩn nhận diện VNPT:**
  - Sidebar Menu dọc (Dark Slate Theme) kết hợp Top Navigation Bar trắng thanh lịch.
  - 6 phân hệ chuyên biệt: **Dashboard (Tổng quan)**, **Emails (Lịch sử & Chi tiết)**, **Threads (Chuỗi hội thoại)**, **Rules (Bộ lọc)**, **Settings (Cài đặt)**, **Help (Hướng dẫn)**.
- 📁 **Trình Quản Lý Thư Mục Trực Tiếp (Inline Folders Manager):**
  - Quét tự động cây thư mục từ Outlook và Webmail IMAP chỉ bằng 1 click `[🔍 Scan thư mục]`.
  - Phân nhóm thư mục theo từng tài khoản email với Accordion Thu gọn / Mở rộng (`▼` / `▶`).
  - Ô Checkbox `[✓]` ngay đầu tên từng tài khoản giúp chọn/bỏ chọn nhanh toàn bộ thư mục của tài khoản đó.
  - Tự động lưu cấu hình và giữ nguyên danh sách (Persistent Cache), không bị mất các rule đã chọn khi scan cập nhật.
- 📨 **Tính Năng Đánh Dấu Đã Đọc (Mark as Read) Đồng Bộ 3 Chiều:**
  - **Trên Telegram:** Đính kèm nút bấm tương tác `[✓ Đánh dấu đã đọc]` (Inline Keyboard). Nhận lệnh từ xa và tự động đồng bộ đánh dấu `\Seen` trên Webmail hoặc `UnRead = False` trên Outlook.
  - **Trên Desktop Popup & Trang Emails:** Nút `[✓ Đã đọc]` giúp xử lý nhanh email mà không cần mở Outlook/Webmail.
- 📬 **Cửa Sổ Thông Báo Nổi Desktop (Desktop Floating Card):**
  - Nằm gọn gàng ở góc màn hình phía trên khay hệ thống, thiết kế bo góc 12px viền xanh sang trọng.
  - Tự động trình chiếu lần lượt các email mới mỗi 10s theo thứ tự thời gian từ cũ sang mới, có nút `[✉️ Mở Mail]` và `[✓ Đã đọc]`.
- 🌐 **Hỗ trợ đa nguồn Email & Đa tài khoản (Multi-Account & Dual Source):**
  - **Microsoft Outlook (Local):** Đọc trực tiếp từ ứng dụng Outlook trên máy tính thông qua Windows MAPI.
  - **Đa tài khoản Webmail / IMAP (Server):** Cho phép thêm và quét đồng thời không giới hạn các tài khoản thư điện tử (VNPT Webmail, Gmail, Zimbra, Yahoo...) qua giao thức IMAP bảo mật (SSL/TLS).
- 🤖 **Tóm tắt Email thông minh bằng AI:**
  - **Offline AI (Local):** Chạy trực tiếp trên máy tính bằng `llama-cpp-python` với mô hình *Qwen2.5-3B-Instruct GGUF* — đảm bảo bảo mật dữ liệu 100%, không cần kết nối mạng.
  - **Online Cloud AI:** Hỗ trợ linh hoạt Google Gemini, Groq, OpenAI GPT, DeepSeek, Grok...
- 📦 **Đóng gói 1-Click:** Cung cấp script tự động build thành file `.exe` chạy độc lập (One-File).

---

## 📂 Cấu trúc thư mục

```text
EmailReminder/
├── app.py                  # Giao diện chính của ứng dụng (CustomTkinter, Popup Modal & System Tray)
├── thread_logic.py         # Module quản lý SQLite độc lập cho Threads (threads.db), chuẩn hóa tiêu đề & tóm tắt cuốn chiếu
├── core_logic.py           # Logic quét Outlook qua MAPI, lọc email, gửi Telegram
├── imap_logic.py           # Logic quét đa tài khoản Webmail trực tiếp qua IMAP Server (SSL/TLS)
├── ai_engines.py           # Kết nối các Cloud AI API (Gemini, Groq, OpenAI, DeepSeek, Grok...)
├── offline_ai.py           # Bộ giải mã mô hình AI Offline (llama-cpp-python)
├── make_icon.py            # Script tự tạo icon đồ họa cho ứng dụng
├── build_exe.bat           # Script đóng gói ứng dụng thành file .exe (CMD)
├── build_exe.ps1           # Script đóng gói ứng dụng thành file .exe (PowerShell)
├── requirements.txt        # Danh sách các thư viện phụ thuộc
├── app_icon.ico / .png     # Icon ứng dụng
├── models/                 # Thư mục chứa file model AI Offline (*.gguf)
└── data/                   # Thư mục lưu cấu hình (config.json) và CSDL Chuỗi hội thoại (threads.db)
```

---

## 🚀 Hướng dẫn cài đặt & Chạy ứng dụng

### 1. Yêu cầu hệ thống
- Hệ điều hành: **Windows 10 / 11** (hoặc Linux/macOS nếu sử dụng chế độ IMAP).
- Nếu dùng nguồn Outlook: Cần cài đặt **Microsoft Outlook** và đang đăng nhập tài khoản mail.
- **Python 3.10 - 3.14** (khuyến nghị Python 3.11+).

### 2. Cài đặt môi trường

1. **Clone mã nguồn về máy:**
   ```bash
   git clone https://github.com/qvuzz/EmailReminder.git
   cd EmailReminder
   ```

2. **Khởi tạo môi trường ảo (Virtual Environment):**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   ```

3. **Cài đặt các thư viện cần thiết:**
   ```powershell
   pip install -r requirements.txt
   ```

4. *(Tùy chọn)* **Cài đặt Model AI Offline:**
   - Tải file mô hình [Qwen2.5-3B-Instruct-Q4_K_M.gguf](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF) (hoặc bất kỳ mô hình GGUF tương thích).
   - Đặt file `.gguf` vào thư mục `models/`.

### 3. Chạy ứng dụng

```powershell
python app.py
```

---

## ⚙️ Hướng dẫn cấu hình

1. **Tab Cài đặt API & Nguồn Email:**
   - **Nguồn đọc Email:** Chọn `Outlook (Local)` hoặc `Webmail / IMAP (Server)`.
   - **Quản lý Tài khoản Webmail / IMAP:**
     - Bấm **➕ Thêm tài khoản** để mở Popup thêm tài khoản mới.
     - Nhập *Tên gợi nhớ* (vd: `VNPT Công việc`, `Gmail Cá nhân`), *IMAP Server* (vd: `email.vnpt.vn`, `imap.gmail.com`), *Port* (`993`), tích chọn *SSL/TLS*, *Tài khoản* và *Mật khẩu* (với Gmail cần dùng **Mật khẩu ứng dụng / App Password** 16 ký tự).
     - Nhấn nút **🧪 Test kết nối** ngay trong popup để kiểm tra.
   - **Telegram Bot Token & Chat ID:** Tạo Bot qua `@BotFather` trên Telegram, lấy Chat ID từ `@userinfobot` hoặc group ID, nhập vào và bấm **🔔 Test Telegram** để kiểm tra kết nối.
   - **AI Engine:** Chọn `Offline (Local llama.cpp)` hoặc các Cloud Engine (`Gemini`, `Groq`, `OpenAI`, `Claude`, `DeepSeek`...) và nhập API Key tương ứng.
   - **Chu kỳ quét:** Thiết lập khoảng thời gian lặp lại quét email (mặc định 15 phút).
2. **Tab Bộ lọc (Lists):**
   - Thêm danh sách người gửi, email CC, thư mục cần quét hoặc các từ khóa quan trọng cần cảnh báo.
3. **Tab Bảng điều khiển:**
   - Nhấn **▶ Bắt đầu giám sát** để chạy tiến trình quét tự động.
   - Có thể thu nhỏ ứng dụng xuống khay hệ thống góc phải màn hình.

---

## 🛠️ Đóng gói ứng dụng thành file `.exe`

Chỉ cần chạy file script đóng gói:

```powershell
# Chạy bằng Batch Script:
build_exe.bat

# Hoặc chạy bằng PowerShell:
.\build_exe.ps1
```

Sau khi hoàn tất, file thực thi sẽ nằm tại: **`dist\Email_Reminder.exe`**.

---

## 📄 Bản quyền & Tác giả

- **Tác giả:** quangvu@vnpt.vn
- **Bản quyền:** © 2026 VNPT AI Assistant. All rights reserved.



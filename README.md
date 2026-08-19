# 📬 Email Reminder v1.2 (VNPT AI Assistant)

> **Ứng dụng tự động quét email từ Microsoft Outlook hoặc Đa tài khoản Webmail (IMAP), tóm tắt nội dung bằng AI (Offline / Online) và gửi thông báo trực tiếp qua Telegram.**

---

## 🌟 Tính năng nổi bật

- 🌐 **Hỗ trợ đa nguồn Email & Đa tài khoản (Multi-Account & Dual Source):**
  - **Microsoft Outlook (Local):** Đọc trực tiếp từ ứng dụng Outlook trên máy tính thông qua Windows MAPI.
  - **Đa tài khoản Webmail / IMAP (Server):** Cho phép thêm và quét đồng thời không giới hạn các tài khoản thư điện tử (VNPT Webmail, Gmail, Zimbra, Yahoo...) qua giao thức IMAP bảo mật (SSL/TLS).
  - **Giao diện thẻ & Popup Modal hiện đại:** Quản lý danh sách tài khoản gọn gàng, thêm/sửa/xóa và test kết nối nhanh chóng qua cửa sổ Popup.
  - **Tối ưu tốc độ quét siêu tốc (Header-First & Cache-First):** Chỉ tải header siêu nhẹ (~1KB) để đối soát, tận dụng Cache bỏ qua việc tải lại thư cũ và chỉ tải nội dung chi tiết đối với email mới.
  - **Hỗ trợ giải mã thư mục tiếng Việt (Modified UTF-7).**
- 🎯 **Bộ lọc linh hoạt (Multi-filter):**
  - Lọc theo **Người gửi (Senders)**.
  - Lọc theo **Email CC**.
  - Lọc theo **Thư mục chỉ định (Folders)**.
  - Lọc theo **Từ khóa tiêu đề / nội dung (Keywords)**.
- 🤖 **Tóm tắt Email thông minh bằng AI:**
  - **Offline AI (Local):** Chạy trực tiếp trên máy tính bằng `llama-cpp-python` với mô hình *Qwen2.5-3B-Instruct GGUF* — đảm bảo bảo mật dữ liệu 100%, không cần kết nối mạng.
  - **Online Cloud AI:** Hỗ trợ linh hoạt Google Gemini, Groq, OpenAI GPT, Anthropic Claude, DeepSeek, Grok...
- 🔔 **Thông báo tức thì qua Telegram:** Tự động định dạng tin nhắn đẹp mắt, phân biệt rõ tên tài khoản nhận thư, chia nhỏ bản tin thông minh khi có nhiều email.
- 🖥️ **Giao diện hiện đại (Modern UI):**
  - Xây dựng bằng `CustomTkinter` với tone màu nhận diện thương hiệu VNPT (Xanh - Trắng).
  - Hỗ trợ chạy ngầm dưới **Khay hệ thống (System Tray)**, tự thu nhỏ và nhấp đúp để mở lại.
- 📦 **Đóng gói 1-Click:** Cung cấp script tự động build thành file `.exe` chạy độc lập (One-File).

---

## 📂 Cấu trúc thư mục

```text
EmailReminder/
├── app.py                  # Giao diện chính của ứng dụng (CustomTkinter, Popup Modal & System Tray)
├── core_logic.py           # Logic quét Outlook qua MAPI, lọc email, gửi Telegram
├── imap_logic.py           # Logic quét đa tài khoản Webmail trực tiếp qua IMAP Server (SSL/TLS)
├── ai_engines.py           # Kết nối các Cloud AI API (Gemini, Groq, OpenAI, Claude, DeepSeek...)
├── offline_ai.py           # Bộ giải mã mô hình AI Offline (llama-cpp-python)
├── make_icon.py            # Script tự tạo icon đồ họa cho ứng dụng
├── build_exe.bat           # Script đóng gói ứng dụng thành file .exe (CMD)
├── build_exe.ps1           # Script đóng gói ứng dụng thành file .exe (PowerShell)
├── requirements.txt        # Danh sách các thư viện phụ thuộc
├── app_icon.ico / .png     # Icon ứng dụng
├── models/                 # Thư mục chứa file model AI Offline (*.gguf)
└── data/                   # Thư mục lưu cấu hình và cache dữ liệu cục bộ
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



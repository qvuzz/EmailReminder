import customtkinter as ctk
import json
import os
import threading
import time
import sys
from datetime import datetime
from tkinter import messagebox
from PIL import Image
import pystray
from pystray import MenuItem as item
from core_logic import scan_emails, send_telegram

if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(APP_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

# Thiết lập chế độ Light (Sáng) với 2 tone Xanh - Trắng chuẩn giao diện VNPT
ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")

# Mã màu giao diện
COLOR_PRIMARY_BLUE = "#00558F"       # Xanh VNPT chủ đạo
COLOR_HOVER_BLUE   = "#004070"       # Xanh đậm khi hover
COLOR_ACCENT_BLUE  = "#0284C7"       # Xanh dương phụ trợ
COLOR_BG_LIGHT     = "#F4F7FA"       # Nền xám xanh nhạt dịu mắt
COLOR_CARD_WHITE   = "#FFFFFF"       # Nền trắng thẻ / khung
COLOR_BORDER       = "#D1DCE5"       # Đường viền xám xanh nhẹ
COLOR_TEXT_MAIN    = "#0F2942"       # Chữ xanh đen đậm
COLOR_TEXT_MUTED   = "#5A6E7F"       # Chữ ghi xám phụ

# Màu đỏ cho nút Dừng / Xóa
COLOR_RED_BTN      = "#D32F2F"
COLOR_RED_HOVER    = "#B71C1C"


def get_resource_path(relative_path):
    """Lấy đường dẫn chuẩn cho cả lúc chạy code thường và lúc đóng gói .exe"""
    if getattr(sys, 'frozen', False):
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

class EmailReminderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Email Reminder v1.0")
        self.geometry("900x680")
        self.configure(fg_color=COLOR_BG_LIGHT)
        # --- GẮN LOGO VÀO CỬA SỔ & TASKBAR ---
        icon_path = get_resource_path("app_icon.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass
        # -------------------------------------
        self.config = self.load_config()
        self.is_running = False
        self.stop_event = threading.Event()

        # --- CẤU HÌNH SYSTEM TRAY & SỰ KIỆN THU NHỎ ---
        self.tray_icon = None
        self.setup_tray_icon()
        self.bind("<Unmap>", self.on_unmap)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # --- HEADER BANNER XANH TRẮNG ---
        self.header_frame = ctk.CTkFrame(self, fg_color=COLOR_PRIMARY_BLUE, corner_radius=0, height=56)
        self.header_frame.pack(fill="x", side="top")
        self.header_frame.pack_propagate(False)
        
        lbl_title = ctk.CTkLabel(
            self.header_frame, 
            text="📬 Email Reminder v1.0", 
            font=("Segoe UI", 15, "bold"), 
            text_color="#FFFFFF"
        )
        lbl_title.pack(side="left", padx=20, pady=12)

        lbl_sub = ctk.CTkLabel(
            self.header_frame, 
            text="VNPT AI Assistant\nCopyright by quangvu@vnpt.vn - 2026", 
            font=("Segoe UI", 11, "bold"), 
            text_color="#B8DCF5",
            justify="right"
        )
        lbl_sub.pack(side="right", padx=20, pady=8)

        # --- TABVIEW GIAO DIỆN ---
        self.tabview = ctk.CTkTabview(
            self,
            fg_color=COLOR_CARD_WHITE,
            segmented_button_fg_color="#E2E8F0",
            segmented_button_selected_color=COLOR_PRIMARY_BLUE,
            segmented_button_selected_hover_color=COLOR_HOVER_BLUE,
            segmented_button_unselected_color="#E2E8F0",
            segmented_button_unselected_hover_color="#CBD5E1",
            text_color=COLOR_PRIMARY_BLUE,
            command=self.update_tab_colors
        )
        self.tabview.pack(padx=16, pady=(10, 16), fill="both", expand=True)
        
        self.tab_dashboard = self.tabview.add("Bảng điều khiển")
        self.tab_filters = self.tabview.add("Bộ lọc (Lists)")
        self.tab_settings = self.tabview.add("Cài đặt API")

        self.update_tab_colors()
        self.setup_settings_tab()
        self.setup_filters_tab()
        self.setup_dashboard_tab()

    def update_tab_colors(self):
        try:
            curr = self.tabview.get()
            for name, btn in self.tabview._segmented_button._buttons_dict.items():
                if name == curr:
                    btn.configure(text_color="#FFFFFF", fg_color=COLOR_PRIMARY_BLUE)
                else:
                    btn.configure(text_color=COLOR_PRIMARY_BLUE, fg_color="#E2E8F0")
        except Exception:
            pass

    def load_config(self):
        default = {
            "tele_token": "", "tele_chat_id": "", "api_key": "",
            "ai_engine": "Offline", "interval_mins": "15",
            "senders": [], "folders": ["Inbox"], "cc_emails": [],
            "keywords": []
        }
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                default.update(json.load(f))
        return default

    def save_config(self):
        raw_key = self.entry_api_key.get().strip()
        # Tự động lọc sạch nếu người dùng lỡ copy cả format JSON hoặc dấu ngoặc kép
        if '"' in raw_key or "'" in raw_key or ":" in raw_key:
            clean_k = raw_key.replace('"', '').replace("'", '').replace(',', '').strip()
            if "api_key" in clean_k:
                clean_k = clean_k.split(":")[-1].strip()
            raw_key = clean_k

        self.config["tele_token"] = self.entry_tele_token.get().strip()
        self.config["tele_chat_id"] = self.entry_tele_chat.get().strip()
        self.config["api_key"] = raw_key
        self.config["ai_engine"] = self.combo_ai.get()
        self.config["interval_mins"] = self.entry_interval.get().strip()
        
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=4)
        self.log("Đã lưu cấu hình thành công.")

    # --- TAB CÀI ĐẶT ---
    def setup_settings_tab(self):
        frame = ctk.CTkScrollableFrame(self.tab_settings, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        ctk.CTkLabel(frame, text="Telegram Bot Token:", font=("Segoe UI", 12, "bold"), text_color=COLOR_TEXT_MAIN).pack(anchor="w")
        self.entry_tele_token = ctk.CTkEntry(frame, width=440, fg_color="#FFFFFF", border_color=COLOR_BORDER, text_color=COLOR_TEXT_MAIN)
        self.entry_tele_token.pack(anchor="w", pady=(2, 10))
        self.entry_tele_token.insert(0, self.config.get("tele_token", ""))

        ctk.CTkLabel(frame, text="Telegram Chat ID:", font=("Segoe UI", 12, "bold"), text_color=COLOR_TEXT_MAIN).pack(anchor="w")
        self.entry_tele_chat = ctk.CTkEntry(frame, width=440, fg_color="#FFFFFF", border_color=COLOR_BORDER, text_color=COLOR_TEXT_MAIN)
        self.entry_tele_chat.pack(anchor="w", pady=(2, 10))
        self.entry_tele_chat.insert(0, self.config.get("tele_chat_id", ""))

        # Nút Hướng dẫn lấy Token ngay dưới Telegram Chat ID
        btn_help = ctk.CTkButton(
            frame, 
            text="❓ Hướng dẫn lấy Token & Chat ID", 
            fg_color="transparent", 
            border_width=1,
            border_color=COLOR_BORDER,
            text_color=COLOR_PRIMARY_BLUE,
            hover_color="#E2E8F0",
            command=self.show_telegram_help
        )
        btn_help.pack(anchor="w", pady=(0, 10))

        ctk.CTkLabel(frame, text="Chu kỳ quét (phút):", font=("Segoe UI", 12, "bold"), text_color=COLOR_TEXT_MAIN).pack(anchor="w")
        self.entry_interval = ctk.CTkEntry(frame, width=150, fg_color="#FFFFFF", border_color=COLOR_BORDER, text_color=COLOR_TEXT_MAIN)
        self.entry_interval.pack(anchor="w", pady=(2, 10))
        self.entry_interval.insert(0, str(self.config.get("interval_mins", "15")))

        ctk.CTkLabel(frame, text="Công cụ Tóm tắt AI:", font=("Segoe UI", 12, "bold"), text_color=COLOR_TEXT_MAIN).pack(anchor="w")
        ai_options = ["Offline", "Groq", "DeepSeek", "Gemini", "Grok", "OpenAI"]
        self.combo_ai = ctk.CTkOptionMenu(
            frame, 
            values=ai_options,
            fg_color=COLOR_PRIMARY_BLUE,
            button_color=COLOR_HOVER_BLUE,
            button_hover_color=COLOR_PRIMARY_BLUE,
            dropdown_fg_color="#FFFFFF",
            dropdown_text_color=COLOR_TEXT_MAIN,
            dropdown_hover_color="#E2E8F0"
        )
        self.combo_ai.pack(anchor="w", pady=(2, 10))
        self.combo_ai.set(self.config.get("ai_engine", "Offline"))

        ctk.CTkLabel(frame, text="API Key tương ứng (Bỏ trống nếu chọn Offline):", font=("Segoe UI", 12, "bold"), text_color=COLOR_TEXT_MAIN).pack(anchor="w")
        self.entry_api_key = ctk.CTkEntry(frame, width=440, show="*", fg_color="#FFFFFF", border_color=COLOR_BORDER, text_color=COLOR_TEXT_MAIN)
        self.entry_api_key.pack(anchor="w", pady=(2, 15))
        self.entry_api_key.insert(0, self.config.get("api_key", ""))

        # Hàng nút Thao tác
        btn_save = ctk.CTkButton(
            frame, 
            text="💾 Lưu cấu hình", 
            fg_color=COLOR_PRIMARY_BLUE, 
            hover_color=COLOR_HOVER_BLUE, 
            font=("Segoe UI", 13, "bold"),
            command=self.save_config
        )
        btn_save.pack(anchor="w", pady=(0, 10))

        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(anchor="w", pady=(0, 15))

        self.btn_test_tele = ctk.CTkButton(
            btn_row, 
            text="🔔 Test Telegram", 
            fg_color=COLOR_ACCENT_BLUE, 
            hover_color="#0369A1", 
            font=("Segoe UI", 12, "bold"),
            command=self.test_telegram_connection
        )
        self.btn_test_tele.pack(side="left", padx=(0, 10))

        self.btn_test_ai = ctk.CTkButton(
            btn_row, 
            text="🤖 Test kết nối AI", 
            fg_color=COLOR_PRIMARY_BLUE, 
            hover_color=COLOR_HOVER_BLUE, 
            font=("Segoe UI", 12, "bold"),
            command=self.test_ai_connection
        )
        self.btn_test_ai.pack(side="left")

    # --- TAB BỘ LỌC ---
    def setup_filters_tab(self):
        grid_frame = ctk.CTkFrame(self.tab_filters, fg_color="transparent")
        grid_frame.pack(fill="both", expand=True, padx=5, pady=5)
        grid_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.filter_scroll_frames = {}
        self.create_filter_column(grid_frame, "Senders (Email/Tên người gửi)", "senders", 0)
        self.create_filter_column(grid_frame, "Folders (Thư mục quét)", "folders", 1)
        self.create_filter_column(grid_frame, "Keywords (Từ khóa Tiêu đề/Nội dung)", "keywords", 2)

    def create_filter_column(self, parent, title, config_key, col):
        frame = ctk.CTkFrame(parent, fg_color=COLOR_CARD_WHITE, border_width=1, border_color=COLOR_BORDER, corner_radius=6)
        frame.grid(row=0, column=col, padx=8, pady=5, sticky="nsew")
        
        ctk.CTkLabel(frame, text=title, font=("Segoe UI", 13, "bold"), text_color=COLOR_PRIMARY_BLUE).pack(pady=(8, 4))
        
        input_frame = ctk.CTkFrame(frame, fg_color="transparent")
        input_frame.pack(fill="x", padx=10, pady=5)

        entry = ctk.CTkEntry(input_frame, placeholder_text="Nhập & nhấn Thêm...", fg_color="#FFFFFF", border_color=COLOR_BORDER, text_color=COLOR_TEXT_MAIN)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        btn = ctk.CTkButton(
            input_frame, 
            text="Thêm", 
            width=65, 
            fg_color=COLOR_PRIMARY_BLUE, 
            hover_color=COLOR_HOVER_BLUE,
            font=("Segoe UI", 12, "bold"),
            command=lambda: self.add_item(config_key, entry)
        )
        btn.pack(side="right")
        entry.bind("<Return>", lambda event: self.add_item(config_key, entry))
        
        scroll_frame = ctk.CTkScrollableFrame(frame, height=240, fg_color="#F8FAFC")
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.filter_scroll_frames[config_key] = scroll_frame
        
        self.refresh_list(config_key)
        
        # Nút Xóa sạch list: Màu Đỏ
        btn_rm = ctk.CTkButton(
            frame, 
            text="🗑️ Xóa sạch list", 
            fg_color=COLOR_RED_BTN, 
            hover_color=COLOR_RED_HOVER, 
            font=("Segoe UI", 12, "bold"),
            command=lambda: self.clear_list(config_key)
        )
        btn_rm.pack(fill="x", padx=10, pady=8)

    def add_item(self, key, entry_widget):
        val = entry_widget.get().strip()
        if val:
            if key not in self.config:
                self.config[key] = []
            if val not in self.config[key]:
                self.config[key].append(val)
                self.save_config()
                self.refresh_list(key)
            entry_widget.delete(0, 'end')

    def remove_item(self, key, val):
        if key in self.config and val in self.config[key]:
            self.config[key].remove(val)
            self.save_config()
            self.refresh_list(key)

    def clear_list(self, key):
        self.config[key] = []
        self.save_config()
        self.refresh_list(key)

    def refresh_list(self, key):
        scroll_frame = self.filter_scroll_frames[key]
        for widget in scroll_frame.winfo_children():
            widget.destroy()

        items = self.config.get(key, [])
        if not items:
            lbl_empty = ctk.CTkLabel(scroll_frame, text="(Trống - chưa có bộ lọc nào)", text_color=COLOR_TEXT_MUTED)
            lbl_empty.pack(pady=15)
            return

        for item in items:
            row_frame = ctk.CTkFrame(scroll_frame, fg_color="#FFFFFF", border_width=1, border_color="#E2E8F0", corner_radius=5)
            row_frame.pack(fill="x", pady=2, padx=2)

            lbl = ctk.CTkLabel(row_frame, text=item, anchor="w", text_color=COLOR_TEXT_MAIN, font=("Segoe UI", 11))
            lbl.pack(side="left", fill="x", expand=True, padx=8, pady=3)

            # Nút Xóa phần tử: Màu Đỏ
            btn_del = ctk.CTkButton(
                row_frame, 
                text="✕", 
                width=26, 
                height=22, 
                fg_color=COLOR_RED_BTN, 
                hover_color=COLOR_RED_HOVER, 
                command=lambda val=item: self.remove_item(key, val)
            )
            btn_del.pack(side="right", padx=5, pady=3)

    # --- TAB ĐIỀU KHIỂN & LOG ---
    def setup_dashboard_tab(self):
        # Nút Bắt đầu (Xanh) / Dừng (Đỏ)
        self.btn_toggle = ctk.CTkButton(
            self.tab_dashboard, 
            text="▶ BẮT ĐẦU THEO DÕI", 
            font=("Segoe UI", 15, "bold"), 
            height=42, 
            fg_color=COLOR_PRIMARY_BLUE, 
            hover_color=COLOR_HOVER_BLUE,
            command=self.toggle_running
        )
        self.btn_toggle.pack(pady=10)

        # Hộp Log nền trắng xám, chữ sắc nét
        self.log_box = ctk.CTkTextbox(
            self.tab_dashboard, 
            fg_color="#F8FAFC", 
            text_color=COLOR_TEXT_MAIN, 
            border_width=1, 
            border_color=COLOR_BORDER,
            font=("Consolas", 12)
        )
        self.log_box.pack(fill="both", expand=True, pady=(5, 10))
        self.log("Hệ thống sẵn sàng. Vui lòng kiểm tra tab Cài Đặt trước khi Bắt đầu.")

    def log(self, msg):
        time_str = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{time_str}] {msg}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def toggle_running(self):
        if not self.is_running:
            self.save_config()
            self.is_running = True
            self.stop_event.clear()
            # Nút Dừng: Màu Đỏ
            self.btn_toggle.configure(text="⬛ DỪNG THEO DÕI", fg_color=COLOR_RED_BTN, hover_color=COLOR_RED_HOVER)
            self.log(f"Đã BẬT tiến trình quét ngầm (Chu kỳ: {self.config.get('interval_mins')} phút).")
            threading.Thread(target=self.worker_thread, daemon=True).start()
        else:
            self.is_running = False
            self.stop_event.set()
            # Trở lại nút Bắt đầu: Màu Xanh
            self.btn_toggle.configure(text="▶ BẮT ĐẦU THEO DÕI", fg_color=COLOR_PRIMARY_BLUE, hover_color=COLOR_HOVER_BLUE)
            self.log("Đã DỪNG tiến trình quét.")

    def worker_thread(self):
        try:
            interval_sec = int(self.config.get("interval_mins", 15)) * 60
        except:
            interval_sec = 900

        while not self.stop_event.is_set():
            self.after(0, self.log, f"Đang quét hòm thư... (AI: {self.config.get('ai_engine')})")
            scan_emails(self.config, lambda msg: self.after(0, self.log, msg))
            
            for _ in range(interval_sec):
                if self.stop_event.is_set(): break
                time.sleep(1)

    def test_telegram_connection(self):
        token = self.entry_tele_token.get().strip()
        chat_id = self.entry_tele_chat.get().strip()
        
        if not token or not chat_id:
            messagebox.showwarning("Thiếu thông tin", "⚠️ Vui lòng nhập Telegram Bot Token và Chat ID trước khi test!")
            return

        self.btn_test_tele.configure(text="⏳ Đang gửi...", state="disabled")
        self.log("Đang kiểm tra kết nối Telegram...")

        def _test_tele():
            try:
                msg = "🔔 <b>Test thành công!</b> Ứng dụng Email Reminder v1.0 đã kết nối được với Telegram của bạn."
                msg_plain = "🔔 Test thành công! Ứng dụng Email Reminder v1.0 đã kết nối được với Telegram của bạn."
                ok = send_telegram(token, chat_id, msg, msg_plain, log_callback=lambda m: self.after(0, self.log, m))
                if ok:
                    self.after(0, self.log, "✅ Gửi tin nhắn thử nghiệm thành công! Hãy kiểm tra điện thoại.")
                    self.after(0, lambda: messagebox.showinfo("Kết Quả Telegram", "✅ Kết nối Telegram thành công!\n\nĐã gửi tin nhắn thử nghiệm tới Telegram của bạn."))
                else:
                    self.after(0, lambda: messagebox.showerror("Lỗi Telegram", "❌ Gửi tin nhắn thất bại!\n\nVui lòng kiểm tra lại Bot Token, Chat ID hoặc đảm bảo bạn đã bấm START với Bot."))
            finally:
                self.after(0, lambda: self.btn_test_tele.configure(text="🔔 Test Telegram", state="normal"))

        threading.Thread(target=_test_tele, daemon=True).start()

    def test_ai_connection(self):
        ai_engine = self.combo_ai.get()
        api_key = self.entry_api_key.get().strip()

        if "Offline" not in ai_engine and not api_key:
            messagebox.showwarning("Thiếu API Key", f"⚠️ Bạn chưa nhập API Key cho [{ai_engine}]!\n\nVui lòng dán API Key vào ô bên dưới trước khi test.")
            return

        self.btn_test_ai.configure(text="⏳ Đang test AI...", state="disabled")
        self.log(f"Đang kiểm tra kết nối [{ai_engine}]...")

        def _test():
            try:
                from ai_engines import summarize_with_ai
                from offline_ai import summarize_offline
                sample_body = "Kính gửi anh/chị, nhờ anh/chị xem xét và phê duyệt giúp báo cáo kế hoạch tuần trước 17h00 hôm nay. Trân trọng!"
                if "Offline" in ai_engine:
                    res = summarize_offline(sample_body, "Kế hoạch tuần", "Nguyễn Văn A")
                else:
                    res = summarize_with_ai(ai_engine, api_key, "Kế hoạch tuần", "Nguyễn Văn A", sample_body, log_callback=lambda m: self.after(0, self.log, m))
                self.after(0, self.log, f" Kết quả test tóm tắt [{ai_engine}]:\n{res}")
                self.after(0, lambda: messagebox.showinfo(f"Kết Quả Test [{ai_engine}]", f"✅ Kết nối AI thành công!\n\n📄 Nội dung tóm tắt mẫu:\n{res}"))
            except Exception as e:
                self.after(0, self.log, f"❌ Lỗi kiểm tra AI: {e}")
                self.after(0, lambda: messagebox.showerror(f"Lỗi Kết Nối [{ai_engine}]", f"❌ Không thể kết nối hoặc lỗi xử lý:\n{e}"))
            finally:
                self.after(0, lambda: self.btn_test_ai.configure(text="🤖 Test kết nối AI", state="normal"))

        threading.Thread(target=_test, daemon=True).start()

    def show_telegram_help(self):
        """Hiển thị cửa sổ Popup hướng dẫn tạo bot Telegram"""
        help_window = ctk.CTkToplevel(self)
        help_window.title("Hướng dẫn tạo Bot & lấy Chat ID Telegram")
        help_window.geometry("580x500")
        help_window.attributes("-topmost", True)  # Luôn nổi lên trên để tiện theo dõi

        textbox = ctk.CTkTextbox(help_window, wrap="word", font=("Arial", 13))
        textbox.pack(fill="both", expand=True, padx=15, pady=15)

        help_content = """📖 HƯỚNG DẪN LẤY TELEGRAM BOT TOKEN & CHAT ID
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BƯỚC 0: DOWNLOAD AI MODEL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Truy cập link: https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/blob/main/qwen2.5-3b-instruct-q4_k_m.gguf
2. Click Download.
3. Vào thư mục chứa file Email Reminder v1.0.exe và copy file qwen2.5-3b-instruct-q4_k_m.gguf vào thư mục \\models\\.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BƯỚC 1: TẠO BOT VÀ LẤY BOT TOKEN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Mở Telegram, tìm kiếm @BotFather (có tích xanh).
2. Nhấn nút Start (hoặc gửi /start).
3. Gửi lệnh /newbot.
4. Đặt tên hiển thị cho bot (Ví dụ: Nhắc Mail VNPT).
5. Đặt username cho bot (phải kết thúc bằng chữ 'bot', ví dụ: my_mail_alert_bot).
6. BotFather sẽ gửi một đoạn mã HTTP API Token (dạng: 7123456789:AAFn9_...). 
👉 Copy đoạn mã này dán vào ô 'Telegram Bot Token'.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BƯỚC 2: KÍCH HOẠT BOT VÀ LẤY CHAT ID
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Bấm vào link bot vừa tạo (t.me/ten_bot_vua_dat) và nhấn nút START. (BẮT BUỘC)
2. Tìm bot @userinfobot hoặc @getmyid_bot trên Telegram và nhấn Start.
3. Bot sẽ trả về mục 'Id' (dạng số nguyên, ví dụ: 123456789).
👉 Copy dãy số này dán vào ô 'Telegram Chat ID'.

* Nhận tin trong Nhóm (Group):
- Thêm bot của bạn vào nhóm chat.
- Thêm bot @getidsbot vào nhóm để lấy Group Chat ID (bắt đầu bằng dấu trừ, ví dụ: -100123456789).
- Dán mã có dấu trừ đó vào ô 'Telegram Chat ID'.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BƯỚC 3: LƯU & KIỂM TRA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Bấm nút 'Lưu cấu hình'.
- Bấm nút '🔔 Test gửi Telegram' để kiểm tra kết quả ngay."""

        textbox.insert("1.0", help_content)
        textbox.configure(state="disabled")  # Khóa chỉ cho đọc/copy, không cho sửa

    # --- TRAY ICON & WINDOW STATE MANAGEMENT ---
    def setup_tray_icon(self):
        """Khởi tạo icon dưới khay hệ thống (System Tray)"""
        try:
            icon_img_path = get_resource_path("app_icon.png")
            if not os.path.exists(icon_img_path):
                icon_img_path = get_resource_path("app_icon.ico")
            
            image = Image.open(icon_img_path)
            menu = pystray.Menu(
                item("📬 Mở giao diện", self.show_window, default=True),
                item("⏯️ Bật/Dừng theo dõi", self.toggle_running_from_tray),
                pystray.Menu.SEPARATOR,
                item("❌ Thoát ứng dụng", self.quit_app)
            )
            self.tray_icon = pystray.Icon("EmailReminder", image, "Email Reminder v1.0", menu)
            self.tray_icon.run_detached()
        except Exception as e:
            print(f"Lỗi khởi tạo Tray Icon: {e}")

    def on_unmap(self, event):
        """Khi click nút minimize (_), ẩn cửa sổ xuống System Tray"""
        if event.widget == self and self.state() == "iconic":
            self.withdraw()
            if self.tray_icon:
                try:
                    self.tray_icon.notify("Ứng dụng đang chạy ngầm dưới khay hệ thống.", "Email Reminder v1.0")
                except Exception:
                    pass

    def show_window(self, icon=None, item=None):
        """Hiển thị lại cửa sổ từ Tray Icon"""
        self.after(0, self._restore_window)

    def _restore_window(self):
        self.deiconify()
        self.state("normal")
        self.lift()
        self.attributes("-topmost", True)
        self.after(100, lambda: self.attributes("-topmost", False))
        self.focus_force()

    def toggle_running_from_tray(self, icon=None, item=None):
        """Bật/dừng tiến trình quét từ menu Tray"""
        self.after(0, self.toggle_running)

    def on_closing(self):
        """Đóng ứng dụng hoàn toàn khi bấm nút X"""
        self.quit_app()

    def quit_app(self, icon=None, item=None):
        """Dừng các tiến trình và thoát ứng dụng sạch sẽ"""
        self.is_running = False
        self.stop_event.set()
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.after(0, self._destroy_app)

    def _destroy_app(self):
        try:
            self.destroy()
        except Exception:
            pass
        sys.exit(0)


if __name__ == "__main__":
    app = EmailReminderApp()
    app.mainloop()
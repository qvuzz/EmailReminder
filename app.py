import customtkinter as ctk
import json
import os
import threading
import time
import sys
import webbrowser
from datetime import datetime, timedelta
from tkinter import messagebox
from PIL import Image
import pystray
from pystray import MenuItem as item
from core_logic import (
    scan_emails, send_telegram, mark_email_as_read_outlook, delete_email_outlook,
    telegram_polling_worker, scan_all_available_folders, fetch_outlook_recent_contacts, _norm
)
from imap_logic import scan_emails_imap, test_imap_connection_logic, mark_email_as_read_imap, delete_email_imap
from security import encrypt_password, decrypt_password, is_encrypted
import uuid
import copy
import ctypes

if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(APP_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

# Thiết lập chế độ Light (Sáng) chuẩn giao diện VNPT SaaS
ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")

# --- BẢNG MÀU VNPT MODERN SAAS THEME ---
COLOR_SIDEBAR_BG     = "#0F172A"  # Dark Slate Navy (Menu dọc)
COLOR_SIDEBAR_HOVER  = "#1E293B"  # Hover menu dọc
COLOR_SIDEBAR_ACTIVE = "#0066CC"  # Active menu dọc (Xanh VNPT)
COLOR_PRIMARY_BLUE   = "#0066CC"  # Xanh dương VNPT chủ đạo
COLOR_HOVER_BLUE     = "#0052A3"  # Xanh đậm khi hover
COLOR_ACCENT_BLUE    = "#0284C7"  # Xanh dương phụ trợ
COLOR_BG_LIGHT       = "#F1F5F9"  # Nền ứng dụng xám nhạt cao cấp
COLOR_CARD_WHITE     = "#FFFFFF"  # Nền trắng thẻ / khung card
COLOR_BORDER         = "#E2E8F0"  # Viền thẻ tinh tế
COLOR_TEXT_MAIN      = "#0F172A"  # Chữ đen đậm
COLOR_TEXT_MUTED     = "#64748B"  # Chữ ghi xám phụ
COLOR_GREEN_BTN      = "#10B981"  # Xanh lá thông báo / Mở mail
COLOR_GREEN_HOVER    = "#059669"
COLOR_RED_BTN        = "#EF4444"  # Đỏ nút Dừng / Xóa
COLOR_RED_HOVER      = "#DC2626"


def get_resource_path(relative_path):
    """Lấy đường dẫn chuẩn cho cả lúc chạy code thường và lúc đóng gói .exe"""
    if getattr(sys, 'frozen', False):
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


class IMAPAccountModal(ctk.CTkToplevel):
    """Cửa sổ Popup thêm / sửa tài khoản Webmail IMAP"""
    def __init__(self, parent, account_data=None, on_save_callback=None):
        super().__init__(parent)
        self.parent = parent
        self.account_data = account_data or {}
        self.on_save_callback = on_save_callback
        self.is_edit = bool(self.account_data.get("id"))
        
        self.title("Chỉnh sửa tài khoản Webmail" if self.is_edit else "Thêm tài khoản Webmail mới")
        self.geometry("520x490")
        self.resizable(False, False)
        self.configure(fg_color=COLOR_BG_LIGHT)
        self.attributes("-topmost", True)
        self.grab_set()

        try:
            self.update_idletasks()
            x = parent.winfo_x() + (parent.winfo_width() - 520) // 2
            y = parent.winfo_y() + (parent.winfo_height() - 490) // 2
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        container = ctk.CTkFrame(self, fg_color=COLOR_CARD_WHITE, corner_radius=10, border_width=1, border_color=COLOR_BORDER)
        container.pack(fill="both", expand=True, padx=16, pady=16)

        lbl_h = ctk.CTkLabel(
            container, 
            text="✏️ CHỈNH SỬA TÀI KHOẢN WEBMAIL" if self.is_edit else "➕ THÊM TÀI KHOẢN WEBMAIL", 
            font=("Segoe UI", 14, "bold"), 
            text_color=COLOR_PRIMARY_BLUE
        )
        lbl_h.pack(anchor="w", padx=16, pady=(14, 10))

        ctk.CTkLabel(container, text="Tên gợi nhớ (ví dụ: VNPT Công việc, Gmail Cá nhân):", font=("Segoe UI", 11, "bold"), text_color=COLOR_TEXT_MAIN).pack(anchor="w", padx=16)
        self.entry_name = ctk.CTkEntry(container, width=450, fg_color="#FFFFFF", border_color=COLOR_BORDER, text_color=COLOR_TEXT_MAIN)
        self.entry_name.pack(anchor="w", padx=16, pady=(2, 8))
        self.entry_name.insert(0, self.account_data.get("name", ""))

        ctk.CTkLabel(container, text="IMAP Server (ví dụ: email.vnpt.vn, imap.gmail.com):", font=("Segoe UI", 11, "bold"), text_color=COLOR_TEXT_MAIN).pack(anchor="w", padx=16)
        self.entry_server = ctk.CTkEntry(container, width=450, fg_color="#FFFFFF", border_color=COLOR_BORDER, text_color=COLOR_TEXT_MAIN)
        self.entry_server.pack(anchor="w", padx=16, pady=(2, 8))
        self.entry_server.insert(0, self.account_data.get("server", ""))

        port_row = ctk.CTkFrame(container, fg_color="transparent")
        port_row.pack(anchor="w", padx=16, pady=(2, 8))
        ctk.CTkLabel(port_row, text="Port: ", font=("Segoe UI", 11, "bold"), text_color=COLOR_TEXT_MAIN).pack(side="left")
        self.entry_port = ctk.CTkEntry(port_row, width=80, fg_color="#FFFFFF", border_color=COLOR_BORDER, text_color=COLOR_TEXT_MAIN)
        self.entry_port.pack(side="left", padx=(0, 20))
        self.entry_port.insert(0, str(self.account_data.get("port", "993")))

        self.cb_ssl = ctk.CTkCheckBox(port_row, text="Sử dụng SSL/TLS (Khuyên dùng)", text_color=COLOR_TEXT_MAIN, font=("Segoe UI", 11, "bold"))
        self.cb_ssl.pack(side="left")
        if self.account_data.get("ssl", True):
            self.cb_ssl.select()
        else:
            self.cb_ssl.deselect()

        ctk.CTkLabel(container, text="Tài khoản / Email đăng nhập:", font=("Segoe UI", 11, "bold"), text_color=COLOR_TEXT_MAIN).pack(anchor="w", padx=16)
        self.entry_user = ctk.CTkEntry(container, width=450, fg_color="#FFFFFF", border_color=COLOR_BORDER, text_color=COLOR_TEXT_MAIN)
        self.entry_user.pack(anchor="w", padx=16, pady=(2, 8))
        self.entry_user.insert(0, self.account_data.get("user", ""))

        ctk.CTkLabel(container, text="Mật khẩu Webmail (hoặc App Password):", font=("Segoe UI", 11, "bold"), text_color=COLOR_TEXT_MAIN).pack(anchor="w", padx=16)
        pwd_row = ctk.CTkFrame(container, fg_color="transparent")
        pwd_row.pack(anchor="w", padx=16, pady=(2, 12))
        self.entry_pwd = ctk.CTkEntry(pwd_row, width=390, show="*", fg_color="#FFFFFF", border_color=COLOR_BORDER, text_color=COLOR_TEXT_MAIN)
        self.entry_pwd.pack(side="left", padx=(0, 10))
        self.entry_pwd.insert(0, decrypt_password(self.account_data.get("password", "")))

        self.show_pwd = False
        self.btn_toggle_pwd = ctk.CTkButton(pwd_row, text="👁️", width=45, fg_color="#E2E8F0", text_color=COLOR_TEXT_MAIN, hover_color="#CBD5E1", command=self.toggle_password)
        self.btn_toggle_pwd.pack(side="left")

        btn_box = ctk.CTkFrame(container, fg_color="transparent")
        btn_box.pack(fill="x", padx=16, pady=(10, 10))

        self.btn_test = ctk.CTkButton(
            btn_box, 
            text="🧪 Test kết nối", 
            fg_color=COLOR_ACCENT_BLUE, 
            hover_color="#0369A1", 
            font=("Segoe UI", 11, "bold"),
            command=self.test_connection
        )
        self.btn_test.pack(side="left", padx=(0, 10))

        btn_save = ctk.CTkButton(
            btn_box, 
            text="💾 Lưu tài khoản", 
            fg_color=COLOR_PRIMARY_BLUE, 
            hover_color=COLOR_HOVER_BLUE, 
            font=("Segoe UI", 11, "bold"),
            command=self.save_account
        )
        btn_save.pack(side="left", padx=(0, 10))

        btn_cancel = ctk.CTkButton(
            btn_box, 
            text="Hủy", 
            fg_color="#E2E8F0", 
            text_color=COLOR_TEXT_MAIN, 
            hover_color="#CBD5E1", 
            font=("Segoe UI", 11, "bold"),
            width=70,
            command=self.destroy
        )
        btn_cancel.pack(side="right")

    def toggle_password(self):
        self.show_pwd = not self.show_pwd
        self.entry_pwd.configure(show="" if self.show_pwd else "*")

    def test_connection(self):
        server = self.entry_server.get().strip()
        port_str = self.entry_port.get().strip()
        user = self.entry_user.get().strip()
        password = self.entry_pwd.get().strip()
        use_ssl = bool(self.cb_ssl.get())

        if not server or not user or not password:
            messagebox.showwarning("Thiếu thông tin", "⚠️ Vui lòng nhập đầy đủ Server, Tài khoản và Mật khẩu trước khi Test!", parent=self)
            return

        self.btn_test.configure(text="⏳ Đang test...", state="disabled")

        def _run():
            try:
                ok, msg = test_imap_connection_logic(server, port_str, user, password, use_ssl)
                if ok:
                    self.after(0, lambda: messagebox.showinfo("Kết Quả Webmail", f"✅ Kết nối thành công tới {server}!\n{msg}", parent=self))
                else:
                    self.after(0, lambda: messagebox.showerror("Lỗi Kết Nối", f"❌ Kết nối thất bại:\n{msg}", parent=self))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Lỗi Kết Nối", f"❌ Không thể kết nối tới Webmail:\n{e}", parent=self))
            finally:
                self.after(0, lambda: self.btn_test.configure(text="🧪 Test kết nối", state="normal"))

        threading.Thread(target=_run, daemon=True).start()

    def save_account(self):
        name = self.entry_name.get().strip()
        server = self.entry_server.get().strip()
        port_str = self.entry_port.get().strip()
        user = self.entry_user.get().strip()
        password = self.entry_pwd.get().strip()
        use_ssl = bool(self.cb_ssl.get())

        if not server or not user or not password:
            messagebox.showwarning("Thiếu thông tin", "⚠️ Vui lòng nhập đầy đủ Server, Tài khoản và Mật khẩu!", parent=self)
            return

        if not name:
            name = user.split("@")[0] if "@" in user else "Webmail"

        acc_id = self.account_data.get("id") or str(uuid.uuid4())[:8]
        new_data = {
            "id": acc_id,
            "name": name,
            "server": server,
            "port": port_str or "993",
            "user": user,
            "password": password,
            "ssl": use_ssl
        }

        if self.on_save_callback:
            self.on_save_callback(new_data, self.is_edit)
        self.destroy()


def open_email_item(email_data, log_callback=None):
    """Mở trực tiếp email trong Microsoft Outlook hoặc trình duyệt Webmail"""
    if not email_data:
        return False
    
    acc_name = email_data.get("account_name", "")
    entry_id = email_data.get("entry_id")
    
    if ("Outlook" in acc_name or entry_id) and entry_id:
        try:
            import win32com.client
            import pythoncom
            pythoncom.CoInitialize()
            outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
            item = outlook.GetItemFromID(entry_id)
            item.Display()
            if log_callback:
                log_callback(f"📨 Đã mở email '{email_data.get('subject')}' trong Microsoft Outlook.")
            return True
        except Exception as e:
            if log_callback:
                log_callback(f"⚠️ Không thể mở email Outlook trực tiếp: {e}")
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    server = str(email_data.get("server", "")).lower()
    user = str(email_data.get("user", "")).lower()
    
    if "gmail" in server or "gmail.com" in user:
        webbrowser.open("https://mail.google.com")
    elif "vnpt" in server or "vnpt.vn" in user:
        webbrowser.open("https://email.vnpt.vn")
    elif server:
        webbrowser.open(f"https://{server}")
    else:
        webbrowser.open("mailto:")
    
    if log_callback:
        log_callback(f"🌐 Đang mở Webmail cho tài khoản {acc_name}...")
    return True


def parse_email_time_helper(email):
    """Chuyển đổi chuỗi thời gian email thành datetime để sắp xếp chuẩn xác"""
    t_str = email.get("time", "") if isinstance(email, dict) else ""
    if not t_str:
        return datetime.min
    for fmt in ("%H:%M %d/%m/%Y", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%H:%M:%S %d/%m/%Y"):
        try:
            return datetime.strptime(t_str, fmt)
        except Exception:
            pass
    return datetime.min


class NotificationPopup(ctk.CTkToplevel):
    """Cửa sổ thông báo nổi ở góc phải màn hình gần System Tray (Desktop Floating Card Notification)"""
    def __init__(self, parent, email_list, on_open_app=None):
        super().__init__(parent)
        self.parent = parent
        # Hiển thị vòng từ cũ sang mới theo thời gian
        self.emails = sorted(email_list, key=parse_email_time_helper) if email_list else []
        self.current_idx = 0
        self.on_open_app = on_open_app
        
        self.is_pinned = False
        self.is_paused = False
        self.countdown = 10  # 10 giây tự động chuyển email kế tiếp
        self._timer_id = None

        self.title("Email Reminder Notification")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        
        self.popup_w = 460
        self.popup_h = 285
        self._position_bottom_right()

        self.card = ctk.CTkFrame(
            self, 
            fg_color=COLOR_CARD_WHITE, 
            corner_radius=12, 
            border_width=2, 
            border_color=COLOR_PRIMARY_BLUE
        )
        self.card.pack(fill="both", expand=True, padx=2, pady=2)

        header = ctk.CTkFrame(self.card, fg_color=COLOR_PRIMARY_BLUE, corner_radius=10, height=36)
        header.pack(fill="x", padx=4, pady=4)
        header.pack_propagate(False)

        lbl_logo = ctk.CTkLabel(
            header, 
            text="📬 THÔNG BÁO EMAIL MỚI", 
            font=("Segoe UI", 11, "bold"), 
            text_color="#FFFFFF"
        )
        lbl_logo.pack(side="left", padx=10, pady=4)

        btn_close = ctk.CTkButton(
            header, 
            text="✕", 
            width=26, 
            height=24, 
            fg_color="transparent", 
            hover_color=COLOR_RED_BTN, 
            text_color="#FFFFFF",
            font=("Segoe UI", 12, "bold"),
            command=self.close_popup
        )
        btn_close.pack(side="right", padx=(2, 6), pady=4)

        self.btn_pin = ctk.CTkButton(
            header, 
            text="📌", 
            width=26, 
            height=24, 
            fg_color="transparent", 
            hover_color=COLOR_HOVER_BLUE, 
            text_color="#FFFFFF",
            font=("Segoe UI", 11),
            command=self.toggle_pin
        )
        self.btn_pin.pack(side="right", padx=2, pady=4)

        self.lbl_timer = ctk.CTkLabel(
            header,
            text=f"⏱️ {self.countdown}s",
            font=("Segoe UI", 10),
            text_color="#B8DCF5"
        )
        self.lbl_timer.pack(side="right", padx=6, pady=4)

        info_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        info_frame.pack(side="top", fill="x", padx=12, pady=(2, 1))

        meta_row = ctk.CTkFrame(info_frame, fg_color="transparent")
        meta_row.pack(fill="x")

        self.lbl_source = ctk.CTkLabel(
            meta_row,
            text="📁 Outlook • Inbox",
            font=("Segoe UI", 10, "bold"),
            text_color=COLOR_TEXT_MUTED
        )
        self.lbl_source.pack(side="left")

        nav_top_box = ctk.CTkFrame(meta_row, fg_color="transparent")
        nav_top_box.pack(side="right")

        self.btn_top_prev = ctk.CTkButton(
            nav_top_box,
            text="◀",
            width=28,
            height=22,
            fg_color=COLOR_PRIMARY_BLUE,
            hover_color=COLOR_HOVER_BLUE,
            text_color="#FFFFFF",
            font=("Segoe UI", 11, "bold"),
            command=self.prev_email
        )
        self.btn_top_prev.pack(side="left", padx=(0, 4))

        self.lbl_counter = ctk.CTkLabel(
            nav_top_box,
            text="[ 1 / 1 ]",
            font=("Segoe UI", 11, "bold"),
            text_color=COLOR_PRIMARY_BLUE,
            fg_color="#E0F2FE",
            corner_radius=4,
            padx=8,
            pady=1
        )
        self.lbl_counter.pack(side="left", padx=(0, 4))

        self.btn_top_next = ctk.CTkButton(
            nav_top_box,
            text="▶",
            width=28,
            height=22,
            fg_color=COLOR_PRIMARY_BLUE,
            hover_color=COLOR_HOVER_BLUE,
            text_color="#FFFFFF",
            font=("Segoe UI", 11, "bold"),
            command=self.next_email
        )
        self.btn_top_next.pack(side="left")

        sender_row = ctk.CTkFrame(info_frame, fg_color="transparent")
        sender_row.pack(fill="x", pady=(1, 0))

        self.lbl_sender = ctk.CTkLabel(
            sender_row,
            text="👤 Người gửi",
            font=("Segoe UI", 11, "bold"),
            text_color=COLOR_TEXT_MAIN,
            anchor="w"
        )
        self.lbl_sender.pack(side="left", fill="x", expand=True)

        self.lbl_time = ctk.CTkLabel(
            sender_row,
            text="🕒 14:30",
            font=("Segoe UI", 10),
            text_color=COLOR_TEXT_MUTED
        )
        self.lbl_time.pack(side="right")

        self.lbl_subject = ctk.CTkLabel(
            info_frame,
            text="✉️ Tiêu đề thư...",
            font=("Segoe UI", 11, "bold"),
            text_color=COLOR_PRIMARY_BLUE,
            anchor="w",
            wraplength=425,
            justify="left"
        )
        self.lbl_subject.pack(fill="x", pady=(1, 1))

        self.footer = ctk.CTkFrame(self.card, fg_color="transparent", height=38)
        self.footer.pack(side="bottom", fill="x", padx=12, pady=(2, 8))

        action_box = ctk.CTkFrame(self.footer, fg_color="transparent")
        action_box.pack(side="right")

        self.btn_open_mail = ctk.CTkButton(
            action_box,
            text="✉️ Mở Mail",
            width=85,
            height=30,
            fg_color="#FFFFFF",
            border_width=1,
            border_color=COLOR_PRIMARY_BLUE,
            text_color=COLOR_PRIMARY_BLUE,
            hover_color="#F0F7FF",
            font=("Segoe UI", 11, "bold"),
            command=self.open_current_email
        )
        self.btn_open_mail.pack(side="left", padx=(0, 6))

        self.btn_read = ctk.CTkButton(
            action_box,
            text="✓ Đã đọc",
            width=70,
            height=30,
            fg_color="#FFFFFF",
            border_width=1,
            border_color=COLOR_PRIMARY_BLUE,
            text_color=COLOR_PRIMARY_BLUE,
            hover_color="#F0F7FF",
            font=("Segoe UI", 11, "bold"),
            command=self.mark_current_email_read
        )
        self.btn_read.pack(side="left", padx=(0, 6))

        self.btn_delete_notif = ctk.CTkButton(
            action_box,
            text="🗑️ Xóa",
            width=62,
            height=30,
            fg_color="#FFFFFF",
            border_width=1,
            border_color="#CBD5E1",
            text_color=COLOR_RED_BTN,
            hover_color="#FEF2F2",
            font=("Segoe UI", 11, "bold"),
            command=self.delete_current_notification
        )
        self.btn_delete_notif.pack(side="left")

        self.txt_content = ctk.CTkTextbox(
            self.card, 
            wrap="word", 
            font=("Segoe UI", 11),
            fg_color="#F8FAFC",
            border_width=1,
            border_color=COLOR_BORDER,
            corner_radius=8
        )
        self.txt_content.pack(side="top", fill="both", expand=True, padx=12, pady=(0, 2))

        self.bind("<Enter>", self.on_mouse_enter)
        self.bind("<Leave>", self.on_mouse_leave)
        self.card.bind("<Enter>", self.on_mouse_enter)
        self.card.bind("<Leave>", self.on_mouse_leave)
        self.txt_content.bind("<Enter>", self.on_mouse_enter)
        self.txt_content.bind("<Leave>", self.on_mouse_leave)

        self.render_email()
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self._start_timer()

    def update_emails(self, new_emails):
        if not new_emails:
            return
        # Hiển thị vòng từ cũ sang mới theo thời gian
        self.emails = sorted(new_emails, key=parse_email_time_helper) if new_emails else []
        self.current_idx = 0
        self.countdown = 10
        self.is_paused = False
        if hasattr(self.parent, "cancel_reopen_popup"):
            self.parent.cancel_reopen_popup()
        self.render_email()
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self._start_timer()

    def prev_email(self):
        if not self.emails:
            return
        self.current_idx = (self.current_idx - 1) % len(self.emails)
        self.countdown = 10
        self.render_email()

    def next_email(self):
        if not self.emails:
            return
        self.current_idx = (self.current_idx + 1) % len(self.emails)
        self.countdown = 10
        self.render_email()

    def open_current_email(self):
        if not self.emails:
            return
        email = self.emails[self.current_idx]
        if email.get("is_thread") and hasattr(self.parent, "open_thread_latest_email_ui"):
            self.parent.open_thread_latest_email_ui(email)
        else:
            log_cb = self.parent.log if hasattr(self.parent, 'log') else None
            open_email_item(email, log_callback=log_cb)

    def render_email(self):
        if not self.emails:
            return
        
        email = self.emails[self.current_idx]
        total = len(self.emails)
        
        acc = email.get("account_name", "Email")
        folder = email.get("folder", "Inbox")
        self.lbl_source.configure(text=f"📁 {acc} • {folder}")
        self.lbl_counter.configure(text=f"[ {self.current_idx + 1} / {total} ]")

        sender = email.get("sender", "Người gửi ẩn")
        self.lbl_sender.configure(text=f"👤 {sender}")

        time_str = email.get("time", "")
        self.lbl_time.configure(text=f"🕒 {time_str}")

        subj = email.get("subject", "(Không tiêu đề)")
        self.lbl_subject.configure(text=f"✉️ {subj}")

        summary = email.get("summary", "(Không có nội dung)")
        self.txt_content.configure(state="normal")
        self.txt_content.delete("1.0", "end")
        self.txt_content.insert("1.0", summary)
        self.txt_content.configure(state="disabled")

    def copy_content(self):
        if not self.emails:
            return
        email = self.emails[self.current_idx]
        text_to_copy = f"Tiêu đề: {email.get('subject')}\nNgười gửi: {email.get('sender')}\nThời gian: {email.get('time')}\nNguồn: {email.get('account_name')} ({email.get('folder')})\n\nNội dung / Tóm tắt:\n{email.get('summary')}"
        try:
            self.clipboard_clear()
            self.clipboard_append(text_to_copy)
            self.btn_copy.configure(text="✅ Đã copy")
            self.after(1500, lambda: self.btn_copy.configure(text="📋 Copy") if self.winfo_exists() else None)
        except Exception:
            pass

    def mark_current_email_read(self):
        if not self.emails:
            return
        email = self.emails[self.current_idx]
        self.countdown = 10
        if email.get("is_thread") and hasattr(self.parent, "mark_thread_read_ui"):
            self.parent.mark_thread_read_ui(email)
        elif hasattr(self.parent, "mark_email_read"):
            self.parent.mark_email_read(email)

    def delete_current_notification(self):
        if not self.emails:
            self.close_popup()
            return
        removed = self.emails.pop(self.current_idx)
        
        # Nếu là thread: xóa toàn bộ chuỗi trong DB và chuyển tất cả các email vào Thùng rác
        if removed.get("is_thread") and removed.get("thread_key"):
            try:
                from thread_logic import get_thread_by_key
                t = get_thread_by_key(removed.get("thread_key"))
                if t and t.get("id") and hasattr(self.parent, "delete_single_thread_ui"):
                    self.parent.delete_single_thread_ui(t["id"])
            except Exception:
                pass
        else:
            # Nếu là email đơn lẻ: xóa khỏi danh sách và chuyển vào Thùng rác trên server
            if hasattr(self.parent, "delete_single_email_from_history"):
                self.parent.delete_single_email_from_history(removed)

        if hasattr(self.parent, "latest_notifications"):
            if removed in self.parent.latest_notifications:
                self.parent.latest_notifications.remove(removed)
                if hasattr(self.parent, "filter_emails_history"):
                    self.parent.filter_emails_history()
        
        if not self.emails:
            self.close_popup()
            return

        if self.current_idx >= len(self.emails):
            self.current_idx = 0
        self.countdown = 10
        self.render_email()

    def open_app_clicked(self):
        if self.on_open_app:
            self.on_open_app()
        self.close_popup()

    def toggle_pin(self):
        self.is_pinned = not self.is_pinned
        if self.is_pinned:
            self.btn_pin.configure(fg_color=COLOR_HOVER_BLUE, text="📌 (Ghim)")
            self.lbl_timer.configure(text="📌 Đã ghim")
            if hasattr(self.parent, "cancel_reopen_popup"):
                self.parent.cancel_reopen_popup()
        else:
            self.btn_pin.configure(fg_color="transparent", text="📌")
            self.countdown = 10
            self.lbl_timer.configure(text=f"⏱️ {self.countdown}s")

    def on_mouse_enter(self, event=None):
        self.is_paused = True

    def on_mouse_leave(self, event=None):
        self.is_paused = False

    def _start_timer(self):
        if self._timer_id:
            try:
                self.after_cancel(self._timer_id)
            except Exception:
                pass
        self._timer_id = self.after(1000, self._tick)

    def _tick(self):
        if not self.winfo_exists():
            return
        if not self.is_pinned:
            if not self.is_paused:
                self.countdown -= 1
                if self.countdown <= 0:
                    if self.current_idx >= len(self.emails) - 1:
                        self.hide_and_schedule_reopen(delay_seconds=300)
                        return
                    else:
                        self.current_idx += 1
                        self.countdown = 10
                        self.render_email()
                else:
                    self.lbl_timer.configure(text=f"⏱️ {self.countdown}s")
            else:
                self.lbl_timer.configure(text=f"⏱️ {self.countdown}s (Dừng)")
        else:
            self.lbl_timer.configure(text="📌 Đã ghim")

        self._timer_id = self.after(1000, self._tick)

    def _position_bottom_right(self):
        try:
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            x = screen_w - self.popup_w - 16
            y = screen_h - self.popup_h - 55
            self.geometry(f"{self.popup_w}x{self.popup_h}+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

    def hide_and_schedule_reopen(self, delay_seconds=300):
        if self._timer_id:
            try:
                self.after_cancel(self._timer_id)
            except Exception:
                pass
            self._timer_id = None
        
        try:
            self.withdraw()
        except Exception:
            pass

        if hasattr(self.parent, "schedule_reopen_popup"):
            self.parent.schedule_reopen_popup(delay_seconds)

    def close_popup(self):
        if self._timer_id:
            try:
                self.after_cancel(self._timer_id)
            except Exception:
                pass
            self._timer_id = None
        
        try:
            self.withdraw()
        except Exception:
            pass
        
        if not self.is_pinned and hasattr(self.parent, "schedule_reopen_popup"):
            self.parent.schedule_reopen_popup(300)


class EmailReminderApp(ctk.CTk):
    """Giao diện chính eMail Assistant phong cách Modern SaaS Dashboard với Menu dọc"""
    def __init__(self):
        super().__init__()
        self.title("eMail Assistant v1.4 - VNPT AI")
        self.geometry("1120x740")
        self.minsize(980, 640)
        self.configure(fg_color=COLOR_BG_LIGHT)

        # Gắn logo vào cửa sổ và taskbar
        icon_path = get_resource_path("app_icon.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        # Dữ liệu cấu hình & trạng thái
        self.config = self.load_config()
        self.is_running = False
        self.stop_event = threading.Event()
        self.notification_popup = None
        self.latest_notifications = []
        self.email_sort_order = "newest"  # "newest" (Mới -> Cũ) hoặc "oldest" (Cũ -> Mới)
        self._reopen_popup_timer = None
        self.cached_contacts = []
        self.sender_suggest_box = None
        self.load_contacts_cache_bg()

        # Thống kê hoạt động phiên hiện tại
        self.stat_scans_count = 0
        self.stat_unread_count = 0
        self.stat_ai_processed = 0

        # Khởi tạo System Tray
        self.tray_icon = None
        self.setup_tray_icon()
        self.bind("<Unmap>", self.on_unmap)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Xây dựng bố cục giao diện SaaS (Sidebar dọc + Topbar + Container trang)
        self.pages = {}
        self.nav_buttons = {}
        self.filter_scroll_frames = {}

        self.setup_ui_layout()
        self.show_page("dashboard")

        # Khởi động luồng lắng nghe phản hồi nút bấm '✓ Đã đọc' từ Telegram Bot
        self.tele_stop_event = threading.Event()
        self.tele_thread = threading.Thread(
            target=telegram_polling_worker,
            args=(
                lambda: self.config,
                lambda e: self.after(0, self.mark_email_read, e),
                lambda m: self.after(0, self.log, m),
                self.tele_stop_event
            ),
            daemon=True
        )
        self.tele_thread.start()

    def setup_ui_layout(self):
        """Khởi tạo bố cục tổng thể gồm Sidebar dọc bên trái và Vùng nội dung bên phải"""
        # =========================================================================
        # 1. SIDEBAR DỌC BÊN TRÁI (Dark Slate Theme)
        # =========================================================================
        self.sidebar_frame = ctk.CTkFrame(self, fg_color=COLOR_SIDEBAR_BG, width=220, corner_radius=0)
        self.sidebar_frame.pack(side="left", fill="y")
        self.sidebar_frame.pack_propagate(False)

        # 1.1 Logo / Header Sidebar
        logo_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        logo_frame.pack(fill="x", padx=16, pady=(20, 24))

        logo_badge = ctk.CTkFrame(logo_frame, fg_color=COLOR_PRIMARY_BLUE, corner_radius=8, height=36)
        logo_badge.pack(fill="x")
        logo_badge.pack_propagate(False)

        lbl_logo = ctk.CTkLabel(
            logo_badge,
            text="📬 eMail Assistant",
            font=("Segoe UI", 13, "bold"),
            text_color="#FFFFFF"
        )
        lbl_logo.pack(side="left", padx=12, pady=6)

        lbl_sub = ctk.CTkLabel(
            logo_frame,
            text="VNPT AI Assistant",
            font=("Segoe UI", 10, "bold"),
            text_color="#94A3B8"
        )
        lbl_sub.pack(anchor="w", padx=4, pady=(6, 0))

        # 1.2 Menu Điều Hướng Dọc (Navigation Items)
        nav_items = [
            ("dashboard", "📊  Dashboard"),
            ("emails",    "✉️  Emails"),
            ("threads",   "🧵  Threads"),
            ("rules",     "⚡  Rules"),
            ("settings",  "⚙️  Settings"),
            ("help",      "📖  Help")
        ]

        self.nav_menu_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.nav_menu_frame.pack(fill="x", padx=12, pady=(0, 20))

        for page_id, label_text in nav_items:
            btn = ctk.CTkButton(
                self.nav_menu_frame,
                text=label_text,
                anchor="w",
                font=("Segoe UI", 12, "bold"),
                height=42,
                corner_radius=8,
                fg_color="transparent",
                hover_color=COLOR_SIDEBAR_HOVER,
                text_color="#CBD5E1",
                command=lambda pid=page_id: self.show_page(pid)
            )
            btn.pack(fill="x", pady=3)
            self.nav_buttons[page_id] = btn

        # 1.3 Footer Sidebar (Trạng thái quét & Thông tin hệ thống)
        sidebar_footer = ctk.CTkFrame(self.sidebar_frame, fg_color="#1E293B", corner_radius=8)
        sidebar_footer.pack(side="bottom", fill="x", padx=12, pady=16)

        self.lbl_sidebar_status_dot = ctk.CTkLabel(
            sidebar_footer,
            text="⚪ Đã dừng",
            font=("Segoe UI", 11, "bold"),
            text_color="#94A3B8"
        )
        self.lbl_sidebar_status_dot.pack(anchor="w", padx=12, pady=(8, 2))

        lbl_sidebar_ver = ctk.CTkLabel(
            sidebar_footer,
            text="Phiên bản v1.4\n © quangvu@vnpt - 2026",
            font=("Segoe UI", 9),
            text_color="#64748B"
        )
        lbl_sidebar_ver.pack(anchor="w", padx=12, pady=(0, 8))

        # =========================================================================
        # 2. VÙNG NỘI DUNG BÊN PHẢI (Topbar + Pages Container)
        # =========================================================================
        self.right_container = ctk.CTkFrame(self, fg_color=COLOR_BG_LIGHT, corner_radius=0)
        self.right_container.pack(side="right", fill="both", expand=True)

        # 2.1 Top Navigation Bar (Trắng thanh lịch)
        self.topbar = ctk.CTkFrame(self.right_container, fg_color="#FFFFFF", height=62, corner_radius=0, border_width=1, border_color=COLOR_BORDER)
        self.topbar.pack(side="top", fill="x")
        self.topbar.pack_propagate(False)

        # Tiêu đề trang hiện tại trên Topbar
        self.lbl_topbar_title = ctk.CTkLabel(
            self.topbar,
            text="Dashboard",
            font=("Segoe UI", 15, "bold"),
            text_color=COLOR_TEXT_MAIN
        )
        self.lbl_topbar_title.pack(side="left", padx=20, pady=14)

        # Cụm Thao tác nhanh trên Topbar (Bắt đầu/Dừng, Xem thông báo, User Profile)
        topbar_actions = ctk.CTkFrame(self.topbar, fg_color="transparent")
        topbar_actions.pack(side="right", padx=16, pady=10)

        # Nút Bật/Dừng theo dõi (Dạng Outline sang trọng)
        self.btn_top_toggle = ctk.CTkButton(
            topbar_actions,
            text="▶ BẮT ĐẦU THEO DÕI",
            font=("Segoe UI", 11, "bold"),
            height=34,
            fg_color="#FFFFFF",
            border_width=1,
            border_color=COLOR_PRIMARY_BLUE,
            text_color=COLOR_PRIMARY_BLUE,
            hover_color="#F0F7FF",
            command=self.toggle_running
        )
        self.btn_top_toggle.pack(side="left", padx=(0, 8))

        # Nút Mở lại thông báo Desktop (Dạng Solid Blue chuẩn VNPT)
        self.btn_top_reopen = ctk.CTkButton(
            topbar_actions,
            text="👁️ Xem thông báo",
            font=("Segoe UI", 11, "bold"),
            height=34,
            fg_color=COLOR_PRIMARY_BLUE,
            hover_color=COLOR_HOVER_BLUE,
            text_color="#FFFFFF",
            command=self.reopen_latest_notifications
        )
        self.btn_top_reopen.pack(side="left", padx=(0, 12))

        # Badge User
        user_badge = ctk.CTkFrame(topbar_actions, fg_color="#F1F5F9", corner_radius=6)
        user_badge.pack(side="left")
        lbl_user = ctk.CTkLabel(
            user_badge,
            text="👤 VNPT User",
            font=("Segoe UI", 11, "bold"),
            text_color=COLOR_PRIMARY_BLUE
        )
        lbl_user.pack(padx=10, pady=6)

        # 2.2 Container chứa các Trang
        self.page_container = ctk.CTkFrame(self.right_container, fg_color="transparent")
        self.page_container.pack(side="top", fill="both", expand=True, padx=20, pady=16)

        # Khởi tạo các trang
        self.setup_dashboard_page()
        self.setup_emails_page()
        self.setup_threads_page()
        self.setup_rules_page()
        self.setup_settings_page()
        self.setup_help_page()

    def show_page(self, page_id):
        """Chuyển đổi hiển thị giữa các trang và cập nhật trạng thái menu dọc"""
        self.current_page = page_id
        for pid, frame in self.pages.items():
            if pid == page_id:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()

        # Cập nhật style nút Sidebar
        for pid, btn in self.nav_buttons.items():
            if pid == page_id:
                btn.configure(fg_color=COLOR_SIDEBAR_ACTIVE, text_color="#FFFFFF")
            else:
                btn.configure(fg_color="transparent", text_color="#CBD5E1")

        # Cập nhật tiêu đề Topbar
        title_map = {
            "dashboard": "Dashboard",
            "emails":    "Emails (Lịch sử quét & Tóm tắt)",
            "threads":   "Threads (Quản lý chuỗi hội thoại email)",
            "rules":     "Rules (Bộ lọc Email)",
            "settings":  "Settings (Cài đặt hệ thống)",
            "help":      "Help & Documentation (Trợ giúp)"
        }
        self.lbl_topbar_title.configure(text=title_map.get(page_id, "Dashboard"))
        if page_id == "threads" and hasattr(self, "refresh_threads_list"):
            self.refresh_threads_list()

    # =========================================================================
    # TRANG 1: 📊 DASHBOARD (TỔNG QUAN BỘ LỌC & TRẠNG THÁI HỆ THỐNG)
    # =========================================================================
    def setup_dashboard_page(self):
        page = ctk.CTkFrame(self.page_container, fg_color="transparent")
        self.pages["dashboard"] = page

        # 1. Hàng 4 Thẻ Chỉ Số (Stat Cards)
        stats_frame = ctk.CTkFrame(page, fg_color="transparent")
        stats_frame.pack(fill="x", pady=(0, 16))
        stats_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        # Card 1: Email Chưa Đọc
        self.card_stat_unread, self.lbl_stat_unread = self._create_stat_card(
            stats_frame, col=0, icon="📬", title="Email chưa đọc", val="0", unit="emails", color=COLOR_PRIMARY_BLUE
        )
        # Card 2: Lượt Quét Hôm Nay
        self.card_stat_scans, self.lbl_stat_scans = self._create_stat_card(
            stats_frame, col=1, icon="🔄", title="Lượt quét hôm nay", val="0", unit="lần", color=COLOR_ACCENT_BLUE
        )
        # Card 3: Tóm Tắt AI & Cache
        self.card_stat_ai, self.lbl_stat_ai = self._create_stat_card(
            stats_frame, col=2, icon="🤖", title="Tóm tắt AI & Cache", val="0", unit="thư", color=COLOR_GREEN_BTN
        )
        # Card 4: Chu kỳ & Trạng thái
        self.card_stat_interval, self.lbl_stat_interval = self._create_stat_card(
            stats_frame, col=3, icon="⏱️", title="Chu kỳ quét", val=f"{self.config.get('interval_mins', 15)}m", unit="Sẵn sàng", color="#8B5CF6"
        )

        # 2. Vùng Nội Dung Chính Dashboard (Chia 2 Cột: Cột Trái Tổng Quan Rules, Cột Phải Live Log)
        main_dash_grid = ctk.CTkFrame(page, fg_color="transparent")
        main_dash_grid.pack(fill="both", expand=True)
        main_dash_grid.grid_columnconfigure(0, weight=5)
        main_dash_grid.grid_columnconfigure(1, weight=5)
        main_dash_grid.grid_rowconfigure(0, weight=1)

        # --- CỘT TRÁI: Thống Kê & Danh Sách Rules Đang Áp Dụng ---
        left_card = ctk.CTkFrame(main_dash_grid, fg_color=COLOR_CARD_WHITE, corner_radius=10, border_width=1, border_color=COLOR_BORDER)
        left_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        left_header = ctk.CTkFrame(left_card, fg_color="transparent")
        left_header.pack(fill="x", padx=16, pady=(12, 8))

        ctk.CTkLabel(left_header, text="⚡ Thống Kê Đối Tượng Bộ Lọc (Rules)", font=("Segoe UI", 13, "bold"), text_color=COLOR_TEXT_MAIN).pack(side="left")

        self.dash_rules_overview_frame = ctk.CTkScrollableFrame(left_card, fg_color="transparent")
        self.dash_rules_overview_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.refresh_dashboard_rules_stats()

        # --- CỘT PHẢI: Nhật Ký Hoạt Động Realtime (Live Logs) ---
        right_card = ctk.CTkFrame(main_dash_grid, fg_color=COLOR_CARD_WHITE, corner_radius=10, border_width=1, border_color=COLOR_BORDER)
        right_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        right_header = ctk.CTkFrame(right_card, fg_color="transparent")
        right_header.pack(fill="x", padx=16, pady=(12, 8))

        ctk.CTkLabel(right_header, text="📈 Nhật Ký Hoạt Động (Live Logs)", font=("Segoe UI", 13, "bold"), text_color=COLOR_TEXT_MAIN).pack(side="left")

        btn_clear_log = ctk.CTkButton(
            right_header,
            text="🧹 Xóa log",
            width=70,
            height=26,
            fg_color="#F1F5F9",
            hover_color="#E2E8F0",
            text_color=COLOR_TEXT_MAIN,
            font=("Segoe UI", 10, "bold"),
            command=self.clear_logs
        )
        btn_clear_log.pack(side="right")

        self.log_box = ctk.CTkTextbox(
            right_card,
            fg_color="#F8FAFC",
            text_color=COLOR_TEXT_MAIN,
            border_width=1,
            border_color=COLOR_BORDER,
            font=("Consolas", 11)
        )
        self.log_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.log("Hệ thống Email Reminder đã sẵn sàng hoạt động.")

    def _create_stat_card(self, parent, col, icon, title, val, unit, color):
        """Hàm trợ giúp tạo thẻ thống kê (Stat Card) đẹp mắt"""
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD_WHITE, corner_radius=10, border_width=1, border_color=COLOR_BORDER)
        card.grid(row=0, column=col, sticky="nsew", padx=6)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=16, pady=14)

        top_row = ctk.CTkFrame(inner, fg_color="transparent")
        top_row.pack(fill="x")

        ctk.CTkLabel(top_row, text=icon, font=("Segoe UI", 16)).pack(side="left")
        ctk.CTkLabel(top_row, text=title, font=("Segoe UI", 11, "bold"), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(6, 0))

        val_row = ctk.CTkFrame(inner, fg_color="transparent")
        val_row.pack(anchor="w", pady=(8, 0))

        lbl_val = ctk.CTkLabel(val_row, text=val, font=("Segoe UI", 18, "bold"), text_color=color)
        lbl_val.pack(side="left")

        ctk.CTkLabel(val_row, text=f" {unit}", font=("Segoe UI", 11), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(4, 0), pady=(4, 0))

        return card, lbl_val

    def refresh_dashboard_rules_stats(self):
        """Cập nhật các chỉ số và vẽ bảng thống kê bộ lọc Rules trên Dashboard"""
        if not hasattr(self, 'dash_rules_overview_frame') or not self.dash_rules_overview_frame.winfo_exists():
            return

        senders = self.config.get("senders", [])
        folders = self.config.get("folders", ["Inbox"])
        keywords = self.config.get("keywords", [])
        ai_engine = self.config.get("ai_engine", "Offline")
        # Xóa và vẽ lại khung chi tiết đối tượng Rules
        for child in self.dash_rules_overview_frame.winfo_children():
            child.destroy()

        # 1. Khung Người Gửi (Senders)
        self._render_rule_stat_box(
            self.dash_rules_overview_frame,
            icon="👤",
            title=f"Người gửi cần theo dõi ({len(senders)} đối tượng):",
            items=senders,
            empty_msg="Nhận tất cả người gửi (Không lọc riêng)"
        )

        # 2. Khung Thư Mục Quét (Folders)
        self._render_rule_stat_box(
            self.dash_rules_overview_frame,
            icon="📁",
            title=f"Thư mục quét ({len(folders)} thư mục):",
            items=folders,
            empty_msg="Inbox (Mặc định)"
        )

        # 3. Khung Từ Khóa Lọc (Keywords)
        self._render_rule_stat_box(
            self.dash_rules_overview_frame,
            icon="🔑",
            title=f"Từ khóa lọc Tiêu đề & Nội dung ({len(keywords)} từ):",
            items=keywords,
            empty_msg="Không lọc từ khóa (Nhận tất cả tiêu đề)"
        )

        # 4. Khung Nguồn Quét Kích Hoạt
        src_box = ctk.CTkFrame(self.dash_rules_overview_frame, fg_color="#F8FAFC", corner_radius=8, border_width=1, border_color=COLOR_BORDER)
        src_box.pack(fill="x", pady=4, padx=2)

        src_top = ctk.CTkFrame(src_box, fg_color="transparent")
        src_top.pack(fill="x", padx=10, pady=(6, 4))
        ctk.CTkLabel(src_top, text="📡 Nguồn email đang kích hoạt:", font=("Segoe UI", 11, "bold"), text_color=COLOR_PRIMARY_BLUE).pack(side="left")

        active_srcs = []
        if self.config.get("enable_outlook", True):
            active_srcs.append("Microsoft Outlook (Local)")
        if self.config.get("enable_imap", False):
            acc_count = len(self.config.get("imap_accounts", []))
            active_srcs.append(f"Webmail / IMAP ({acc_count} tài khoản)")

        if not active_srcs:
            active_srcs.append("⚠️ Chưa bật nguồn quét nào")

        tag_container = ctk.CTkFrame(src_box, fg_color="transparent")
        tag_container.pack(fill="x", padx=10, pady=(0, 6))

        for src in active_srcs:
            badge = ctk.CTkLabel(
                tag_container,
                text=src,
                font=("Segoe UI", 10, "bold"),
                text_color=COLOR_TEXT_MAIN,
                fg_color="#E2E8F0",
                corner_radius=4,
                padx=8,
                pady=2
            )
            badge.pack(side="left", padx=(0, 6), pady=2)

        self.bind_smooth_scroll(self.dash_rules_overview_frame)

    def _render_rule_stat_box(self, parent, icon, title, items, empty_msg):
        """Vẽ khối tóm tắt 1 nhóm rules"""
        box = ctk.CTkFrame(parent, fg_color="#F8FAFC", corner_radius=8, border_width=1, border_color=COLOR_BORDER)
        box.pack(fill="x", pady=4, padx=2)

        top = ctk.CTkFrame(box, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(6, 4))
        ctk.CTkLabel(top, text=f"{icon} {title}", font=("Segoe UI", 11, "bold"), text_color=COLOR_PRIMARY_BLUE).pack(side="left")

        content_box = ctk.CTkFrame(box, fg_color="transparent")
        content_box.pack(fill="x", padx=10, pady=(0, 6))

        if not items:
            ctk.CTkLabel(content_box, text=f"• {empty_msg}", font=("Segoe UI", 10, "italic"), text_color=COLOR_TEXT_MUTED).pack(anchor="w")
        else:
            for item_text in items:
                badge = ctk.CTkLabel(
                    content_box,
                    text=item_text,
                    font=("Segoe UI", 10),
                    text_color=COLOR_TEXT_MAIN,
                    fg_color="#FFFFFF",
                    corner_radius=4,
                    padx=8,
                    pady=2
                )
                badge.pack(side="left", padx=(0, 4), pady=2)

    def _render_single_email_card(self, parent, email):
        """Vẽ thẻ email với Tiêu đề, Người gửi, Tóm tắt AI và nút Mở thư"""
        card = ctk.CTkFrame(parent, fg_color="#FFFFFF", corner_radius=8, border_width=1, border_color=COLOR_BORDER)
        card.pack(fill="x", pady=4, padx=2)

        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.pack(fill="x", padx=10, pady=(8, 2))

        acc = email.get("account_name", "Email")
        folder = email.get("folder", "Inbox")
        badge = ctk.CTkLabel(top_row, text=f"📁 {acc} • {folder}", font=("Segoe UI", 9, "bold"), text_color=COLOR_PRIMARY_BLUE, fg_color="#E0F2FE", corner_radius=4, padx=6, pady=1)
        badge.pack(side="left")

        time_str = email.get("time", "")
        ctk.CTkLabel(top_row, text=f"🕒 {time_str}", font=("Segoe UI", 9), text_color=COLOR_TEXT_MUTED).pack(side="right")

        sender = email.get("sender", "Người gửi")
        ctk.CTkLabel(card, text=f"👤 {sender}", font=("Segoe UI", 10, "bold"), text_color=COLOR_TEXT_MAIN, anchor="w").pack(fill="x", padx=10, pady=(2, 0))

        subj = email.get("subject", "(Không tiêu đề)")
        ctk.CTkLabel(card, text=f"✉️ {subj}", font=("Segoe UI", 11, "bold"), text_color=COLOR_PRIMARY_BLUE, anchor="w").pack(fill="x", padx=10, pady=(2, 4))

        summary = email.get("summary", "")
        if summary:
            txt = ctk.CTkTextbox(card, height=55, font=("Segoe UI", 10), fg_color="#F8FAFC", border_width=1, border_color=COLOR_BORDER, corner_radius=6)
            txt.pack(fill="x", padx=10, pady=(0, 6))
            txt.insert("1.0", summary)
            txt.configure(state="disabled")

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(0, 8))

        btn_open = ctk.CTkButton(
            btn_row,
            text="✉️ Mở Mail",
            width=76,
            height=26,
            fg_color="#FFFFFF",
            border_width=1,
            border_color=COLOR_PRIMARY_BLUE,
            text_color=COLOR_PRIMARY_BLUE,
            hover_color="#F0F7FF",
            font=("Segoe UI", 10, "bold"),
            command=lambda e=email: open_email_item(e, log_callback=self.log)
        )
        btn_open.pack(side="left", padx=(0, 6))

        btn_mark_read = ctk.CTkButton(
            btn_row,
            text="✓ Đã đọc",
            width=68,
            height=26,
            fg_color="#FFFFFF",
            border_width=1,
            border_color=COLOR_PRIMARY_BLUE,
            text_color=COLOR_PRIMARY_BLUE,
            hover_color="#F0F7FF",
            font=("Segoe UI", 10, "bold"),
            command=lambda e=email: self.mark_email_read(e)
        )
        btn_mark_read.pack(side="left", padx=(0, 6))

        btn_copy = ctk.CTkButton(
            btn_row,
            text="📋 Copy",
            width=62,
            height=26,
            fg_color="#FFFFFF",
            border_width=1,
            border_color="#CBD5E1",
            text_color="#475569",
            hover_color="#F1F5F9",
            font=("Segoe UI", 10, "bold"),
            command=lambda e=email: self._copy_email_text(e)
        )
        btn_copy.pack(side="left")

        btn_del = ctk.CTkButton(
            btn_row,
            text="🗑️ Xóa",
            width=60,
            height=26,
            fg_color="#FFFFFF",
            border_width=1,
            border_color="#CBD5E1",
            text_color=COLOR_RED_BTN,
            hover_color="#FEF2F2",
            font=("Segoe UI", 10, "bold"),
            command=lambda e=email: self.delete_single_email_from_history(e)
        )
        btn_del.pack(side="right")

    def delete_single_email_from_history(self, email):
        """Xóa 1 email khỏi danh sách lịch sử và chuyển trực tiếp vào Thùng rác trên Outlook/Webmail"""
        if not email:
            return

        if email in self.latest_notifications:
            self.latest_notifications.remove(email)
            self.stat_unread_count = len(self.latest_notifications)
            if hasattr(self, 'lbl_stat_unread'):
                self.lbl_stat_unread.configure(text=str(self.stat_unread_count))
            self.filter_emails_history()

        # Đồng bộ loại bỏ khỏi popup nếu popup đang mở
        if hasattr(self, 'notification_popup') and self.notification_popup and self.notification_popup.winfo_exists():
            if email in self.notification_popup.emails:
                self.notification_popup.emails.remove(email)
                if not self.notification_popup.emails:
                    self.notification_popup.close_popup()
                else:
                    self.notification_popup.render_email()

        def _bg_del():
            try:
                acc_name = email.get("account_name", "")
                entry_id = email.get("entry_id")
                if ("Outlook" in acc_name or entry_id) and entry_id:
                    delete_email_outlook(entry_id, log_callback=self.log)
                else:
                    accounts = self.config.get("imap_accounts", [])
                    matched_acc = None
                    for acc in accounts:
                        if acc.get("account_name") == acc_name or acc.get("server") == email.get("server") or acc.get("user") == email.get("user"):
                            matched_acc = acc
                            break
                    if not matched_acc and accounts:
                        matched_acc = accounts[0]
                    if matched_acc:
                        raw_folder = email.get("actual_folder") or email.get("folder", "INBOX")
                        msg_id = email.get("msg_id", "")
                        email_id = email.get("email_id")
                        delete_email_imap(matched_acc, raw_folder, msg_id, email_id, log_callback=self.log)
            except Exception as e:
                self.log(f"⚠️ Lỗi khi chuyển thư vào thùng rác: {e}")

        threading.Thread(target=_bg_del, daemon=True).start()
        self.log(f"🗑️ Đang chuyển email vào Thùng rác: '{email.get('subject', '')}'")

    def mark_email_read(self, email):
        """Đánh dấu đã đọc trên Outlook hoặc Webmail/IMAP và loại bỏ khỏi danh sách thông báo"""
        if not email:
            return

        # 1. Loại bỏ khỏi danh sách thông báo chưa đọc của app
        if email in self.latest_notifications:
            self.latest_notifications.remove(email)
            self.stat_unread_count = len(self.latest_notifications)
            if hasattr(self, 'lbl_stat_unread'):
                self.lbl_stat_unread.configure(text=str(self.stat_unread_count))
            self.filter_emails_history()

        # 2. Đồng bộ loại bỏ khỏi popup nếu popup đang mở
        if hasattr(self, 'notification_popup') and self.notification_popup and self.notification_popup.winfo_exists():
            if email in self.notification_popup.emails:
                self.notification_popup.emails.remove(email)
                if not self.notification_popup.emails:
                    self.notification_popup.close_popup()
                else:
                    self.notification_popup.current_idx = self.notification_popup.current_idx % len(self.notification_popup.emails)
                    self.notification_popup.render_email()

        # 3. Đánh dấu đã đọc trên server / Outlook trong background thread
        def _run_mark():
            def _log(m):
                try:
                    if self.winfo_exists():
                        self.after(0, self.log, m)
                except Exception:
                    pass

            subj = email.get("subject", "")
            entry_id = email.get("entry_id")
            if entry_id or "Outlook" in email.get("account_name", ""):
                ok = mark_email_as_read_outlook(entry_id, log_callback=_log)
            else:
                acc_user = email.get("user", "").lower()
                acc_srv = email.get("server", "").lower()
                matched_acc = next((a for a in self.config.get("imap_accounts", []) if a.get("user", "").lower() == acc_user or a.get("server", "").lower() == acc_srv), None)
                if not matched_acc and self.config.get("imap_accounts"):
                    matched_acc = self.config["imap_accounts"][0]
                
                raw_folder = email.get("actual_folder", "INBOX")
                msg_id = email.get("msg_id", "")
                email_id = email.get("email_id")
                ok = mark_email_as_read_imap(matched_acc, raw_folder, msg_id, email_id, log_callback=_log)

        threading.Thread(target=_run_mark, daemon=True).start()

    def _copy_email_text(self, email):
        text_to_copy = f"Tiêu đề: {email.get('subject')}\nNgười gửi: {email.get('sender')}\nThời gian: {email.get('time')}\nNguồn: {email.get('account_name')} ({email.get('folder')})\n\nNội dung / Tóm tắt:\n{email.get('summary')}"
        try:
            self.clipboard_clear()
            self.clipboard_append(text_to_copy)
            self.log(f"📋 Đã sao chép nội dung email '{email.get('subject')}' vào Clipboard.")
        except Exception:
            pass

    def log(self, msg):
        time_str = datetime.now().strftime("%H:%M:%S")
        if hasattr(self, 'log_box') and self.log_box.winfo_exists():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", f"[{time_str}] {msg}\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")

    def clear_logs(self):
        if hasattr(self, 'log_box') and self.log_box.winfo_exists():
            self.log_box.configure(state="normal")
            self.log_box.delete("1.0", "end")
            self.log_box.configure(state="disabled")

    def bind_smooth_scroll(self, scrollable_frame, step_pixels=None):
        """Kích hoạt cuộn chuột mượt mà và tốc độ cao đồng bộ chuẩn Windows cho CTkScrollableFrame và toàn bộ widget con"""
        if not hasattr(scrollable_frame, "_parent_canvas"):
            return

        canvas = scrollable_frame._parent_canvas

        def _get_scroll_step():
            if step_pixels is not None:
                return step_pixels
            try:
                lines = ctypes.c_uint()
                ctypes.windll.user32.SystemParametersInfoW(104, 0, ctypes.byref(lines), 0)
                lines_val = int(lines.value)
                if lines_val in (-1, 0xFFFFFFFF):
                    return 300
                return max(40, lines_val * 20)
            except Exception:
                return 60

        def _on_mousewheel(event):
            try:
                # Windows event.delta is typically 120 (up) or -120 (down)
                notch = event.delta / 120.0
                step = _get_scroll_step()
                steps = int(-1 * notch * step)
                canvas.yview_scroll(steps, "units")
            except Exception:
                pass
            return "break"

        def _bind_recursive(widget):
            try:
                widget.bind("<MouseWheel>", _on_mousewheel, add="+")
            except Exception:
                pass
            if hasattr(widget, "_canvas") and widget._canvas:
                try: widget._canvas.bind("<MouseWheel>", _on_mousewheel, add="+")
                except Exception: pass
            if hasattr(widget, "_textbox") and widget._textbox:
                try: widget._textbox.bind("<MouseWheel>", _on_mousewheel, add="+")
                except Exception: pass
            for child in widget.winfo_children():
                _bind_recursive(child)

        canvas.bind("<MouseWheel>", _on_mousewheel, add="+")
        if hasattr(scrollable_frame, "_parent_frame") and scrollable_frame._parent_frame:
            scrollable_frame._parent_frame.bind("<MouseWheel>", _on_mousewheel, add="+")
        _bind_recursive(scrollable_frame)

    # =========================================================================
    # TRANG 2: ✉️ EMAILS (LỊCH SỬ CHI TIẾT)
    # =========================================================================
    def setup_emails_page(self):
        page = ctk.CTkFrame(self.page_container, fg_color="transparent")
        self.pages["emails"] = page

        top_ctrl = ctk.CTkFrame(page, fg_color=COLOR_CARD_WHITE, corner_radius=10, border_width=1, border_color=COLOR_BORDER)
        top_ctrl.pack(fill="x", pady=(0, 12))

        inner = ctk.CTkFrame(top_ctrl, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(inner, text="🔍 Tìm kiếm:", font=("Segoe UI", 12, "bold"), text_color=COLOR_TEXT_MAIN).pack(side="left", padx=(0, 8))
        self.entry_email_search = ctk.CTkEntry(inner, placeholder_text="Nhập từ khóa, tên người gửi hoặc tiêu đề...", width=320, fg_color="#FFFFFF", border_color=COLOR_BORDER)
        self.entry_email_search.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.entry_email_search.bind("<KeyRelease>", lambda e: self.filter_emails_history())

        # Nút đổi chiều sắp xếp thời gian (Mới nhất / Cũ nhất)
        self.btn_email_sort = ctk.CTkButton(
            inner,
            text="⇅ Mới nhất",
            width=110,
            height=32,
            fg_color="#FFFFFF",
            border_width=1,
            border_color=COLOR_PRIMARY_BLUE,
            text_color=COLOR_PRIMARY_BLUE,
            hover_color="#F0F7FF",
            font=("Segoe UI", 11, "bold"),
            command=self.toggle_email_sort_order
        )
        self.btn_email_sort.pack(side="right", padx=(0, 8))

        btn_clear_hist = ctk.CTkButton(
            inner,
            text="🗑️ Xóa danh sách",
            width=110,
            height=32,
            fg_color="#FFFFFF",
            border_width=1,
            border_color="#CBD5E1",
            text_color="#475569",
            hover_color="#F1F5F9",
            font=("Segoe UI", 11),
            command=self.clear_emails_history
        )
        btn_clear_hist.pack(side="right")

        list_container = ctk.CTkFrame(page, fg_color=COLOR_CARD_WHITE, corner_radius=10, border_width=1, border_color=COLOR_BORDER)
        list_container.pack(fill="both", expand=True)

        self.emails_full_scroll = ctk.CTkScrollableFrame(list_container, fg_color="transparent")
        self.emails_full_scroll.pack(fill="both", expand=True, padx=12, pady=12)
        self.filter_emails_history()

    def toggle_email_sort_order(self):
        if self.email_sort_order == "newest":
            self.email_sort_order = "oldest"
            if hasattr(self, "btn_email_sort"):
                self.btn_email_sort.configure(text="⇅ Cũ nhất")
        else:
            self.email_sort_order = "newest"
            if hasattr(self, "btn_email_sort"):
                self.btn_email_sort.configure(text="⇅ Mới nhất")
        self.filter_emails_history()

    def filter_emails_history(self):
        for child in self.emails_full_scroll.winfo_children():
            child.destroy()

        kw = self.entry_email_search.get().strip().lower() if hasattr(self, 'entry_email_search') else ""
        emails = list(self.latest_notifications)

        if kw:
            emails = [e for e in emails if kw in e.get("subject", "").lower() or kw in e.get("sender", "").lower() or kw in e.get("summary", "").lower()]

        # Sắp xếp theo thời gian dựa trên trạng thái nút mũi tên 2 chiều
        is_reverse = (self.email_sort_order == "newest")
        emails = sorted(emails, key=parse_email_time_helper, reverse=is_reverse)

        if not emails:
            empty = ctk.CTkFrame(self.emails_full_scroll, fg_color="#F8FAFC", corner_radius=8)
            empty.pack(fill="x", pady=30, padx=10)
            ctk.CTkLabel(
                empty,
                text="ℹ️ Không có email nào khớp với kết quả tìm kiếm.",
                font=("Segoe UI", 12, "italic"),
                text_color=COLOR_TEXT_MUTED
            ).pack(pady=20)
            return

        for email in emails:
            self._render_single_email_card(self.emails_full_scroll, email)

        self.bind_smooth_scroll(self.emails_full_scroll)

    def clear_emails_history(self):
        self.latest_notifications = []
        self.filter_emails_history()
        self.log("Đã xóa sạch lịch sử email đã quét.")

    # =========================================================================
    # TRANG 3: 🧵 THREADS (QUẢN LÝ CHUỖI HỘI THOẠI EMAIL)
    # =========================================================================
    def setup_threads_page(self):
        page = ctk.CTkFrame(self.page_container, fg_color="transparent")
        self.pages["threads"] = page

        top_ctrl = ctk.CTkFrame(page, fg_color=COLOR_CARD_WHITE, corner_radius=10, border_width=1, border_color=COLOR_BORDER)
        top_ctrl.pack(fill="x", pady=(0, 12))

        inner = ctk.CTkFrame(top_ctrl, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(inner, text="🔍 Tìm kiếm chuỗi:", font=("Segoe UI", 12, "bold"), text_color=COLOR_TEXT_MAIN).pack(side="left", padx=(0, 8))
        self.entry_thread_search = ctk.CTkEntry(inner, placeholder_text="Nhập từ khóa tiêu đề, người gửi hoặc nội dung tóm tắt chuỗi...", width=320, fg_color="#FFFFFF", border_color=COLOR_BORDER)
        self.entry_thread_search.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.entry_thread_search.bind("<KeyRelease>", lambda e: self.refresh_threads_list())

        self.btn_thread_sort = ctk.CTkButton(
            inner,
            text="⇅ Mới nhất",
            width=105,
            height=32,
            fg_color="#FFFFFF",
            border_width=1,
            border_color=COLOR_PRIMARY_BLUE,
            text_color=COLOR_PRIMARY_BLUE,
            hover_color="#F0F7FF",
            font=("Segoe UI", 11, "bold"),
            command=self.toggle_thread_sort_order
        )
        self.btn_thread_sort.pack(side="right", padx=(0, 8))

        btn_refresh = ctk.CTkButton(
            inner,
            text="🔄 Làm mới",
            width=95,
            height=32,
            fg_color="#FFFFFF",
            border_width=1,
            border_color="#CBD5E1",
            text_color="#475569",
            hover_color="#F1F5F9",
            font=("Segoe UI", 11),
            command=self.refresh_threads_list
        )
        btn_refresh.pack(side="right")

        list_container = ctk.CTkFrame(page, fg_color=COLOR_CARD_WHITE, corner_radius=10, border_width=1, border_color=COLOR_BORDER)
        list_container.pack(fill="both", expand=True)

        self.threads_scroll_frame = ctk.CTkScrollableFrame(list_container, fg_color="transparent")
        self.threads_scroll_frame.pack(fill="both", expand=True, padx=12, pady=12)
        self.thread_sort_order = "newest"
        self.refresh_threads_list()

    def toggle_thread_sort_order(self):
        if getattr(self, "thread_sort_order", "newest") == "newest":
            self.thread_sort_order = "oldest"
            if hasattr(self, "btn_thread_sort"):
                self.btn_thread_sort.configure(text="⇅ Cũ nhất")
        else:
            self.thread_sort_order = "newest"
            if hasattr(self, "btn_thread_sort"):
                self.btn_thread_sort.configure(text="⇅ Mới nhất")
        self.refresh_threads_list()

    def refresh_threads_list(self):
        if not hasattr(self, 'threads_scroll_frame'):
            return
        from thread_logic import get_all_threads
        for child in self.threads_scroll_frame.winfo_children():
            child.destroy()

        kw = self.entry_thread_search.get().strip() if hasattr(self, 'entry_thread_search') else ""
        threads = get_all_threads(limit=200, search_kw=kw)

        if getattr(self, "thread_sort_order", "newest") == "oldest":
            threads = sorted(threads, key=lambda t: parse_email_time_helper({"time": t.get("last_updated", "")}))
        else:
            threads = sorted(threads, key=lambda t: parse_email_time_helper({"time": t.get("last_updated", "")}), reverse=True)

        if not threads:
            empty = ctk.CTkFrame(self.threads_scroll_frame, fg_color="#F8FAFC", corner_radius=8)
            empty.pack(fill="x", pady=30, padx=10)
            ctk.CTkLabel(
                empty,
                text="ℹ️ Chưa có chuỗi hội thoại nào trong cơ sở dữ liệu." if not kw else "ℹ️ Không tìm thấy chuỗi email nào khớp từ khóa.",
                font=("Segoe UI", 12, "italic"),
                text_color=COLOR_TEXT_MUTED
            ).pack(pady=20)
            return

        for t in threads:
            self._render_thread_card(self.threads_scroll_frame, t)

        self.bind_smooth_scroll(self.threads_scroll_frame)

    def _render_thread_card(self, parent, thread_item):
        card = ctk.CTkFrame(parent, fg_color="#FFFFFF", corner_radius=8, border_width=1, border_color=COLOR_BORDER)
        card.pack(fill="x", pady=4, padx=2)

        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.pack(fill="x", padx=10, pady=(8, 2))

        acc = thread_item.get("account_name") or "Email"
        folder = thread_item.get("folder") or "Inbox"
        badge_src = ctk.CTkLabel(top_row, text=f"📁 {acc} • {folder}", font=("Segoe UI", 9, "bold"), text_color=COLOR_PRIMARY_BLUE, fg_color="#E0F2FE", corner_radius=4, padx=6, pady=1)
        badge_src.pack(side="left", padx=(0, 6))

        count = thread_item.get("email_count", 1)
        badge_count = ctk.CTkLabel(top_row, text=f"💬 {count} thư trong chuỗi", font=("Segoe UI", 9, "bold"), text_color="#15803D", fg_color="#DCFCE7", corner_radius=4, padx=6, pady=1)
        badge_count.pack(side="left")

        time_str = thread_item.get("last_updated", "")
        ctk.CTkLabel(top_row, text=f"🕒 Cập nhật: {time_str}", font=("Segoe UI", 9), text_color=COLOR_TEXT_MUTED).pack(side="right")

        last_sender = thread_item.get("last_sender", "Người gửi ẩn")
        ctk.CTkLabel(card, text=f"👤 Phản hồi gần nhất: {last_sender}", font=("Segoe UI", 10, "bold"), text_color=COLOR_TEXT_MAIN, anchor="w").pack(fill="x", padx=10, pady=(2, 0))

        subj = thread_item.get("subject", "(Không tiêu đề)")
        ctk.CTkLabel(card, text=f"🧵 {subj}", font=("Segoe UI", 12, "bold"), text_color=COLOR_PRIMARY_BLUE, anchor="w").pack(fill="x", padx=10, pady=(2, 4))

        summary = thread_item.get("current_summary", "")
        if summary:
            # Tự động tính chiều cao hộp thoại theo độ dài nội dung (tối thiểu 95px, tối đa 240px)
            num_lines = len(summary.split("\n"))
            box_height = max(95, min(240, num_lines * 20 + 35))
            txt = ctk.CTkTextbox(card, height=box_height, font=("Segoe UI", 11), fg_color="#F8FAFC", border_width=1, border_color=COLOR_BORDER, corner_radius=6)
            txt.pack(fill="x", padx=10, pady=(0, 6))
            txt.insert("1.0", summary)
            txt.configure(state="disabled")

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(0, 8))

        btn_open = ctk.CTkButton(
            btn_row,
            text="✉️ Mở Mail",
            width=76,
            height=26,
            fg_color="#FFFFFF",
            border_width=1,
            border_color=COLOR_PRIMARY_BLUE,
            text_color=COLOR_PRIMARY_BLUE,
            hover_color="#F0F7FF",
            font=("Segoe UI", 10, "bold"),
            command=lambda t=thread_item: self.open_thread_latest_email_ui(t)
        )
        btn_open.pack(side="left", padx=(0, 6))

        btn_mark_thread = ctk.CTkButton(
            btn_row,
            text="✓ Đã đọc",
            width=76,
            height=26,
            fg_color="#FFFFFF",
            border_width=1,
            border_color=COLOR_PRIMARY_BLUE,
            text_color=COLOR_PRIMARY_BLUE,
            hover_color="#F0F7FF",
            font=("Segoe UI", 10, "bold"),
            command=lambda t=thread_item: self.mark_thread_read_ui(t)
        )
        btn_mark_thread.pack(side="left", padx=(0, 6))

        btn_copy = ctk.CTkButton(
            btn_row,
            text="📋 Copy tóm tắt",
            width=100,
            height=26,
            fg_color="#FFFFFF",
            border_width=1,
            border_color="#CBD5E1",
            text_color="#475569",
            hover_color="#F1F5F9",
            font=("Segoe UI", 10, "bold"),
            command=lambda t=thread_item: self.copy_thread_summary_ui(t)
        )
        btn_copy.pack(side="left", padx=(0, 6))

        btn_del = ctk.CTkButton(
            btn_row,
            text="🗑️ Xóa chuỗi",
            width=85,
            height=26,
            fg_color="#FFFFFF",
            border_width=1,
            border_color="#CBD5E1",
            text_color=COLOR_RED_BTN,
            hover_color="#FEF2F2",
            font=("Segoe UI", 10, "bold"),
            command=lambda tid=thread_item.get("id"): self.delete_single_thread_ui(tid)
        )
        btn_del.pack(side="right")

    def open_thread_latest_email_ui(self, thread_item):
        """Mở email mới nhất trong chuỗi hội thoại"""
        import json
        items = []
        if thread_item.get("email_items"):
            try:
                if isinstance(thread_item["email_items"], str):
                    items = json.loads(thread_item["email_items"])
                elif isinstance(thread_item["email_items"], list):
                    items = thread_item["email_items"]
            except Exception:
                items = []

        if not items and thread_item.get("thread_key"):
            try:
                from thread_logic import get_thread_by_key
                found = get_thread_by_key(thread_item.get("thread_key"))
                if found and found.get("email_items"):
                    items = json.loads(found["email_items"])
            except Exception:
                pass

        if items:
            latest_email = items[-1]
        else:
            latest_email = {
                "account_name": thread_item.get("account_name", "Email"),
                "folder": thread_item.get("folder", "Inbox"),
                "subject": thread_item.get("subject", ""),
                "sender": thread_item.get("last_sender", ""),
                "time": thread_item.get("last_updated", "")
            }

        open_email_item(latest_email, log_callback=self.log)

    def mark_thread_read_ui(self, thread_item):
        from thread_logic import mark_thread_as_read
        tid = thread_item.get("id")
        if not tid:
            from thread_logic import get_thread_by_key
            found = get_thread_by_key(thread_item.get("thread_key"))
            if found: tid = found.get("id")

        if tid:
            mark_thread_as_read(tid, config=self.config, log_callback=self.log)
            # Đồng bộ loại bỏ khỏi popup thông báo nếu đang mở
            if hasattr(self, 'notification_popup') and self.notification_popup and self.notification_popup.winfo_exists():
                self.notification_popup.emails = [e for e in self.notification_popup.emails if e.get("thread_key") != thread_item.get("thread_key")]
                if not self.notification_popup.emails:
                    self.notification_popup.close_popup()
                else:
                    self.notification_popup.render_email()
            self.log(f"✅ Đã xử lý đánh dấu ĐÃ ĐỌC toàn bộ chuỗi: '{thread_item.get('subject')}'")

    def copy_thread_summary_ui(self, thread_item):
        text = f"Chuỗi email: {thread_item.get('subject')}\nSố lượng thư: {thread_item.get('email_count')}\nCập nhật gần nhất: {thread_item.get('last_updated')}\nPhản hồi gần nhất: {thread_item.get('last_sender')}\n\nTóm tắt sự việc:\n{thread_item.get('current_summary')}"
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.log(f"📋 Đã copy tóm tắt chuỗi: '{thread_item.get('subject')}'")
        except Exception:
            pass

    def delete_single_thread_ui(self, thread_id):
        """Xóa chuỗi trong DB và chuyển tất cả các email trong chuỗi vào thùng rác trên server"""
        from thread_logic import delete_thread_with_emails
        def _bg():
            delete_thread_with_emails(thread_id, config=self.config, log_callback=self.log)
            self.after(0, self.refresh_threads_list)

        threading.Thread(target=_bg, daemon=True).start()
        self.refresh_threads_list()
        self.log(f"🗑️ Đang chuyển tất cả email trong chuỗi ID {thread_id} vào thùng rác...")

    # =========================================================================
    # TRANG 4: ⚡ RULES (BỘ LỌC)
    # =========================================================================
    def setup_rules_page(self):
        page = ctk.CTkFrame(self.page_container, fg_color="transparent")
        self.pages["rules"] = page

        grid_frame = ctk.CTkFrame(page, fg_color="transparent")
        grid_frame.pack(fill="both", expand=True)
        grid_frame.grid_columnconfigure((0, 1, 2), weight=1)
        grid_frame.grid_rowconfigure(0, weight=1)

        self.create_filter_column(grid_frame, "👤 Senders (Email/Tên người gửi)", "senders", 0)
        self.create_filter_column(grid_frame, "📁 Folders (Thư mục quét)", "folders", 1)
        self.create_filter_column(grid_frame, "🔑 Keywords (Từ khóa Tiêu đề/Nội dung)", "keywords", 2)

    def create_filter_column(self, parent, title, config_key, col):
        frame = ctk.CTkFrame(parent, fg_color=COLOR_CARD_WHITE, border_width=1, border_color=COLOR_BORDER, corner_radius=10)
        frame.grid(row=0, column=col, padx=6, sticky="nsew")

        ctk.CTkLabel(frame, text=title, font=("Segoe UI", 13, "bold"), text_color=COLOR_PRIMARY_BLUE).pack(pady=(12, 6))

        if config_key == "folders":
            top_bar = ctk.CTkFrame(frame, fg_color="transparent")
            top_bar.pack(fill="x", padx=12, pady=5)

            self.btn_scan_folders = ctk.CTkButton(
                top_bar,
                text="🔍 Scan thư mục",
                height=30,
                fg_color="#FFFFFF",
                border_width=1,
                border_color=COLOR_PRIMARY_BLUE,
                text_color=COLOR_PRIMARY_BLUE,
                hover_color="#F0F7FF",
                font=("Segoe UI", 11, "bold"),
                command=self.trigger_scan_folders_inline
            )
            self.btn_scan_folders.pack(fill="x", pady=(0, 6))

            self.entry_folder_search = ctk.CTkEntry(
                top_bar,
                placeholder_text="🔍 Tìm nhanh thư mục...",
                height=28,
                fg_color="#FFFFFF",
                border_color=COLOR_BORDER,
                text_color=COLOR_TEXT_MAIN,
                font=("Segoe UI", 10)
            )
            self.entry_folder_search.pack(fill="x")
            self.entry_folder_search.bind("<KeyRelease>", lambda event: self.filter_folders_tree_inline())

            scroll_frame = ctk.CTkScrollableFrame(frame, fg_color="#F8FAFC", corner_radius=8)
            scroll_frame.pack(fill="both", expand=True, padx=12, pady=6)
            self.filter_scroll_frames[config_key] = scroll_frame

            self.refresh_filter_list(config_key)

            btn_cancel = ctk.CTkButton(
                frame,
                text="🗑️ Hủy Lựa Chọn",
                height=32,
                fg_color="#FFFFFF",
                border_width=1,
                border_color="#CBD5E1",
                text_color="#475569",
                hover_color="#F1F5F9",
                font=("Segoe UI", 11),
                command=self.clear_all_folders_inline
            )
            btn_cancel.pack(fill="x", padx=12, pady=(4, 12))

        else:
            input_frame = ctk.CTkFrame(frame, fg_color="transparent")
            input_frame.pack(fill="x", padx=12, pady=5)

            entry = ctk.CTkEntry(
                input_frame, 
                placeholder_text="Nhập email/tên và bấm Thêm..." if config_key == "senders" else "Nhập từ khóa và bấm Thêm...", 
                fg_color="#FFFFFF", 
                border_color=COLOR_BORDER, 
                text_color=COLOR_TEXT_MAIN
            )
            entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

            btn = ctk.CTkButton(
                input_frame, 
                text="Thêm", 
                width=65, 
                fg_color="#FFFFFF", 
                border_width=1, 
                border_color=COLOR_PRIMARY_BLUE, 
                text_color=COLOR_PRIMARY_BLUE, 
                hover_color="#F0F7FF", 
                font=("Segoe UI", 11, "bold"),
                command=lambda: self.add_filter_item(config_key, entry)
            )
            btn.pack(side="right")
            entry.bind("<Return>", lambda event: self.add_filter_item(config_key, entry))

            if config_key == "senders":
                suggest_frame = ctk.CTkFrame(frame, fg_color="#FFFFFF", corner_radius=6, border_width=1, border_color=COLOR_PRIMARY_BLUE)
                self.sender_suggest_box = suggest_frame
                self.sender_suggest_entry = entry
                entry.bind("<KeyRelease>", lambda event: self._on_sender_input_key_release(entry))
                entry.bind("<FocusOut>", lambda event: self.after(250, self._hide_sender_suggestions))

            scroll_frame = ctk.CTkScrollableFrame(frame, fg_color="#F8FAFC", corner_radius=8)
            scroll_frame.pack(fill="both", expand=True, padx=12, pady=6)
            self.filter_scroll_frames[config_key] = scroll_frame

            self.refresh_filter_list(config_key)

            btn_rm = ctk.CTkButton(
                frame, 
                text="🗑️ Xóa sạch", 
                height=32,
                fg_color="#FFFFFF", 
                border_width=1, 
                border_color="#CBD5E1", 
                text_color="#475569", 
                hover_color="#F1F5F9", 
                font=("Segoe UI", 11),
                command=lambda: self.clear_filter_list(config_key)
            )
            btn_rm.pack(fill="x", padx=12, pady=(4, 12))

    def load_contacts_cache_bg(self):
        """Quét và gom danh sách liên hệ từ Outlook & lịch sử quét email chạy ngầm"""
        def _bg():
            contacts = []
            seen = set()
            try:
                # 1. Lấy từ Outlook
                if self.config.get("enable_outlook", True):
                    out_contacts = fetch_outlook_recent_contacts(limit=300)
                    for c in out_contacts:
                        val = c.get("filter_val", "").strip()
                        if val and val.lower() not in seen:
                            seen.add(val.lower())
                            contacts.append(c)
            except Exception:
                pass

            # 2. Lấy từ SQLite threads.db
            try:
                from thread_logic import get_all_threads
                threads = get_all_threads(limit=300)
                for t in threads:
                    s = t.get("last_sender", "").strip()
                    if s and s.lower() not in seen:
                        seen.add(s.lower())
                        contacts.append({"name": s, "email": s if "@" in s else "", "filter_val": s})
            except Exception:
                pass

            # 3. Lấy từ summary_cache.json
            try:
                cache_file = os.path.join(DATA_DIR, "summary_cache.json")
                if os.path.exists(cache_file):
                    with open(cache_file, "r", encoding="utf-8") as f:
                        c_data = json.load(f)
                    for e_val in c_data.values():
                        s = e_val.get("sender", "").strip()
                        if s and s.lower() not in seen:
                            seen.add(s.lower())
                            contacts.append({"name": s, "email": s if "@" in s else "", "filter_val": s})
            except Exception:
                pass

            self.cached_contacts = contacts

        threading.Thread(target=_bg, daemon=True).start()

    def _on_sender_input_key_release(self, entry):
        if not hasattr(self, 'sender_suggest_box') or not self.sender_suggest_box:
            return
        kw = entry.get().strip().lower()
        if len(kw) < 1:
            self._hide_sender_suggestions()
            return

        matches = []
        kw_norm = _norm(kw)
        for c in getattr(self, 'cached_contacts', []):
            name = c.get("name", "")
            email = c.get("email", "")
            val = c.get("filter_val", "")
            if (kw in name.lower()) or (kw in email.lower()) or (kw in val.lower()) or (kw_norm in _norm(name)) or (kw_norm in _norm(email)):
                matches.append(c)
            if len(matches) >= 8:
                break

        if not matches:
            self._hide_sender_suggestions()
            return

        for child in self.sender_suggest_box.winfo_children():
            child.destroy()

        for c in matches:
            name = c.get("name", "")
            email = c.get("email", "")
            display_text = f"👤 {name} ({email})" if name and email and name != email else f"👤 {c.get('filter_val')}"
            
            btn = ctk.CTkButton(
                self.sender_suggest_box,
                text=display_text,
                height=26,
                fg_color="transparent",
                hover_color="#E0F2FE",
                text_color=COLOR_TEXT_MAIN,
                font=("Segoe UI", 10),
                anchor="w",
                command=lambda ct=c: self._select_sender_suggestion(ct, entry)
            )
            btn.pack(fill="x", padx=4, pady=1)

        self.sender_suggest_box.pack(fill="x", padx=12, pady=(0, 4), before=self.filter_scroll_frames.get("senders"))

    def _select_sender_suggestion(self, contact, entry):
        val = contact.get("filter_val") or contact.get("email") or contact.get("name")
        if val:
            entry.delete(0, "end")
            entry.insert(0, val)
            self.add_filter_item("senders", entry)
        self._hide_sender_suggestions()

    def _hide_sender_suggestions(self):
        if hasattr(self, 'sender_suggest_box') and self.sender_suggest_box and self.sender_suggest_box.winfo_exists():
            self.sender_suggest_box.pack_forget()

    def trigger_scan_folders_inline(self):
        if hasattr(self, 'cb_enable_outlook'):
            self.config["enable_outlook"] = bool(self.cb_enable_outlook.get())
        if hasattr(self, 'cb_enable_imap'):
            self.config["enable_imap"] = bool(self.cb_enable_imap.get())

        if hasattr(self, 'btn_scan_folders') and self.btn_scan_folders.winfo_exists():
            self.btn_scan_folders.configure(text="⏳ Đang quét thư mục...", state="disabled")
        
        def _bg_scan():
            try:
                new_grouped = scan_all_available_folders(self.config, log_callback=None)
                if self.winfo_exists():
                    self.after(0, lambda: self._on_inline_scan_completed(new_grouped))
            except Exception:
                if self.winfo_exists():
                    self.after(0, lambda: self._on_inline_scan_completed({}))

        threading.Thread(target=_bg_scan, daemon=True).start()

    def _on_inline_scan_completed(self, new_grouped):
        if hasattr(self, 'btn_scan_folders') and self.btn_scan_folders.winfo_exists():
            self.btn_scan_folders.configure(text="🔍 Scan thư mục", state="normal")
        
        if new_grouped:
            self.config["scanned_folders_tree"] = new_grouped
            self.save_config_silent()
            total_f = sum(len(flist) for flist in new_grouped.values())
            self.log(f"📁 Đã quét xong: Tìm thấy {total_f} thư mục từ {len(new_grouped)} tài khoản.")
        else:
            self.log("⚠️ Không tìm thấy thư mục nào từ Outlook hoặc Webmail.")

        self.render_folders_tree_inline()
        self.refresh_dashboard_rules_stats()

    def render_folders_tree_inline(self):
        scroll_frame = self.filter_scroll_frames.get("folders")
        if not scroll_frame or not scroll_frame.winfo_exists():
            return

        for w in scroll_frame.winfo_children():
            w.destroy()

        grouped = self.config.get("scanned_folders_tree", {})
        if not grouped:
            lbl_empty = ctk.CTkLabel(
                scroll_frame, 
                text="(Trống)\n\nBấm nút [🔍 Scan thư mục] ở trên\nđể quét và chọn thư mục.", 
                text_color=COLOR_TEXT_MUTED, 
                font=("Segoe UI", 10, "italic"),
                justify="center"
            )
            lbl_empty.pack(pady=40)
            return

        current_norm = [_norm(f) for f in self.config.get("folders", [])]
        self.inline_folder_groups = {}

        for grp_title, f_names in grouped.items():
            group_card = ctk.CTkFrame(scroll_frame, fg_color="transparent")
            group_card.pack(fill="x", pady=3, padx=2)

            grp_header = ctk.CTkFrame(group_card, fg_color="#F1F5F9", corner_radius=6, border_width=1, border_color="#CBD5E1")
            grp_header.pack(fill="x")

            btn_toggle = ctk.CTkButton(
                grp_header,
                text="▼",
                width=24,
                height=24,
                fg_color="transparent",
                text_color=COLOR_PRIMARY_BLUE,
                hover_color="#E2E8F0",
                font=("Segoe UI", 10, "bold"),
                command=lambda g=grp_title: self.toggle_inline_folder_group(g)
            )
            btn_toggle.pack(side="left", padx=(2, 0), pady=2)

            # Checkbox cha đại diện cho toàn bộ tài khoản
            selected_count = sum(1 for fn in f_names if _norm(fn) in current_norm)
            all_selected = len(f_names) > 0 and selected_count == len(f_names)
            grp_cb_var = ctk.BooleanVar(value=all_selected)

            cb_grp = ctk.CTkCheckBox(
                grp_header,
                text=f"🏢 {grp_title} ({selected_count}/{len(f_names)})",
                variable=grp_cb_var,
                font=("Segoe UI", 10, "bold"),
                text_color=COLOR_TEXT_MAIN,
                fg_color=COLOR_PRIMARY_BLUE,
                hover_color=COLOR_HOVER_BLUE,
                command=lambda g=grp_title, cv=grp_cb_var: self.on_group_checkbox_toggled(g, cv)
            )
            cb_grp.pack(side="left", padx=4, pady=3)

            body_frame = ctk.CTkFrame(group_card, fg_color="#FFFFFF", corner_radius=6, border_width=1, border_color="#E2E8F0")
            body_frame.pack(fill="x", padx=2, pady=(2, 2))

            # Rearrange: thư mục đã chọn đưa lên đầu tiên
            def _folder_sort_key(fn):
                is_sel = 0 if _norm(fn) in current_norm else 1
                norm = _norm(fn)
                is_inbox = 0 if norm in ["inbox", "hộp thư đến", "hop thu den"] else 1
                return (is_sel, is_inbox, fn.lower())

            sorted_fnames = sorted(f_names, key=_folder_sort_key)
            grp_rows = []

            for fname in sorted_fnames:
                row = ctk.CTkFrame(body_frame, fg_color="transparent")
                row.pack(fill="x", padx=6, pady=1)

                cb_var = ctk.BooleanVar()
                if _norm(fname) in current_norm:
                    cb_var.set(True)
                else:
                    cb_var.set(False)

                norm = _norm(fname)
                is_inbox = 0 if norm in ["inbox", "hộp thư đến", "hop thu den"] else 1
                grp_rows.append({"name": fname, "var": cb_var, "frame": row, "inbox_rank": is_inbox})

                cb = ctk.CTkCheckBox(
                    row,
                    text=fname,
                    variable=cb_var,
                    font=("Segoe UI", 10),
                    text_color=COLOR_TEXT_MAIN,
                    fg_color=COLOR_PRIMARY_BLUE,
                    hover_color=COLOR_HOVER_BLUE,
                    command=lambda fn=fname, cv=cb_var, gt=grp_title: self.on_folder_checkbox_toggled(fn, cv, gt)
                )
                cb.pack(side="left", pady=3)

            self.inline_folder_groups[grp_title] = {
                "card": group_card,
                "body": body_frame,
                "btn": btn_toggle,
                "cb_grp": cb_grp,
                "grp_cb_var": grp_cb_var,
                "rows": grp_rows,
                "expanded": True
            }

        self.bind_smooth_scroll(scroll_frame)
        self.filter_folders_tree_inline()

    def filter_folders_tree_inline(self):
        """Lọc nhanh danh sách thư mục hiển thị theo từ khóa tìm kiếm"""
        if not hasattr(self, 'inline_folder_groups') or not self.inline_folder_groups:
            return
        kw = self.entry_folder_search.get().strip().lower() if hasattr(self, 'entry_folder_search') else ""

        for grp_title, data in self.inline_folder_groups.items():
            matched_count = 0
            for r in data["rows"]:
                fname_lower = r["name"].lower()
                fname_norm = _norm(r["name"])
                if not kw or (kw in fname_lower) or (kw in fname_norm):
                    r["frame"].pack(fill="x", padx=6, pady=1)
                    matched_count += 1
                else:
                    r["frame"].pack_forget()

            group_card = data.get("card")
            if group_card and group_card.winfo_exists():
                if kw and matched_count == 0:
                    group_card.pack_forget()
                else:
                    group_card.pack(fill="x", pady=3, padx=2)
                    if kw and not data["expanded"]:
                        data["body"].pack(fill="x", padx=2, pady=(2, 2))
                        data["btn"].configure(text="▼")
                        data["expanded"] = True

    def toggle_inline_folder_group(self, grp_title):
        data = self.inline_folder_groups.get(grp_title)
        if not data:
            return
        if data["expanded"]:
            data["body"].pack_forget()
            data["btn"].configure(text="▶")
            data["expanded"] = False
        else:
            data["body"].pack(fill="x", padx=2, pady=(2, 2))
            data["btn"].configure(text="▼")
            data["expanded"] = True

    def _update_group_header_ui(self, grp_title):
        data = self.inline_folder_groups.get(grp_title)
        if not data:
            return
        selected_count = sum(1 for r in data["rows"] if r["var"].get())
        total_count = len(data["rows"])
        all_checked = total_count > 0 and selected_count == total_count
        data["grp_cb_var"].set(all_checked)
        data["cb_grp"].configure(text=f"🏢 {grp_title} ({selected_count}/{total_count})")

    def _reorder_group_rows(self, grp_title):
        data = self.inline_folder_groups.get(grp_title)
        if not data or "rows" not in data:
            return
        def _row_key(r):
            is_sel = 0 if r["var"].get() else 1
            return (is_sel, r["inbox_rank"], r["name"].lower())

        sorted_rows = sorted(data["rows"], key=_row_key)
        for r in sorted_rows:
            r["frame"].pack_forget()
            r["frame"].pack(fill="x", padx=6, pady=1)

    def on_group_checkbox_toggled(self, grp_title, grp_cb_var):
        state = grp_cb_var.get()
        self.set_inline_folder_group_state(grp_title, state)

    def set_inline_folder_group_state(self, grp_title, state):
        data = self.inline_folder_groups.get(grp_title)
        if not data:
            return
        current_folders = self.config.get("folders", [])
        for r in data["rows"]:
            fname = r["name"]
            r["var"].set(state)
            if state:
                if fname not in current_folders:
                    current_folders.append(fname)
            else:
                current_norm = _norm(fname)
                current_folders = [f for f in current_folders if _norm(f) != current_norm and f != fname]
        self.config["folders"] = current_folders
        self.save_config_silent()
        self.refresh_dashboard_rules_stats()
        self._update_group_header_ui(grp_title)
        self._reorder_group_rows(grp_title)

    def on_folder_checkbox_toggled(self, fname, cb_var, grp_title=None):
        current_folders = self.config.get("folders", [])
        if cb_var.get():
            if fname not in current_folders:
                current_folders.append(fname)
        else:
            norm_name = _norm(fname)
            current_folders = [f for f in current_folders if _norm(f) != norm_name and f != fname]
        self.config["folders"] = current_folders
        self.save_config_silent()
        self.refresh_dashboard_rules_stats()

        if grp_title and grp_title in self.inline_folder_groups:
            self._update_group_header_ui(grp_title)
            self._reorder_group_rows(grp_title)

    def select_all_folders_inline(self):
        grouped = self.config.get("scanned_folders_tree", {})
        all_f = []
        for flist in grouped.values():
            all_f.extend(flist)
        self.config["folders"] = list(dict.fromkeys(all_f))
        self.save_config_silent()
        self.render_folders_tree_inline()
        self.refresh_dashboard_rules_stats()

    def clear_all_folders_inline(self):
        self.config["folders"] = []
        self.save_config_silent()
        self.render_folders_tree_inline()
        self.refresh_dashboard_rules_stats()

    def add_filter_item(self, key, entry_widget):
        val = entry_widget.get().strip()
        if not val:
            return
        if key not in self.config:
            self.config[key] = []
        if val not in self.config[key]:
            self.config[key].append(val)
            self.save_config_silent()
            self.refresh_filter_list(key)
            self.refresh_dashboard_rules_stats()
        entry_widget.delete(0, "end")

    def remove_filter_item(self, key, val):
        if key in self.config and val in self.config[key]:
            self.config[key].remove(val)
            self.save_config_silent()
            self.refresh_filter_list(key)
            self.refresh_dashboard_rules_stats()

    def clear_filter_list(self, key):
        self.config[key] = []
        self.save_config_silent()
        self.refresh_filter_list(key)
        self.refresh_dashboard_rules_stats()

    def refresh_filter_list(self, key):
        if key == "folders":
            self.render_folders_tree_inline()
            return

        scroll_frame = self.filter_scroll_frames[key]
        for widget in scroll_frame.winfo_children():
            widget.destroy()

        items = self.config.get(key, [])
        if not items:
            lbl_empty = ctk.CTkLabel(scroll_frame, text="(Trống - nhận tất cả)", text_color=COLOR_TEXT_MUTED, font=("Segoe UI", 11, "italic"))
            lbl_empty.pack(pady=20)
            return

        for item_val in items:
            row_frame = ctk.CTkFrame(scroll_frame, fg_color="#FFFFFF", border_width=1, border_color="#E2E8F0", corner_radius=6)
            row_frame.pack(fill="x", pady=2, padx=2)

            lbl = ctk.CTkLabel(row_frame, text=item_val, anchor="w", text_color=COLOR_TEXT_MAIN, font=("Segoe UI", 11))
            lbl.pack(side="left", fill="x", expand=True, padx=8, pady=4)

            btn_del = ctk.CTkButton(
                row_frame, 
                text="✕", 
                width=24, 
                height=22, 
                fg_color=COLOR_RED_BTN, 
                hover_color=COLOR_RED_HOVER, 
                command=lambda v=item_val: self.remove_filter_item(key, v)
            )
            btn_del.pack(side="right", padx=6, pady=4)

        self.bind_smooth_scroll(scroll_frame)

    # =========================================================================
    # TRANG 4: ⚙️ SETTINGS (CÀI ĐẶT HỆ THỐNG)
    # =========================================================================
    def setup_settings_page(self):
        page = ctk.CTkFrame(self.page_container, fg_color="transparent")
        self.pages["settings"] = page

        scroll = ctk.CTkScrollableFrame(page, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        # 1. NGUỒN QUÉT EMAIL
        self.sec1_frame = self._create_settings_section(scroll, "📡 1. Nguồn Quét Email")
        
        source_cb_row = ctk.CTkFrame(self.sec1_frame, fg_color="transparent")
        source_cb_row.pack(anchor="w", padx=16, pady=(0, 10))

        self.cb_enable_outlook = ctk.CTkCheckBox(
            source_cb_row,
            text="Microsoft Outlook (Local App)",
            text_color=COLOR_TEXT_MAIN,
            font=("Segoe UI", 11, "bold"),
            fg_color=COLOR_PRIMARY_BLUE,
            hover_color=COLOR_HOVER_BLUE,
            command=self.on_outlook_checkbox_toggled
        )
        self.cb_enable_outlook.pack(side="left", padx=(0, 20))
        if self.config.get("enable_outlook", True):
            self.cb_enable_outlook.select()

        self.cb_enable_imap = ctk.CTkCheckBox(
            source_cb_row,
            text="Webmail / IMAP (Server)",
            text_color=COLOR_TEXT_MAIN,
            font=("Segoe UI", 11, "bold"),
            fg_color=COLOR_PRIMARY_BLUE,
            hover_color=COLOR_HOVER_BLUE,
            command=self.on_imap_checkbox_toggled
        )
        self.cb_enable_imap.pack(side="left")
        if self.config.get("enable_imap", False):
            self.cb_enable_imap.select()

        # 2. QUẢN LÝ ĐA TÀI KHOẢN WEBMAIL
        self.imap_config_frame = self._create_settings_section(scroll, "🌐 2. Quản Lý Tài Khoản Webmail / IMAP")
        
        imap_header_row = ctk.CTkFrame(self.imap_config_frame, fg_color="transparent")
        imap_header_row.pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkLabel(
            imap_header_row,
            text="Danh sách hòm thư Webmail đang theo dõi:",
            font=("Segoe UI", 11),
            text_color=COLOR_TEXT_MUTED
        ).pack(side="left")

        btn_add_imap = ctk.CTkButton(
            imap_header_row,
            text="➕ Thêm tài khoản",
            font=("Segoe UI", 11, "bold"),
            width=130,
            height=30,
            fg_color="#FFFFFF",
            border_width=1,
            border_color=COLOR_PRIMARY_BLUE,
            text_color=COLOR_PRIMARY_BLUE,
            hover_color="#F0F7FF",
            command=self.open_add_imap_account_modal
        )
        btn_add_imap.pack(side="right")

        self.imap_accounts_list_frame = ctk.CTkFrame(self.imap_config_frame, fg_color="transparent")
        self.imap_accounts_list_frame.pack(fill="x", padx=16, pady=(0, 10))
        self.render_imap_accounts_list()

        if not self.config.get("enable_imap", False):
            self.imap_config_frame.pack_forget()

        # 3. CẤU HÌNH AI TÓM TẮT
        sec3 = self._create_settings_section(scroll, "🤖 3. Cấu Hình Trí Tuệ Nhân Tạo (AI Engine)")
        
        ai_row = ctk.CTkFrame(sec3, fg_color="transparent")
        ai_row.pack(fill="x", padx=16, pady=(0, 6))

        ctk.CTkLabel(ai_row, text="Nhà cung cấp AI:", font=("Segoe UI", 11, "bold"), text_color=COLOR_TEXT_MAIN).pack(side="left", padx=(0, 10))

        self.combo_ai = ctk.CTkComboBox(
            ai_row,
            values=["Offline (Cục bộ máy tính)", "Gemini", "Groq", "DeepSeek", "Grok", "OpenAI"],
            width=220,
            fg_color="#FFFFFF",
            border_color=COLOR_BORDER,
            text_color=COLOR_TEXT_MAIN,
            command=self.on_ai_engine_changed
        )
        self.combo_ai.pack(side="left", padx=(0, 12))
        curr_ai = self.config.get("ai_engine", "Offline")
        self.combo_ai.set(curr_ai)

        self.btn_test_ai = ctk.CTkButton(
            ai_row,
            text="🤖 Test AI",
            width=80,
            height=28,
            fg_color="#FFFFFF",
            border_width=1,
            border_color=COLOR_PRIMARY_BLUE,
            text_color=COLOR_PRIMARY_BLUE,
            hover_color="#F0F7FF",
            font=("Segoe UI", 11, "bold"),
            command=self.test_ai_connection
        )
        self.btn_test_ai.pack(side="left")

        # API Key
        self.lbl_api_key = ctk.CTkLabel(sec3, text="API Key:", font=("Segoe UI", 11, "bold"), text_color=COLOR_TEXT_MAIN)
        self.lbl_api_key.pack(anchor="w", padx=16, pady=(6, 0))

        self.entry_api_key = ctk.CTkEntry(
            sec3, 
            width=500, 
            show="*", 
            placeholder_text="Dán API Key vào đây (nếu dùng AI Đám mây)...",
            fg_color="#FFFFFF", 
            border_color=COLOR_BORDER, 
            text_color=COLOR_TEXT_MAIN
        )
        self.entry_api_key.pack(anchor="w", padx=16, pady=(2, 10))
        self.entry_api_key.insert(0, self.config.get("api_key", ""))
        self.on_ai_engine_changed(curr_ai)

        # 4. KÊNH THÔNG BÁO (TELEGRAM & DESKTOP SYSTEM TRAY)
        sec4 = self._create_settings_section(scroll, "🔔 4. Kênh Nhận Thông Báo Email Mới")

        self.cb_enable_tray_notify = ctk.CTkCheckBox(
            sec4,
            text="Hiển thị thông báo nổi trên Desktop / System Tray",
            text_color=COLOR_TEXT_MAIN,
            font=("Segoe UI", 11, "bold"),
            fg_color=COLOR_PRIMARY_BLUE,
            hover_color=COLOR_HOVER_BLUE
        )
        self.cb_enable_tray_notify.pack(anchor="w", padx=16, pady=(0, 6))
        if self.config.get("enable_tray_notify", True):
            self.cb_enable_tray_notify.select()

        self.cb_enable_telegram = ctk.CTkCheckBox(
            sec4,
            text="Gửi thông báo qua Telegram (Điện thoại)",
            text_color=COLOR_TEXT_MAIN,
            font=("Segoe UI", 11, "bold"),
            fg_color=COLOR_PRIMARY_BLUE,
            hover_color=COLOR_HOVER_BLUE,
            command=self.on_telegram_checkbox_toggled
        )
        self.cb_enable_telegram.pack(anchor="w", padx=16, pady=(0, 8))
        if self.config.get("enable_telegram", True):
            self.cb_enable_telegram.select()

        self.telegram_inputs_frame = ctk.CTkFrame(sec4, fg_color="transparent")
        self.telegram_inputs_frame.pack(fill="x", padx=16, pady=(0, 10))

        ctk.CTkLabel(self.telegram_inputs_frame, text="Telegram Bot Token:", font=("Segoe UI", 11, "bold"), text_color=COLOR_TEXT_MAIN).pack(anchor="w")
        self.entry_tele_token = ctk.CTkEntry(self.telegram_inputs_frame, width=500, fg_color="#FFFFFF", border_color=COLOR_BORDER, text_color=COLOR_TEXT_MAIN)
        self.entry_tele_token.pack(anchor="w", pady=(2, 6))
        self.entry_tele_token.insert(0, self.config.get("tele_token", ""))

        ctk.CTkLabel(self.telegram_inputs_frame, text="Telegram Chat ID:", font=("Segoe UI", 11, "bold"), text_color=COLOR_TEXT_MAIN).pack(anchor="w")
        self.entry_tele_chat = ctk.CTkEntry(self.telegram_inputs_frame, width=500, fg_color="#FFFFFF", border_color=COLOR_BORDER, text_color=COLOR_TEXT_MAIN)
        self.entry_tele_chat.pack(anchor="w", pady=(2, 8))
        self.entry_tele_chat.insert(0, self.config.get("tele_chat_id", ""))

        tele_btn_row = ctk.CTkFrame(self.telegram_inputs_frame, fg_color="transparent")
        tele_btn_row.pack(anchor="w", pady=(2, 0))

        self.btn_test_tele = ctk.CTkButton(
            tele_btn_row,
            text="🔔 Test Telegram",
            width=120,
            height=30,
            fg_color="#FFFFFF",
            border_width=1,
            border_color=COLOR_PRIMARY_BLUE,
            text_color=COLOR_PRIMARY_BLUE,
            hover_color="#F0F7FF",
            font=("Segoe UI", 11, "bold"),
            command=self.test_telegram_connection
        )
        self.btn_test_tele.pack(side="left", padx=(0, 8))

        self.btn_test_popup = ctk.CTkButton(
            tele_btn_row,
            text="📬 Test Desktop Notification",
            width=180,
            height=30,
            fg_color="#FFFFFF",
            border_width=1,
            border_color=COLOR_PRIMARY_BLUE,
            text_color=COLOR_PRIMARY_BLUE,
            hover_color="#F0F7FF",
            font=("Segoe UI", 11, "bold"),
            command=self.test_desktop_notification
        )
        self.btn_test_popup.pack(side="left")

        # 5. CHU KỲ QUÉT & NÚT LƯU
        sec5 = self._create_settings_section(scroll, "⏱️ 5. Chu Kỳ Quét & Lưu Cấu Hình")

        interval_row = ctk.CTkFrame(sec5, fg_color="transparent")
        interval_row.pack(anchor="w", padx=16, pady=(0, 12))

        ctk.CTkLabel(interval_row, text="Chu kỳ quét ngầm tự động (Phút):", font=("Segoe UI", 11, "bold"), text_color=COLOR_TEXT_MAIN).pack(side="left", padx=(0, 10))
        self.entry_interval = ctk.CTkEntry(interval_row, width=80, fg_color="#FFFFFF", border_color=COLOR_BORDER, text_color=COLOR_TEXT_MAIN)
        self.entry_interval.pack(side="left")
        self.entry_interval.insert(0, str(self.config.get("interval_mins", "15")))

        btn_save = ctk.CTkButton(
            sec5,
            text="💾 LƯU CẤU HÌNH HỆ THỐNG",
            font=("Segoe UI", 13, "bold"),
            height=40,
            fg_color=COLOR_PRIMARY_BLUE,
            hover_color=COLOR_HOVER_BLUE,
            command=self.save_config
        )
        btn_save.pack(anchor="w", padx=16, pady=(0, 16))

        self.bind_smooth_scroll(scroll)

    def _create_settings_section(self, parent, title):
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD_WHITE, corner_radius=10, border_width=1, border_color=COLOR_BORDER)
        card.pack(fill="x", pady=6)
        ctk.CTkLabel(card, text=title, font=("Segoe UI", 13, "bold"), text_color=COLOR_PRIMARY_BLUE).pack(anchor="w", padx=16, pady=(12, 8))
        return card

    def on_ai_engine_changed(self, val):
        if "Offline" in val:
            if hasattr(self, 'entry_api_key'):
                self.entry_api_key.configure(state="disabled")
        else:
            if hasattr(self, 'entry_api_key'):
                self.entry_api_key.configure(state="normal")

    def on_telegram_checkbox_toggled(self):
        if self.cb_enable_telegram.get():
            self.telegram_inputs_frame.pack(fill="x", padx=16, pady=(0, 10))
        else:
            self.telegram_inputs_frame.pack_forget()

    def on_outlook_checkbox_toggled(self):
        self.config["enable_outlook"] = bool(self.cb_enable_outlook.get())
        self.save_config_silent()
        self.refresh_dashboard_rules_stats()

    def on_imap_checkbox_toggled(self):
        is_enabled = bool(self.cb_enable_imap.get())
        self.config["enable_imap"] = is_enabled
        self.save_config_silent()
        self.refresh_dashboard_rules_stats()
        if is_enabled:
            self.imap_config_frame.pack(after=self.sec1_frame, fill="x", pady=6)
        else:
            self.imap_config_frame.pack_forget()

    def render_imap_accounts_list(self):
        for child in self.imap_accounts_list_frame.winfo_children():
            child.destroy()

        accounts = self.config.get("imap_accounts", [])
        if not accounts:
            empty_box = ctk.CTkFrame(self.imap_accounts_list_frame, fg_color="#F8FAFC", border_width=1, border_color=COLOR_BORDER, corner_radius=6)
            empty_box.pack(fill="x", pady=5)
            ctk.CTkLabel(
                empty_box, 
                text="ℹ️ Chưa có tài khoản Webmail nào. Nhấn '➕ Thêm tài khoản' để cấu hình.",
                font=("Segoe UI", 11, "italic"),
                text_color=COLOR_TEXT_MUTED
            ).pack(padx=16, pady=10)
            return

        for acc in accounts:
            card = ctk.CTkFrame(self.imap_accounts_list_frame, fg_color="#FFFFFF", border_width=1, border_color=COLOR_BORDER, corner_radius=8)
            card.pack(fill="x", pady=3)

            left_info = ctk.CTkFrame(card, fg_color="transparent")
            left_info.pack(side="left", padx=12, pady=8)

            acc_name = acc.get("name", "Webmail")
            acc_user = acc.get("user", "")
            acc_srv = acc.get("server", "")
            acc_port = acc.get("port", "993")
            ssl_badge = "🔒 SSL" if acc.get("ssl", True) else "🔓 No SSL"

            title_row = ctk.CTkFrame(left_info, fg_color="transparent")
            title_row.pack(anchor="w")
            ctk.CTkLabel(title_row, text=f"🏷️ {acc_name}", font=("Segoe UI", 12, "bold"), text_color=COLOR_PRIMARY_BLUE).pack(side="left")

            detail_text = f"📧 {acc_user}   •   🌐 {acc_srv}:{acc_port} ({ssl_badge})"
            ctk.CTkLabel(left_info, text=detail_text, font=("Segoe UI", 10), text_color=COLOR_TEXT_MUTED).pack(anchor="w", pady=(2, 0))

            action_row = ctk.CTkFrame(card, fg_color="transparent")
            action_row.pack(side="right", padx=10, pady=8)

            btn_test = ctk.CTkButton(
                action_row, 
                text="Test", 
                width=42, 
                height=26, 
                fg_color="#FFFFFF", 
                border_width=1,
                border_color=COLOR_PRIMARY_BLUE,
                text_color=COLOR_PRIMARY_BLUE,
                hover_color="#F0F7FF", 
                font=("Segoe UI", 11, "bold")
            )
            btn_test.configure(command=lambda a=acc, b=btn_test: self.test_single_account_card(a, b))
            btn_test.pack(side="left", padx=(0, 6))

            btn_edit = ctk.CTkButton(
                action_row, 
                text="Sửa", 
                width=38, 
                height=26, 
                fg_color="#FFFFFF", 
                border_width=1,
                border_color="#CBD5E1",
                text_color="#475569",
                hover_color="#F1F5F9", 
                font=("Segoe UI", 11, "bold"), 
                command=lambda aid=acc.get("id"): self.open_edit_imap_account_modal(aid)
            )
            btn_edit.pack(side="left", padx=(0, 6))

            btn_del = ctk.CTkButton(
                action_row, 
                text="✕", 
                width=26, 
                height=26, 
                fg_color=COLOR_RED_BTN, 
                hover_color=COLOR_RED_HOVER, 
                text_color="#FFFFFF",
                corner_radius=4,
                font=("Segoe UI", 12, "bold"), 
                command=lambda aid=acc.get("id"), aname=acc_name: self.delete_imap_account(aid, aname)
            )
            btn_del.pack(side="left")

    def open_add_imap_account_modal(self):
        def on_save(new_acc, is_edit):
            if "imap_accounts" not in self.config:
                self.config["imap_accounts"] = []
            self.config["imap_accounts"].append(new_acc)
            self.save_config_silent()
            self.render_imap_accounts_list()
            self.log(f"Đã thêm tài khoản Webmail '{new_acc.get('name')}'.")
        IMAPAccountModal(self, on_save_callback=on_save)

    def open_edit_imap_account_modal(self, account_id):
        acc = next((a for a in self.config.get("imap_accounts", []) if a.get("id") == account_id), None)
        if not acc: return
        def on_save(updated_acc, is_edit):
            for i, a in enumerate(self.config.get("imap_accounts", [])):
                if a.get("id") == account_id:
                    self.config["imap_accounts"][i] = updated_acc
                    break
            self.save_config_silent()
            self.render_imap_accounts_list()
            self.log(f"Đã cập nhật tài khoản Webmail '{updated_acc.get('name')}'.")
        IMAPAccountModal(self, account_data=acc, on_save_callback=on_save)

    def delete_imap_account(self, account_id, account_name):
        if messagebox.askyesno("Xác nhận xóa", f"Bạn có chắc muốn xóa tài khoản Webmail '{account_name}' không?", parent=self):
            self.config["imap_accounts"] = [a for a in self.config.get("imap_accounts", []) if a.get("id") != account_id]
            self.save_config_silent()
            self.render_imap_accounts_list()
            self.log(f"Đã xóa tài khoản Webmail '{account_name}'.")

    def test_single_account_card(self, acc, btn_widget):
        srv = acc.get("server", "").strip()
        port = acc.get("port", "993").strip()
        user = acc.get("user", "").strip()
        pwd = decrypt_password(acc.get("password", ""))
        ssl_val = acc.get("ssl", True)

        btn_widget.configure(text="⏳", state="disabled")
        self.log(f"Đang kiểm tra kết nối Webmail '{acc.get('name')}' ({srv})...")

        def _test():
            try:
                ok, msg = test_imap_connection_logic(srv, port, user, pwd, ssl_val)
                if ok:
                    self.after(0, self.log, f"✅ Kết nối thành công '{acc.get('name')}': {msg}")
                    self.after(0, lambda: messagebox.showinfo("Kết Quả Webmail", f"✅ Kết nối thành công tới '{acc.get('name')}' ({srv})!\n{msg}"))
                else:
                    self.after(0, self.log, f"❌ Lỗi kết nối tài khoản '{acc.get('name')}': {msg}")
                    self.after(0, lambda: messagebox.showerror("Lỗi Kết Nối", f"❌ Kết nối thất bại tới '{acc.get('name')}':\n{msg}"))
            except Exception as e:
                self.after(0, self.log, f"❌ Lỗi kết nối tài khoản '{acc.get('name')}': {e}")
                self.after(0, lambda: messagebox.showerror("Lỗi Kết Nối", f"❌ Không thể kết nối tới Webmail:\n{e}"))
            finally:
                self.after(0, lambda: btn_widget.configure(text="Test", state="normal"))

        threading.Thread(target=_test, daemon=True).start()

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
                msg = "🔔 <b>Test thành công!</b> Ứng dụng eMail Smart Assistant v1.3 đã kết nối được với Telegram của bạn."
                msg_plain = "🔔 Test thành công! Ứng dụng eMail Smart Assistant v1.3 đã kết nối được với Telegram của bạn."
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

        self.btn_test_ai.configure(text="⏳ Test...", state="disabled")
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
                
                if res and res.startswith("[Lỗi"):
                    self.after(0, self.log, f"❌ Test AI thất bại: {res}")
                    self.after(0, lambda: messagebox.showerror(f"Lỗi API [{ai_engine}]", f"❌ Kiểm tra kết nối AI thất bại:\n\n{res}\n\n💡 Gợi ý: Hãy kiểm tra bạn đã chọn đúng hãng AI tương ứng với loại API Key chưa."))
                else:
                    self.after(0, self.log, f"✅ Kết quả test tóm tắt [{ai_engine}]:\n{res}")
                    self.after(0, lambda: messagebox.showinfo(f"Kết Quả Test [{ai_engine}]", f"✅ Kết nối AI thành công!\n\n📄 Nội dung tóm tắt mẫu:\n{res}"))
            except Exception as e:
                self.after(0, self.log, f"❌ Lỗi kiểm tra AI: {e}")
                self.after(0, lambda: messagebox.showerror(f"Lỗi Kết Nối [{ai_engine}]", f"❌ Không thể kết nối hoặc lỗi xử lý:\n{e}"))
            finally:
                self.after(0, lambda: self.btn_test_ai.configure(text="🤖 Test AI", state="normal"))

        threading.Thread(target=_test, daemon=True).start()

    def test_desktop_notification(self):
        sample_emails = [
            {
                "account_name": "VNPT Webmail",
                "folder": "Hộp thư đến",
                "subject": "[GẤP] Báo cáo tiến độ triển khai dự án tuần 34",
                "sender": "Nguyễn Văn A <nguyenvana@vnpt.vn>",
                "time": datetime.now().strftime("%H:%M %d/%m/%Y"),
                "summary": "📌 Tóm tắt AI:\n- Người gửi yêu cầu hoàn thành báo cáo tiến độ tuần 34 trước 17h00 hôm nay.\n- Các đơn vị chưa gửi phụ lục cần bổ sung gấp trong chiều nay.\n- Người liên hệ: Nguyễn Văn A (0912345678)."
            },
            {
                "account_name": "Outlook",
                "folder": "Inbox",
                "subject": "Thư mời họp rà soát hợp đồng đối tác",
                "sender": "Trần Thị B <tranb@gmail.com>",
                "time": (datetime.now() - timedelta(minutes=15)).strftime("%H:%M %d/%m/%Y"),
                "summary": "📌 Tóm tắt AI:\n- Cuộc họp rà soát hợp đồng diễn ra vào lúc 09h00 sáng mai tại phòng họp số 2.\n- Thành phần: Ban Giám đốc và phụ trách kinh doanh các đơn vị."
            },
            {
                "account_name": "Outlook",
                "folder": "Khách hàng VIP",
                "subject": "Xác nhận lịch tiếp nhận dịch vụ viễn thông",
                "sender": "Lê Hoàng C <lehoangc@vnpt.vn>",
                "time": (datetime.now() - timedelta(minutes=45)).strftime("%H:%M %d/%m/%Y"),
                "summary": "📌 Tóm tắt AI:\n- Khách hàng đã đồng ý nghiệm thu giai đoạn 1 và đề nghị lịch triển khai giai đoạn 2 vào thứ Hai tuần tới."
            }
        ]
        self.latest_notifications = sample_emails
        self.show_desktop_notification(sample_emails)
        self.filter_emails_history()
        self.log("🔔 Đã hiển thị thẻ thông báo Desktop thử nghiệm với 3 email mẫu (tự động chuyển mỗi 10s).")

    # =========================================================================
    # TRANG 5: 📖 HELP (HƯỚNG DẪN CHI TIẾT)
    # =========================================================================
    def setup_help_page(self):
        page = ctk.CTkFrame(self.page_container, fg_color="transparent")
        self.pages["help"] = page

        scroll = ctk.CTkScrollableFrame(page, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        # Card 1: Offline AI Model
        c1 = self._create_settings_section(scroll, "🤖 1. Cài Đặt Mô Hình Offline AI (Chạy 100% Cục Bộ Trên Máy Tính)")
        txt1 = """Ứng dụng hỗ trợ tóm tắt email hoàn toàn ngoại tuyến (Offline) bằng mô hình Qwen 2.5 Instruct mà không cần Internet hay API Key.

Các bước cài đặt:
1. Tải file mô hình AI định dạng GGUF:
   👉 Link tải: https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/blob/main/qwen2.5-3b-instruct-q4_k_m.gguf
2. Sau khi tải về file 'qwen2.5-3b-instruct-q4_k_m.gguf', hãy chép file vào thư mục \\models\\ cùng cấp với ứng dụng.
3. Trong tab Settings (Cài đặt), chọn AI Engine là 'Offline (Cục bộ máy tính)' và nhấn 'Test AI'."""
        self._create_help_textbox(c1, txt1)

        # Card 2: Telegram Bot
        c2 = self._create_settings_section(scroll, "📱 2. Hướng Dẫn Tạo Bot Telegram & Lấy Chat ID")
        txt2 = """Các bước cấu hình nhận thông báo email qua Telegram:

BƯỚC 1: LẤY BOT TOKEN
1. Mở ứng dụng Telegram, tìm kiếm @BotFather (có tích xanh).
2. Bấm nút Start (hoặc gõ lệnh /start), sau đó gửi lệnh /newbot.
3. Đặt tên hiển thị cho bot (Ví dụ: Nhắc Mail VNPT).
4. Đặt username cho bot (kết thúc bằng chữ 'bot', ví dụ: my_mail_alert_bot).
5. BotFather sẽ trả về mã HTTP API Token (dạng: 7123456789:AAFn9_...).
👉 Copy mã này dán vào ô 'Telegram Bot Token' trong mục Settings.

BƯỚC 2: LẤY CHAT ID (BẮT BUỘC)
1. Bấm vào link bot bạn vừa tạo (t.me/ten_bot_vua_dat) và nhấn nút START.
2. Tìm bot @userinfobot hoặc @getmyid_bot trên Telegram và nhấn Start.
3. Bot sẽ trả về mục 'Id' của bạn (dạng số nguyên, ví dụ: 123456789).
👉 Copy dãy số này dán vào ô 'Telegram Chat ID' trong mục Settings.
(Nếu dùng nhóm: Thêm bot vào nhóm và dùng bot @getidsbot để lấy Group Chat ID có dấu trừ)."""
        self._create_help_textbox(c2, txt2)

        # Card 3: Cloud AI Key
        c3 = self._create_settings_section(scroll, "🔑 3. Hướng Dẫn Lấy API Key AI Đám Mây (Gemini, Groq, DeepSeek)")
        txt3 = """Nếu muốn sử dụng AI tốc độ cao và dịch nghĩa thông minh từ các nhà cung cấp đám mây:
- Google Gemini: Lấy API Key miễn phí tại https://aistudio.google.com/
- Groq (Miễn phí siêu tốc): Lấy API Key tại https://console.groq.com/
- DeepSeek: Lấy API Key tại https://platform.deepseek.com/
- OpenAI: Lấy API Key tại https://platform.openai.com/

Sau khi có key, hãy chọn đúng hãng AI tương ứng và dán key vào ô API Key."""
        self._create_help_textbox(c3, txt3)

        # Card 4: Desktop Notification
        c4 = self._create_settings_section(scroll, "📬 4. Hướng Dẫn Tính Năng Thông Báo Desktop & Khay Hệ Thống")
        txt4 = """- Tự động trình chiếu: Cứ mỗi 10 giây thông báo sẽ tự lật sang email kế tiếp.
- Tự động ẩn: Sau khi duyệt hết 1 vòng tất cả các email mới, thông báo sẽ tự động ẩn xuống khay hệ thống.
- Tự động mở lại: Sau 5 phút, thông báo sẽ tự động bung lại để nhắc nhở.
- Nút Ghim (📌): Bấm nút ghim ở thanh tiêu đề để cố định thông báo không tự chuyển hoặc tự ẩn.
- Nút Mở Mail (✉️): Mở trực tiếp email gốc trong Microsoft Outlook hoặc Webmail.
- Chuột phải icon khay hệ thống: Chọn '📬 Xem thông báo email mới' để mở lại bất cứ lúc nào."""
        self._create_help_textbox(c4, txt4)
        self.bind_smooth_scroll(scroll)

    def _create_help_textbox(self, parent, content):
        tb = ctk.CTkTextbox(parent, height=135, font=("Segoe UI", 11), fg_color="#F8FAFC", border_width=1, border_color=COLOR_BORDER, corner_radius=8)
        tb.pack(fill="x", padx=16, pady=(0, 12))
        tb.insert("1.0", content)
        tb.configure(state="disabled")

    # =========================================================================
    # LOGIC CHẠY NGẦM, CẤU HÌNH & SYSTEM TRAY
    # =========================================================================
    def load_config(self):
        default = {
            "tele_token": "", "tele_chat_id": "", "api_key": "",
            "ai_engine": "Offline", "interval_mins": "15",
            "senders": [], "folders": ["Inbox"], "cc_emails": [],
            "keywords": [],
            "enable_outlook": True,
            "enable_imap": False,
            "imap_accounts": [],
            "enable_telegram": True,
            "enable_tray_notify": True
        }
        loaded = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                default.update(loaded)

        if "enable_outlook" not in loaded and "enable_imap" not in loaded:
            old_source = loaded.get("email_source", "Outlook (Local)")
            if old_source == "Webmail / IMAP (Server)":
                default["enable_outlook"] = False
                default["enable_imap"] = True

        if default.get("imap_password") and is_encrypted(default.get("imap_password")):
            default["imap_password"] = decrypt_password(default["imap_password"])

        return default

    def save_config(self):
        self.config["ai_engine"] = self.combo_ai.get()
        self.config["api_key"] = self.entry_api_key.get().strip()
        self.config["tele_token"] = self.entry_tele_token.get().strip()
        self.config["tele_chat_id"] = self.entry_tele_chat.get().strip()
        self.config["interval_mins"] = self.entry_interval.get().strip() or "15"
        self.config["enable_outlook"] = bool(self.cb_enable_outlook.get())
        self.config["enable_imap"] = bool(self.cb_enable_imap.get())
        self.config["enable_telegram"] = bool(self.cb_enable_telegram.get())
        self.config["enable_tray_notify"] = bool(self.cb_enable_tray_notify.get())
        
        save_payload = copy.deepcopy(self.config)
        for acc in save_payload.get("imap_accounts", []):
            if "password" in acc and acc["password"]:
                acc["password"] = encrypt_password(acc["password"])

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(save_payload, f, ensure_ascii=False, indent=4)

        if hasattr(self, 'lbl_stat_interval'):
            status_text = "Đang chạy" if self.is_running else "Đã dừng"
            self.lbl_stat_interval.configure(text=f"{self.config.get('interval_mins')}m")

        self.log("✅ Đã lưu cấu hình thành công.")
        messagebox.showinfo("Lưu Cấu Hình", "✅ Đã lưu cấu hình thành công!", parent=self)

    def toggle_running(self):
        if not self.is_running:
            self.save_config_silent()
            if not self.config.get("enable_outlook", True) and not self.config.get("enable_imap", False):
                messagebox.showwarning("Chưa chọn nguồn quét", "⚠️ Vui lòng tick chọn ít nhất một nguồn quét email (Outlook hoặc Webmail / IMAP) trong mục Settings!", parent=self)
                return

            self.is_running = True
            self.stop_event.clear()
            self.btn_top_toggle.configure(
                text="⬛ DỪNG THEO DÕI",
                fg_color="#FFFFFF",
                border_width=1,
                border_color=COLOR_RED_BTN,
                text_color=COLOR_RED_BTN,
                hover_color="#FEF2F2"
            )
            self.lbl_sidebar_status_dot.configure(text="🟢 Đang theo dõi", text_color="#10B981")
            self.lbl_stat_interval.configure(text=f"{self.config.get('interval_mins')}m")
            self.log(f"Đã BẬT tiến trình quét ngầm (Chu kỳ: {self.config.get('interval_mins')} phút).")
            threading.Thread(target=self.worker_thread, daemon=True).start()
        else:
            self.is_running = False
            self.stop_event.set()
            self.btn_top_toggle.configure(
                text="▶ BẮT ĐẦU THEO DÕI",
                fg_color="#FFFFFF",
                border_width=1,
                border_color=COLOR_PRIMARY_BLUE,
                text_color=COLOR_PRIMARY_BLUE,
                hover_color="#F0F7FF"
            )
            self.lbl_sidebar_status_dot.configure(text="⚪ Đã dừng", text_color="#94A3B8")
            self.log("Đã DỪNG tiến trình quét.")

    def save_config_silent(self):
        if hasattr(self, 'combo_ai'):
            self.config["ai_engine"] = self.combo_ai.get()
            self.config["api_key"] = self.entry_api_key.get().strip()
            self.config["tele_token"] = self.entry_tele_token.get().strip()
            self.config["tele_chat_id"] = self.entry_tele_chat.get().strip()
            self.config["interval_mins"] = self.entry_interval.get().strip() or "15"
            self.config["enable_outlook"] = bool(self.cb_enable_outlook.get())
            self.config["enable_imap"] = bool(self.cb_enable_imap.get())
            self.config["enable_telegram"] = bool(self.cb_enable_telegram.get())
            self.config["enable_tray_notify"] = bool(self.cb_enable_tray_notify.get())
            save_payload = copy.deepcopy(self.config)
            for acc in save_payload.get("imap_accounts", []):
                if "password" in acc and acc["password"]:
                    acc["password"] = encrypt_password(acc["password"])
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(save_payload, f, ensure_ascii=False, indent=4)

    def worker_thread(self):
        try:
            interval_sec = int(self.config.get("interval_mins", 15)) * 60
        except Exception:
            interval_sec = 900

        while not self.stop_event.is_set():
            self.stat_scans_count += 1
            self.after(0, lambda: self.lbl_stat_scans.configure(text=str(self.stat_scans_count)))

            active_srcs = []
            if self.config.get("enable_outlook", True):
                active_srcs.append("Outlook")
            if self.config.get("enable_imap", False):
                active_srcs.append("Webmail/IMAP")

            src_str = " + ".join(active_srcs) if active_srcs else "Chưa chọn nguồn"
            self.after(0, self.log, f"Đang quét hòm thư... ({src_str} | AI: {self.config.get('ai_engine')})")

            if not self.config.get("folders", []):
                self.after(0, self.log, "ℹ️ Cột Folders trong Rules chưa chọn thư mục nào -> Tạm dừng quét cho tới khi bạn tick chọn thư mục.")
            else:
                if self.config.get("enable_outlook", True) and not self.stop_event.is_set():
                    try:
                        scan_emails(
                            self.config, 
                            lambda msg: self.after(0, self.log, msg),
                            on_emails_found_callback=self.on_new_emails_found
                        )
                    except Exception as out_err:
                        self.after(0, self.log, f"❌ Lỗi quét Outlook: {out_err}")

                if self.config.get("enable_imap", False) and not self.stop_event.is_set():
                    try:
                        scan_emails_imap(
                            self.config, 
                            lambda msg: self.after(0, self.log, msg),
                            on_emails_found_callback=self.on_new_emails_found
                        )
                    except Exception as imap_err:
                        self.after(0, self.log, f"❌ Lỗi quét Webmail/IMAP: {imap_err}")

            for _ in range(interval_sec):
                if self.stop_event.is_set(): break
                time.sleep(1)

    def on_new_emails_found(self, standalone_emails, thread_notifications=None):
        if not standalone_emails and not thread_notifications:
            return
        
        # Hỗ trợ cả tương thích ngược (1 tham số list) và 2 tham số (standalone + threads)
        if thread_notifications is None and isinstance(standalone_emails, list):
            emails = list(standalone_emails)
            thread_notifs = []
        else:
            emails = list(standalone_emails) if standalone_emails else []
            thread_notifs = list(thread_notifications) if thread_notifications else []

        if emails:
            self.latest_notifications = emails
            self.stat_unread_count = len(emails)
            self.stat_ai_processed += len(emails)
            
            if hasattr(self, 'lbl_stat_unread'):
                self.after(0, lambda: self.lbl_stat_unread.configure(text=str(self.stat_unread_count)))
            if hasattr(self, 'lbl_stat_ai'):
                self.after(0, lambda: self.lbl_stat_ai.configure(text=str(self.stat_ai_processed)))

            self.after(0, self.filter_emails_history)

        # Tự động cập nhật trang Threads khi có diễn biến chuỗi mới
        if thread_notifs:
            self.stat_ai_processed += len(thread_notifs)
            if hasattr(self, 'lbl_stat_ai'):
                self.after(0, lambda: self.lbl_stat_ai.configure(text=str(self.stat_ai_processed)))
        self.after(0, lambda: self.refresh_threads_list() if hasattr(self, 'refresh_threads_list') else None)

        # Danh sách popup Desktop: Email đơn lẻ + Bản tóm tắt cuốn chiếu duy nhất của Thread
        all_notify_items = list(emails) + list(thread_notifs)
        if self.config.get("enable_tray_notify", True) and all_notify_items:
            self.after(0, lambda: self.show_desktop_notification(all_notify_items))

    def show_desktop_notification(self, emails):
        try:
            if self.notification_popup and self.notification_popup.winfo_exists():
                self.notification_popup.update_emails(emails)
            else:
                self.notification_popup = NotificationPopup(self, emails, on_open_app=self.show_window)
            self.notification_popup.deiconify()
            self.notification_popup.lift()
            self.notification_popup.attributes("-topmost", True)
            self.log(f"🔔 Đã kích hoạt thẻ thông báo Desktop ({len(emails)} email).")
        except Exception as e:
            self.log(f"⚠️ Lỗi khởi chạy thông báo Desktop: {e}")

    def reopen_latest_notifications(self, icon=None, item=None):
        def _open():
            if self.latest_notifications:
                self.show_desktop_notification(self.latest_notifications)
            else:
                sample_emails = [{
                    "account_name": "Email Reminder",
                    "folder": "Trạng thái",
                    "subject": "Chưa có thông báo email mới",
                    "sender": "Hệ thống",
                    "time": datetime.now().strftime("%H:%M %d/%m/%Y"),
                    "summary": "Chưa có email mới nào khớp bộ lọc trong các lần quét gần nhất.\n\nKhi có thư mới xuất hiện, thông báo nổi sẽ tự động hiển thị tại góc màn hình."
                }]
                self.show_desktop_notification(sample_emails)
        self.after(0, _open)

    def schedule_reopen_popup(self, delay_seconds=300):
        self.cancel_reopen_popup()
        self._reopen_popup_timer = self.after(delay_seconds * 1000, self._auto_reopen_popup)

    def cancel_reopen_popup(self):
        if self._reopen_popup_timer:
            try:
                self.after_cancel(self._reopen_popup_timer)
            except Exception:
                pass
            self._reopen_popup_timer = None

    def _auto_reopen_popup(self):
        self._reopen_popup_timer = None
        if self.latest_notifications and self.config.get("enable_tray_notify", True):
            if self.notification_popup and self.notification_popup.winfo_exists() and self.notification_popup.is_pinned:
                return
            self.log("🔔 Tự động hiển thị lại thông báo email (chu kỳ 5 phút)...")
            self.show_desktop_notification(self.latest_notifications)

    def setup_tray_icon(self):
        try:
            icon_img_path = get_resource_path("app_icon.png")
            if not os.path.exists(icon_img_path):
                icon_img_path = get_resource_path("app_icon.ico")
            
            image = Image.open(icon_img_path)
            menu = pystray.Menu(
                item("📬 Xem thông báo email mới", self.reopen_latest_notifications),
                item("⚙️ Mở giao diện", self.show_window, default=True),
                item("⏯️ Bật/Dừng theo dõi", self.toggle_running_from_tray),
                pystray.Menu.SEPARATOR,
                item("❌ Thoát ứng dụng", self.quit_app)
            )
            self.tray_icon = pystray.Icon("eMailAssistant", image, "eMail Assistant v1.4", menu)
            self.tray_icon.run_detached()
        except Exception as e:
            print(f"Lỗi khởi tạo Tray Icon: {e}")

    def on_unmap(self, event):
        if event.widget == self and self.state() == "iconic":
            self.withdraw()
            if self.tray_icon:
                try:
                    self.tray_icon.notify("Ứng dụng đang chạy ngầm dưới khay hệ thống.", "eMail Assistant v1.4")
                except Exception:
                    pass

    def show_window(self, icon=None, item=None):
        self.after(0, self._restore_window)

    def _restore_window(self):
        self.deiconify()
        self.state("normal")
        self.lift()
        self.attributes("-topmost", True)
        self.after(100, lambda: self.attributes("-topmost", False))
        self.focus_force()

    def toggle_running_from_tray(self, icon=None, item=None):
        self.after(0, self.toggle_running)

    def on_closing(self):
        self.quit_app()

    def quit_app(self, icon=None, item=None):
        self.is_running = False
        self.stop_event.set()
        if hasattr(self, 'tele_stop_event'):
            self.tele_stop_event.set()
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
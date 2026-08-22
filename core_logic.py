try:
    import win32com.client
    import win32timezone
    import pythoncom
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
import json
import os
import requests
import html
import sys
import unicodedata
import re
from datetime import datetime, timedelta
from offline_ai import summarize_offline
from ai_engines import summarize_with_ai

if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(APP_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
CACHE_FILE = os.path.join(DATA_DIR, "summary_cache.json")

def _norm(text):
    """Chuẩn hóa chuỗi tiếng Việt về Unicode NFC và chữ thường để so khớp chính xác 100%"""
    if not text:
        return ""
    return unicodedata.normalize('NFC', str(text)).lower().strip()

CACHE_TTL_DAYS = 7   # Email >7 ngày không bao giờ nằm trong cửa sổ quét 48h → cache vô dụng

def load_cache():
    """Tải bộ nhớ đệm tóm tắt từ file JSON, tự động xóa entry cũ hơn 7 ngày"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                cutoff = datetime.now() - timedelta(days=CACHE_TTL_DAYS)
                cleaned = {}
                for k, v in data.items():
                    try:
                        cached_at_str = v.get("cached_at", "")
                        if cached_at_str:
                            cached_dt = datetime.strptime(cached_at_str, "%Y-%m-%d %H:%M:%S")
                            if cached_dt >= cutoff:
                                cleaned[k] = v
                        else:
                            cleaned[k] = v  # Giữ entry cũ không có timestamp để an toàn
                    except Exception:
                        cleaned[k] = v
                return cleaned
        except Exception:
            return {}
    return {}

def save_cache(cache_dict):
    """Lưu bộ nhớ đệm tóm tắt vào file JSON"""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_dict, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Lỗi khi lưu cache: {e}")


def add_folder_and_all_subfolders(folder, target_dict):
    """Thêm thư mục và toàn bộ thư mục con (subfolders) vào danh sách quét"""
    try:
        if folder.EntryID not in target_dict:
            target_dict[folder.EntryID] = folder
        for sub in folder.Folders:
            add_folder_and_all_subfolders(sub, target_dict)
    except Exception:
        pass

def get_all_folders_recursive(folder, folder_dict):
    """Đệ quy quét toàn bộ cây thư mục Outlook (tự động bỏ qua các thư mục lưu trữ Archive)"""
    try:
        norm_name = _norm(folder.Name)
        # Bỏ qua nếu là thư mục lưu trữ Archive
        if any(arc in norm_name for arc in ["archive", "archives", "archieve", "lưu trữ", "luu tru"]):
            return
        folder_dict[norm_name] = folder
        for subfolder in folder.Folders:
            get_all_folders_recursive(subfolder, folder_dict)
    except Exception:
        pass

_sender_email_cache = {}

def get_real_email(msg):
    """Lấy địa chỉ email thực sự của người gửi (xử lý cả Exchange User với bộ nhớ đệm nhanh)"""
    try:
        sender_email = msg.SenderEmailAddress or ""
        if "@" in sender_email and not sender_email.startswith("/"):
            return sender_email
        
        sender_name = msg.SenderName or ""
        if sender_name and sender_name in _sender_email_cache:
            return _sender_email_cache[sender_name]

        sender = getattr(msg, "Sender", None)
        if sender:
            ex_user = sender.GetExchangeUser()
            if ex_user and ex_user.PrimarySmtpAddress:
                _sender_email_cache[sender_name] = ex_user.PrimarySmtpAddress
                return ex_user.PrimarySmtpAddress
            ex_dl = sender.GetExchangeDistributionList()
            if ex_dl and ex_dl.PrimarySmtpAddress:
                _sender_email_cache[sender_name] = ex_dl.PrimarySmtpAddress
                return ex_dl.PrimarySmtpAddress
    except Exception:
        pass
    
    return msg.SenderName or "Unknown"

# Bộ nhớ tạm lưu trữ đối tượng Email tương ứng với short_id trên Telegram
PENDING_TELEGRAM_EMAILS = {}

def send_single_telegram_msg(token, chat_id, html_text, plain_text, log_callback, reply_markup=None):
    """Gửi một tin nhắn đơn lẻ về Telegram (hỗ trợ Inline Keyboard, có fallback plain text)"""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": html_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        res = requests.post(url, json=payload, timeout=12)
        if res.status_code == 200:
            return True
        
        # Nếu HTML lỗi, thử gửi dạng plain text
        err_detail = "Không rõ"
        try:
            err_detail = res.json().get("description", res.text)
        except Exception:
            pass
            
        log_callback(f"⚠️ Telegram từ chối HTML (Mã {res.status_code}: {err_detail}). Đang thử gửi dạng Text...")
        
        payload["text"] = plain_text
        payload.pop("parse_mode", None)
        res_plain = requests.post(url, json=payload, timeout=12)
        
        if res_plain.status_code == 200:
            return True
        else:
            try:
                plain_err = res_plain.json().get("description", res_plain.text)
            except Exception:
                plain_err = res_plain.text
            log_callback(f"❌ Telegram từ chối gửi tin (Mã {res_plain.status_code}: {plain_err})")
            return False
    except Exception as e:
        log_callback(f"❌ Lỗi kết nối tới máy chủ Telegram: {e}")
        return False

# Alias cho hàm gửi tin nhắn telegram đơn lẻ
send_telegram = send_single_telegram_msg

def send_telegram_report(token, chat_id, found_emails, log_callback):
    """Gửi từng email kèm nút bấm '✓ Đánh dấu đã đọc' về Telegram"""
    if not token or not chat_id:
        log_callback("⚠️ Chưa cấu hình Telegram Bot Token hoặc Chat ID.")
        return False

    total = len(found_emails)
    if total == 0:
        return True

    all_success = True
    for i, m in enumerate(found_emails):
        s_subj = html.escape(m.get('subject', ''))
        s_fold = html.escape(m.get('folder', ''))
        s_send = html.escape(m.get('sender', ''))
        s_time = html.escape(m.get('time', ''))
        s_summ = html.escape(m.get('summary', ''))

        acc_name = m.get('account_name', '')
        acc_str_html = f" | 🏢 <i>{html.escape(acc_name)}</i>" if acc_name else ""
        acc_str_plain = f" | 🏢 {acc_name}" if acc_name else ""

        header_h = f"📬 <b>THÔNG BÁO EMAIL MỚI ({i+1}/{total})</b>\n\n"
        header_p = f"📬 THÔNG BÁO EMAIL MỚI ({i+1}/{total})\n\n"

        item_html = (
            header_h +
            f"📌 <b>Tiêu đề:</b> <b>{s_subj}</b>\n"
            f"👤 <b>Người gửi:</b> {s_send}\n"
            f"⏰ <b>Thời gian:</b> {s_time} | 📁 {s_fold}{acc_str_html}\n\n"
            f"💡 <b>Tóm tắt nội dung:</b>\n{s_summ}"
        )
        item_plain = (
            header_p +
            f"📌 Tiêu đề: {m.get('subject', '')}\n"
            f"👤 Người gửi: {m.get('sender', '')}\n"
            f"⏰ Thời gian: {m.get('time', '')} | 📁 {m.get('folder', '')}{acc_str_plain}\n\n"
            f"💡 Tóm tắt nội dung:\n{m.get('summary', '')}"
        )

        import uuid
        short_id = uuid.uuid4().hex[:10]
        PENDING_TELEGRAM_EMAILS[short_id] = m

        reply_markup = {
            "inline_keyboard": [
                [{"text": "✓ Đánh dấu đã đọc", "callback_data": f"read:{short_id}"}]
            ]
        }

        ok = send_single_telegram_msg(token, chat_id, item_html, item_plain, log_callback, reply_markup=reply_markup)
        if not ok:
            all_success = False

    return all_success


def telegram_polling_worker(config_getter, mark_read_callback, log_callback, stop_event):
    """Luồng chạy ngầm lắng nghe và phản hồi khi người dùng bấm '✓ Đánh dấu đã đọc' trên Telegram"""
    offset = 0
    import time
    while not stop_event.is_set():
        config = config_getter()
        if not config.get("enable_telegram", True):
            time.sleep(2)
            continue

        token = config.get("tele_token", "").strip()
        if not token:
            time.sleep(2)
            continue

        url = f"https://api.telegram.org/bot{token}/getUpdates"
        try:
            params = {"offset": offset, "timeout": 12, "allowed_updates": ["callback_query"]}
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    if "callback_query" in update:
                        cb = update["callback_query"]
                        cb_id = cb["id"]
                        cb_data = cb.get("data", "")
                        msg = cb.get("message", {})
                        chat_id = msg.get("chat", {}).get("id")
                        msg_id = msg.get("message_id")

                        if cb_data.startswith("read:"):
                            short_id = cb_data.split("read:", 1)[1]
                            email_obj = PENDING_TELEGRAM_EMAILS.get(short_id)
                            now_time = datetime.now().strftime("%H:%M")
                            
                            # 1. Phản hồi popup toast nhỏ trên màn hình điện thoại Telegram
                            try:
                                requests.post(
                                    f"https://api.telegram.org/bot{token}/answerCallbackQuery",
                                    json={"callback_query_id": cb_id, "text": f"✅ Đã đánh dấu đã đọc lúc {now_time}!"},
                                    timeout=8
                                )
                            except Exception:
                                pass

                            # 2. Đổi nút bấm thành [✅ Đã đọc lúc HH:MM]
                            if chat_id and msg_id:
                                try:
                                    requests.post(
                                        f"https://api.telegram.org/bot{token}/editMessageReplyMarkup",
                                        json={
                                            "chat_id": chat_id,
                                            "message_id": msg_id,
                                            "reply_markup": {
                                                "inline_keyboard": [
                                                    [{"text": f"✅ Đã đọc lúc {now_time}", "callback_data": "none"}]
                                                ]
                                            }
                                        },
                                        timeout=8
                                    )
                                except Exception:
                                    pass

                            # 3. Kích hoạt đánh dấu đã đọc trên hệ thống Outlook / Webmail
                            if email_obj and mark_read_callback:
                                mark_read_callback(email_obj)
                                if log_callback:
                                    log_callback(f"📱 [Telegram] Người dùng đã bấm ĐÃ ĐỌC email '{email_obj.get('subject')[:30]}...'")
        except Exception:
            pass
        
        time.sleep(1)


def scan_emails(config, log_callback, on_emails_found_callback=None):
    if not HAS_WIN32:
        log_callback("❌ Lỗi: Chức năng quét Outlook chỉ hoạt động trên hệ điều hành Windows.")
        return []
    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        all_folders = {}
        try:
            get_all_folders_recursive(outlook.GetDefaultFolder(6).Parent, all_folders)
        except Exception:
            pass

        for acc in outlook.Folders:
            try:
                acc_norm = _norm(acc.Name)
                if not any(arc in acc_norm for arc in ["archive", "archives", "archieve", "lưu trữ", "luu tru"]):
                    get_all_folders_recursive(acc, all_folders)
            except Exception:
                pass

        log_callback(f"🗂 Outlook thấy {len(all_folders)} thư mục. Danh sách: {', '.join(sorted(all_folders.keys())[:20])}")

        ignored_folder_names = {
            "deleted items", "thùng rác", "thung rac", "đã xóa", "da xoa", "trash", "bin",
            "junk email", "thư rác", "thu rac", "spam",
            "drafts", "thư nháp", "thu nhap", "bản thảo", "ban thao",
            "outbox", "hộp thư đi", "hop thu di",
            "sent items", "thư đã gửi", "thu da gui", "sent",
            "calendar", "lịch", "lich",
            "contacts", "danh bạ", "danh ba",
            "journal", "nhật ký", "nhat ky",
            "notes", "ghi chú", "ghi chu",
            "tasks", "nhiệm vụ", "nhiem vu",
            "archive", "archives", "archieve", "lưu trữ", "luu tru", "archive folders", "online archive",
            "conversation action settings", "rss feeds", "quick step settings",
            "sync issues", "conflicts", "local failures", "server failures"
        }

        folders_to_scan = {}
        explicit_folder_ids = set()
        
        target_folders = [_norm(f) for f in config.get("folders", []) if f.strip()]
        if not target_folders:
            for fn_norm, f_obj in all_folders.items():
                if fn_norm not in ignored_folder_names and not any(ign in fn_norm for ign in ["deleted", "trash", "junk", "draft", "sent", "calendar", "contacts", "archive", "archieve", "lưu trữ", "luu tru"]):
                    try:
                        if getattr(f_obj, "DefaultItemType", 0) == 0:
                            f_dict = {}
                            add_folder_and_all_subfolders(f_obj, f_dict)
                            folders_to_scan.update(f_dict)
                    except Exception:
                        pass
            if not folders_to_scan:
                try:
                    inbox_f = outlook.GetDefaultFolder(6)
                    if inbox_f:
                        f_dict = {}
                        add_folder_and_all_subfolders(inbox_f, f_dict)
                        folders_to_scan.update(f_dict)
                except Exception:
                    pass
            log_callback(f"ℹ️ [Outlook] Cột Folders đang để trống -> Tự động quét toàn bộ {len(folders_to_scan)} thư mục mail để lọc Senders & Keywords.")
        else:
            for tf in target_folders:
                if tf in all_folders:
                    f_dict = {}
                    add_folder_and_all_subfolders(all_folders[tf], f_dict)
                    folders_to_scan.update(f_dict)
                    explicit_folder_ids.update(f_dict.keys())
                else:
                    log_callback(f"⚠️ Không tìm thấy thư mục '{tf}' trong Outlook (có thể tên sai hoặc chưa tạo)")

        target_senders = []
        for s in config.get("senders", []):
            if not s or not s.strip():
                continue
            match = re.search(r'<([^>]+)>', s)
            if match:
                email_p = match.group(1).strip()
                name_p = s[:match.start()].strip()
                if email_p: target_senders.append(_norm(email_p))
                if name_p: target_senders.append(_norm(name_p))
            else:
                target_senders.append(_norm(s))

        target_cc = [_norm(c) for c in config.get("cc_emails", []) if c.strip()]
        target_keywords = [_norm(k) for k in config.get("keywords", []) if k.strip()]
        
        has_any_filter = bool(target_folders or target_senders or target_cc or target_keywords)
        
        log_callback(f"📁 Bộ lọc thư mục: {', '.join(target_folders)}")
        log_callback(f"👤 Bộ lọc senders: {target_senders if target_senders else '(Không lọc)'}")
        if target_keywords:
            log_callback(f"🔑 Bộ lọc từ khóa ({len(target_keywords)} từ): {', '.join(target_keywords)}")

        folder_names = [f.Name for f in folders_to_scan.values()]
        log_callback(f"📂 Đang kiểm tra {len(folders_to_scan)} thư mục: {', '.join(folder_names)}")

        cache = load_cache()
        time_limit = datetime.now() - timedelta(days=2)
        
        found_emails = []
        new_ai_calls = 0
        total_unread_scanned = 0

        seen_entry_ids = set()

        for f_id, folder in folders_to_scan.items():
            try:
                all_items = folder.Items
                time_str = time_limit.strftime("%m/%d/%Y %H:%M %p")
                filter_str = f"[UnRead] = True AND [ReceivedTime] > '{time_str}'"
                try:
                    messages = all_items.Restrict(filter_str)
                    log_callback(f"📬 '{folder.Name}': tìm thấy {messages.Count} email chưa đọc trong 48h")
                except Exception:
                    messages = all_items
                    log_callback(f"⚠️ '{folder.Name}': Restrict thất bại, quét toàn bộ thư mục")
            except Exception as e:
                log_callback(f"⚠️ Không thể đọc thư mục '{folder.Name}': {e}")
                continue

            is_in_target_folder = f_id in explicit_folder_ids

            for msg in messages:
                try:
                    recv_time = getattr(msg, "ReceivedTime", None)
                    if recv_time is None: continue
                    if hasattr(recv_time, "replace"): recv_time = recv_time.replace(tzinfo=None)
                    if recv_time < time_limit: continue
                    if not getattr(msg, "UnRead", False): continue

                    total_unread_scanned += 1
                    entry_id = getattr(msg, "EntryID", None)
                    if not entry_id: continue
                    
                    # Tránh trùng lặp nếu email nằm trong nhiều thư mục/search folder
                    if entry_id in seen_entry_ids:
                        continue
                    seen_entry_ids.add(entry_id)

                    subject_raw = getattr(msg, "Subject", "") or "(Không tiêu đề)"
                    sender_name_raw = getattr(msg, "SenderName", "") or ""
                    real_email_raw = get_real_email(msg) or ""
                    body_raw = (getattr(msg, "Body", "") or "").strip()

                    # Định dạng hiển thị Người gửi: Tên + Email
                    if sender_name_raw and real_email_raw and sender_name_raw.lower() != real_email_raw.lower():
                        sender_display = f"{sender_name_raw} <{real_email_raw}>"
                    elif real_email_raw:
                        sender_display = real_email_raw
                    elif sender_name_raw:
                        sender_display = sender_name_raw
                    else:
                        sender_display = "Người gửi ẩn"

                    sender_email_norm = _norm(real_email_raw)
                    sender_name_norm = _norm(sender_name_raw)
                    cc_norm = _norm(getattr(msg, "CC", "") + " " + getattr(msg, "To", ""))
                    subject_norm = _norm(subject_raw)
                    body_norm = _norm(body_raw)

                    matched_sender = any(
                        (s and s in sender_email_norm) or 
                        (s and s in sender_name_norm) or 
                        (sender_email_norm and sender_email_norm in s) or 
                        (sender_name_norm and sender_name_norm in s)
                        for s in target_senders if s
                    ) if target_senders else False
                    matched_cc = any(c in cc_norm for c in target_cc) if target_cc else False
                    matched_keyword = any(k in subject_norm or k in body_norm for k in target_keywords) if target_keywords else False

                    # 3 RULE HOÀN TOÀN ĐỘC LẬP:
                    # - Rule 1 (Folders): Email nằm trong thư mục chỉ định -> LẤY
                    # - Rule 2 (Senders): Email từ người gửi chỉ định -> LẤY
                    # - Rule 3 (Keywords): Email chứa từ khóa chỉ định -> LẤY
                    if not has_any_filter:
                        should_read = True
                    else:
                        should_read = (is_in_target_folder or matched_sender or matched_keyword or matched_cc)

                    if should_read:
                        subject = subject_raw
                        body = body_raw
                        log_callback(f"🎯 Khớp email: '{subject[:40]}' từ {sender_display}")
                        
                        # --- CƠ CHẾ SMART CACHE ---
                        if entry_id in cache and cache[entry_id].get("summary") and not cache[entry_id]["summary"].startswith("[Lỗi"):
                            summary = cache[entry_id]["summary"]
                        else:
                            new_ai_calls += 1
                            ai_engine = config.get("ai_engine", "Offline")
                            log_callback(f"🤖 Đang tóm tắt AI [{ai_engine}] cho: '{subject[:35]}...'")
                            try:
                                if "Offline" in ai_engine:
                                    summary = summarize_offline(body, subject, sender_display)
                                else:
                                    summary = summarize_with_ai(ai_engine, config.get("api_key", ""), subject, sender_display, body, log_callback=log_callback)
                                    if not summary: raise ValueError("AI trả về kết quả rỗng")
                            except Exception as ai_err:
                                log_callback(f"⚠️ AI [{ai_engine}] lỗi, dùng tóm tắt cục bộ: {ai_err}")
                                summary = summarize_offline(body, subject, sender_display)
                            
                            if not summary.startswith("[Lỗi"):
                                cache[entry_id] = {
                                    "summary": summary,
                                    "subject": subject,
                                    "sender": sender_display,
                                    "cached_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                }

                        found_emails.append({
                            "account_name": "Outlook",
                            "folder": folder.Name,
                            "subject": subject,
                            "sender": sender_display,
                            "time": recv_time.strftime("%H:%M %d/%m/%Y"),
                            "summary": summary,
                            "body": body,
                            "entry_id": entry_id
                        })
                except Exception as msg_err:
                    log_callback(f"⚠️ Lỗi xử lý item: {type(msg_err).__name__}: {msg_err}")
                    continue

        if found_emails:
            # Luôn lưu cache ngay sau khi tóm tắt xong, KHÔNG phụ thuộc vào Telegram
            if new_ai_calls > 0:
                save_cache(cache)

            # Phân loại Thread & Standalone
            from thread_logic import process_scanned_emails_for_threads
            standalone_emails, thread_notifications = process_scanned_emails_for_threads(
                found_emails, config, log_callback=log_callback
            )
            notify_items = standalone_emails + thread_notifications

            # 1. Gửi Telegram nếu được bật
            if config.get("enable_telegram", True):
                tele_token = config.get("tele_token")
                tele_chat_id = config.get("tele_chat_id")
                if tele_token and tele_chat_id and notify_items:
                    success = send_telegram_report(
                        tele_token, 
                        tele_chat_id, 
                        notify_items, 
                        log_callback
                    )
                    if success:
                        log_callback(f"✅ Đã gửi Telegram {len(notify_items)} thông báo ({len(standalone_emails)} email đơn lẻ, {len(thread_notifications)} chuỗi hội thoại).")
                elif not tele_token or not tele_chat_id:
                    log_callback("⚠️ Kênh Telegram đang bật nhưng chưa cấu hình Token / Chat ID.")
            
            # 2. Callback thông báo giao diện / Desktop System Tray
            if on_emails_found_callback:
                try:
                    on_emails_found_callback(standalone_emails, thread_notifications)
                except Exception:
                    try:
                        on_emails_found_callback(found_emails)
                    except Exception as cb_err:
                        log_callback(f"⚠️ Lỗi hiển thị thông báo Desktop: {cb_err}")

            return found_emails
        else:
            if total_unread_scanned > 0:
                log_callback(f"ℹ️ Quét xong: Đã quét {total_unread_scanned} email chưa đọc trong 48h nhưng không có email nào khớp bộ lọc (Senders: {target_senders or '(Tất cả)'}, Keywords: {target_keywords or '(Tất cả)'}).")
            else:
                log_callback("ℹ️ Quét xong: Không có email nào chưa đọc trong 48h qua.")
            return []
            
    except Exception as e:
        log_callback(f"❌ Lỗi hệ thống khi quét mail: {e}")
    finally:
        pythoncom.CoUninitialize()


def mark_email_as_read_outlook(entry_id, log_callback=None):
    """Đánh dấu đã đọc email trong Microsoft Outlook bằng EntryID"""
    if not entry_id:
        return False
    try:
        import win32com.client
        import pythoncom
        pythoncom.CoInitialize()
        outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        item = outlook.GetItemFromID(entry_id)
        if item:
            item.UnRead = False
            item.Save()
            if log_callback:
                log_callback(f"📨 [Outlook] Đã đánh dấu ĐÃ ĐỌC thành công: '{item.Subject}'")
            return True
    except Exception as e:
        if log_callback:
            log_callback(f"⚠️ [Outlook] Không thể đánh dấu đã đọc: {e}")
        return False
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
    return False


def delete_email_outlook(entry_id, log_callback=None):
    """Xóa email trong Microsoft Outlook bằng cách chuyển vào Deleted Items / Thùng rác"""
    if not entry_id:
        return False
    try:
        import win32com.client
        import pythoncom
        pythoncom.CoInitialize()
        outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        item = outlook.GetItemFromID(entry_id)
        if item:
            subj = getattr(item, "Subject", "Email")
            item.Delete()  # Trong Outlook MAPI, item.Delete() chuyển email vào thư mục Deleted Items
            if log_callback:
                log_callback(f"🗑️ [Outlook] Đã chuyển email vào Thùng rác: '{subj}'")
            return True
    except Exception as e:
        if log_callback:
            log_callback(f"⚠️ [Outlook] Không thể xóa email: {e}")
        return False
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
    return False


def fetch_outlook_recent_contacts(limit=300, log_callback=None):
    """Lấy danh sách người gửi và danh bạ gần đây từ Microsoft Outlook để gợi ý tìm kiếm"""
    contacts = []
    seen = set()
    try:
        import win32com.client
        import pythoncom
        pythoncom.CoInitialize()
        outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")

        # 1. Quét từ Hòm thư đến Inbox gần nhất
        try:
            inbox = outlook.GetDefaultFolder(6)  # olFolderInbox
            items = inbox.Items
            items.Sort("[ReceivedTime]", True)
            for it in list(items)[:limit]:
                try:
                    s_name = (getattr(it, 'SenderName', '') or '').strip()
                    s_email = (getattr(it, 'SenderEmailAddress', '') or '').strip()
                    if s_email.startswith("/O=") or s_email.startswith("/o="):
                        try:
                            sender_obj = getattr(it, 'Sender', None)
                            if sender_obj:
                                ex_user = sender_obj.GetExchangeUser()
                                if ex_user and ex_user.PrimarySmtpAddress:
                                    s_email = ex_user.PrimarySmtpAddress.strip()
                        except Exception:
                            pass

                    email_clean = s_email if not (s_email.startswith("/O=") or s_email.startswith("/o=")) else ""
                    if email_clean or s_name:
                        key = (email_clean.lower() if email_clean else s_name.lower())
                        if key and key not in seen:
                            seen.add(key)
                            contacts.append({
                                "name": s_name,
                                "email": email_clean,
                                "filter_val": email_clean if email_clean else s_name
                            })
                except Exception:
                    continue
        except Exception:
            pass

        # 2. Quét từ Danh bạ Contacts
        try:
            cf = outlook.GetDefaultFolder(10)  # olFolderContacts
            c_items = cf.Items
            for item in list(c_items)[:limit]:
                try:
                    name = (getattr(item, 'FullName', '') or getattr(item, 'Subject', '') or '').strip()
                    email = (getattr(item, 'Email1Address', '') or getattr(item, 'Email2Address', '') or '').strip()
                    if email or name:
                        key = (email.lower() if email else name.lower())
                        if key and key not in seen:
                            seen.add(key)
                            contacts.append({
                                "name": name,
                                "email": email,
                                "filter_val": email if email else name
                            })
                except Exception:
                    continue
        except Exception:
            pass

    except Exception as e:
        if log_callback:
            log_callback(f"⚠️ Lỗi lấy danh bạ Outlook: {e}")
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass

    return contacts


def scan_all_available_folders(config, log_callback=None):
    """Quét và trả về danh sách thư mục được nhóm theo từng tài khoản email"""
    grouped_folders = {}  # group_title -> [folder_names]

    def _sort_folders(names_list):
        def _k(n):
            norm = _norm(n)
            if norm in ["inbox", "hộp thư đến", "hop thu den"]:
                return (0, n.lower())
            return (1, n.lower())
        return sorted(list(dict.fromkeys(names_list)), key=_k)

    # 1. Quét Microsoft Outlook
    if config.get("enable_outlook", True) and HAS_WIN32:
        try:
            pythoncom.CoInitialize()
            outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
            
            for acc in outlook.Folders:
                acc_name = acc.Name
                acc_norm = _norm(acc_name)
                # Bỏ qua tài khoản / kho lưu trữ Archives
                if any(arc in acc_norm for arc in ["archive", "archives", "archieve", "lưu trữ", "luu tru"]):
                    continue
                store_folders = {}
                try:
                    get_all_folders_recursive(acc, store_folders)
                except Exception:
                    pass
                if store_folders:
                    folder_names = [f.Name for f in store_folders.values()]
                    group_title = f"Microsoft Outlook ({acc_name})"
                    grouped_folders[group_title] = _sort_folders(folder_names)

            if not grouped_folders:
                all_folders = {}
                try:
                    get_all_folders_recursive(outlook.GetDefaultFolder(6).Parent, all_folders)
                    if all_folders:
                        grouped_folders["Microsoft Outlook"] = _sort_folders([f.Name for f in all_folders.values()])
                except Exception:
                    pass
        except Exception as e:
            if log_callback:
                log_callback(f"⚠️ Không thể quét thư mục Outlook: {e}")
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    # 2. Quét Webmail / IMAP
    if config.get("enable_imap", False):
        import imaplib
        from imap_logic import get_imap_folders, decode_utf7_imap
        from security import decrypt_password

        accounts = config.get("imap_accounts", [])
        for acc in accounts:
            acc_name = acc.get("name", "Webmail")
            user = acc.get("user", "").strip()
            group_title = f"{acc_name} ({user})" if user else acc_name
            try:
                server = acc.get("server", "").strip()
                port = int(acc.get("port", 993))
                pwd = decrypt_password(acc.get("password", ""))
                use_ssl = acc.get("ssl", True)
                if server and user and pwd:
                    if use_ssl:
                        mail = imaplib.IMAP4_SSL(server, port, timeout=10)
                    else:
                        mail = imaplib.IMAP4(server, port, timeout=10)
                    mail.login(user, pwd)
                    raw_folders = get_imap_folders(mail, lambda m: None)
                    clean_names = []
                    for rf in raw_folders:
                        clean_name = decode_utf7_imap(rf.strip('"'))
                        if clean_name:
                            clean_names.append(clean_name)
                    mail.logout()
                    if clean_names:
                        grouped_folders[group_title] = _sort_folders(clean_names)
            except Exception as e:
                if log_callback:
                    log_callback(f"⚠️ [{acc_name}] Không thể quét thư mục IMAP: {e}")

    return grouped_folders
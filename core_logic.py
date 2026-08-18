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

def load_cache():
    """Tải bộ nhớ đệm tóm tắt từ file JSON"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
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
    """Đệ quy quét toàn bộ cây thư mục Outlook"""
    try:
        folder_dict[_norm(folder.Name)] = folder
        for subfolder in folder.Folders:
            get_all_folders_recursive(subfolder, folder_dict)
    except Exception:
        pass

def get_real_email(msg):
    """Lấy địa chỉ email thực sự của người gửi (xử lý cả Exchange User)"""
    try:
        sender_email = msg.SenderEmailAddress or ""
        if "@" in sender_email and not sender_email.startswith("/"):
            return sender_email
        
        sender = getattr(msg, "Sender", None)
        if sender:
            ex_user = sender.GetExchangeUser()
            if ex_user and ex_user.PrimarySmtpAddress:
                return ex_user.PrimarySmtpAddress
            ex_dl = sender.GetExchangeDistributionList()
            if ex_dl and ex_dl.PrimarySmtpAddress:
                return ex_dl.PrimarySmtpAddress
    except Exception:
        pass
    
    return msg.SenderName or "Unknown"

def send_single_telegram_msg(token, chat_id, html_text, plain_text, log_callback):
    """Gửi một tin nhắn đơn lẻ về Telegram (có fallback plain text và log lỗi chi tiết)"""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": html_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
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
    """Tự động chia nhỏ bản tin và gửi về Telegram không lo bị giới hạn ký tự"""
    if not token or not chat_id:
        log_callback("⚠️ Chưa cấu hình Telegram Bot Token hoặc Chat ID.")
        return False

    total = len(found_emails)
    if total == 0:
        return True

    # Tạo các khối tin nhắn nhỏ (mỗi khối tối đa 3 email hoặc < 3000 ký tự)
    chunks = []
    current_html = ""
    current_plain = ""
    chunk_count = 0

    for i, m in enumerate(found_emails):
        s_subj = html.escape(m['subject'])
        s_fold = html.escape(m['folder'])
        s_send = html.escape(m['sender'])
        s_time = html.escape(m['time'])
        s_summ = html.escape(m['summary'])

        item_html = (
            f"<b>{i+1}. 📌 Tiêu đề:</b> <b>{s_subj}</b>\n"
            f"👤 <b>Người gửi:</b> {s_send}\n"
            f"⏰ <b>Thời gian:</b> {s_time} | 📁 {s_fold}\n"
            f"💡 <b>Tóm tắt:</b> {s_summ}\n\n"
            f"────────────────────\n\n"
        )
        item_plain = (
            f"{i+1}. 📌 Tiêu đề: {m['subject']}\n"
            f"👤 Người gửi: {m['sender']}\n"
            f"⏰ Thời gian: {m['time']} | 📁 {m['folder']}\n"
            f"💡 Tóm tắt: {m['summary']}\n\n"
            f"────────────────────\n\n"
        )

        # Nếu thêm email này vào làm tin nhắn dài hơn 3000 ký tự -> ngắt sang tin nhắn mới
        if len(current_html) + len(item_html) > 3000 and current_html != "":
            chunks.append((current_html, current_plain))
            current_html = item_html
            current_plain = item_plain
        else:
            current_html += item_html
            current_plain += item_plain

    if current_html:
        chunks.append((current_html, current_plain))

    # Gửi lần lượt từng khối tin nhắn
    all_success = True
    for idx, (h_text, p_text) in enumerate(chunks):
        header_h = f"📬 <b>THÔNG BÁO: CÓ {total} EMAIL CHƯA ĐỌC</b>"
        header_p = f"📬 THÔNG BÁO: CÓ {total} EMAIL CHƯA ĐỌC"
        if len(chunks) > 1:
            header_h += f" (Phần {idx+1}/{len(chunks)})\n\n"
            header_p += f" (Phần {idx+1}/{len(chunks)})\n\n"
        else:
            header_h += "\n\n"
            header_p += "\n\n"

        ok = send_single_telegram_msg(token, chat_id, header_h + h_text, header_p + p_text, log_callback)
        if not ok:
            all_success = False

    return all_success


def scan_emails(config, log_callback):
    if not HAS_WIN32:
        log_callback("❌ Lỗi: Chức năng quét Outlook chỉ hoạt động trên hệ điều hành Windows.")
        return
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
                if acc.Name.lower() != "archives":
                    get_all_folders_recursive(acc, all_folders)
            except Exception:
                pass

        log_callback(f"🗂 Outlook thấy {len(all_folders)} thư mục. Danh sách: {', '.join(sorted(all_folders.keys())[:20])}")

        folders_to_scan = {}
        explicit_folder_ids = set()
        
        target_folders = [_norm(f) for f in config.get("folders", []) if f.strip()]
        for tf in target_folders:
            if tf in all_folders:
                f_dict = {}
                add_folder_and_all_subfolders(all_folders[tf], f_dict)
                folders_to_scan.update(f_dict)
                explicit_folder_ids.update(f_dict.keys())
            else:
                log_callback(f"⚠️ Không tìm thấy thư mục '{tf}' trong Outlook (có thể tên sai hoặc chưa tạo)")
        
        target_senders = [_norm(s) for s in config.get("senders", []) if s.strip()]
        target_cc = [_norm(c) for c in config.get("cc_emails", []) if c.strip()]
        target_keywords = [_norm(k) for k in config.get("keywords", []) if k.strip()]
        
        # Nếu có cấu hình Senders hoặc Keywords -> luôn bổ sung Inbox và các thư mục con vào phạm vi quét
        default_inbox = outlook.GetDefaultFolder(6)
        if target_senders or target_keywords or not folders_to_scan:
            add_folder_and_all_subfolders(default_inbox, folders_to_scan)
        
        has_any_filter = bool(target_folders or target_senders or target_cc or target_keywords)
        
        if target_folders:
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

                    matched_sender = any(s in sender_email_norm or s in sender_name_norm for s in target_senders) if target_senders else False
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
                        
                        # --- CƠ CHẾ SMART CACHE ---
                        if entry_id in cache and cache[entry_id].get("summary"):
                            summary = cache[entry_id]["summary"]
                        else:
                            new_ai_calls += 1
                            ai_engine = config.get("ai_engine", "Offline")
                            try:
                                if "Offline" in ai_engine:
                                    summary = summarize_offline(body, subject, sender_display)
                                else:
                                    summary = summarize_with_ai(ai_engine, config.get("api_key", ""), subject, sender_display, body, log_callback=log_callback)
                                    if not summary: raise ValueError("AI trả về kết quả rỗng")
                            except Exception as ai_err:
                                log_callback(f"⚠️ AI [{ai_engine}] lỗi, dùng tóm tắt cục bộ: {ai_err}")
                                summary = summarize_offline(body, subject, sender_display)
                            
                            cache[entry_id] = {
                                "summary": summary,
                                "subject": subject,
                                "sender": sender_display,
                                "cached_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }

                        found_emails.append({
                            "folder": folder.Name,
                            "subject": subject,
                            "sender": sender_display,
                            "time": recv_time.strftime("%H:%M %d/%m/%Y"),
                            "summary": summary
                        })
                except Exception as msg_err:
                    log_callback(f"⚠️ Lỗi xử lý item: {type(msg_err).__name__}: {msg_err}")
                    continue

        if found_emails:
            # Luôn lưu cache ngay sau khi tóm tắt xong, KHÔNG phụ thuộc vào Telegram
            if new_ai_calls > 0:
                save_cache(cache)

            # Tự động chia nhỏ và gửi bản tin qua Telegram (tránh lỗi Telegram 400 Bad Request khi tin nhắn dài)
            success = send_telegram_report(
                config.get("tele_token"), 
                config.get("tele_chat_id"), 
                found_emails, 
                log_callback
            )

            cached_count = len(found_emails) - new_ai_calls
            if success:
                if new_ai_calls > 0:
                    log_callback(f"✅ Đã gửi báo cáo {len(found_emails)} email ({new_ai_calls} tóm tắt mới qua AI, {cached_count} từ Cache).")
                else:
                    log_callback(f"✅ Đã nhắc nhở {len(found_emails)} email (100% từ Cache, không tốn API).")
        else:
            if total_unread_scanned > 0:
                log_callback(f"ℹ️ Quét xong: Có {total_unread_scanned} email chưa đọc nhưng không khớp bộ lọc (Senders / Folders).")
            else:
                log_callback("ℹ️ Quét xong: Không có email nào chưa đọc trong 48h qua.")
            
    except Exception as e:
        log_callback(f"❌ Lỗi hệ thống khi quét mail: {e}")
    finally:
        pythoncom.CoUninitialize()
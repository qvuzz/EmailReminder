import imaplib
import email
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
import binascii
import re
import os
import sys
from datetime import datetime as dt_class, timedelta

from core_logic import (
    load_cache, 
    save_cache, 
    send_telegram_report, 
    _norm
)
from offline_ai import summarize_offline
from ai_engines import summarize_with_ai
from security import decrypt_password

def decode_utf7_imap(s):
    """Giải mã Modified UTF-7 (dành cho tên thư mục IMAP tiếng Việt như Hộp thư đến)"""
    res = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == '&':
            j = s.find('-', i)
            if j == -1:
                res.append(s[i:])
                break
            sub = s[i+1:j]
            if not sub:
                res.append('&')
            else:
                b64 = sub.replace(',', '/')
                pad = len(b64) % 4
                if pad:
                    b64 += '=' * (4 - pad)
                try:
                    decoded = binascii.a2b_base64(b64).decode('utf-16-be')
                    res.append(decoded)
                except Exception:
                    res.append(s[i:j+1])
            i = j + 1
        else:
            res.append(c)
            i += 1
    return "".join(res)

def encode_utf7_imap(s):
    """Mã hóa chuỗi ký tự thường sang dạng Modified UTF-7 để chọn thư mục trên IMAP Server"""
    res = []
    i = 0
    while i < len(s):
        c = s[i]
        if ord(c) < 32 or ord(c) > 126:
            run = []
            while i < len(s) and (ord(s[i]) < 32 or ord(s[i]) > 126):
                run.append(s[i])
                i += 1
            utf16_bytes = "".join(run).encode('utf-16-be')
            b64 = binascii.b2a_base64(utf16_bytes).decode('ascii').strip().replace('/', ',').replace('=', '')
            res.append(f"&{b64}-")
        else:
            if c == '&':
                res.append('&-')
            else:
                res.append(c)
            i += 1
    return "".join(res)

def strip_html_tags(html_text):
    """Lọc sạch các thẻ HTML và CSS rác từ mail định dạng HTML"""
    if not html_text:
        return ""
    # Xóa các khối script và style
    clean = re.sub(r'<(script|style)[^>]*>[\s\S]*?</\1>', '', html_text, flags=re.IGNORECASE)
    # Xóa các thẻ HTML
    clean = re.sub(r'<[^>]+>', ' ', clean)
    # Giải mã ký tự HTML entities (như &nbsp;, &lt;, &gt;)
    import html
    clean = html.unescape(clean)
    # Chuẩn hóa khoảng trắng
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()

def get_email_body(msg):
    """Lấy nội dung văn bản (body) từ đối tượng Message, ưu tiên plain text"""
    text_parts = []
    html_parts = []
    
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition") or "")
            if "attachment" in content_disposition:
                continue
            
            payload = part.get_payload(decode=True)
            if not payload:
                continue
                
            charset = part.get_content_charset() or 'utf-8'
            try:
                text_content = payload.decode(charset, errors='replace')
            except Exception:
                text_content = payload.decode('utf-8', errors='ignore')

            if content_type == "text/plain":
                text_parts.append(text_content)
            elif content_type == "text/html":
                html_parts.append(text_content)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or 'utf-8'
            try:
                text_content = payload.decode(charset, errors='replace')
            except Exception:
                text_content = payload.decode('utf-8', errors='ignore')
            if msg.get_content_type() == "text/html":
                html_parts.append(text_content)
            else:
                text_parts.append(text_content)
                
    if text_parts:
        body = "\n".join(text_parts).strip()
    elif html_parts:
        body = strip_html_tags("\n".join(html_parts))
    else:
        body = ""
        
    if body and ("<html" in body.lower() or "<body" in body.lower() or "<div" in body.lower() or "<p" in body.lower()):
        body = strip_html_tags(body)
        
    return body.strip()

def decode_email_header(header_value):
    """Giải mã các chuỗi mã hóa tiêu đề hoặc tên người gửi (RFC 2047)"""
    if not header_value:
        return ""
    try:
        decoded_parts = decode_header(header_value)
        decoded_str = ""
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                decoded_str += part.decode(encoding or 'utf-8', errors='ignore')
            else:
                decoded_str += part
        return decoded_str.strip()
    except Exception:
        return str(header_value)

def get_imap_folders(mail, log_callback):
    """Lấy danh sách tất cả các thư mục mail thô từ server"""
    folders = []
    try:
        status, folder_list = mail.list()
        if status == 'OK':
            for folder_bytes in folder_list:
                folder_str = folder_bytes.decode('utf-8', errors='ignore')
                # Trích xuất thư mục nằm trong dấu ngoặc kép ở cuối dòng
                match = re.search(r'"([^"]+)"\s*$', folder_str)
                if match:
                    folders.append(match.group(1))
                else:
                    parts = folder_str.split()
                    if parts:
                        folders.append(parts[-1])
    except Exception as e:
        log_callback(f"⚠️ Không thể lấy danh sách thư mục IMAP: {e}")
    return folders

def test_imap_connection_logic(server, port_str, user, password, use_ssl):
    """Kiểm tra kết nối và đăng nhập tới máy chủ IMAP, trả về (thành_công, số_thư_mục_hoặc_lỗi)"""
    try:
        port = int(port_str) if port_str else (993 if use_ssl else 143)
    except Exception:
        port = 993 if use_ssl else 143

    if use_ssl:
        mail = imaplib.IMAP4_SSL(server, port, timeout=12)
    else:
        mail = imaplib.IMAP4(server, port, timeout=12)

    plain_pwd = decrypt_password(password)
    mail.login(user, plain_pwd)
    status, folders = mail.list()
    mail.logout()
    return True, f"Tìm thấy {len(folders)} thư mục." if folders else "Đăng nhập thành công!"

def scan_single_imap_account(acc, config, cache, seen_msg_ids, log_callback):
    """Quét thư chưa đọc cho một tài khoản IMAP cụ thể"""
    acc_name = acc.get("name", "Webmail").strip() or "Webmail"
    server = acc.get("server", "").strip()
    port_str = acc.get("port", "993")
    user = acc.get("user", "").strip()
    password = acc.get("password", "").strip()
    use_ssl = acc.get("ssl", True)

    if not server or not user or not password:
        log_callback(f"⚠️ [{acc_name}] Bỏ qua do thiếu thông tin (Server/Tài khoản/Mật khẩu).")
        return [], 0, 0

    try:
        port = int(port_str) if port_str else (993 if use_ssl else 143)
    except Exception:
        port = 993 if use_ssl else 143

    found_emails = []
    new_ai_calls = 0
    total_unread_scanned = 0

    try:
        log_callback(f"📧 [{acc_name}] Đang kết nối tới server {server}:{port}...")
        if use_ssl:
            mail = imaplib.IMAP4_SSL(server, port, timeout=20)
        else:
            mail = imaplib.IMAP4(server, port, timeout=20)

        plain_pwd = decrypt_password(password)
        mail.login(user, plain_pwd)

        # Lấy danh sách thư mục thô và giải mã tiếng Việt
        server_folders = get_imap_folders(mail, log_callback)
        decoded_server_folders = {}
        for f in server_folders:
            decoded_name = decode_utf7_imap(f)
            decoded_server_folders[_norm(decoded_name)] = f

        # Lọc danh sách thư mục quét từ config
        target_folders = [_norm(f) for f in config.get("folders", []) if f.strip()]
        folders_to_scan = []
        if not target_folders:
            log_callback(f"ℹ️ [{acc_name}] Cột Folders đang để trống -> Mặc định quét Hộp thư đến (INBOX).")
            folders_to_scan.append(("Inbox", "INBOX"))
        else:
            for tf in target_folders:
                matched = False
                for decoded_norm, raw_utf7 in decoded_server_folders.items():
                    if tf == decoded_norm or (tf == "inbox" and decoded_norm == "inbox"):
                        folders_to_scan.append((tf, raw_utf7))
                        matched = True
                        break
                if not matched:
                    if tf == "inbox":
                        folders_to_scan.append(("Inbox", "INBOX"))
                    else:
                        encoded_tf = encode_utf7_imap(tf)
                        folders_to_scan.append((tf, encoded_tf))

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

        log_callback(f"📂 [{acc_name}] Đang kiểm tra {len(folders_to_scan)} thư mục: {', '.join([f[0] for f in folders_to_scan])}")

        time_limit = dt_class.now() - timedelta(days=2)
        imap_date_str = time_limit.strftime("%d-%b-%Y")

        for friendly_name, raw_folder in folders_to_scan:
            try:
                status, select_data = mail.select(raw_folder)
                if status != 'OK':
                    log_callback(f"⚠️ [{acc_name}] Thư mục '{friendly_name}' không thể chọn trên server.")
                    continue

                status, search_data = mail.search(None, f'UNSEEN SINCE {imap_date_str}')
                if status != 'OK' or not search_data or not search_data[0]:
                    continue

                all_email_ids = search_data[0].split()
                # Giới hạn tối đa 25 thư chưa đọc mới nhất để tốc độ quét luôn tức thì
                email_ids = all_email_ids[-25:] if len(all_email_ids) > 25 else all_email_ids
                total_unseen = len(email_ids)
                
                if total_unseen > 0:
                    log_callback(f"📨 [{acc_name}] Phát hiện {total_unseen} thư chưa đọc trong '{friendly_name}', đang đối soát...")

                for idx, email_id in enumerate(reversed(email_ids)):
                    try:
                        # BƯỚC 1: Chỉ tải Header siêu nhẹ (~1KB) thay vì toàn bộ dung lượng mail
                        status, header_data = mail.fetch(email_id, '(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM TO CC DATE MESSAGE-ID)])')
                        if status != 'OK' or not header_data or not header_data[0]:
                            continue

                        raw_headers = header_data[0][1]
                        if not raw_headers:
                            continue

                        msg_header = email.message_from_bytes(raw_headers)

                        # Tiêu đề
                        subject_raw = msg_header.get('Subject', '')
                        subject = decode_email_header(subject_raw) or "(Không tiêu đề)"

                        # Người gửi
                        from_header = msg_header.get('From', '')
                        sender_name, sender_email = parseaddr(from_header)
                        sender_name = decode_email_header(sender_name)

                        if sender_name and sender_email and sender_name.lower() != sender_email.lower():
                            sender_display = f"{sender_name} <{sender_email}>"
                        elif sender_email:
                            sender_display = sender_email
                        elif sender_name:
                            sender_display = sender_name
                        else:
                            sender_display = "Người gửi ẩn"

                        # Thời gian nhận
                        date_header = msg_header.get('Date')
                        recv_time = None
                        if date_header:
                            try:
                                recv_time = parsedate_to_datetime(date_header)
                                if recv_time.tzinfo is not None:
                                    recv_time = recv_time.replace(tzinfo=None)
                            except Exception:
                                pass
                        if not recv_time:
                            recv_time = dt_class.now()

                        if recv_time < time_limit:
                            continue

                        total_unread_scanned += 1

                        # Cache ID
                        msg_id = msg_header.get('Message-ID', '')
                        if not msg_id:
                            msg_id = f"{user}_{subject}_{sender_email}_{recv_time.strftime('%Y%m%d%H%M%S')}"

                        if msg_id in seen_msg_ids:
                            continue
                        seen_msg_ids.add(msg_id)

                        # Kiểm tra bộ lọc cơ bản từ Header trước
                        sender_email_norm = _norm(sender_email)
                        sender_name_norm = _norm(sender_name)
                        to_header = msg_header.get('To', '')
                        cc_header = msg_header.get('Cc', '')
                        cc_norm = _norm(f"{to_header} {cc_header}")
                        subject_norm = _norm(subject)

                        matched_sender = any(
                            (s and s in sender_email_norm) or 
                            (s and s in sender_name_norm) or 
                            (sender_email_norm and sender_email_norm in s) or 
                            (sender_name_norm and sender_name_norm in s)
                            for s in target_senders if s
                        ) if target_senders else False
                        matched_cc = any(c in cc_norm for c in target_cc) if target_cc else False
                        matched_keyword_subject = any(k in subject_norm for k in target_keywords) if target_keywords else False
                        is_in_target_folder = any(tf == _norm(friendly_name) for tf in target_folders)

                        # BƯỚC 2: Kiểm tra Cache trước
                        if msg_id in cache and cache[msg_id].get("summary") and not cache[msg_id]["summary"].startswith("[Lỗi"):
                            summary = cache[msg_id]["summary"]
                            # Đã có trong cache -> Không cần tải nội dung body mail nữa
                            should_read = True if not has_any_filter else (is_in_target_folder or matched_sender or matched_keyword_subject or matched_cc)
                            if should_read:
                                found_emails.append({
                                    "account_name": acc_name,
                                    "folder": friendly_name,
                                    "actual_folder": raw_folder,
                                    "subject": subject,
                                    "sender": sender_display,
                                    "time": recv_time.strftime("%H:%M %d/%m/%Y"),
                                    "summary": summary,
                                    "server": acc.get("server", ""),
                                    "user": acc.get("user", ""),
                                    "msg_id": msg_id,
                                    "email_id": email_id.decode() if isinstance(email_id, bytes) else str(email_id)
                                })
                            continue

                        # BƯỚC 3: Thư MỚI chưa có trong Cache -> Mới cần tải Body để AI tóm tắt
                        log_callback(f"⏳ [{acc_name}] Đang đọc & tóm tắt ({idx+1}/{total_unseen}): '{subject[:35]}...'")
                        status, full_data = mail.fetch(email_id, '(BODY.PEEK[])')
                        body_raw = ""
                        if status == 'OK' and full_data and full_data[0]:
                            full_raw_msg = full_data[0][1]
                            if full_raw_msg:
                                full_msg = email.message_from_bytes(full_raw_msg)
                                body_raw = get_email_body(full_msg)

                        body_norm = _norm(body_raw)
                        matched_keyword_body = any(k in body_norm for k in target_keywords) if target_keywords else False
                        matched_keyword = (matched_keyword_subject or matched_keyword_body)

                        if not has_any_filter:
                            should_read = True
                        else:
                            should_read = (is_in_target_folder or matched_sender or matched_keyword or matched_cc)

                        if should_read:
                            new_ai_calls += 1
                            ai_engine = config.get("ai_engine", "Offline")
                            try:
                                if "Offline" in ai_engine:
                                    summary = summarize_offline(body_raw, subject, sender_display)
                                else:
                                    summary = summarize_with_ai(ai_engine, config.get("api_key", ""), subject, sender_display, body_raw, log_callback=log_callback)
                                    if not summary:
                                        raise ValueError("AI trả về kết quả rỗng")
                            except Exception as ai_err:
                                log_callback(f"⚠️ AI [{ai_engine}] lỗi, dùng tóm tắt cục bộ: {ai_err}")
                                summary = summarize_offline(body_raw, subject, sender_display)

                            if not summary.startswith("[Lỗi"):
                                cache[msg_id] = {
                                    "summary": summary,
                                    "subject": subject,
                                    "sender": sender_display,
                                    "cached_at": dt_class.now().strftime("%Y-%m-%d %H:%M:%S")
                                }

                            found_emails.append({
                                "account_name": acc_name,
                                "folder": friendly_name,
                                "actual_folder": raw_folder,
                                "subject": subject,
                                "sender": sender_display,
                                "time": recv_time.strftime("%H:%M %d/%m/%Y"),
                                "summary": summary,
                                "body": body,
                                "server": acc.get("server", ""),
                                "user": acc.get("user", ""),
                                "msg_id": msg_id,
                                "email_id": email_id.decode() if isinstance(email_id, bytes) else str(email_id)
                            })
                    except Exception as msg_err:
                        log_callback(f"⚠️ [{acc_name}] Lỗi đọc thư thứ {email_id}: {msg_err}")
                        continue
            except Exception as folder_err:
                log_callback(f"⚠️ [{acc_name}] Lỗi xử lý thư mục {friendly_name}: {folder_err}")
                continue

        mail.logout()
    except Exception as e:
        log_callback(f"❌ [{acc_name}] Lỗi kết nối IMAP server: {e}")

    return found_emails, new_ai_calls, total_unread_scanned

def scan_emails_imap(config, log_callback, on_emails_found_callback=None):
    """Quét các email chưa đọc trực tiếp từ danh sách các máy chủ Webmail qua cổng IMAP"""
    accounts = config.get("imap_accounts", [])
    
    # Hỗ trợ tương thích ngược cấu hình đơn cũ
    if not accounts and config.get("imap_server"):
        accounts = [{
            "id": "default",
            "name": "Webmail",
            "server": config.get("imap_server", ""),
            "port": str(config.get("imap_port", "993")),
            "user": config.get("imap_user", ""),
            "password": config.get("imap_password", ""),
            "ssl": bool(config.get("imap_ssl", True))
        }]

    if not accounts:
        log_callback("⚠️ Chưa có tài khoản Webmail/IMAP nào được cấu hình. Vui lòng thêm tài khoản ở tab Cài Đặt.")
        return []

    cache = load_cache()
    all_found_emails = []
    total_new_ai_calls = 0
    total_unread_all_accs = 0
    seen_msg_ids = set()

    for acc in accounts:
        try:
            found, ai_calls, unread_count = scan_single_imap_account(
                acc, config, cache, seen_msg_ids, log_callback
            )
            all_found_emails.extend(found)
            total_new_ai_calls += ai_calls
            total_unread_all_accs += unread_count
        except Exception as acc_err:
            log_callback(f"⚠️ Lỗi quét tài khoản '{acc.get('name', 'Webmail')}': {acc_err}")

    # Gửi Telegram & Cập nhật Cache chung
    if all_found_emails:
        if total_new_ai_calls > 0:
            save_cache(cache)

        # Phân loại Thread & Standalone
        from thread_logic import process_scanned_emails_for_threads
        standalone_emails, thread_notifications = process_scanned_emails_for_threads(
            all_found_emails, config, log_callback=log_callback
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
                    on_emails_found_callback(all_found_emails)
                except Exception as cb_err:
                    log_callback(f"⚠️ Lỗi hiển thị thông báo Desktop: {cb_err}")

        return all_found_emails
    else:
        if total_unread_all_accs > 0:
            log_callback(f"ℹ️ Quét xong tất cả tài khoản: Có {total_unread_all_accs} email chưa đọc trên các server nhưng không thỏa bộ lọc.")
        else:
            log_callback("ℹ️ Quét xong: Không có email nào chưa đọc trong 48h qua trên tất cả các tài khoản.")
        return []


def mark_email_as_read_imap(account, actual_folder, msg_id, email_id=None, log_callback=None):
    """Đánh dấu đã đọc email trên Webmail / IMAP"""
    if not account:
        return False
    try:
        server = account.get("server", "").strip()
        port = int(account.get("port", 993))
        user = account.get("user", "").strip()
        pwd = decrypt_password(account.get("password", ""))
        use_ssl = account.get("ssl", True)

        if use_ssl:
            mail = imaplib.IMAP4_SSL(server, port, timeout=15)
        else:
            mail = imaplib.IMAP4(server, port, timeout=15)

        mail.login(user, pwd)
        target_folder = actual_folder or "INBOX"
        status, _ = mail.select(f'"{target_folder}"', readonly=False)
        if status != 'OK':
            status, _ = mail.select('INBOX', readonly=False)

        marked = False
        # 1. Thử đánh dấu theo email_id trước
        if email_id:
            try:
                res, _ = mail.store(str(email_id), '+FLAGS', '(\\Seen)')
                if res == 'OK':
                    marked = True
            except Exception:
                pass

        # 2. Nếu chưa được, tìm kiếm theo Message-ID
        if not marked and msg_id:
            try:
                typ, data = mail.search(None, f'HEADER Message-ID "{msg_id}"')
                if typ == 'OK' and data and data[0]:
                    for num in data[0].split():
                        mail.store(num, '+FLAGS', '(\\Seen)')
                        marked = True
            except Exception:
                pass

        mail.logout()
        if log_callback:
            log_callback(f"🌐 [{account.get('name', 'Webmail')}] Đã đánh dấu ĐÃ ĐỌC thành công trên server.")
        return True
    except Exception as e:
        if log_callback:
            log_callback(f"⚠️ [{account.get('name', 'Webmail')}] Lỗi đánh dấu đã đọc trên IMAP: {e}")
        return False


def delete_email_imap(account, actual_folder, msg_id, email_id=None, log_callback=None):
    """Xóa email trên Webmail / IMAP (chuyển vào Thùng rác và đánh dấu \\Deleted)"""
    if not account:
        return False
    try:
        server = account.get("server", "").strip()
        port = int(account.get("port", 993))
        user = account.get("user", "").strip()
        pwd = decrypt_password(account.get("password", ""))
        use_ssl = account.get("ssl", True)

        if use_ssl:
            mail = imaplib.IMAP4_SSL(server, port, timeout=15)
        else:
            mail = imaplib.IMAP4(server, port, timeout=15)

        mail.login(user, pwd)
        target_folder = actual_folder or "INBOX"
        status, _ = mail.select(f'"{target_folder}"', readonly=False)
        if status != 'OK':
            status, _ = mail.select('INBOX', readonly=False)

        # Tìm các folder thùng rác phổ biến
        trash_folder = None
        try:
            status, folder_list = mail.list()
            if status == 'OK':
                for f_info in folder_list:
                    f_name = f_info.decode('utf-8', errors='ignore')
                    for kw in ['trash', 'thung rac', 'thùng rác', 'deleted', 'deleted items', 'deleted messages']:
                        if kw in f_name.lower():
                            parts = f_name.split(' "/" ')
                            if len(parts) > 1:
                                trash_folder = parts[-1].strip().strip('"')
                            break
                    if trash_folder:
                        break
        except Exception:
            pass

        target_nums = []
        if email_id:
            target_nums.append(str(email_id).encode())

        if not target_nums and msg_id:
            try:
                typ, data = mail.search(None, f'HEADER Message-ID "{msg_id}"')
                if typ == 'OK' and data and data[0]:
                    target_nums.extend(data[0].split())
            except Exception:
                pass

        deleted = False
        for num in target_nums:
            if trash_folder and trash_folder.upper() != target_folder.upper():
                try:
                    mail.copy(num, f'"{trash_folder}"')
                except Exception:
                    pass
            mail.store(num, '+FLAGS', '(\\Deleted)')
            deleted = True

        if deleted:
            try:
                mail.expunge()
            except Exception:
                pass
            if log_callback:
                log_callback(f"🗑️ [{account.get('name', 'Webmail')}] Đã chuyển email vào Thùng rác.")
            mail.logout()
            return True

        mail.logout()
        return False
    except Exception as e:
        if log_callback:
            log_callback(f"⚠️ [{account.get('name', 'Webmail')}] Lỗi khi xóa email: {e}")
        return False

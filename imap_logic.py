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
    body = ""
    if msg.is_multipart():
        # Quét qua các phần của email
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            
            if content_type == "text/plain" and "attachment" not in content_disposition:
                charset = part.get_content_charset() or 'utf-8'
                try:
                    body = part.get_payload(decode=True).decode(charset, errors='ignore')
                    break  # Ưu tiên text/plain và ngắt ngay
                except Exception:
                    pass
            elif content_type == "text/html" and "attachment" not in content_disposition:
                charset = part.get_content_charset() or 'utf-8'
                try:
                    body = part.get_payload(decode=True).decode(charset, errors='ignore')
                except Exception:
                    pass
    else:
        charset = msg.get_content_charset() or 'utf-8'
        try:
            body = msg.get_payload(decode=True).decode(charset, errors='ignore')
        except Exception:
            pass
            
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

def scan_emails_imap(config, log_callback):
    """Quét các email chưa đọc trực tiếp từ máy chủ Webmail qua cổng IMAP"""
    imap_server = config.get("imap_server", "").strip()
    imap_port_str = config.get("imap_port", "993").strip()
    imap_user = config.get("imap_user", "").strip()
    imap_password = config.get("imap_password", "").strip()
    imap_ssl = config.get("imap_ssl", True)

    if not imap_server or not imap_user or not imap_password:
        log_callback("⚠️ Thiếu cấu hình Webmail (Server / Tài khoản / Mật khẩu). Vui lòng cấu hình ở tab Cài Đặt.")
        return

    try:
        imap_port = int(imap_port_str) if imap_port_str else (993 if imap_ssl else 143)
    except Exception:
        imap_port = 993 if imap_ssl else 143

    try:
        log_callback(f"📧 Đang kết nối tới server IMAP: {imap_server}:{imap_port}...")
        if imap_ssl:
            mail = imaplib.IMAP4_SSL(imap_server, imap_port, timeout=20)
        else:
            mail = imaplib.IMAP4(imap_server, imap_port, timeout=20)

        log_callback("📧 Đang đăng nhập Webmail...")
        mail.login(imap_user, imap_password)

        # Lấy danh sách thư mục thô và giải mã tiếng Việt
        server_folders = get_imap_folders(mail, log_callback)
        decoded_server_folders = {}
        for f in server_folders:
            decoded_name = decode_utf7_imap(f)
            decoded_server_folders[_norm(decoded_name)] = f

        # Lọc danh sách thư mục quét từ config
        target_folders = [_norm(f) for f in config.get("folders", []) if f.strip()]
        if not target_folders:
            target_folders = ["inbox"]

        folders_to_scan = []
        for tf in target_folders:
            matched = False
            for decoded_norm, raw_utf7 in decoded_server_folders.items():
                if tf == decoded_norm or (tf == "inbox" and decoded_norm == "inbox"):
                    folders_to_scan.append((decoded_name, raw_utf7))
                    matched = True
                    break
            if not matched:
                if tf == "inbox":
                    folders_to_scan.append(("Inbox", "INBOX"))
                else:
                    # Cố gắng tự mã hóa nếu thư mục chưa được quét khớp (hoặc tạo folder trực tiếp)
                    encoded_tf = encode_utf7_imap(tf)
                    folders_to_scan.append((tf, encoded_tf))

        target_senders = [_norm(s) for s in config.get("senders", []) if s.strip()]
        target_cc = [_norm(c) for c in config.get("cc_emails", []) if c.strip()]
        target_keywords = [_norm(k) for k in config.get("keywords", []) if k.strip()]
        has_any_filter = bool(target_folders or target_senders or target_cc or target_keywords)

        log_callback(f"📂 Đang kiểm tra {len(folders_to_scan)} thư mục IMAP: {', '.join([f[0] for f in folders_to_scan])}")

        cache = load_cache()
        time_limit = dt_class.now() - timedelta(days=2)
        imap_date_str = time_limit.strftime("%d-%b-%Y") # Định dạng chuẩn IMAP: DD-Mon-YYYY

        found_emails = []
        new_ai_calls = 0
        total_unread_scanned = 0
        seen_msg_ids = set()

        for friendly_name, raw_folder in folders_to_scan:
            try:
                # Chọn thư mục
                status, select_data = mail.select(raw_folder)
                if status != 'OK':
                    log_callback(f"⚠️ Thư mục '{friendly_name}' không thể chọn trên server (có thể tên sai).")
                    continue

                # Tìm các thư chưa đọc kể từ 48 giờ trước
                status, search_data = mail.search(None, f'UNSEEN SINCE {imap_date_str}')
                if status != 'OK':
                    continue

                email_ids = search_data[0].split()
                # Quét từ thư mới nhất tới cũ hơn
                for email_id in reversed(email_ids):
                    try:
                        # Tải thông tin mail dùng BODY.PEEK để không đánh dấu đã đọc
                        status, msg_data = mail.fetch(email_id, '(BODY.PEEK[])')
                        if status != 'OK' or not msg_data or not msg_data[0]:
                            continue

                        raw_msg = msg_data[0][1]
                        if not raw_msg:
                            continue

                        msg = email.message_from_bytes(raw_msg)
                        
                        # Phân tích Tiêu đề
                        subject_raw = msg.get('Subject', '')
                        subject = decode_email_header(subject_raw) or "(Không tiêu đề)"

                        # Phân tích Người gửi
                        from_header = msg.get('From', '')
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

                        # Phân tích Thời gian nhận
                        date_header = msg.get('Date')
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

                        # Định danh duy nhất: Sử dụng Message-ID hoặc băm thông tin làm Key cache
                        msg_id = msg.get('Message-ID', '')
                        if not msg_id:
                            msg_id = f"{subject}_{sender_email}_{recv_time.strftime('%Y%m%d%H%M%S')}"

                        if msg_id in seen_msg_ids:
                            continue
                        seen_msg_ids.add(msg_id)

                        # Phép thử lọc mail
                        sender_email_norm = _norm(sender_email)
                        sender_name_norm = _norm(sender_name)
                        to_header = msg.get('To', '')
                        cc_header = msg.get('Cc', '')
                        cc_norm = _norm(f"{to_header} {cc_header}")
                        subject_norm = _norm(subject)
                        body_raw = get_email_body(msg)
                        body_norm = _norm(body_raw)

                        matched_sender = any(s in sender_email_norm or s in sender_name_norm for s in target_senders) if target_senders else False
                        matched_cc = any(c in cc_norm for c in target_cc) if target_cc else False
                        matched_keyword = any(k in subject_norm or k in body_norm for k in target_keywords) if target_keywords else False

                        is_in_target_folder = any(tf == _norm(friendly_name) for tf in target_folders)

                        if not has_any_filter:
                            should_read = True
                        else:
                            should_read = (is_in_target_folder or matched_sender or matched_keyword or matched_cc)

                        if should_read:
                            # Đọc cache / tóm tắt AI
                            if msg_id in cache and cache[msg_id].get("summary"):
                                summary = cache[msg_id]["summary"]
                            else:
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

                                cache[msg_id] = {
                                    "summary": summary,
                                    "subject": subject,
                                    "sender": sender_display,
                                    "cached_at": dt_class.now().strftime("%Y-%m-%d %H:%M:%S")
                                }

                            found_emails.append({
                                "folder": friendly_name,
                                "subject": subject,
                                "sender": sender_display,
                                "time": recv_time.strftime("%H:%M %d/%m/%Y"),
                                "summary": summary
                            })
                    except Exception as msg_err:
                        log_callback(f"⚠️ Lỗi đọc thư thứ {email_id}: {msg_err}")
                        continue
            except Exception as folder_err:
                log_callback(f"⚠️ Lỗi xử lý thư mục {friendly_name}: {folder_err}")
                continue

        # Gửi Telegram & Cập nhật Cache
        if found_emails:
            if new_ai_calls > 0:
                save_cache(cache)

            success = send_telegram_report(
                config.get("tele_token"),
                config.get("tele_chat_id"),
                found_emails,
                log_callback
            )

            cached_count = len(found_emails) - new_ai_calls
            if success:
                if new_ai_calls > 0:
                    log_callback(f"✅ Đã nhắc báo {len(found_emails)} email ({new_ai_calls} tóm tắt mới, {cached_count} từ Cache).")
                else:
                    log_callback(f"✅ Đã nhắc báo {len(found_emails)} email (100% từ Cache).")
        else:
            if total_unread_scanned > 0:
                log_callback(f"ℹ️ Quét xong: Có {total_unread_scanned} email chưa đọc trên server nhưng không thỏa bộ lọc.")
            else:
                log_callback("ℹ️ Quét xong: Không có email nào chưa đọc trong 48h qua.")

        mail.logout()
    except Exception as e:
        log_callback(f"❌ Lỗi hệ thống khi kết nối Webmail IMAP: {e}")

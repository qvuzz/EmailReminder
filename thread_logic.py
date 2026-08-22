import sqlite3
import os
import re
import sys
from datetime import datetime

if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(APP_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
THREADS_DB_FILE = os.path.join(DATA_DIR, "threads.db")


def get_db_connection():
    """Tạo kết nối SQLite an toàn với cơ chế timeout và row_factory"""
    conn = sqlite3.connect(THREADS_DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_thread_db():
    """Khởi tạo cấu trúc bảng email_threads nếu chưa tồn tại"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_key TEXT UNIQUE NOT NULL,
                subject TEXT NOT NULL,
                current_summary TEXT DEFAULT '',
                email_count INTEGER DEFAULT 1,
                last_updated TEXT NOT NULL,
                account_name TEXT DEFAULT '',
                folder TEXT DEFAULT '',
                last_sender TEXT DEFAULT '',
                email_items TEXT DEFAULT '[]'
            )
        """)
        try:
            cursor.execute("ALTER TABLE email_threads ADD COLUMN email_items TEXT DEFAULT '[]'")
        except Exception:
            pass
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_thread_key ON email_threads(thread_key)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_last_updated ON email_threads(last_updated)")
        conn.commit()


def normalize_thread_subject(raw_subject):
    """
    Chuẩn hóa tiêu đề email:
    - Loại bỏ các tiền tố reply/forward (Re:, Fwd:, Tr:, FW:, Reply:, Trả lời:, Chuyển tiếp:...).
    - Loại bỏ các thẻ tag vuông phổ biến trong thư công việc doanh nghiệp ([NOC], [Khẩn], [Cảnh báo], [VNPT]...).
    - Trả về tuple: (thread_key, cleaned_subject, is_thread_candidate)
    """
    if not raw_subject:
        return "", "(Không tiêu đề)", False

    s = raw_subject.strip()
    is_reply_or_fwd = False

    # 1. Bóc tách tiền tố Re:, Fwd:, FW:, Tr:,... liên tục (kể cả lồng nhau như Re: Fwd: Re:)
    prefix_pattern = r'^(?:(?:re|fwd|fw|tr|reply|forward|trả\s*lời|chuyển\s*tiếp|thư\s*trả\s*lời)\s*[:：\-\]]\s*)+'
    while True:
        m = re.match(prefix_pattern, s, flags=re.IGNORECASE)
        if m:
            is_reply_or_fwd = True
            s = s[m.end():].strip()
        else:
            break

    # 2. Loại bỏ các thẻ tag vuông ở đầu hoặc giữa tiêu đề nếu có ([NOC], [Khẩn], [Ticket#123]...)
    # Giữ lại nội dung nếu cả tiêu đề chỉ là [Tag]
    s_cleaned = re.sub(r'\[(?:noc|khẩn|khan|cảnh\s*báo|canh\s*bao|vnpt|ticket[#\s0-9]*|hỗ\s*trợ|tb|thông\s*báo)\]', '', s, flags=re.IGNORECASE).strip()
    if s_cleaned:
        s = s_cleaned

    # Làm sạch khoảng trắng thừa
    s = re.sub(r'\s+', ' ', s).strip()
    if not s:
        s = raw_subject.strip()

    cleaned_display_subject = s
    # thread_key: viết thường, loại bỏ ký tự đặc biệt thừa để so khớp chính xác
    thread_key = re.sub(r'[^\w\s]', '', s.lower()).strip()
    thread_key = re.sub(r'\s+', ' ', thread_key)

    return thread_key, cleaned_display_subject, is_reply_or_fwd


def get_thread_by_key(thread_key):
    """Truy vấn thông tin thread theo thread_key"""
    if not thread_key:
        return None
    init_thread_db()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM email_threads WHERE thread_key = ?", (thread_key,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_threads(limit=200, search_kw=""):
    """Lấy danh sách tất cả các Thread, hỗ trợ tìm kiếm từ khóa"""
    init_thread_db()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if search_kw:
            kw = f"%{search_kw.strip().lower()}%"
            cursor.execute("""
                SELECT * FROM email_threads 
                WHERE LOWER(subject) LIKE ? OR LOWER(current_summary) LIKE ? OR LOWER(last_sender) LIKE ?
                ORDER BY datetime(last_updated) DESC, id DESC 
                LIMIT ?
            """, (kw, kw, kw, limit))
        else:
            cursor.execute("""
                SELECT * FROM email_threads 
                ORDER BY datetime(last_updated) DESC, id DESC 
                LIMIT ?
            """, (limit,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def save_or_update_thread(thread_key, subject, current_summary, email_count, last_updated, account_name="", folder="", last_sender="", email_items=None):
    """Lưu mới hoặc cập nhật một Thread vào threads.db"""
    import json
    init_thread_db()
    items_json = json.dumps(email_items or [], ensure_ascii=False)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO email_threads (thread_key, subject, current_summary, email_count, last_updated, account_name, folder, last_sender, email_items)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(thread_key) DO UPDATE SET
                subject = excluded.subject,
                current_summary = excluded.current_summary,
                email_count = excluded.email_count,
                last_updated = excluded.last_updated,
                account_name = excluded.account_name,
                folder = excluded.folder,
                last_sender = excluded.last_sender,
                email_items = excluded.email_items
        """, (thread_key, subject, current_summary, email_count, last_updated, account_name, folder, last_sender, items_json))
        conn.commit()


def mark_thread_as_read(thread_id, config=None, log_callback=None):
    """Đánh dấu ĐÃ ĐỌC tất cả các email trong Thread trên Outlook và Webmail/IMAP"""
    import json
    from core_logic import mark_email_as_read_outlook
    from imap_logic import mark_email_as_read_imap

    init_thread_db()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM email_threads WHERE id = ?", (thread_id,))
        row = cursor.fetchone()
        if not row:
            return False
        thread = dict(row)

    items_str = thread.get("email_items", "[]")
    try:
        items = json.loads(items_str) if items_str else []
    except Exception:
        items = []

    success_count = 0
    accounts = config.get("imap_accounts", []) if config else []

    for item in items:
        # 1. Outlook
        if item.get("entry_id"):
            try:
                res = mark_email_as_read_outlook(item["entry_id"], log_callback=log_callback)
                if res: success_count += 1
            except Exception:
                pass
        
        # 2. IMAP
        elif item.get("server") or item.get("user") or item.get("msg_id"):
            matched_acc = None
            for acc in accounts:
                if acc.get("server") == item.get("server") or acc.get("user") == item.get("user"):
                    matched_acc = acc
                    break
            if not matched_acc and accounts:
                matched_acc = accounts[0]

            if matched_acc:
                try:
                    res = mark_email_as_read_imap(
                        account=matched_acc,
                        actual_folder=item.get("actual_folder") or item.get("folder", "INBOX"),
                        msg_id=item.get("msg_id", ""),
                        email_id=item.get("email_id"),
                        log_callback=log_callback
                    )
                    if res: success_count += 1
                except Exception:
                    pass

    if log_callback:
        log_callback(f"✅ Đã đánh dấu ĐÃ ĐỌC ({success_count}/{len(items) if items else 1} thư) cho chuỗi: '{thread.get('subject')}'")
    return True


def delete_thread(thread_id):
    """Xóa 1 thread theo ID khỏi SQLite"""
    init_thread_db()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM email_threads WHERE id = ?", (thread_id,))
        conn.commit()


def delete_thread_with_emails(thread_id, config=None, log_callback=None):
    """Xóa chuỗi trong DB và chuyển tất cả các email thuộc chuỗi vào Thùng rác trên Outlook & Webmail"""
    import json
    from core_logic import delete_email_outlook
    from imap_logic import delete_email_imap

    init_thread_db()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM email_threads WHERE id = ?", (thread_id,))
        row = cursor.fetchone()
        if not row:
            return False
        thread = dict(row)

    items_str = thread.get("email_items", "[]")
    try:
        items = json.loads(items_str) if items_str else []
    except Exception:
        items = []

    success_count = 0
    accounts = config.get("imap_accounts", []) if config else []

    # Xóa bản ghi trong SQLite ngay từ đầu để UI và các luồng khác không hiển thị lại thread này
    delete_thread(thread_id)

    for item in items:
        # 1. Outlook
        if item.get("entry_id"):
            try:
                res = delete_email_outlook(item["entry_id"], log_callback=log_callback)
                if res: success_count += 1
            except Exception:
                pass
        
        # 2. IMAP
        elif item.get("server") or item.get("user") or item.get("msg_id"):
            matched_acc = None
            for acc in accounts:
                if acc.get("server") == item.get("server") or acc.get("user") == item.get("user"):
                    matched_acc = acc
                    break
            if not matched_acc and accounts:
                matched_acc = accounts[0]

            if matched_acc:
                try:
                    res = delete_email_imap(
                        account=matched_acc,
                        actual_folder=item.get("actual_folder") or item.get("folder", "INBOX"),
                        msg_id=item.get("msg_id", ""),
                        email_id=item.get("email_id"),
                        log_callback=log_callback
                    )
                    if res: success_count += 1
                except Exception:
                    pass

    if log_callback:
        log_callback(f"🗑️ Đã chuyển {success_count}/{len(items) if items else 1} email trong chuỗi vào thùng rác: '{thread.get('subject')}'")
    return True


def clear_all_threads():
    """Xóa sạch tất cả các thread"""
    init_thread_db()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM email_threads")
        conn.commit()


def process_scanned_emails_for_threads(scanned_emails, config, log_callback=None):
    """
    Phân loại và điều hướng danh sách email vừa quét:
    - Email đơn lẻ (không thuộc thread): Trả về trong `standalone_emails` để xử lý thông thường.
    - Email thuộc Thread: Tự động gom vào `threads.db`, gọi AI tóm tắt cuốn chiếu và trả về bản ghi tóm tắt thread duy nhất để bắn thông báo.
    """
    if not scanned_emails:
        return [], []

    from ai_engines import summarize_thread_rolling_with_ai

    init_thread_db()
    standalone_emails = []
    thread_groups = {}  # thread_key -> {'subject': ..., 'cleaned': ..., 'emails': []}

    # 1. Bóc tách và phân nhóm
    for email in scanned_emails:
        raw_subj = email.get("subject", "")
        thread_key, cleaned_subj, is_reply_or_fwd = normalize_thread_subject(raw_subj)
        
        # Kiểm tra xem thread_key đã tồn tại trong DB chưa
        existing = get_thread_by_key(thread_key) if thread_key else None

        if is_reply_or_fwd or existing:
            # Thuộc chuỗi thread
            if thread_key not in thread_groups:
                thread_groups[thread_key] = {
                    "raw_subject": raw_subj,
                    "cleaned_subject": cleaned_subj or raw_subj,
                    "emails": [],
                    "existing_db": existing
                }
            thread_groups[thread_key]["emails"].append(email)
        else:
            # Tạm thời xem là email đơn lẻ
            if thread_key not in thread_groups:
                thread_groups[thread_key] = {
                    "raw_subject": raw_subj,
                    "cleaned_subject": cleaned_subj or raw_subj,
                    "emails": [],
                    "existing_db": None
                }
            thread_groups[thread_key]["emails"].append(email)

    # 2. Xử lý từng nhóm: Nhóm nào chỉ có 1 email và không có tiền tố Re:/Fwd: và chưa có trong DB -> Standalone email
    thread_notifications = []

    for t_key, t_info in thread_groups.items():
        emails_list = t_info["emails"]
        existing = t_info["existing_db"]
        cleaned_subj = t_info["cleaned_subject"]

        # QUY TẮC PHÂN LOẠI CHUỖI HỘI THOẠI:
        # Chuỗi hội thoại (Thread) CHỈ ĐƯỢC TẠO HOẶC CẬP NHẬT KHI:
        # 1. Đã có thread trong DB trước đó (existing is not None -> email này là phản hồi tiếp theo).
        # 2. Hoặc trong đợt quét hiện tại có từ 2 email trở lên cùng chủ đề (len(emails_list) >= 2).
        # -> Nếu chưa có trong DB VÀ chỉ có 1 email duy nhất: Giữ nguyên là email đơn lẻ (Standalone)!
        if not existing and len(emails_list) < 2:
            standalone_emails.extend(emails_list)
            continue

        # Ngược lại: Đây chính xác là một Thread!
        if log_callback:
            log_callback(f"🧵 Đang xử lý chuỗi hội thoại ({len(emails_list)} email mới): '{cleaned_subj}'")

        old_count = existing["email_count"] if existing else 0
        old_summary = existing["current_summary"] if existing else ""
        new_count = old_count + len(emails_list)

        ai_type = config.get("ai_engine", "Offline")
        api_key = config.get("api_key", "")

        # Thực hiện tóm tắt cuốn chiếu tự động
        updated_summary = summarize_thread_rolling_with_ai(
            ai_type=ai_type,
            api_key=api_key,
            subject=cleaned_subj,
            current_summary=old_summary,
            new_emails=emails_list,
            log_callback=log_callback
        )

        last_email = emails_list[-1]
        last_sender = last_email.get("sender", "")
        last_time = last_email.get("time", datetime.now().strftime("%H:%M %d/%m/%Y"))
        account_name = last_email.get("account_name", "")
        folder = last_email.get("folder", "")

        old_items = []
        if existing and existing.get("email_items"):
            try:
                import json
                old_items = json.loads(existing["email_items"])
            except Exception:
                old_items = []
        combined_items = old_items + emails_list

        # Lưu/Cập nhật vào SQLite threads.db
        save_or_update_thread(
            thread_key=t_key,
            subject=cleaned_subj,
            current_summary=updated_summary,
            email_count=new_count,
            last_updated=last_time,
            account_name=account_name,
            folder=folder,
            last_sender=last_sender,
            email_items=combined_items
        )

        # Tạo thông báo duy nhất cho toàn bộ Thread
        thread_notify_item = {
            "is_thread": True,
            "thread_key": t_key,
            "subject": f"🧵 [Hội thoại] {cleaned_subj}",
            "sender": f"{last_sender} (và {new_count - 1} phản hồi)" if new_count > 1 else last_sender,
            "time": last_time,
            "account_name": account_name,
            "folder": folder,
            "summary": updated_summary,
            "email_count": new_count
        }
        thread_notifications.append(thread_notify_item)

    return standalone_emails, thread_notifications

import os
import sys
import re

# Xác định đường dẫn gốc chuẩn xác (hoạt động tốt cả khi chạy script lẫn file .exe đóng gói)
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Đường dẫn file mô hình Qwen 2.5 - 3B trong thư mục models/
MODEL_PATH = os.path.join(BASE_DIR, "models", "qwen2.5-3b-instruct-q4_k_m.gguf")

# Biến lưu trữ đối tượng mô hình nạp vào RAM (Singleton - nạp 1 lần duy nhất)
_LOCAL_LLM = None

def get_llm():
    """Hàm khởi tạo và nạp mô hình Qwen 2.5 - 3B vào RAM một lần duy nhất"""
    global _LOCAL_LLM
    if _LOCAL_LLM is None and os.path.exists(MODEL_PATH):
        try:
            from llama_cpp import Llama
            # Cấu hình tối ưu chạy mượt trên CPU văn phòng
            _LOCAL_LLM = Llama(
                model_path=MODEL_PATH,
                n_ctx=2048,          # Độ dài ngữ cảnh (đủ xử lý email dài)
                n_threads=4,         # Số luồng CPU sử dụng
                verbose=False        # Tắt in log C++ rác ra console
            )
        except Exception as e:
            print(f"Lỗi khởi tạo mô hình Local AI: {e}")
            _LOCAL_LLM = None
    return _LOCAL_LLM

def summarize_offline(body_text, subject="", sender=""):
    """
    Tóm tắt email Offline:
    1. Ưu tiên dùng Mô hình Qwen 2.5 - 3B Local (.gguf).
    2. Tự động chuyển về thuật toán từ khóa dự phòng nếu file model bị thiếu/lỗi.
    """
    if not body_text or len(body_text.strip()) < 15:
        return "(Không có nội dung)"

    llm = get_llm()

    # --- PHƯƠNG ÁN 1: DÙNG QWEN 2.5 - 3B LOCAL ---
    if llm:
        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Bạn là trợ lý tóm tắt email kỹ thuật viễn thông & CNTT. "
                        "Hãy tóm tắt nội dung email bằng tiếng Việt trong 1-2 câu ngắn gọn, súc tích.\n"
                        "YÊU CẦU QUAN TRỌNG: Giữ nguyên các thông số kỹ thuật cốt lõi nếu có "
                        "(như mã trạm/BTS, địa chỉ IP, mã kênh/tuyến cáp, loại sự cố, thời gian bảo trì/cutover, hạn chót xử lý)."
                    )
                },
                {
                    "role": "user",
                    "content": f"Tiêu đề: {subject}\nNgười gửi: {sender}\nNội dung email:\n{body_text[:3000]}"
                }
            ]
            response = llm.create_chat_completion(
                messages=messages,
                temperature=0.2,
                max_tokens=180
            )
            return response["choices"][0]["message"]["content"].strip()
        except Exception:
            pass  # Nếu có lỗi bất ngờ trong quá trình suy luận -> chuyển sang thuật toán dự phòng

    # --- PHƯƠNG ÁN 2: THUẬT TOÁN TỪ KHÓA DỰ PHÒNG (FALLBACK) ---
    return _extract_keywords_summary(body_text)


def _extract_keywords_summary(body_text):
    """Thuật toán trích xuất câu quan trọng dự phòng khi không có AI LLM"""
    ACTION_KEYWORDS = [
        "đề nghị", "yêu cầu", "nhờ", "kính gửi", "kính chuyển", "báo cáo",
        "phê duyệt", "xem xét", "thông báo", "hạn chót", "deadline", 
        "trước ngày", "gửi lại", "tiến độ", "kế hoạch", "hoàn thành",
        "sự cố", "mất liên lạc", "suy hao", "nghẽn", "cắt chuyển", "cutover",
        "bảo trì", "bts", "ip", "vlan", "voip", "sip", "ticket",
        "please", "urgently", "approved", "review", "due date"
    ]

    lines = [line.strip() for line in body_text.splitlines() if line.strip()]
    valid_lines = []
    
    for line in lines:
        lower_line = line.lower()
        if any(lower_line.startswith(sig) for sig in ["trân trọng", "thanks", "best regards", "thân ái", "--", "sđt:", "tel:"]):
            break
        if len(line.split()) <= 4 and any(lower_line.startswith(g) for g in ["kính gửi", "dear", "chào", "hi"]):
            continue
        valid_lines.append(line)

    clean_text = " ".join(valid_lines)
    sentences = re.split(r'(?<=[.!?\n])\s+', clean_text)
    
    scored_sentences = []
    for idx, sentence in enumerate(sentences):
        st = sentence.strip()
        if len(st) < 15: 
            continue
        score = sum(2 for kw in ACTION_KEYWORDS if kw in st.lower())
        if idx < 3: 
            score += 1
        scored_sentences.append((score, idx, st))

    if not scored_sentences:
        return clean_text[:200] + "..." if len(clean_text) > 200 else clean_text

    scored_sentences.sort(key=lambda x: x[0], reverse=True)
    top_sentences = sorted(scored_sentences[:2], key=lambda x: x[1])
    summary = " ".join([s[2] for s in top_sentences])
    return summary[:400] + ("..." if len(summary) > 400 else "")
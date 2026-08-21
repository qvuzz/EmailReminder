import requests
from offline_ai import summarize_offline

def summarize_with_ai(ai_type, api_key, subject, sender, body, log_callback=None):
    """Tổng đài điều hướng API cho các hãng AI Đám Mây"""
    if not body or len(body.strip()) < 20: 
        return "Nội dung quá ngắn."
    
    # Rẽ nhánh về Local AI nếu không có API Key
    if not api_key: 
        if log_callback:
            log_callback(f"ℹ️ Chưa cấu hình API Key cho {ai_type}, chuyển sang dùng Offline AI.")
        return summarize_offline(body, subject, sender)

    sys_prompt = "Bạn là trợ lý tóm tắt. Hãy tóm tắt email công việc tiếng Việt trong 1-2 câu ngắn gọn, nêu rõ hành động chính."
    user_prompt = f"Tiêu đề: {subject}\nNgười gửi: {sender}\nNội dung: {body[:3000]}"

    try:
        if ai_type == "Gemini":
            return _call_gemini(api_key, sys_prompt, user_prompt)
        
        openai_compatible_configs = {
            "Groq": ("https://api.groq.com/openai/v1/chat/completions", "openai/gpt-oss-120b"),
            "DeepSeek": ("https://api.deepseek.com/chat/completions", "deepseek-chat"),
            "Grok": ("https://api.x.ai/v1/chat/completions", "grok-4.6"),
            "OpenAI": ("https://api.openai.com/v1/chat/completions", "gpt-4o-mini")
        }
        
        if ai_type in openai_compatible_configs:
            url, model = openai_compatible_configs[ai_type]
            return _call_openai_compatible(url, model, api_key, sys_prompt, user_prompt)

        # Trả về Offline nếu tên AI lạ
        return summarize_offline(body, subject, sender)

    except Exception as e:
        err_msg = str(e)
        if log_callback:
            log_callback(f"⚠️ Lỗi gọi {ai_type} API: {err_msg}")
        return f"[Lỗi {ai_type}: {err_msg} -> Dùng tạm Offline]: {summarize_offline(body, subject, sender)}"

def summarize_thread_rolling_with_ai(ai_type, api_key, subject, current_summary, new_emails, log_callback=None):
    """
    Tóm tắt cuốn chiếu chuỗi hội thoại email (Email Thread Rolling Summarization).
    Kết hợp [Bản tóm tắt cũ] + [Các email mới phát sinh] để cập nhật tổng quan, diễn biến và action items.
    """
    if not new_emails:
        return current_summary or "Chưa có nội dung tóm tắt."

    sys_prompt = (
        "Bạn là trợ lý AI chuyên tổng hợp và cập nhật chuỗi hội thoại email công việc (Email Thread).\n"
        "Nhiệm vụ: Hãy phân tích [BẢN TÓM TẮT TRƯỚC ĐÓ] và [CÁC EMAIL MỚI PHÁT SINH] để đưa ra MỘT bản tóm tắt cuốn chiếu cập nhật toàn diện, ngắn gọn (3-5 câu) bằng tiếng Việt gồm:\n"
        "1. 📌 Vụ việc/Sự cố: Tóm tắt ngắn gọn nguồn gốc sự việc.\n"
        "2. ⚡ Diễn biến mới nhất: Diễn biến quan trọng từ các email phản hồi gần nhất.\n"
        "3. ✅ Trạng thái & Hành động: Trạng thái hiện tại (Đang xử lý / Đã khắc phục / Chờ phản hồi) và ai cần làm gì tiếp theo."
    )

    prompt_parts = [
        f"Chuỗi email: {subject}",
        f"\n[BẢN TÓM TẮT TRƯỚC ĐÓ]:\n{current_summary if current_summary else '(Đây là chuỗi email mới bắt đầu tổng hợp)'}",
        "\n[CÁC EMAIL MỚI PHÁT SINH TRONG CHUỖI]:"
    ]

    for i, e in enumerate(new_emails, 1):
        sender = e.get("sender", "Người gửi")
        time_str = e.get("time", "")
        body_snippet = e.get("body", "")[:1200]
        if not body_snippet and e.get("summary"):
            body_snippet = e.get("summary")
        prompt_parts.append(f"Email {i} - Gửi bởi: {sender} lúc {time_str}\nNội dung: {body_snippet}")

    user_prompt = "\n".join(prompt_parts)

    if "Offline" in ai_type or not api_key:
        if log_callback:
            log_callback(f"ℹ️ Đang tóm tắt cuốn chiếu Thread bằng Offline AI...")
        combined_body = f"{current_summary}\n" + "\n".join([e.get('body', '')[:600] for e in new_emails])
        return summarize_offline(combined_body, subject, new_emails[-1].get("sender", ""))

    try:
        if ai_type == "Gemini":
            return _call_gemini(api_key, sys_prompt, user_prompt)

        openai_compatible_configs = {
            "Groq": ("https://api.groq.com/openai/v1/chat/completions", "openai/gpt-oss-120b"),
            "DeepSeek": ("https://api.deepseek.com/chat/completions", "deepseek-chat"),
            "Grok": ("https://api.x.ai/v1/chat/completions", "grok-4.6"),
            "OpenAI": ("https://api.openai.com/v1/chat/completions", "gpt-4o-mini")
        }

        if ai_type in openai_compatible_configs:
            url, model = openai_compatible_configs[ai_type]
            return _call_openai_compatible(url, model, api_key, sys_prompt, user_prompt)

        return summarize_offline(user_prompt, subject, new_emails[-1].get("sender", ""))

    except Exception as e:
        err_msg = str(e)
        if log_callback:
            log_callback(f"⚠️ Lỗi tóm tắt cuốn chiếu qua {ai_type}: {err_msg}")
        combined_body = f"{current_summary}\n" + "\n".join([e.get('body', '')[:600] for e in new_emails])
        return summarize_offline(combined_body, subject, new_emails[-1].get("sender", ""))

def _call_openai_compatible(url, model, api_key, sys_prompt, prompt):
    headers = {"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": prompt}],
        "temperature": 0.2, "max_tokens": 300
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=20)
    if resp.status_code != 200:
        try:
            err_data = resp.json()
            err_detail = err_data.get("error", {}).get("message") if isinstance(err_data.get("error"), dict) else err_data.get("error") or resp.text
        except Exception:
            err_detail = resp.text
        raise RuntimeError(f"HTTP {resp.status_code} ({err_detail})")
        
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()

def _get_gemini_models(api_key):
    """Tự động hỏi Google danh sách model mà API Key này được phép dùng"""
    models = []
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key.strip()}"
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            for m in data.get("models", []):
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" in methods:
                    name = m.get("name", "").replace("models/", "")
                    if name:
                        models.append(name)
    except Exception:
        pass

    if models:
        # Sắp xếp ưu tiên: flash trước -> pro tiếp theo -> các model khác
        flash_models = [m for m in models if "flash" in m.lower()]
        pro_models = [m for m in models if "pro" in m.lower() and "flash" not in m.lower()]
        other_models = [m for m in models if m not in flash_models and m not in pro_models]
        return flash_models + pro_models + other_models

    # Fallback danh sách cố định nếu không query được list models
    return [
        "gemini-1.5-flash",
        "gemini-1.5-flash-latest",
        "gemini-1.5-flash-8b",
        "gemini-2.0-flash",
        "gemini-1.5-pro",
        "gemini-1.5-pro-latest",
        "gemini-pro"
    ]

def _call_gemini(api_key, sys_prompt, prompt):
    candidate_models = _get_gemini_models(api_key)
    last_err = None

    for model_name in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key.strip()}"
        payload = {
            "system_instruction": {"parts": [{"text": sys_prompt}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 1000
            }
        }
        try:
            resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                if "candidates" in data and data["candidates"] and "content" in data["candidates"][0]:
                    parts = data["candidates"][0]["content"].get("parts", [])
                    if parts and "text" in parts[0]:
                        return parts[0]["text"].strip()
                raise ValueError("Gemini trả về cấu trúc rỗng.")

            try:
                err_data = resp.json()
                err_detail = err_data.get("error", {}).get("message") or resp.text
            except Exception:
                err_detail = resp.text

            last_err = f"HTTP {resp.status_code} ({err_detail})"

            # Nếu lỗi sai API Key (400 Invalid key hoặc 403 Forbidden) thì ngắt ngay
            if "API key not valid" in err_detail or "API_KEY_INVALID" in err_detail or resp.status_code == 403:
                break

        except Exception as e:
            last_err = str(e)

    raise RuntimeError(last_err or "Không thể kết nối tới Google Gemini API.")
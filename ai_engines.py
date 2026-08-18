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

def _call_gemini(api_key, sys_prompt, prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key.strip()}"
    payload = {
        "system_instruction": {"parts": [{"text": sys_prompt}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1000,
            "thinkingConfig": {"thinkingBudget": 0}
        }
    }
    resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=20)
    if resp.status_code != 200:
        try:
            err_data = resp.json()
            err_detail = err_data.get("error", {}).get("message") or resp.text
        except Exception:
            err_detail = resp.text
        raise RuntimeError(f"HTTP {resp.status_code} ({err_detail})")

    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()
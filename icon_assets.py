"""
icon_assets.py - High-DPI Vector Icon Generator & Cache for eMail Assistant
Renders Lucide-style modern minimalist 2px-stroke icons with anti-aliasing via PIL & CTkImage.
"""

from PIL import Image, ImageDraw
import customtkinter as ctk

_ICON_CACHE = {}

def get_icon(name: str, size: int = 16, color: str = "#475569", color_dark: str = None) -> ctk.CTkImage:
    """
    Trả về đối tượng CTkImage chứa icon vector sắc nét chuẩn Retina/4K.
    name: 'search', 'refresh', 'sort', 'mail', 'mail_open', 'check', 'check_circle',
          'copy', 'trash', 'play', 'stop', 'eye', 'sparkles', 'plus', 'x', 'folder',
          'user', 'dashboard', 'threads', 'settings', 'help', 'bell', 'save'
    """
    key = (name, size, color, color_dark or color)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]

    img_light = _draw_icon(name, size, color)
    if color_dark and color_dark != color:
        img_dark = _draw_icon(name, size, color_dark)
        ctk_img = ctk.CTkImage(light_image=img_light, dark_image=img_dark, size=(size, size))
    else:
        ctk_img = ctk.CTkImage(light_image=img_light, dark_image=img_light, size=(size, size))

    _ICON_CACHE[key] = ctk_img
    return ctk_img


def _draw_icon(name: str, size: int, color_hex: str) -> Image.Image:
    # Vẽ trên canvas 4x để khử răng cưa (supersampling anti-aliasing) siêu mượt
    scale = 4
    canvas_size = size * scale
    img = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Stroke width tương đương 1.6px ~ 2px ở kích thước gốc
    w = max(int(round(1.8 * scale)), 2)
    s = canvas_size
    pad = int(round(0.12 * s))

    def _rgb(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    col = _rgb(color_hex) if color_hex.startswith("#") and len(color_hex) == 7 else (71, 85, 105)

    if name == "search":
        # Kính lúp (Vòng tròn + Cán chéo)
        r = int(s * 0.32)
        cx, cy = int(s * 0.42), int(s * 0.42)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=w)
        # Cán kính lúp
        x1, y1 = int(cx + r * 0.707), int(cy + r * 0.707)
        x2, y2 = int(s * 0.86), int(s * 0.86)
        draw.line([x1, y1, x2, y2], fill=col, width=int(w * 1.2), joint="round")

    elif name == "refresh":
        # 2 mũi tên xoay tròn (Refresh-cw)
        box = [pad, pad, s - pad, s - pad]
        draw.arc(box, start=30, end=150, fill=col, width=w)
        draw.arc(box, start=210, end=330, fill=col, width=w)
        # Đầu mũi tên 1 (trên)
        draw.polygon([(s - pad - int(3*scale), pad - int(2*scale)), 
                      (s - pad + int(5*scale), pad + int(1*scale)), 
                      (s - pad - int(1*scale), pad + int(7*scale))], fill=col)
        # Đầu mũi tên 2 (dưới)
        draw.polygon([(pad + int(3*scale), s - pad + int(2*scale)), 
                      (pad - int(5*scale), s - pad - int(1*scale)), 
                      (pad + int(1*scale), s - pad - int(7*scale))], fill=col)

    elif name == "sort":
        # 2 mũi tên lên xuống đối xứng
        mid_l = int(s * 0.38)
        mid_r = int(s * 0.62)
        top = pad + int(2*scale)
        bot = s - pad - int(2*scale)
        # Mũi tên lên
        draw.line([(mid_l, bot), (mid_l, top)], fill=col, width=w)
        draw.line([(mid_l - int(4*scale), top + int(4*scale)), (mid_l, top), (mid_l + int(4*scale), top + int(4*scale))], fill=col, width=w, joint="round")
        # Mũi tên xuống
        draw.line([(mid_r, top), (mid_r, bot)], fill=col, width=w)
        draw.line([(mid_r - int(4*scale), bot - int(4*scale)), (mid_r, bot), (mid_r + int(4*scale), bot - int(4*scale))], fill=col, width=w, joint="round")

    elif name in ("mail", "mail_open"):
        # Phong bì thư
        top = int(s * 0.26)
        bot = int(s * 0.74)
        left = pad
        right = s - pad
        draw.rounded_rectangle([left, top, right, bot], radius=int(3*scale), outline=col, width=w)
        # Nắp phong bì
        mid_x = s // 2
        mid_y = int(s * 0.52)
        draw.line([(left, top), (mid_x, mid_y), (right, top)], fill=col, width=w, joint="round")

    elif name == "check":
        # Tích chữ V
        draw.line([(int(s * 0.22), int(s * 0.52)), 
                   (int(s * 0.44), int(s * 0.74)), 
                   (int(s * 0.78), int(s * 0.30))], fill=col, width=int(w * 1.2), joint="round")

    elif name == "check_circle":
        # Vòng tròn có tích chữ V bên trong
        draw.ellipse([pad, pad, s - pad, s - pad], outline=col, width=w)
        draw.line([(int(s * 0.30), int(s * 0.52)), 
                   (int(s * 0.46), int(s * 0.68)), 
                   (int(s * 0.70), int(s * 0.36))], fill=col, width=int(w * 1.1), joint="round")

    elif name == "copy":
        # 2 trang giấy chồng
        off = int(4 * scale)
        # Tờ phía sau
        draw.rounded_rectangle([pad + off, pad, s - pad, s - pad - off], radius=int(2.5*scale), outline=col, width=w)
        # Tờ phía trước
        draw.rounded_rectangle([pad, pad + off, s - pad - off, s - pad], radius=int(2.5*scale), fill=(255, 255, 255, 0), outline=col, width=w)

    elif name == "trash":
        # Thùng rác hiện đại
        top_y = int(s * 0.28)
        draw.line([(int(s * 0.18), top_y), (int(s * 0.82), top_y)], fill=col, width=w) # Miệng thùng
        draw.line([(int(s * 0.38), top_y), (int(s * 0.38), int(s * 0.20)), 
                   (int(s * 0.62), int(s * 0.20)), (int(s * 0.62), top_y)], fill=col, width=w) # Quai thùng
        # Thân thùng
        draw.line([(int(s * 0.26), top_y), (int(s * 0.30), int(s * 0.80)), 
                   (int(s * 0.70), int(s * 0.80)), (int(s * 0.74), top_y)], fill=col, width=w, joint="round")
        # 2 sọc dọc trong thùng
        draw.line([(int(s * 0.42), int(s * 0.38)), (int(s * 0.42), int(s * 0.70))], fill=col, width=int(w * 0.9))
        draw.line([(int(s * 0.58), int(s * 0.38)), (int(s * 0.58), int(s * 0.70))], fill=col, width=int(w * 0.9))

    elif name == "play":
        # Tam giác Play viền bo
        draw.polygon([(int(s * 0.32), int(s * 0.22)), 
                      (int(s * 0.78), int(s * 0.50)), 
                      (int(s * 0.32), int(s * 0.78))], fill=col)

    elif name == "stop":
        # Hình vuông Stop bo góc
        draw.rounded_rectangle([int(s * 0.26), int(s * 0.26), int(s * 0.74), int(s * 0.74)], radius=int(2*scale), fill=col)

    elif name == "eye":
        # Con mắt
        cx, cy = s // 2, s // 2
        # Cung trên & dưới
        draw.arc([pad, int(s * 0.20), s - pad, int(s * 0.80)], start=30, end=150, fill=col, width=w)
        draw.arc([pad, int(s * 0.20), s - pad, int(s * 0.80)], start=210, end=330, fill=col, width=w)
        # Đồng tử
        r = int(s * 0.15)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)

    elif name == "sparkles":
        # Tia sáng / Gợi ý thông minh (4 cánh)
        cx, cy = s // 2, s // 2
        draw.line([(cx, pad), (cx, s - pad)], fill=col, width=w)
        draw.line([(pad, cy), (s - pad, cy)], fill=col, width=w)
        d = int(s * 0.22)
        draw.line([(cx - d, cy - d), (cx + d, cy + d)], fill=col, width=int(w * 0.8))
        draw.line([(cx - d, cy + d), (cx + d, cy - d)], fill=col, width=int(w * 0.8))

    elif name == "plus":
        # Dấu cộng mảnh
        cx, cy = s // 2, s // 2
        draw.line([(cx, pad + int(2*scale)), (cx, s - pad - int(2*scale))], fill=col, width=w)
        draw.line([(pad + int(2*scale), cy), (s - pad - int(2*scale), cy)], fill=col, width=w)

    elif name == "x":
        # Dấu X chéo
        p = pad + int(2*scale)
        draw.line([(p, p), (s - p, s - p)], fill=col, width=w)
        draw.line([(p, s - p), (s - p, p)], fill=col, width=w)

    elif name == "folder":
        # Thư mục
        left, top, right, bot = pad, int(s * 0.28), s - pad, int(s * 0.78)
        # Tab thư mục
        draw.polygon([(left, top), (left + int(s * 0.35), top), 
                      (left + int(s * 0.45), top + int(s * 0.12)), 
                      (right, top + int(s * 0.12)), (right, bot), (left, bot)], outline=col, fill=(255, 255, 255, 0))
        draw.line([(left, top + int(s * 0.12)), (right, top + int(s * 0.12))], fill=col, width=w)

    elif name == "dashboard":
        # 4 ô vuông grid
        g = int(3*scale)
        mid_x, mid_y = s // 2, s // 2
        draw.rounded_rectangle([pad, pad, mid_x - g, mid_y - g], radius=int(2*scale), outline=col, width=w)
        draw.rounded_rectangle([mid_x + g, pad, s - pad, mid_y - g], radius=int(2*scale), outline=col, width=w)
        draw.rounded_rectangle([pad, mid_y + g, mid_x - g, s - pad], radius=int(2*scale), outline=col, width=w)
        draw.rounded_rectangle([mid_x + g, mid_y + g, s - pad, s - pad], radius=int(2*scale), outline=col, width=w)

    elif name == "threads":
        # 2 bong bóng hội thoại lồng
        draw.rounded_rectangle([pad, pad, int(s * 0.68), int(s * 0.62)], radius=int(3*scale), outline=col, width=w)
        draw.rounded_rectangle([int(s * 0.32), int(s * 0.38), s - pad, s - pad], radius=int(3*scale), outline=col, width=w)

    elif name == "settings":
        # Bánh răng cài đặt
        cx, cy = s // 2, s // 2
        r_out = int(s * 0.36)
        r_in = int(s * 0.18)
        draw.ellipse([cx - r_out, cy - r_out, cx + r_out, cy + r_out], outline=col, width=w)
        draw.ellipse([cx - r_in, cy - r_in, cx + r_in, cy + r_in], outline=col, width=w)
        # Các răng
        for angle in (0, 45, 90, 135):
            draw.line([(cx - r_out - int(2*scale), cy), (cx + r_out + int(2*scale), cy)], fill=col, width=w)

    elif name == "help":
        # Vòng tròn dấu hỏi
        draw.ellipse([pad, pad, s - pad, s - pad], outline=col, width=w)
        cx = s // 2
        # Dấu hỏi
        draw.arc([int(s * 0.35), int(s * 0.25), int(s * 0.65), int(s * 0.50)], start=180, end=0, fill=col, width=w)
        draw.line([(cx, int(s * 0.50)), (cx, int(s * 0.60))], fill=col, width=w)
        draw.ellipse([cx - int(1.5*scale), int(s * 0.70), cx + int(1.5*scale), int(s * 0.70) + int(3*scale)], fill=col)

    elif name == "save":
        # Đĩa mềm lưu
        draw.rounded_rectangle([pad, pad, s - pad, s - pad], radius=int(3*scale), outline=col, width=w)
        # Khe cửa trượt
        draw.rectangle([int(s * 0.32), pad, int(s * 0.68), int(s * 0.44)], outline=col, width=w)
        # Ô nhãn bên dưới
        draw.rectangle([int(s * 0.28), int(s * 0.56), int(s * 0.72), s - pad], outline=col, width=w)

    else:
        # Default circle
        draw.ellipse([pad, pad, s - pad, s - pad], outline=col, width=w)

    # Downsample về kích thước chuẩn với bộ lọc Lanczos chất lượng cao nhất
    return img.resize((size, size), Image.Resampling.LANCZOS)

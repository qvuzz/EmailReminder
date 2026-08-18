from PIL import Image, ImageDraw

def create_app_icon():
    size = (512, 512)
    # Tạo nền trong suốt
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Vẽ khung nền Gradient Bo Góc (Xanh dương sang Xanh đậm)
    x0, y0, x1, y1 = 40, 40, 472, 472
    radius = 110
    
    # Tạo lớp gradient
    gradient = Image.new("RGBA", size, (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(gradient)
    for y in range(size[1]):
        r = int(24 + (15 - 24) * (y / size[1]))
        g = int(119 + (75 - 119) * (y / size[1]))
        b = int(242 + (180 - 242) * (y / size[1]))
        g_draw.line([(0, y), (size[0], y)], fill=(r, g, b, 255))
    
    # Tạo mặt nạ bo tròn (Rounded mask)
    mask = Image.new("L", size, 0)
    m_draw = ImageDraw.Draw(mask)
    m_draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=255)
    
    # Áp nền gradient qua mặt nạ
    img.paste(gradient, (0, 0), mask)
    
    # Vẽ lại viền nhẹ cho nền
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, outline=(255, 255, 255, 50), width=4)

    # 2. Vẽ Phong bì thư (Màu trắng ngọc)
    env_x0, env_y0, env_x1, env_y1 = 110, 160, 402, 360
    env_radius = 24
    
    # Thân phong bì
    draw.rounded_rectangle([env_x0, env_y0, env_x1, env_y1], radius=env_radius, fill=(245, 247, 250, 255))
    
    # Nếp gấp phong bì (Tam giác trên)
    flap_top = [(env_x0, env_y0 + 10), (256, 275), (env_x1, env_y0 + 10)]
    draw.polygon(flap_top, fill=(230, 235, 243, 255))
    draw.line([(env_x0, env_y0 + 10), (256, 275)], fill=(195, 205, 218, 255), width=6)
    draw.line([(env_x1, env_y0 + 10), (256, 275)], fill=(195, 205, 218, 255), width=6)

    # Nếp gấp hai bên dưới
    draw.line([(env_x0 + 5, env_y1 - 5), (220, 250)], fill=(215, 225, 236, 255), width=5)
    draw.line([(env_x1 - 5, env_y1 - 5), (292, 250)], fill=(215, 225, 236, 255), width=5)

    # 3. Vẽ Chấm thông báo nổi bật (Màu Cam / Đỏ biểu thị Reminder & AI Alert)
    badge_center = (395, 125)
    badge_r = 46
    
    # Viền trắng quanh chấm thông báo
    draw.ellipse([
        (badge_center[0] - badge_r - 6, badge_center[1] - badge_r - 6),
        (badge_center[0] + badge_r + 6, badge_center[1] + badge_r + 6)
    ], fill=(255, 255, 255, 255))
    
    # Thân chấm màu cam dạ quang
    draw.ellipse([
        (badge_center[0] - badge_r, badge_center[1] - badge_r),
        (badge_center[0] + badge_r, badge_center[1] + badge_r)
    ], fill=(255, 94, 58, 255))
    
    # Biểu tượng tia chớp nhỏ ở giữa chấm (biểu thị tốc độ / AI)
    lightning = [
        (398, 95), (378, 125), (394, 125), 
        (392, 155), (412, 120), (398, 120)
    ]
    draw.polygon(lightning, fill=(255, 255, 255, 255))

    # 4. Xuất file ảnh PNG và file ICO đầy đủ các kích thước chuẩn Windows
    img.save("app_icon.png", format="PNG")
    
    icon_sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    img.save("app_icon.ico", format="ICO", sizes=icon_sizes)
    print("✅ Đã tạo thành công file 'app_icon.ico' và 'app_icon.png'!")

if __name__ == "__main__":
    create_app_icon()
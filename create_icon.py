import os
import math
from PIL import Image, ImageDraw

def generate_jarvis_icon():
    size = (256, 256)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = 128, 128

    # Outer dark titanium rim
    draw.ellipse([10, 10, 246, 246], fill="#080c14", outline="#00e5ff", width=6)
    draw.ellipse([26, 26, 230, 230], fill="#05080e", outline="#0077b6", width=2)

    # 10 Arc Reactor copper coils
    num_coils = 10
    r_coils = 86
    for i in range(num_coils):
        angle = i * (2 * math.pi / num_coils)
        x1 = cx + math.cos(angle) * (r_coils - 14)
        y1 = cy + math.sin(angle) * (r_coils - 14)
        x2 = cx + math.cos(angle) * (r_coils + 14)
        y2 = cy + math.sin(angle) * (r_coils + 14)
        draw.line([x1, y1, x2, y2], fill="#00e5ff", width=6)

    # Inner magnetic field ring
    draw.ellipse([64, 64, 192, 192], fill="#0a1128", outline="#00e5ff", width=4)

    # Glowing plasma core
    draw.ellipse([92, 92, 164, 164], fill="#00e5ff", outline="#ffffff", width=4)
    draw.ellipse([110, 110, 146, 146], fill="#ffffff")

    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    os.makedirs(assets_dir, exist_ok=True)
    
    png_path = os.path.join(assets_dir, "buddy_icon.png")
    ico_path = os.path.join(assets_dir, "buddy_icon.ico")
    
    img.save(png_path, format="PNG")
    img.save(ico_path, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print(f"[*] J.A.R.V.I.S. Arc Reactor Icon generated at {ico_path}")

def generate_buddy_icon():
    return generate_jarvis_icon()

if __name__ == "__main__":
    generate_jarvis_icon()


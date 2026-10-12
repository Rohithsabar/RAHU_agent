from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)

image = Image.new("RGBA", (512, 512), "#102a43")
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((16, 16, 496, 496), radius=112, fill="#102a43")
font_candidates = [
    Path("C:/Windows/Fonts/arialbd.ttf"),
    Path("C:/Windows/Fonts/segoeuib.ttf"),
]
font_path = next((path for path in font_candidates if path.exists()), None)
font = ImageFont.truetype(str(font_path), 330) if font_path else ImageFont.load_default()
draw.text((84, 52), "R", font=font, fill="#f6fbff", stroke_width=0)
draw.ellipse((382, 74, 460, 152), fill="#35c49a")

image.save(ASSETS / "rahu.png")
image.save(
    ASSETS / "rahu.ico",
    format="ICO",
    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)
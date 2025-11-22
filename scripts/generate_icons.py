from __future__ import annotations

import io
from pathlib import Path


def _gen_png(size: int) -> bytes:
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore

        img = Image.new("RGBA", (size, size), (11, 11, 11, 255))
        draw = ImageDraw.Draw(img)
        r = size // 2 - max(4, size // 10)
        draw.ellipse([(size//2 - r, size//2 - r), (size//2 + r, size//2 + r)], fill=(0, 200, 120, 255))
        txt = "IVY"
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
        if font:
            tw, th = draw.textsize(txt, font=font)
            draw.text(((size - tw)//2, (size - th)//2), txt, fill=(0,0,0,255), font=font)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        # 1x1 PNG fallback
        return bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c6360000002000100ffff03000006000557bf2a0000000049454e44ae426082"
        )


def main() -> None:
    pub = Path("webui/public")
    pub.mkdir(parents=True, exist_ok=True)
    p192 = pub / "icon-192.png"
    p512 = pub / "icon-512.png"
    fav = pub / "favicon.ico"
    if not p192.exists():
        p192.write_bytes(_gen_png(192))
    if not p512.exists():
        p512.write_bytes(_gen_png(512))
    if not fav.exists():
        try:
            from PIL import Image  # type: ignore

            img = Image.open(io.BytesIO(_gen_png(64)))
            buf = io.BytesIO()
            img.save(buf, format="ICO")
            fav.write_bytes(buf.getvalue())
        except Exception:
            fav.write_bytes(_gen_png(32))


if __name__ == "__main__":
    main()


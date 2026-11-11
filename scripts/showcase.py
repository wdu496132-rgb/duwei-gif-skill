import argparse
from bisect import bisect_right
from itertools import accumulate
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont, ImageSequence

WIDTH, HEIGHT, FPS = 1080, 1920, 60
COLORS = (
    "#F8E9E7", "#EEE8FA", "#E6F2EB", "#E9EDFA", "#ECE2FA",
    "#F9E9EF", "#E5F0F9", "#F5EDDD", "#EEE8F7",
)


def decode(path, background):
    images, timing = [], []
    with Image.open(path) as gif:
        for frame in ImageSequence.Iterator(gif):
            sprite = frame.convert("RGBA").resize((273,273), Image.Resampling.LANCZOS)
            flat = Image.new("RGB", sprite.size, background)
            flat.paste(sprite, mask=sprite.getchannel("A"))
            images.append(flat)
            duration = frame.info.get("duration")
            if duration is None or duration <= 0:
                raise ValueError(f"Missing frame duration in {path}")
            timing.append(duration)
    if len(images) < 2:
        raise ValueError(f"Expected an animated GIF at {path}")
    return images, list(accumulate(timing))


def render(manifest, dest, regular_font, bold_font):
    config = json.loads(manifest.read_text(encoding="utf-8"))
    entries = config["items"]
    if len(entries) not in (8, 9):
        raise ValueError("Showcase requires eight (2×4) or nine (3×3) GIFs")
    duration = float(config.get("seconds", 8))
    if not 1 <= duration <= 60:
        raise ValueError("Set a video duration from 1 to 60 seconds")
    regular = ImageFont.truetype(regular_font, 33, index=2 if regular_font.endswith(".ttc") else 0)
    bold = ImageFont.truetype(bold_font, 78, index=2 if bold_font.endswith(".ttc") else 0)
    base = Image.new("RGB", (WIDTH,HEIGHT), "#F8F5FC")
    draw = ImageDraw.Draw(base)
    draw.rounded_rectangle((485,210,595,219), radius=5, fill="#AA88CD")
    draw.text((540,294), config.get("title","角色 Q 版动图"), font=bold, fill="#302644", anchor="mm")
    draw.text((540,385), config.get("subtitle",f"{len(entries)} 个角色的招牌动作"),
              font=regular, fill="#6B5C80", anchor="mm")
    tiles = []
    for index, (entry, color) in enumerate(zip(entries, COLORS)):
        if len(entries) == 8:
            x, y = 64+(index%2)*486, 450+(index//2)*345
            tile_width = 452
            image_x = x + (tile_width-273)//2
        else:
            x, y = 64+(index%3)*326, 472+(index//3)*351
            tile_width = 299
            image_x = x + 13
        draw.rounded_rectangle((x,y,x+tile_width,y+323), radius=30, fill=color)
        draw.text((x+tile_width//2,y+292), entry["name"], font=regular, fill="#524365", anchor="mm")
        images, ends = decode(manifest.parent / entry["gif"], color)
        tiles.append(((image_x,y+1),images,ends))
    dest.parent.mkdir(parents=True, exist_ok=True)
    draft = dest.with_name(f"{dest.stem}.partial.mp4")
    command = [
        "ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pixel_format", "rgb24",
        "-video_size", f"{WIDTH}x{HEIGHT}", "-framerate", str(FPS), "-i", "-",
        "-an", "-c:v", "libx264", "-threads", "4", "-preset", "fast", "-crf", "17",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(draft),
    ]
    previous = ()
    try:
        with subprocess.Popen(command, stdin=subprocess.PIPE) as encoder:
            with encoder.stdin as pipe:
                for frame in range(round(duration*FPS)):
                    ms = frame*1000/FPS
                    indices = tuple(bisect_right(ends, ms % ends[-1]) for _,_,ends in tiles)
                    if indices != previous:
                        composite = base.copy()
                        for index, (position, images, _) in zip(indices, tiles):
                            composite.paste(images[index], position)
                        pixels = composite.tobytes()
                        previous = indices
                    pipe.write(pixels)
            if encoder.wait():
                raise RuntimeError("FFmpeg video encoding failed")
        subprocess.run(["ffmpeg","-v","error","-xerror","-i",str(draft),"-f","null","-"],check=True)
        draft.replace(dest)
    finally:
        draft.unlink(missing_ok=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description="Render eight or nine character GIFs as an opaque 9:16 MP4.")
    cli.add_argument("manifest", type=Path)
    cli.add_argument("output", type=Path)
    font_dir = "/usr/share/fonts/opentype/noto"
    cli.add_argument("--regular-font", default=f"{font_dir}/NotoSansCJK-Regular.ttc")
    cli.add_argument("--bold-font", default=f"{font_dir}/NotoSansCJK-Bold.ttc")
    args = cli.parse_args()
    if args.output.suffix.lower() != ".mp4":
        cli.error("Choose an .mp4 output")
    render(args.manifest, args.output, args.regular_font, args.bold_font)

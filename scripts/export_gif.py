import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageColor, ImageSequence

from motion import flow, grid, sample

def interpolate(a, b, forward, backward, phase):
    y, x = grid(a.shape[1])
    dy = (1-phase)*backward[0] - phase*forward[0]
    dx = (1-phase)*backward[1] - phase*forward[1]
    left = np.stack([sample(channel, y+phase*dy, x+phase*dx) for channel in a], axis=-1)
    right = np.stack([sample(channel, y-(1-phase)*dy, x-(1-phase)*dx) for channel in b], axis=-1)
    left_alpha, right_alpha = left[:, :, 3:], right[:, :, 3:]
    # Compare opaque color only where both drawings have visible pixels.
    color_error = np.max(abs(right[:,:,:3]-left[:,:,:3]), axis=-1, keepdims=True)
    error = np.maximum(abs(left_alpha-right_alpha), color_error)
    confidence = np.clip((error-16)/54, 0, 1)
    bias = phase**7 / (phase**7 + (1-phase)**7)
    weight = phase + confidence*(bias-phase)
    mixed = left*(1-weight) + right*weight
    alpha = mixed[:,:,3:]
    rgb = mixed[:,:,:3]*255/np.maximum(alpha,1)
    visible = alpha >= 125
    rgba = np.concatenate([np.where(visible,rgb,0), visible*255], axis=-1)
    return Image.fromarray(np.uint8(np.clip(rgba+.5,0,255)))

def make_frames(originals):
    flattened = []
    premultiplied = []
    for image in originals:
        on_gray = Image.new("RGB", image.size, "#ece8f2")
        on_gray.paste(image, mask=image.getchannel("A"))
        flattened.append(on_gray)
        array = np.asarray(image, dtype=np.float32).transpose(2,0,1).copy()
        array[:3] *= array[3:4] / 255
        premultiplied.append(array)
    result = []
    for index, pose in enumerate(originals):
        next_index = (index+1) % len(originals)
        a, b = flattened[index], flattened[next_index]
        forward, backward = flow(a,b), flow(b,a)
        result.append(pose)
        for phase in (.25, .5, .75):
            result.append(interpolate(premultiplied[index], premultiplied[next_index], forward, backward, phase))
    return result

def encode(frames, path, milliseconds, background=None):
    matte = background or "#ece8f2"
    sheet = Image.new("RGB", (1024, 1024), matte)
    for index, frame in enumerate(frames):
        thumb = frame.resize((128,128),Image.Resampling.LANCZOS)
        sheet.paste(thumb, (128*(index%8),128*(index//8)), thumb)
    palette = sheet.quantize(colors=254, method=Image.Quantize.MEDIANCUT)
    encoded = []
    for frame in frames:
        alpha = frame.getchannel("A")
        flat = Image.new("RGB", frame.size, matte)
        flat.paste(frame, mask=alpha)
        quantized = flat.quantize(palette=palette, dither=Image.Dither.NONE)
        if background is None:
            quantized.paste(255, mask=alpha.point(lambda a: 255-a))
        encoded.append(quantized)
    durations = action_timing(milliseconds)
    transparency = {"transparency": 255} if background is None else {}
    encoded[0].save(path, save_all=True, append_images=encoded[1:], duration=durations,
                    loop=0, disposal=2, optimize=False, **transparency)

def action_timing(milliseconds):
    # Give the wind-up and settle a little more time than the action itself.
    key_pose_weights = [11,10,10,9,8,8,7,7,8,9,10,10,10,10,10,11]
    weights = np.repeat(key_pose_weights,4)
    edges = np.round(np.concatenate(([0],np.cumsum(weights))) * (milliseconds/10) / weights.sum())
    return (np.diff(edges).astype(int)*10).tolist()
def extract(path):
    atlas = Image.open(path).convert("RGBA")
    width, height = atlas.size
    cells = []
    for row in range(4):
        for col in range(4):
            box = (col*width//4,row*height//4,(col+1)*width//4,(row+1)*height//4)
            crop = atlas.crop(box).resize((width//4,height//4),Image.Resampling.LANCZOS)
            pixels = np.asarray(crop)
            alpha = pixels[:,:,3]
            if np.median(alpha[:10,:10]) > 160:
                rgb = pixels[:,:,:3]
                mask = (alpha>=180) & ~((rgb.min(axis=2)>232)&(np.ptp(rgb,axis=2)<12))
            else:
                mask = alpha>=140
            crop.putalpha(Image.fromarray(np.uint8(mask)*255))
            cells.append(crop)
    boxes = [cell.getbbox() for cell in cells]
    assert all(boxes), path
    union = (min(b[0] for b in boxes), min(b[1] for b in boxes),
             max(b[2] for b in boxes), max(b[3] for b in boxes))
    w,h = union[2]-union[0],union[3]-union[1]
    fit = 442/max(w,h)
    shape = round(w*fit),round(h*fit)
    origins = ((512-shape[0])//2,(512-shape[1])//2)
    result = []
    for cell in cells:
        frame = Image.new("RGBA",(512,512))
        frame.alpha_composite(cell.crop(union).resize(shape,Image.Resampling.LANCZOS),origins)
        frame.putalpha(frame.getchannel("A").point(lambda a:255 if a>=128 else 0))
        result.append(frame)
    return result


def verify(path, milliseconds, size, transparent):
    with Image.open(path) as gif:
        if gif.size != (size, size) or gif.n_frames != 64 or gif.info.get("loop") != 0:
            raise ValueError("Expected a square 64-frame looping GIF")
        distinct = set()
        duration = 0
        for frame in ImageSequence.Iterator(gif):
            rgba = frame.convert("RGBA")
            alpha = rgba.getchannel("A")
            expected_alpha = (0, 255) if transparent else (255, 255)
            if alpha.getextrema() != expected_alpha:
                raise ValueError("Frame alpha does not match the requested background")
            if transparent:
                x0, y0, x1, y1 = alpha.getbbox()
                if min(x0, y0, size-x1, size-y1) < 4:
                    raise ValueError("A frame touches the safe margin")
            distinct.add(rgba.tobytes())
            duration += frame.info["duration"]
        if len(distinct) != 64 or duration != milliseconds:
            raise ValueError(f"Decoded {len(distinct)} distinct poses over {duration} ms")


def main():
    parser = argparse.ArgumentParser(description="Export 64-frame transparent character GIFs.")
    parser.add_argument("source", type=Path, help="4×4 sprite atlas PNG or 16-frame GIF")
    parser.add_argument("output", type=Path, help="Destination .gif")
    parser.add_argument("--duration-ms", required=True, type=int)
    parser.add_argument("--order", help="Optional 16 zero-based atlas cell indices separated by commas")
    parser.add_argument("--size", type=int, default=512, help="Square output side in pixels")
    parser.add_argument("--background", help="Optional solid CSS color, such as #f8f5fc")
    args = parser.parse_args()
    if not 128 <= args.size <= 1024:
        parser.error("Output size must be from 128 to 1024 pixels")
    try:
        background = ImageColor.getrgb(args.background) if args.background else None
    except ValueError as error:
        parser.error(str(error))
    if background and len(background) != 3:
        parser.error("Background color must be opaque")
    if args.duration_ms < 1600 or args.duration_ms % 10:
        parser.error("Duration must be a multiple of 10 ms and at least 1600 ms")
    if args.output.suffix.lower() != ".gif" or args.output.resolve() == args.source.resolve():
        parser.error("Choose a separate .gif output")
    if args.source.suffix.lower() == ".gif":
        with Image.open(args.source) as gif:
            poses = [frame.convert("RGBA") for frame in ImageSequence.Iterator(gif)]
        if any(pose.size != (512, 512) for pose in poses):
            parser.error("Source GIF must be 512×512")
    else:
        poses = extract(args.source)
    if len(poses) != 16:
        parser.error("Provide 16 ordered key poses")
    if args.order:
        order = [int(value) for value in args.order.split(",")]
        if len(order) != 16 or any(not 0 <= cell < 16 for cell in order):
            parser.error("--order requires 16 indices from 0 to 15")
        poses = [poses[cell] for cell in order]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    draft = args.output.with_name(f"{args.output.stem}.partial.gif")
    try:
        frames = make_frames(poses)
        if args.size != 512:
            resized = []
            for frame in frames:
                image = frame.resize((args.size, args.size), Image.Resampling.LANCZOS)
                image.putalpha(image.getchannel("A").point(lambda a: 255 if a >= 128 else 0))
                resized.append(image)
            frames = resized
        encode(frames, draft, args.duration_ms, background)
        verify(draft, args.duration_ms, args.size, background is None)
        draft.replace(args.output)
    finally:
        draft.unlink(missing_ok=True)
    print(args.output)


if __name__ == "__main__":
    main()

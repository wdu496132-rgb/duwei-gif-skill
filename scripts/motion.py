import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, map_coordinates, zoom

def grid(size):
    return np.indices((size, size), dtype=np.float32)


def sample(array, y, x):
    return map_coordinates(array, (y, x), order=1, mode="nearest", prefilter=False)


def flow(source, target):
    # Estimate movement at low resolution first, then recover small local details.
    u = v = None
    for size in (40, 80, 160):
        a, b = [np.asarray(im.convert("L").resize((size, size), Image.Resampling.LANCZOS),
                           dtype=np.float32) / 255 for im in (source, target)]
        y, x = grid(size)
        by, bx = np.gradient(b)
        if u is None:
            u, v = np.zeros_like(a), np.zeros_like(a)
        else:
            u, v = zoom(u, 2, order=1) * 2, zoom(v, 2, order=1) * 2
        for _ in range(6):
            wy, wx = y + v, x + u
            dx, dy = sample(bx, wy, wx), sample(by, wy, wx)
            error = a - sample(b, wy, wx)
            xx, yy, xy, ex, ey = [gaussian_filter(value, 2.0) for value in
                                  (dx*dx, dy*dy, dx*dy, dx*error, dy*error)]
            xx, yy = xx + .0009, yy + .0009
            determinant = xx * yy - xy * xy
            u += gaussian_filter(np.clip((yy*ex - xy*ey) / determinant, -2, 2), 1)
            v += gaussian_filter(np.clip((xx*ey - xy*ex) / determinant, -2, 2), 1)
    ratio = source.width / size
    return tuple(zoom(field, ratio, order=1) * ratio for field in (v, u))

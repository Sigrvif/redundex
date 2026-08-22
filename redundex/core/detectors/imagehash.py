import numpy
from PIL import Image

_SIZE = 32


def _dct_matrix(n):
    k = numpy.arange(n).reshape(n, 1).astype(numpy.float64)
    i = numpy.arange(n).reshape(1, n).astype(numpy.float64)
    m = numpy.cos(numpy.pi * (2 * k + 1) * i / (2 * n)) * numpy.sqrt(2.0 / n)
    m[0, :] /= numpy.sqrt(2.0)
    return m


_DCT = _dct_matrix(_SIZE)


def _pack_bits(bits):
    return int.from_bytes(numpy.packbits(bits, bitorder="big").tobytes(), "big")


def phash_gray(gray):
    d = _DCT @ gray @ _DCT.T
    low = d[:8, :8]
    return _pack_bits((low > numpy.median(low)).flatten())


def _box_downsample(gray, size):
    h, w = gray.shape
    bh, bw = h // size, w // size
    return gray[: bh * size, : bw * size].reshape(size, bh, size, bw).mean(axis=(1, 3))


def hash_gray_frame(gray):
    g = numpy.asarray(gray, dtype=numpy.float64)
    if g.shape != (_SIZE, _SIZE):
        g = _box_downsample(g, _SIZE)
    return phash_gray(g)


def phash_image(path):
    with Image.open(path) as im:
        gray = numpy.asarray(
            im.convert("L").resize((_SIZE, _SIZE), Image.LANCZOS), dtype=numpy.float64
        )
    return phash_gray(gray)


def dhash_image(path):
    with Image.open(path) as im:
        g = numpy.asarray(
            im.convert("L").resize((9, 8), Image.LANCZOS), dtype=numpy.float64
        )
    return _pack_bits((g[:, 1:] > g[:, :-1]).flatten())


def image_job(path):
    with Image.open(path) as im:
        w, h = im.size
        gray32 = numpy.asarray(
            im.convert("L").resize((_SIZE, _SIZE), Image.LANCZOS),
            dtype=numpy.float64,
        )
        g98 = numpy.asarray(
            im.convert("L").resize((9, 8), Image.LANCZOS), dtype=numpy.float64
        )
    dh = _pack_bits((g98[:, 1:] > g98[:, :-1]).flatten())
    return path, phash_gray(gray32), dh, w, h


def hamming(a, b):
    return (a ^ b).bit_count()


def to_signed64(v):
    return v - 2**64 if v >= 2**63 else v


def from_signed64(v):
    return v + 2**64 if v < 0 else v

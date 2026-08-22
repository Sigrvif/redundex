import numpy
from PIL import Image

from redundex.core.detectors.imagehash import (
    dhash_image,
    from_signed64,
    hamming,
    image_job,
    phash_image,
    to_signed64,
)


def _blocks(path, size, variant=0):
    rng = numpy.random.default_rng(variant)
    arr = numpy.zeros((size, size), dtype=numpy.uint8)
    arr[:, : size // 2] = 70
    arr[size // 3 : size // 2, size // 4 : 3 * size // 4] = 210
    arr[: size // 6, :] = 30
    if variant:
        arr = arr.astype(numpy.int16) + rng.integers(-8, 9, (size, size))
        arr = numpy.clip(arr, 0, 255).astype(numpy.uint8)
    Image.fromarray(arr).save(path)
    return str(path)


def _stripes(path, size):
    y, x = numpy.mgrid[0:size, 0:size]
    arr = ((x + y) % (size // 4) < size // 8).astype(numpy.uint8) * 255
    Image.fromarray(arr).save(path)
    return str(path)


def test_same_file_stable_hash(tmp_path):
    p = _blocks(tmp_path / "a.png", 256)
    assert phash_image(p) == phash_image(p)
    assert dhash_image(p) == dhash_image(p)


def test_resize_keeps_phash_close(tmp_path):
    a = _blocks(tmp_path / "big.png", 256)
    b = _blocks(tmp_path / "small.png", 64)
    assert hamming(phash_image(a), phash_image(b)) <= 8
    assert hamming(dhash_image(a), dhash_image(b)) <= 8


def test_noise_keeps_phash_close(tmp_path):
    a = _blocks(tmp_path / "clean.png", 256, variant=0)
    b = _blocks(tmp_path / "noisy.png", 256, variant=7)
    assert hamming(phash_image(a), phash_image(b)) <= 8


def test_different_images_far_apart(tmp_path):
    a = _blocks(tmp_path / "blocks.png", 256)
    b = _stripes(tmp_path / "stripes.png", 256)
    assert hamming(phash_image(a), phash_image(b)) > 20


def test_hamming():
    assert hamming(0b1010, 0b1001) == 2
    assert hamming(0, 0xFFFFFFFFFFFFFFFF) == 64


def test_signed64_roundtrip():
    for v in (0, 1, 2**62, 2**63, 2**63 + 5, 2**64 - 1):
        s = to_signed64(v)
        assert -(2**63) <= s < 2**63
        assert from_signed64(s) == v


def test_image_job_returns_size_and_hashes(tmp_path):
    p = _blocks(tmp_path / "a.png", 128)
    path, ph, dh, w, h = image_job(p)
    assert path == p and w == 128 and h == 128
    assert 0 <= ph < 2**64 and 0 <= dh < 2**64

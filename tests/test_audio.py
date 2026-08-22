from redundex.core.detectors.audio import audio_candidates, best_ber


def _word(i, salt=0):
    return ((i + 1 + salt) * 2654435761) % (2**32)


def test_best_ber_identical():
    seq = [_word(i) for i in range(12)]
    ber, offset = best_ber(seq, seq)
    assert ber == 0.0 and offset == 0


def test_best_ber_finds_offset():
    short = [_word(i) for i in range(10)]
    long = [_word(i, 100) for i in range(3)] + short + [_word(i, 200) for i in range(3)]
    ber, offset = best_ber(short, long)
    assert ber == 0.0
    assert offset == 3


def test_best_ber_unrelated():
    a = [_word(i) for i in range(40)]
    b = [_word(i, 999) for i in range(40)]
    ber, _ = best_ber(a, b)
    assert ber > 0.4


def test_audio_candidates_shared_segment():
    shared = [_word(i) for i in range(10)]
    a = [_word(i, 10) for i in range(5)] + shared
    b = shared + [_word(i, 20) for i in range(5)]
    other = [_word(i, 999) for i in range(15)]
    pairs = audio_candidates({"a.mp3": a, "b.mp3": b, "c.mp3": other})
    assert ("a.mp3", "b.mp3") in pairs
    assert all("c.mp3" not in p for p in pairs)


def test_audio_candidates_empty():
    assert audio_candidates({}) == set()

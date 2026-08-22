from redundex.core.types import FileKind, MatchReason, ScanConfig


def test_scan_config_defaults():
    cfg = ScanConfig()
    assert cfg.image_threshold == 8
    assert cfg.video_interval == 5.0
    assert cfg.video_max_frames == 200
    assert cfg.video_frame_threshold == 6
    assert cfg.video_similarity == 0.90
    assert cfg.containment_similarity == 0.85
    assert cfg.audio_ber == 0.30
    assert cfg.exact and cfg.image and cfg.video and cfg.audio and cfg.docs
    assert cfg.follow_symlinks is False
    assert cfg.cache_path is None and cfg.workers is None


def test_enums_are_strings():
    assert FileKind.IMAGE == "image"
    assert MatchReason.CONTAINED_IN == "contained-in"

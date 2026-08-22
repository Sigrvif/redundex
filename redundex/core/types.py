from dataclasses import dataclass, field
from enum import Enum


class FileKind(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOC = "doc"
    ARCHIVE = "archive"
    OTHER = "other"

    __str__ = str.__str__


class MatchReason(str, Enum):
    EXACT = "exact"
    PERCEPTUAL = "perceptual"
    CONTAINED_IN = "contained-in"
    SAME_TRACK = "same-track"
    SAME_TEXT = "same-text"

    __str__ = str.__str__


@dataclass(frozen=True)
class FileEntry:
    path: str
    size: int
    mtime_ns: int
    kind: FileKind


@dataclass(frozen=True)
class Match:
    a: str
    b: str
    reason: MatchReason
    score: float
    detail: str = ""


@dataclass
class Group:
    members: list
    matches: list
    redundancy: int = 0


@dataclass
class ScanConfig:
    follow_symlinks: bool = False
    cache_path: str | None = None
    exact: bool = True
    image: bool = True
    image_threshold: int = 8
    video: bool = True
    video_interval: float = 5.0
    video_max_frames: int = 200
    video_frame_threshold: int = 6
    video_similarity: float = 0.90
    containment_similarity: float = 0.85
    audio: bool = True
    audio_ber: float = 0.30
    docs: bool = True
    workers: int | None = None


@dataclass
class ScanResult:
    groups: list = field(default_factory=list)
    problems: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)
    cancelled: bool = False


def format_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024

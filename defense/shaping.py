"""
Reply shaping and reply jitter at a cloud agent (paper 2 round 2: B1 shaping, B2 jitter; the pilot of
paper 3's shaping defence).

Every size here is in bytes on the wire: the reply text as the A2A SDK serializes it into an SSE event
(pydantic's JSON: UTF-8, with quotes, backslashes, newlines and tabs escaped to two bytes), and every
event as the UTF-8 bytes of its JSON. Characters are never counted.

Shaping (ShapeConfig):
    size      the reply is cut to reply_bytes encoded bytes (at a character boundary; a cut reply is
              logged) and split into n = reply_bytes / chunk_bytes chunks, chunk k ending at the last
              character boundary at or below (k + 1) * chunk_bytes, so each chunk is at most
              chunk_bytes + 3 bytes (MAX_SLACK: a 4-byte character that did not fit) and no capacity
              is lost to boundaries. Every streamed event is padded to the size an event with a
              chunk of chunk_bytes + MAX_SLACK bytes has, the final artifact to the size an artifact
              with a reply of reply_bytes bytes has (a filler field in the metadata, never the text)
    time      the first event leaves deadline_s after the request arrived, then one every interval_s
    overrun   the model is not done by the deadline: "truncate" sends what it has streamed so far
              (on time), "late" waits for it (and leaks that it was late)

Jitter (JitterConfig): every SSE event the agent sends waits an extra delay drawn from a normal
distribution (mean_ms, sd_ms), clipped at 0 as netem does with a negative draw (the packet leaves at
once), in order: event i leaves at max(event i-1's departure, its own ready time + its delay), as a
FIFO link (netem with a rate) would deliver it. Seeded. clipped_normal() gives the mean and sd after
clipping.

The request side is padded separately (agents/base.py pad_request). What shaping leaves visible:
whether a call happens at all (escalation), which endpoint it goes to, and the traffic on links it
does not cover (at C2's V1, the ticket post after the reply).
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass

import pydantic_core

OVERRUN = ("truncate", "late")
MAX_SLACK = 3                                   # a chunk ends at most 3 bytes past its share (4-byte UTF-8)
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def json_bytes(text: str) -> int:
    """Bytes the text takes inside a JSON string as the SDK serializes it (pydantic: UTF-8, escapes)."""
    return len(pydantic_core.to_json(text)) - 2


def wire_bytes(model) -> int:
    """UTF-8 bytes of a pydantic model's JSON as the SDK sends it (exclude_none)."""
    return len(model.model_dump_json(exclude_none=True).encode("utf-8"))


def clean(text: str) -> str:
    """Control characters other than newline and tab become spaces (their escapes are 6 bytes)."""
    return _CONTROL.sub(" ", text)


@dataclass(frozen=True)
class ShapeConfig:
    reply_bytes: int
    deadline_s: float
    chunk_bytes: int = 128
    interval_s: float = 0.05
    overrun: str = "truncate"

    def __post_init__(self):
        if self.reply_bytes <= 0 or self.chunk_bytes <= 0 or self.reply_bytes % self.chunk_bytes:
            raise ValueError("reply_bytes must be a positive multiple of chunk_bytes")
        if self.deadline_s <= 0 or self.interval_s < 0:
            raise ValueError("deadline_s must be > 0 and interval_s >= 0")
        if self.overrun not in OVERRUN:
            raise ValueError(f"overrun must be one of {OVERRUN}")

    @property
    def events(self) -> int:
        return self.reply_bytes // self.chunk_bytes

    @classmethod
    def parse(cls, spec: str) -> "ShapeConfig":
        """REPLY_BYTES/DEADLINE_S[/CHUNK_BYTES[/INTERVAL_S[/OVERRUN]]], e.g. 2048/14/128/0.05/truncate."""
        p = spec.split("/")
        if not 2 <= len(p) <= 5:
            raise ValueError(f"shape {spec!r}: REPLY_BYTES/DEADLINE_S[/CHUNK_BYTES[/INTERVAL_S[/OVERRUN]]]")
        kw = {"reply_bytes": int(p[0]), "deadline_s": float(p[1])}
        if len(p) > 2:
            kw["chunk_bytes"] = int(p[2])
        if len(p) > 3:
            kw["interval_s"] = float(p[3])
        if len(p) > 4:
            kw["overrun"] = p[4]
        return cls(**kw)

    def spec(self) -> str:
        return f"{self.reply_bytes}/{self.deadline_s:g}/{self.chunk_bytes}/{self.interval_s:g}/{self.overrun}"

    def release_s(self) -> float:
        """Seconds from the request to the last event."""
        return self.deadline_s + (self.events - 1) * self.interval_s


def split_reply(text: str, cfg: ShapeConfig) -> tuple[list[str], dict]:
    """The reply as cfg.events chunks: cut to cfg.reply_bytes encoded bytes, chunk k ending at the
    last character boundary at or below (k + 1) * chunk_bytes. Returns (chunks, what was done):
    chars and encoded bytes of the model's reply, bytes sent, whether it was cut."""
    t = clean(text)
    chunks, cur, pos, k = [], [], 0, 0
    cut = False
    for ch in t:
        b = json_bytes(ch)
        if pos + b > cfg.reply_bytes:
            cut = True
            break
        while pos + b > (k + 1) * cfg.chunk_bytes:   # this character starts the next chunk
            chunks.append("".join(cur))
            cur, k = [], k + 1
        cur.append(ch)
        pos += b
    chunks.append("".join(cur))
    chunks += [""] * (cfg.events - len(chunks))
    assert len(chunks) == cfg.events
    return chunks, {"chars": len(text), "bytes": json_bytes(t), "sent_bytes": pos, "truncated": cut}


def pad_to(serialize, set_pad, target: int) -> int:
    """Grow an object's wire size (serialize() → bytes count) to exactly target bytes with a filler
    field: set_pad("") then measure, set_pad("x" * (target - size)). Returns the filler length;
    raises if the object is already larger than target."""
    set_pad("")
    need = target - serialize()
    if need < 0:
        raise ValueError(f"event of {target - need} B is larger than the shaped size {target} B")
    set_pad("x" * need)
    got = serialize()
    if got != target:
        raise ValueError(f"padding gave {got} B, not {target} B")
    return need


@dataclass(frozen=True)
class JitterConfig:
    mean_ms: float
    sd_ms: float
    seed: int = 0

    def __post_init__(self):
        if self.mean_ms < 0 or self.sd_ms < 0:
            raise ValueError("jitter mean and sd must be >= 0")

    @classmethod
    def parse(cls, spec: str) -> "JitterConfig":
        """MEAN_MS/SD_MS[/SEED], e.g. 4/1.8 or 4/1.8/7."""
        p = spec.split("/")
        if not 2 <= len(p) <= 3:
            raise ValueError(f"jitter {spec!r}: MEAN_MS/SD_MS[/SEED]")
        return cls(float(p[0]), float(p[1]), int(p[2]) if len(p) > 2 else 0)

    def spec(self) -> str:
        return f"{self.mean_ms:g}/{self.sd_ms:g}/{self.seed}"


def clipped_normal(mean: float, sd: float) -> dict:
    """max(0, X) for X ~ N(mean, sd): the share of draws clipped, and the mean and sd after clipping."""
    if sd == 0:
        return {"p_clipped": float(mean < 0), "mean": max(0.0, mean), "sd": 0.0}
    a = mean / sd
    cdf, pdf = 0.5 * (1 + math.erf(a / math.sqrt(2))), math.exp(-a * a / 2) / math.sqrt(2 * math.pi)
    m1 = mean * cdf + sd * pdf
    m2 = (mean ** 2 + sd ** 2) * cdf + mean * sd * pdf
    return {"p_clipped": 1 - cdf, "mean": m1, "sd": math.sqrt(max(0.0, m2 - m1 ** 2))}


class Jitter:
    """Per-event delays in order: depart(i) = max(depart(i-1), ready(i) + d_i), d_i = max(0, N(mean, sd)).
    Times in seconds (time.monotonic)."""

    def __init__(self, cfg: JitterConfig, stream: str = ""):
        self.cfg = cfg
        self.rng = random.Random(f"{cfg.seed}:{stream}")
        self.last = float("-inf")
        self.last_draw_ms: float | None = None          # the latest draw, before the order constraint

    def draw_s(self) -> float:
        d = max(0.0, self.rng.gauss(self.cfg.mean_ms, self.cfg.sd_ms))
        self.last_draw_ms = d
        return d / 1000.0

    def departure(self, ready: float) -> float:
        self.last = max(self.last, ready + self.draw_s())
        return self.last

"""Reply shaping and reply jitter (defense/shaping.py, agents/base.py): the parts, a shaped agent on
localhost whose replies of different lengths, characters and generation times look the same on the
SSE stream (the same number of events, each of the same size in bytes, released at the same times
after the request; a reply over the cap is cut and logged), and a jittered agent whose events keep
their order."""

import asyncio
import json
import logging
import socket
import time
import uuid

import httpx
import pytest
from a2a.types import TextPart

from agents.base import AgentConfig, AgentRole, BaseA2AAgent
from defense.shaping import (MAX_SLACK, Jitter, JitterConfig, ShapeConfig, clipped_normal, json_bytes, pad_to,
                             split_reply)

SPEC = "512/1.2/128/0.1/truncate"


def test_shape_config_parses_and_checks():
    c = ShapeConfig.parse(SPEC)
    assert (c.reply_bytes, c.deadline_s, c.chunk_bytes, c.interval_s, c.overrun, c.events) == (512, 1.2, 128, 0.1, "truncate", 4)
    assert ShapeConfig.parse(c.spec()) == c and abs(c.release_s() - 1.5) < 1e-9
    for bad in ("500/1/128", "512/0", "512/1/128/0.1/drop", "512"):
        with pytest.raises(ValueError):
            ShapeConfig.parse(bad)


def test_json_bytes_are_the_sdk_s_wire_bytes():
    empty = len(TextPart(text="").model_dump_json(exclude_none=True).encode())
    for s in ('plain', 'a"b\\c\nd\te', "é°–→", "😀x", " "):
        assert json_bytes(s) == len(TextPart(text=s).model_dump_json(exclude_none=True).encode()) - empty, s


def test_the_cap_counts_encoded_bytes_not_characters():
    c = ShapeConfig.parse(SPEC)
    for text, cut in (("a" * 512, False), ("a\n" * 200, True), ("é" * 256, False), ("é" * 257, True),
                      ("😀" * 200, True), ('x"' * 170 + "y", False), ("short", False)):
        chunks, fit = split_reply(text, c)
        sent = "".join(chunks)
        assert len(chunks) == c.events and text.startswith(sent)
        assert fit["truncated"] == cut and fit["sent_bytes"] == json_bytes(sent) <= c.reply_bytes, text[:8]
        assert fit["bytes"] == json_bytes(text) and fit["chars"] == len(text)
        assert all(json_bytes(ch) <= c.chunk_bytes + MAX_SLACK for ch in chunks)
        if cut:
            assert c.reply_bytes - fit["sent_bytes"] < 4
    chunks, _ = split_reply("ab\x01\x7fc", c)                  # control characters become spaces
    assert "".join(chunks) == "ab  c"


def test_pad_to_hits_the_target_in_bytes():
    box = {"_pad": ""}
    n = pad_to(lambda: len(json.dumps({"a": "é\"\n", **box}, ensure_ascii=False).encode()),
               lambda f: box.update({"_pad": f}), 80)
    assert len(json.dumps({"a": "é\"\n", **box}, ensure_ascii=False).encode()) == 80 and n > 0
    with pytest.raises(ValueError):
        pad_to(lambda: len(json.dumps({"a": "x" * 100, **box})), lambda f: box.update({"_pad": f}), 50)


def test_jitter_keeps_order_and_its_mean():
    j = Jitter(JitterConfig.parse("4/1.8/7"), stream="s")
    readies = [i * 0.05 for i in range(4000)]                    # far apart: the mean delay shows
    d = [j.departure(r) - r for r in readies]
    assert min(d) >= 0 and abs(sum(d) / len(d) * 1000 - clipped_normal(4, 1.8)["mean"]) < 0.15
    c = clipped_normal(4, 1.8)
    assert abs(c["p_clipped"] - 0.0131) < 0.0005 and 4.0 < c["mean"] < 4.02 and 1.7 < c["sd"] < 1.8
    zero = Jitter(JitterConfig.parse("0.5/3/1"))                 # mostly negative draws: clipped, not redrawn
    assert sum(zero.draw_s() == 0 for _ in range(2000)) > 600
    j2 = Jitter(JitterConfig.parse("4/1.8/7"), stream="s")
    burst = [j2.departure(1.0) for _ in range(50)]               # ready together: never reordered
    assert burst == sorted(burst)
    assert JitterConfig.parse("4/1.8").spec() == "4/1.8/0"
    with pytest.raises(ValueError):
        JitterConfig.parse("4")


class _Writer(BaseA2AAgent):
    """Writes a reply of n characters (of the kind given) in n / 100 s: content "N" or "N:KIND"."""

    async def handle_task(self, task_id, content, emit=None):
        n, _, kind = content.partition(":")
        n = int(n)
        unit = {"": 'a"b\n', "accents": "é°–→", "emoji": "😀a"}[kind]
        text = (unit * n)[:n]
        for i in range(0, n, 50):
            await asyncio.sleep(0.01 * min(50, n - i) / 50 * n / 100)
            if emit is not None:
                await emit(text[i:i + 50])
        return text


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _stream(url: str, content: str) -> list[tuple[float, int, str]]:
    """POST message/stream and read the SSE body: (seconds after the request, bytes, event kind) per event."""
    req = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "message/stream",
           "params": {"message": {"role": "user", "parts": [{"kind": "text", "text": content}],
                                  "messageId": str(uuid.uuid4()), "kind": "message"}}}
    out = []
    async with httpx.AsyncClient(timeout=30) as c:
        t0 = time.monotonic()
        async with c.stream("POST", url, json=req) as r:
            async for line in r.aiter_lines():
                if line.startswith("data:"):
                    ev = json.loads(line[5:])["result"]
                    kind = ev.get("kind") + ":" + (ev.get("status", {}).get("state", "") if ev.get("kind") == "status-update" else "")
                    out.append((time.monotonic() - t0, len(line.encode()), kind))
    return out


async def _serve(cfg: AgentConfig, contents: list[str]):
    agent = _Writer(cfg)
    server = asyncio.create_task(agent.run())
    await asyncio.sleep(1.0)
    try:
        return [await _stream(agent.config.base_url(), c) for c in contents]
    finally:
        await agent.shutdown()
        await asyncio.wait([server], timeout=4)


def test_shaped_replies_look_alike_on_the_stream(tmp_path, caplog):
    log = tmp_path / "replies.jsonl"
    cfg = AgentConfig(role=AgentRole.DIAGNOSTICS, host="127.0.0.1", port=_free_port(), tls=False, shape=SPEC,
                      reply_log=str(log))
    contents = ["40", "900", "300:accents", "200:emoji"]       # at once; cut and late; multibyte; 4-byte
    with caplog.at_level(logging.WARNING):
        streams = asyncio.run(_serve(cfg, contents))
    kinds = [k for _, _, k in streams[0]]
    assert all([k for _, _, k in s] == kinds for s in streams)
    assert kinds.count("status-update:working") == 1 + 4                    # start_work, then the 4 reply events
    sizes = [n for _, n, _ in streams[0]]                                    # bytes, whatever the characters
    assert all([n for _, n, _ in s] == sizes for s in streams)
    reply = [i for i, k in enumerate(kinds) if k == "status-update:working"][1:]
    for ev in streams:
        assert 1.2 <= ev[reply[0]][0] < 1.6                                  # released at the deadline
        gaps = [ev[j][0] - ev[i][0] for i, j in zip(reply, reply[1:])]
        assert all(0.08 <= x <= 0.25 for x in gaps)
    rec = [json.loads(x) for x in log.read_text().splitlines()]
    assert [r["shaping"]["truncated"] for r in rec] == [False, True, True, False]
    assert rec[1]["shaping"]["overrun"] and rec[1]["shaping"]["sent_bytes"] <= 512
    assert rec[2]["shaping"]["bytes"] > 512 >= rec[2]["shaping"]["sent_bytes"]   # 300 chars, about 750 B
    assert sum("TRUNCATED reply" in r.message for r in caplog.records) == 2


def test_jittered_events_keep_their_order(tmp_path):
    log = tmp_path / "replies.jsonl"
    cfg = AgentConfig(role=AgentRole.DIAGNOSTICS, host="127.0.0.1", port=_free_port(), tls=False, jitter="30/10/1",
                      reply_log=str(log))
    plain = AgentConfig(role=AgentRole.DIAGNOSTICS, host="127.0.0.1", port=_free_port(), tls=False)
    (jit,) = asyncio.run(_serve(cfg, ["300"]))
    (ref,) = asyncio.run(_serve(plain, ["300"]))
    assert [k for _, _, k in jit] == [k for _, _, k in ref]                 # the same events, in order
    assert jit[-1][2] == "status-update:completed"
    r = json.loads(log.read_text())
    assert r["jitter"]["events"] == len(jit) and 15 < r["jitter"]["mean_ms"] < 60
    assert jit[-1][0] > ref[-1][0]

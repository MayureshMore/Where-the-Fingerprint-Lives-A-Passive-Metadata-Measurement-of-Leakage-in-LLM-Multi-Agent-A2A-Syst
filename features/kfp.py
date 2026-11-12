"""
k-FP features (Hayes & Danezis, "k-fingerprinting", USENIX Security 2016) as a baseline.

k-FP was built for Tor, where every cell has the same size, so its features use only packet
direction and timing. They are reproduced here from that feature list: packet counts, inter-arrival
and transmission-time statistics, packet ordering, the first and last 30 packets, outgoing
concentration in chunks of 20, packets per second, and the 70- and 20-bin "alternative"
concentration and rate vectors. Packet sizes are never used. Direction is "towards an agent
server port" (+1) or "from one" (-1); the port number itself is never a feature.

    packets_from_pcap(path)          → [(ts, src_port, dst_port, wire_len)]
    tcp_packets(path)                → [(ts, src_port, dst_port, wire_len, tcp_payload_len, tcp_flags)]
    tcp_packets(path, dedup=True)    → the same with every payload byte counted once: a data segment
                                       whose bytes an earlier segment of its connection and direction
                                       already carried (a TCP retransmission) is dropped, and one that
                                       repeats part of them keeps only its new bytes (TCP sequence
                                       numbers, so it works on payload-stripped pcaps)
    kfp_features(times, directions)  → 1-D vector, length N_KFP
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from scripts.strip_payload import _MAGICS, _network_offset

_NANO = {b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d"}
N_CONC, N_RATE = 70, 20
N_KFP = 3 + 12 + 12 + 4 + 4 + 4 + 5 + 2 + 2 + N_CONC + N_RATE


_SYN, _FIN, _RST = 0x02, 0x01, 0x04


def tcp_packets(path: Path, dedup: bool = False) -> list[tuple[float, int, int, int, int, int]]:
    """TCP packets with their payload length, read from the IP and TCP headers alone (the IP
    length field, not the captured bytes), so it works on payload-stripped pcaps. dedup: every
    payload byte counted once (see dedup_view)."""
    records = tcp_records(path)
    return dedup_view(records) if dedup else [r[:6] for r in records]


def duplicate_bytes(records) -> list[int]:
    """Per record, how many of its payload bytes an earlier record of the same connection and
    direction already carried (sequence numbers relative to the first one seen, mod 2^32; a SYN
    starts the direction afresh, so a reused port pair is a new connection)."""
    seen: dict[tuple[int, int], list] = {}
    out = []
    for _, sp, dp, _, pl, fl, seq in records:
        key = (sp, dp)
        if fl & _SYN:
            seen.pop(key, None)
        if pl == 0:
            out.append(0)
            continue
        st = seen.setdefault(key, [seq, []])
        lo = ((seq - st[0] + 2 ** 31) % 2 ** 32) - 2 ** 31
        hi = lo + pl
        out.append(sum(max(0, min(hi, y) - max(lo, x)) for x, y in st[1]))
        merged: list[tuple[int, int]] = []
        for x, y in sorted(st[1] + [(lo, hi)]):
            if merged and x <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], y))
            else:
                merged.append((x, y))
        st[1] = merged
    return out


def is_retransmission(record, dup: int) -> bool:
    """A record that carries no new byte and no FIN or RST: dropped by dedup_view."""
    return record[4] > 0 and dup == record[4] and not record[5] & (_FIN | _RST)


def dedup_view(records) -> list[tuple[float, int, int, int, int, int]]:
    """The records with every payload byte counted once: retransmissions dropped, a partial
    retransmission keeping only its new bytes (on-wire length reduced by the repeated ones)."""
    dups = duplicate_bytes(records)
    return [(ts, sp, dp, wl - d, pl - d, fl) for (ts, sp, dp, wl, pl, fl, _), d in zip(records, dups)
            if not is_retransmission((ts, sp, dp, wl, pl, fl), d)]


def tcp_records(path: Path) -> list[tuple[float, int, int, int, int, int, int]]:
    """tcp_packets with the TCP sequence number as a seventh field."""
    raw = Path(path).read_bytes()
    endian = _MAGICS[raw[:4]]
    scale = 1e-9 if raw[:4] in _NANO else 1e-6
    linktype = struct.unpack(endian + "I", raw[20:24])[0]
    out, pos = [], 24
    while pos + 16 <= len(raw):
        sec, frac, incl, orig = struct.unpack(endian + "IIII", raw[pos:pos + 16])
        data = raw[pos + 16:pos + 16 + incl]
        pos += 16 + incl
        off = _network_offset(linktype, data)
        if len(data) <= off:
            continue
        v = data[off] >> 4
        if v == 4 and len(data) > off + 9:
            ihl = max((data[off] & 0x0F) * 4, 20)
            proto, l4 = data[off + 9], off + ihl
            ip_payload = struct.unpack(">H", data[off + 2:off + 4])[0] - ihl
        elif v == 6 and len(data) > off + 6:
            proto, l4 = data[off + 6], off + 40
            ip_payload = struct.unpack(">H", data[off + 4:off + 6])[0]
        else:
            continue
        if proto != 6 or len(data) < l4 + 14:
            continue
        sport, dport, seq = struct.unpack(">HHI", data[l4:l4 + 8])
        doff, flags = (data[l4 + 12] >> 4) * 4, data[l4 + 13]
        out.append((sec + frac * scale, sport, dport, orig, max(ip_payload - doff, 0), flags, seq))
    return out


def packets_from_pcap(path: Path) -> list[tuple[float, int, int, int]]:
    return [p[:4] for p in tcp_packets(path)]


def _iat_stats(t: np.ndarray) -> list[float]:
    d = np.diff(t) if len(t) > 1 else np.zeros(1)
    return [float(d.max()), float(d.mean()), float(d.std()), float(np.percentile(d, 75))]


def _time_quartiles(t: np.ndarray) -> list[float]:
    if len(t) == 0:
        return [0.0] * 4
    r = t - t[0]
    return [float(np.percentile(r, q)) for q in (25, 50, 75, 100)]


def _bins(values: list[float], n: int) -> list[float]:
    """Sum `values` into n roughly equal consecutive bins (k-FP's 'alternative' lists)."""
    if not values:
        return [0.0] * n
    parts = np.array_split(np.asarray(values, dtype=float), n)
    return [float(p.sum()) if len(p) else 0.0 for p in parts]


def kfp_features(times, directions) -> np.ndarray:
    t = np.asarray(times, dtype=float)
    d = np.asarray(directions, dtype=int)
    order = np.argsort(t, kind="stable")
    t, d = t[order], d[order]
    if len(t):
        t = t - t[0]
    out_m, in_m = d > 0, d < 0
    n, n_out, n_in = len(d), int(out_m.sum()), int(in_m.sum())
    f: list[float] = [n_in, n_out, n]
    for sel in (in_m, out_m, np.ones(n, bool)):
        f += _iat_stats(t[sel])
    for sel in (in_m, out_m, np.ones(n, bool)):
        f += _time_quartiles(t[sel])
    pos = np.arange(n)
    for sel in (out_m, in_m):
        p = pos[sel] if sel.any() else np.zeros(1)
        f += [float(p.mean()), float(p.std())]
    first, last = d[:30], d[-30:]
    f += [int((first < 0).sum()), int((first > 0).sum()), int((last < 0).sum()), int((last > 0).sum())]
    conc = [int((d[i:i + 20] > 0).sum()) for i in range(0, n, 20)] or [0]
    f += [float(np.std(conc)), float(np.mean(conc)), float(np.median(conc)), float(np.max(conc))]
    secs = int(np.floor(t[-1])) + 1 if n else 1
    rate = np.bincount(np.floor(t).astype(int), minlength=secs).tolist() if n else [0]
    f += [float(np.mean(rate)), float(np.std(rate)), float(np.median(rate)),
          float(np.min(rate)), float(np.max(rate))]
    f += [n_in / n if n else 0.0, n_out / n if n else 0.0]
    alt_conc, alt_rate = _bins(conc, N_CONC), _bins(rate, N_RATE)
    f += [float(sum(alt_conc)), float(sum(alt_rate))]
    f += alt_conc + alt_rate
    v = np.asarray(f, dtype=np.float32)
    assert v.shape == (N_KFP,), v.shape
    return v

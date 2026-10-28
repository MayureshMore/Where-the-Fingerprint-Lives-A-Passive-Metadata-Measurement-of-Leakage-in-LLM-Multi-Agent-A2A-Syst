#!/usr/bin/env python3
"""
Strip payload bytes from pcap captures before release.

The testbed captures at a 96-byte snaplen. On loopback and tunnel links the
link + IP + TCP headers take roughly 56-76 bytes, so each stored packet still
carries a 20-40 byte slice of (cleartext) application payload. This tool
truncates every packet to exactly its link, network and transport headers,
computed per packet from the IPv4 IHL / IPv6 next-header and the TCP data
offset. Timestamps and the original on-wire length (orig_len) are preserved,
and every feature in features/ reads only those two fields, so features
re-extracted from stripped captures are identical to the published ones.

Handles classic pcap (either byte order, micro- or nanosecond) with link types
DLT_NULL (0, BSD loopback), DLT_EN10MB (1), DLT_RAW (101 / 12, tunnel) and
DLT_LINUX_SLL (113). Anything it cannot parse is cut to the link header plus
the fixed 20/40-byte IP header, never kept in full.

Usage:
    python scripts/strip_payload.py --out STAGE_DIR data/raw data/raw_wan ...
        → STAGE_DIR/data/raw/..., STAGE_DIR/data/raw_wan/... (pcaps stripped,
          every other file copied unchanged)
    python scripts/strip_payload.py --check DIR ...   # report payload bytes left (exit 1 if any)
"""

from __future__ import annotations

import argparse
import shutil
import struct
import sys
from pathlib import Path

_MAGICS = {
    b"\xd4\xc3\xb2\xa1": "<", b"\xa1\xb2\xc3\xd4": ">",   # microsecond
    b"\x4d\x3c\xb2\xa1": "<", b"\xa1\xb2\x3c\x4d": ">",   # nanosecond
}
_LINK_HDR = {0: 4, 1: 14, 12: 0, 101: 0, 113: 16}
_PCAP_EXT = (".pcap", ".cap")


def _network_offset(linktype: int, data: bytes) -> int:
    """Length of the link-layer header (handles one 802.1Q VLAN tag on Ethernet)."""
    off = _LINK_HDR[linktype]
    if linktype == 1 and len(data) >= 18 and data[12:14] == b"\x81\x00":
        off = 18
    return off


def header_length(linktype: int, data: bytes) -> int:
    """Bytes of link + network + transport header at the start of a captured packet."""
    off = _network_offset(linktype, data)
    if len(data) <= off:
        return len(data)
    version = data[off] >> 4
    if version == 4:
        ihl = (data[off] & 0x0F) * 4
        proto = data[off + 9] if len(data) > off + 9 else None
        l4 = off + max(ihl, 20)
    elif version == 6:
        proto = data[off + 6] if len(data) > off + 6 else None
        l4 = off + 40
    else:
        return min(len(data), off)
    if proto == 6 and len(data) >= l4 + 13:            # TCP: data offset in 32-bit words
        return min(len(data), l4 + max((data[l4 + 12] >> 4) * 4, 20))
    if proto == 17:                                     # UDP: fixed 8-byte header
        return min(len(data), l4 + 8)
    return min(len(data), l4)


def strip_file(src: Path, dst: Path) -> tuple[int, int]:
    """Write a header-only copy of src to dst. Returns (packets, payload bytes removed)."""
    raw = src.read_bytes()
    endian = _MAGICS.get(raw[:4])
    if endian is None:
        raise ValueError(f"{src}: not a classic pcap file (pcapng is not supported)")
    linktype = struct.unpack(endian + "I", raw[20:24])[0]
    if linktype not in _LINK_HDR:
        raise ValueError(f"{src}: unsupported link type {linktype}")
    out = bytearray(raw[:24])
    pos, packets, removed = 24, 0, 0
    while pos + 16 <= len(raw):
        ts_sec, ts_frac, incl_len, orig_len = struct.unpack(endian + "IIII", raw[pos:pos + 16])
        data = raw[pos + 16:pos + 16 + incl_len]
        keep = header_length(linktype, data)
        out += struct.pack(endian + "IIII", ts_sec, ts_frac, keep, orig_len)
        out += data[:keep]
        removed += incl_len - keep
        packets += 1
        pos += 16 + incl_len
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(bytes(out))
    return packets, removed


def payload_bytes(path: Path) -> int:
    """Captured bytes beyond the headers (0 for a stripped file)."""
    raw = path.read_bytes()
    endian = _MAGICS[raw[:4]]
    linktype = struct.unpack(endian + "I", raw[20:24])[0]
    pos, extra = 24, 0
    while pos + 16 <= len(raw):
        incl_len = struct.unpack(endian + "I", raw[pos + 8:pos + 12])[0]
        data = raw[pos + 16:pos + 16 + incl_len]
        extra += incl_len - header_length(linktype, data)
        pos += 16 + incl_len
    return extra


def main(a: argparse.Namespace) -> None:
    dirs = [Path(d) for d in a.dirs]
    if a.check:
        left = {str(f): payload_bytes(f) for d in dirs for f in sorted(d.rglob("*"))
                if f.suffix in _PCAP_EXT}
        dirty = {f: n for f, n in left.items() if n}
        print(f"checked {len(left)} pcaps: {len(dirty)} still carry payload bytes")
        for f, n in list(dirty.items())[:10]:
            print(f"  {f}: {n} bytes")
        sys.exit(1 if dirty else 0)

    out_root = Path(a.out)
    total_files = total_pkts = total_removed = 0
    for d in dirs:
        for f in sorted(d.rglob("*")):
            if not f.is_file():
                continue
            dst = out_root / f
            if f.suffix in _PCAP_EXT:
                n, r = strip_file(f, dst)
                total_files += 1; total_pkts += n; total_removed += r
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst)
    print(f"stripped {total_files} pcaps ({total_pkts} packets): removed {total_removed} payload bytes "
          f"→ {out_root}/")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("dirs", nargs="+", help="capture directories to process")
    p.add_argument("--out", help="output root; each DIR is written to OUT/DIR")
    p.add_argument("--check", action="store_true", help="report payload bytes left in DIRs")
    args = p.parse_args()
    if not args.check and not args.out:
        p.error("--out is required unless --check is given")
    main(args)

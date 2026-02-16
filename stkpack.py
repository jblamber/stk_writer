#!/usr/bin/env python3
import argparse
import datetime as _dt
import io
import os
import struct
import sys
from pathlib import Path
import wave
import audioop

KTDT_SIZE = 0x1084
MAGIC = b"VDK0PR \x00"
KTDT_TAG = b"KTDT"
HEADER_RESERVED = b"\x00" * 4

TARGET_RATE = 48000
TARGET_WIDTH = 2  # bytes -> 16-bit
TARGET_CHANNELS = 2  # stereo

# A conservative parameter prefix seen in the provided kits
#  - 0x64,0x00,0x00,0x7F, then zeros, then a DWORD 0x00000040, then zeros
# In the actual file, these follow the path in each 281-byte entry.
PARAM_SUFFIX = (b"\x64\x00\x00\x7F"  # level=?, pitch=?, pan/vel=?
                + b"\x00" * 12
                + struct.pack('<I', 0x40)
                + b"\x00" * 8)


def _read_wav_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _to_pcm16_stereo_48k(raw: bytes) -> bytes:
    """Convert a WAV file (bytes) to 48kHz, 16-bit PCM stereo WAV bytes.
    Uses wave+audioop from the stdlib; handles PCM formats. Float/encoded ADPCM not supported.
    """
    with wave.open(io.BytesIO(raw), 'rb') as r:
        nch = r.getnchannels()
        sampwidth = r.getsampwidth()
        fr = r.getframerate()
        nframes = r.getnframes()
        comp = r.getcomptype()
        if comp not in (b'NONE', 'NONE'):
            raise ValueError(f"Unsupported compressed WAV (comptype={comp})")
        frames = r.readframes(nframes)

    # Convert bit depth to 16-bit little-endian linear PCM if needed
    if sampwidth != TARGET_WIDTH:
        frames = audioop.lin2lin(frames, sampwidth, TARGET_WIDTH)
        sampwidth = TARGET_WIDTH

    # Convert channels to stereo
    if nch == 1:
        # duplicate mono to stereo
        frames = audioop.tostereo(frames, sampwidth, 1, 1)
        nch = 2
    elif nch == 2:
        pass
    else:
        # mixdown >2 channels to stereo (average L/R pairs)
        # First reduce to mono, then to stereo by duplication
        frames = audioop.tomono(frames, sampwidth, 0.5, 0.5)
        frames = audioop.tostereo(frames, sampwidth, 1, 1)
        nch = 2

    # Resample to 48kHz
    if fr != TARGET_RATE:
        # audioop.ratecv returns (converted_data, state)
        converted, _ = audioop.ratecv(frames, sampwidth, nch, fr, TARGET_RATE, None)
        frames = converted
        fr = TARGET_RATE

    # Ensure even frame count alignment
    # Build a new WAV container
    out_b = io.BytesIO()
    with wave.open(out_b, 'wb') as w:
        w.setnchannels(TARGET_CHANNELS)
        w.setsampwidth(TARGET_WIDTH)
        w.setframerate(TARGET_RATE)
        w.writeframes(frames)
    return out_b.getvalue()


def _pick_samples(folder: Path, files: list[Path]) -> tuple[list[bytes], list[str]]:
    """Return list of up to 15 converted WAV bytes and their original stem names."""
    selected: list[Path] = []

    if folder is not None:
        wavs = sorted([p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == '.wav'])
        selected = wavs[:15]
    elif files:
        selected = files[:15]
    else:
        raise ValueError("Provide a --folder or at least one WAV file")

    # Convert all
    converted: list[bytes] = []
    names: list[str] = []
    for p in selected:
        b = _read_wav_bytes(p)
        converted.append(_to_pcm16_stereo_48k(b))
        names.append(p.stem)

    # If fewer than 15: pad with duplicates of the smallest (by data length)
    if len(converted) < 15:
        # pick the smallest by total byte length of WAV
        min_idx = min(range(len(converted)), key=lambda i: len(converted[i])) if converted else None
        if min_idx is None:
            raise ValueError("No WAV files found to pad from")
        smallest = converted[min_idx]
        smallest_name = names[min_idx]
        while len(converted) < 15:
            converted.append(smallest)
            # Add a suffix to padded names to keep them somewhat distinct if needed,
            # but still based on the original name.
            names.append(f"{smallest_name}_pad{len(converted)}")

    return converted[:15], names[:15]


def _make_paths(title: str, names: list[str]) -> list[bytes]:
    # Internal path format observed: SmplTrek/Pool/Audio/Drum/<folder>/<file>.wav\0
    # We'll use fixed root plus title basename
    root_str = f"SmplTrek/Pool/Audio/Drum/{title}"
    # ensure ASCII/UTF-8 safe bytes
    paths: list[bytes] = []
    for name in names:
        s = f"{root_str}/{name}.wav".encode('utf-8') + b"\x00"
        paths.append(s)
    return paths


def _build_ktdt(paths: list[bytes]) -> bytes:
    # Each entry is 281 bytes. Path at offset 0, params at offset 256.
    entry_size = 281
    buf = bytearray(KTDT_SIZE)
    for i in range(15):
        off = i * entry_size
        path = paths[i]
        if len(path) > 256:
            path = path[:255] + b"\x00"
        buf[off : off + len(path)] = path
        buf[off + 256 : off + 256 + len(PARAM_SUFFIX)] = PARAM_SUFFIX
    return bytes(buf)


def _write_stk(out_path: Path, ktdt_body: bytes, wavs: list[bytes]):
    with open(out_path, 'wb') as f:
        # Header (32 bytes total before KTDT body)
        f.write(MAGIC)
        f.write(b"\x00" * 4)
        f.write(struct.pack('<I', 0x10))  # Offset to KTDT tag?
        f.write(KTDT_TAG)
        f.write(struct.pack('<I', KTDT_SIZE))
        f.write(b"\x00" * 4)  # reserved
        f.write(struct.pack('<I', 1))  # version/marker
        # KTDT body starts at 0x20
        f.write(ktdt_body)
        # Append WAVs
        for w in wavs:
            f.write(w)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Pack up to 15 WAV files into a .stk kit")
    ap.add_argument('--folder', type=Path, help='Folder to scan for WAVs (first 15 alphabetically)')
    ap.add_argument('files', nargs='*', type=Path, help='Individual WAV files (up to 15)')
    ap.add_argument('--title', required=True, help='Kit title (used in device UI and internal paths)')
    ap.add_argument('-o', '--output', type=Path, help='Output .stk path; defaults to {currentDateTime}_kit.stk')
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    # Determine inputs
    if args.folder is not None and not args.folder.exists():
        raise SystemExit(f"Folder not found: {args.folder}")
    if args.folder is not None and not args.folder.is_dir():
        raise SystemExit(f"Not a folder: {args.folder}")

    try:
        wavs, names = _pick_samples(args.folder, args.files)
    except Exception as e:
        raise SystemExit(f"Error preparing samples: {e}")

    # Build KTDT and write file
    paths = _make_paths(args.title, names)
    try:
        ktdt = _build_ktdt(paths)
    except Exception as e:
        raise SystemExit(f"Error building KTDT: {e}")

    # Output path
    out_path = args.output
    if out_path is None:
        ts = _dt.datetime.now().strftime('%Y%m%d_%H%M%S')
        out_path = Path(f"{ts}_kit.stk")
    else:
        if out_path.suffix.lower() != '.stk':
            out_path = out_path.with_suffix('.stk')

    try:
        _write_stk(out_path, ktdt, wavs)
    except Exception as e:
        raise SystemExit(f"Error writing .stk: {e}")

    # Quick sanity: first RIFF should start at 0x10 + 0x1084 = 0x10A4
    size = out_path.stat().st_size
    print(f"Wrote {out_path} ({size} bytes)")
    print("First RIFF should begin at 0x10A4; KTDT size = 0x1084; entries = 15")


if __name__ == '__main__':
    main()

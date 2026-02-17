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

#4228
KTDT_SIZE = 0x1084
MAGIC = b"VDK0PR \x00"
KTDT_TAG = b"KTDT"
HEADER_RESERVED = b"\x00" * 4

TARGET_RATE = 48000
TARGET_WIDTH = 2  # bytes -> 16-bit
TARGET_CHANNELS = 1  # mono

# A conservative parameter prefix seen in the provided kits
#  - 0x64 (Level=100), 0x00, 0x00, 0x7F, then zeros, then a DWORD 0x00000040, then zeros
# In the actual file, these follow the path in each 280-byte entry.
PARAM_SUFFIX = (b"\x64\x00\x00\x7F"  # level=100, pitch=0, pan/vel=127
                + b"\x00" * 12
                + struct.pack('<I', 0x40)
                + b"\x00" * 4)  # Total 24 bytes

# Observed extra chunks in working kits: cue (28 bytes) + LIST (30 bytes)
# Total 36 + 38 = 74 bytes of extra header before 'data' chunk
CUE_CHUNK = (b"cue \x1c\x00\x00\x00"
             + b"\x01\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00"
             + b"data\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00")
LIST_CHUNK = (b"LIST\x1e\x00\x00\x00"
              + b"adtllabl\x12\x00\x00\x00\x01\x00\x00\x00"
              + b"Tempo: 000.0\x00\x00")

# 12-byte footer at end of KTDT (at offset 4200)
# Contains 0x64 (100) at offset 8, likely a volume parameter.
KTDT_FOOTER = b"\x00" * 8 + b"\x64\x00\x00\x00"


def _read_wav_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _to_pcm16_48k(raw: bytes, target_channels: int) -> bytes:
    """Convert a WAV file (bytes) to 48kHz, 16-bit PCM WAV bytes.
    Uses wave+audioop from the stdlib; handles PCM formats.
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

    # Convert bit depth to 16-bit linear PCM if needed
    if sampwidth != TARGET_WIDTH:
        frames = audioop.lin2lin(frames, sampwidth, TARGET_WIDTH)
        sampwidth = TARGET_WIDTH

    # Convert channels
    if nch != target_channels:
        if target_channels == 1:
            # Downmix to mono
            frames = audioop.tomono(frames, sampwidth, 1/nch, 1/nch)
        elif target_channels == 2 and nch == 1:
            # Expand mono to stereo
            frames = audioop.tostereo(frames, sampwidth, 1, 1)
        else:
            # Multi-channel to stereo: downmix to mono first, then to stereo
            # (or we could just use tomono and then tostereo)
            mono_frames = audioop.tomono(frames, sampwidth, 1/nch, 1/nch)
            frames = audioop.tostereo(mono_frames, sampwidth, 1, 1)
        nch = target_channels

    # Resample to 48kHz
    if fr != TARGET_RATE:
        # audioop.ratecv returns (converted_data, state)
        frames, _ = audioop.ratecv(frames, sampwidth, nch, fr, TARGET_RATE, None)
        fr = TARGET_RATE

    # Build a new standard WAV container
    out_b = io.BytesIO()
    with wave.open(out_b, 'wb') as w:
        w.setnchannels(target_channels)
        w.setsampwidth(TARGET_WIDTH)
        w.setframerate(TARGET_RATE)
        w.writeframes(frames)
    
    # Mirror structure of working kits: fmt, cue, LIST, then data.
    # We must insert the extra chunks and update the RIFF size.
    orig = out_b.getvalue()
    # RIFF header (12) + fmt chunk (16+8) + data tag/size (8) + audio data
    fmt_chunk = orig[12:12+24]
    data_tag_size = orig[12+24:12+24+8]
    audio_data = orig[12+24+8:]
    
    new_riff_size = 4 + len(fmt_chunk) + len(CUE_CHUNK) + len(LIST_CHUNK) + len(data_tag_size) + len(audio_data)
    
    final = (b"RIFF" + struct.pack('<I', new_riff_size) + b"WAVE"
             + fmt_chunk
             + CUE_CHUNK
             + LIST_CHUNK
             + data_tag_size
             + audio_data)
    return final


def _pick_samples(folder: Path, files: list[Path], target_channels: int) -> tuple[list[bytes], list[str]]:
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
        converted.append(_to_pcm16_48k(b, target_channels))
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


def _build_ktdt(paths: list[bytes], first_wav_len: int) -> bytes:
    # Each entry is 280 bytes. Path at offset 0, params at offset 256.
    # Total 15 * 280 = 4200.
    # KTDT_SIZE is 4228 (0x1084).
    # Footer (12 bytes) starts at 4200.
    # First ISDT (16 bytes) starts at 4212.
    entry_size = 280
    buf = bytearray(KTDT_SIZE)
    for i in range(15):
        off = i * entry_size
        path = paths[i]
        if len(path) > 256:
            path = path[:255] + b"\x00"
        buf[off : off + len(path)] = path
        buf[off + 256 : off + 256 + len(PARAM_SUFFIX)] = PARAM_SUFFIX
    
    # Add footer
    buf[4200 : 4200 + 12] = KTDT_FOOTER
    
    # Add first ISDT (index 0)
    # ISDT block: "ISDT", size (4), index (4), unknown constant (4)
    isdt = b"ISDT" + struct.pack('<I', first_wav_len) + struct.pack('<I', 0) + b"\x01\x00\x00\x00"
    buf[4212 : 4212 + 16] = isdt
    
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
        # It now includes the 12-byte footer and the first ISDT block.
        f.write(ktdt_body)
        
        # Append WAVs with ISDT prefix
        # First sample's ISDT is already in ktdt_body.
        for i, w in enumerate(wavs):
            if i == 0:
                # First sample only writes the WAV data.
                f.write(w)
            else:
                # ISDT block: "ISDT", size (4), index (4), unknown constant (4)
                isdt = b"\x00ISDT" + struct.pack('<I', len(w)) + struct.pack('<I', i) + b"\x01\x00\x00\x00"
                f.write(isdt)
                f.write(w)
            
            # Pad each sample to 2-byte boundary if needed? 
            # Reference kits seem to have a single null byte between samples in some cases.
            if i != (len(wavs) - 1):
                f.write(b"\x00")
        f.write(b"\x00\x00") #two end terminating bytes

def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Pack up to 15 WAV files into a .stk kit")
    ap.add_argument('--folder', type=Path, help='Folder to scan for WAVs (first 15 alphabetically)')
    ap.add_argument('files', nargs='*', type=Path, help='Individual WAV files (up to 15)')
    ap.add_argument('--title', required=True, help='Kit title (used in device UI and internal paths)')
    ap.add_argument('-o', '--output', type=Path, help='Output .stk path; defaults to {currentDateTime}_kit.stk')
    
    group = ap.add_mutually_exclusive_group()
    group.add_argument('--stereo', action='store_const', dest='channels', const=2, default=2,
                       help='Convert to stereo (default)')
    group.add_argument('--mono', action='store_const', dest='channels', const=1,
                       help='Convert to mono')
    
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    # Determine inputs
    if args.folder is not None and not args.folder.exists():
        raise SystemExit(f"Folder not found: {args.folder}")
    if args.folder is not None and not args.folder.is_dir():
        raise SystemExit(f"Not a folder: {args.folder}")

    try:
        wavs, names = _pick_samples(args.folder, args.files, args.channels)
    except Exception as e:
        raise SystemExit(f"Error preparing samples: {e}")

    # Build KTDT and write file
    paths = _make_paths(args.title, names)
    try:
        first_wav_len = len(wavs[0]) if wavs else 0
        ktdt = _build_ktdt(paths, first_wav_len)
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

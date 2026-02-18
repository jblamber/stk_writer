#!/usr/bin/env python3
"""
stkpack.py - STK Kit File Packer for Sonicware Devices

This is not any sort of official Sonicware product. This script is provided for
educational and personal purposes only by a passionate Sonicware fan.

This utility packs up to 15 WAV audio files into a single .stk kit file
compatible with Sonicware devices (e.g., SmplTrek or ELZ1 play). The tool automatically
converts audio samples to the required format: 48kHz sample rate, 16-bit PCM,
and either mono or stereo channels as specified.

Key features:
- Accepts WAV files from a folder or as individual file arguments
- Converts audio to device-compatible format (48kHz, 16-bit PCM)
- Supports both mono and stereo output modes
- Pads kits with fewer than 15 samples using duplicates
- Generates internal file paths compatible with SmplTrek's filesystem structure
- Creates properly formatted KTDT (kit data) and ISDT (instrument data) chunks

The output .stk file contains:
- A file header with magic bytes and metadata
- A KTDT chunk (4228 bytes) with sample paths and parameters
- Up to 15 embedded WAV files with ISDT prefixes
- Proper padding and alignment for device compatibility

Usage:
    python3 stkpack.py --title "MyKit" --folder /path/to/samples
    python3 stkpack.py --title "MyKit" sample1.wav sample2.wav -o output.stk
"""
import argparse
import datetime as _dt
import io
import struct
import subprocess
import tempfile
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

# Standard parameter suffix for each 280-byte entry.
# Layout (24 bytes):
# 0: Volume (0-100, default 100)
# 1: Pan (-64 to 63, default 0)
# 2-15: Zeros
# 16: FX Send (0-127, default 0)
# 17-18: Pitch (-1200 to 1200 cents, stored as cents * 256 / 100, i.e. semitones * 256)
# 19-23: Zeros
def _get_param_suffix(volume=100, pitch=0, pan=0, fx_send=0):
    # Volume: Byte 0
    # Pan: Byte 1 (-64 to 63)
    # Byte 2-3: Zeros (historically 0x00 0x7F but 0,0 seems fine for device)
    # FX Send: Byte 16 (0-127)
    # Pitch: Bytes 17-18 (Signed 16-bit, in 1/256 semitone units)
    pitch_units = int(pitch * 256 / 100)
    # Ensure FX send is correctly packed as a single byte at 16,
    # and pitch as a signed short at 17-18.
    return (struct.pack('<bbBB', volume, pan, 0, 0) # bytes 0-3
            + b"\x00" * 12                          # bytes 4-15
            + struct.pack('<BhB', fx_send, pitch_units, 0) # bytes 16-19
            + b"\x00" * 4)                          # bytes 20-23

# 12-byte footer at end of KTDT (at offset 4200)

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


def _build_ktdt(paths: list[bytes], first_wav_len: int, params: list[dict] = None) -> bytes:
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
        
        p = params[i] if params and i < len(params) else {}
        suffix = _get_param_suffix(
            volume=p.get('volume', 100),
            pitch=p.get('pitch', 0),
            pan=p.get('pan', 0),
            fx_send=p.get('fx_send', 0)
        )
        buf[off + 256 : off + 256 + 24] = suffix
    
    # Add footer
    buf[4200 : 4200 + 12] = KTDT_FOOTER
    
    # Add first ISDT (index 0)
    # ISDT block: "ISDT", size (4), index (4), unknown constant (4)
    # The 'size' field in ISDT appears to be len(wav) + 26 bytes in the reference file?
    # No, RIFF_SIZE is len(wav) - 8. 
    # Reference: ISDT_SIZE_FIELD = RIFF_SIZE + 26 = (len(wav) - 8) + 26 = len(wav) + 18.
    isdt_size = first_wav_len + 18
    isdt = b"ISDT" + struct.pack('<I', isdt_size) + struct.pack('<I', 0) + b"\x01\x00\x00\x00"
    buf[4212 : 4212 + 16] = isdt
    
    return bytes(buf)


def _prompt_int(prompt, default, min_val, max_val):
    while True:
        val = input(f"{prompt} (default {default}, {min_val} to {max_val}): ").strip()
        if not val:
            return default
        try:
            i = int(val)
            if min_val <= i <= max_val:
                return i
            print(f"Value must be between {min_val} and {max_val}.")
        except ValueError:
            print("Invalid input. Please enter an integer.")

def _preview_audio(wav_bytes: bytes):
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            tf.write(wav_bytes)
            tf_path = tf.name
        
        # Determine player
        players = ["afplay", "aplay", "play"]
        played = False
        for p in players:
            try:
                subprocess.run([p, tf_path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                played = True
                break
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        if not played:
            print("Could not find a working audio player (afplay, aplay, or play).")
        
        Path(tf_path).unlink(missing_ok=True)
    except Exception as e:
        print(f"Preview error: {e}")

def _customize_samples(wavs: list[bytes], names: list[str]) -> list[dict]:
    params = []
    print("\n--- Sample Customization ---")
    print("For each sample, enter values or press Enter for default.")
    print("Press 'p' + Enter at any prompt to preview the sound.")
    
    for i, (w, name) in enumerate(zip(wavs, names)):
        print(f"\nSample {i+1}/15: {name}")
        
        p = {'volume': 100, 'pitch': 0, 'pan': 0, 'fx_send': 0}
        
        def get_input(prompt, key, min_v, max_v):
            while True:
                val = input(f"  {prompt} (default {p[key]}, {min_v} to {max_v}, 'p' to preview): ").strip().lower()
                if val == 'p':
                    _preview_audio(w)
                    continue
                if not val:
                    return p[key]
                try:
                    i_val = int(val)
                    if min_v <= i_val <= max_v:
                        return i_val
                    print(f"  Value must be between {min_v} and {max_v}.")
                except ValueError:
                    print("  Invalid input.")

        p['volume'] = get_input("Volume", 'volume', 0, 100)
        p['pitch'] = get_input("Pitch", 'pitch', -1200, 1200)
        p['pan'] = get_input("Pan", 'pan', -64, 63)
        p['fx_send'] = get_input("FX Send", 'fx_send', 0, 127)
        params.append(p)
        
    return params


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
                # Size field is len(wav) + 18.
                isdt_size = len(w) + 18
                isdt = b"\x00\x00ISDT" + struct.pack('<I', isdt_size) + struct.pack('<I', i) + b"\x01\x00\x00\x00"
                f.write(isdt)
                f.write(w)
            
            # Pad each sample to 2-byte boundary if needed? 
            # Reference kits seem to have two null bytes between samples (including the one inside ISDT prefix if we consider it part of it).
            # We already write \x00\x00ISDT for i > 0.
            # For the very last one, we add \x00\x00.
            if i == (len(wavs) - 1):
                f.write(b"\x00\x00")

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
    ap.add_argument('--customize', action='store_true',
                       help='Interactively customize sample parameters (Volume, Pitch, Pan, FX Send)')
    
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

    # Interactive customization
    params = None
    if args.customize:
        try:
            params = _customize_samples(wavs, names)
        except (EOFError, KeyboardInterrupt):
            raise SystemExit("\nCustomization cancelled.")

    # Build KTDT and write file
    paths = _make_paths(args.title, names)
    try:
        first_wav_len = len(wavs[0]) if wavs else 0
        ktdt = _build_ktdt(paths, first_wav_len, params=params)
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

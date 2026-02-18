"""
STK WAV Extractor

This is not any sort of official Sonicware product. This script is provided for
educational and personal purposes only by a passionate Sonicware fan.

This script extracts individual WAV audio files embedded within Sonicware .stk kit files.

STK files are kit files used by Sonicware devices (such as SmplTrek) that contain
multiple audio samples packed together. This utility scans through the STK file structure,
locates embedded WAV files by their RIFF headers, and extracts them as separate .wav files.

The script handles:
- Reading binary STK file data
- Skipping the KTDT header/metadata section (first 0x10A4 bytes)
- Scanning for RIFF headers to identify WAV files
- Extracting up to 15 WAV samples with proper size calculation
- Saving extracted samples with sequential naming (sample_00.wav, sample_01.wav, etc.)

Usage:
    python3 extract_wavs.py <input.stk> <output_dir>

Example:
    python3 extract_wavs.py MyKit.stk extracted_samples/
"""

import struct
import sys
from pathlib import Path


def extract_wavs(stk_path: Path, output_dir: Path):
    """
    Extract WAV files from a Sonicware STK kit file.

    This function reads an STK file, skips the KTDT metadata section, and extracts
    up to 15 embedded WAV files by scanning for RIFF headers and parsing their size fields.

    Args:
        stk_path: Path to the input .stk file to extract from
        output_dir: Path to the directory where extracted WAV files will be saved

    Returns:
        None. Prints extraction progress to stdout and writes WAV files to output_dir.
    """
    if not stk_path.exists():
        print(f"File not found: {stk_path}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(stk_path, 'rb') as f:
        data = f.read()

    # KTDT body ends at 0x10A4 (4260 bytes) - this is the metadata/header section
    # containing kit information. The actual audio data follows after this offset.
    audio_data = data[0x10A4:]
    
    pos = 0
    count = 0
    while pos < len(audio_data):
        # Look for RIFF header
        if audio_data[pos:pos+4] == b'RIFF':
            # Read size
            size = struct.unpack('<I', audio_data[pos+4:pos+8])[0]
            total_size = size + 8
            wav_content = audio_data[pos : pos + total_size]
            
            out_file = output_dir / f"sample_{count:02d}.wav"
            out_file.write_bytes(wav_content)
            print(f"Extracted {out_file} ({total_size} bytes)")
            
            pos += total_size
            count += 1
            if count >= 15:
                break
        else:
            # Maybe some padding?
            pos += 1
            if pos > len(audio_data) - 8:
                break

    print(f"Extracted {count} samples.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 extract_wavs.py <input.stk> <output_dir>")
        sys.exit(1)
    
    extract_wavs(Path(sys.argv[1]), Path(sys.argv[2]))

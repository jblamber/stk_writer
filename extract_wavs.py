import struct
import sys
from pathlib import Path
import io
import wave

def extract_wavs(stk_path: Path, output_dir: Path):
    if not stk_path.exists():
        print(f"File not found: {stk_path}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(stk_path, 'rb') as f:
        data = f.read()

    # KTDT body ends at 0x10A4
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

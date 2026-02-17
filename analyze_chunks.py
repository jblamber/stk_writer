import struct
import sys

def analyze(path):
    print(f"--- {path} ---")
    with open(path, 'rb') as f:
        header = f.read(12)
        if header[:4] != b'RIFF':
            print("Not a RIFF file")
            return
        file_size = struct.unpack('<I', header[4:8])[0]
        print(f"RIFF size: {file_size}")
        
        pos = 12
        while True:
            f.seek(pos)
            tag_raw = f.read(4)
            if not tag_raw or len(tag_raw) < 4:
                break
            tag = tag_raw.decode(errors='replace')
            size_raw = f.read(4)
            if not size_raw or len(size_raw) < 4:
                break
            size = struct.unpack('<I', size_raw)[0]
            print(f"Chunk: {tag} at {pos:x}, size: {size}")
            
            if tag == 'fmt ':
                f.seek(pos + 8)
                fmt_data = f.read(min(size, 16))
                wFormatTag, nChannels, nSamplesPerSec, nAvgBytesPerSec, nBlockAlign, wBitsPerSample = struct.unpack('<HHIIHH', fmt_data)
                print(f"  fmt: {wFormatTag=}, {nChannels=}, {nSamplesPerSec=}, {wBitsPerSample=}")
            
            pos += 8 + size
            if size % 2 == 1:
                pos += 1
            if pos >= file_size + 8:
                break

if __name__ == "__main__":
    analyze(sys.argv[1])

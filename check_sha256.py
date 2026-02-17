import hashlib
import sys
from pathlib import Path

def get_sha256(file_path):
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        return f"Error: {e}"

def main():
    if len(sys.argv) != 3:
        print("Usage: python3 check_sha256.py <file1> <file2>")
        sys.exit(1)

    file1 = Path(sys.argv[1])
    file2 = Path(sys.argv[2])

    if not file1.is_file():
        print(f"Error: {file1} is not a file.")
        sys.exit(1)
    if not file2.is_file():
        print(f"Error: {file2} is not a file.")
        sys.exit(1)

    sha1 = get_sha256(file1)
    sha2 = get_sha256(file2)

    print(f"SHA256 ({file1.name}): {sha1}")
    print(f"SHA256 ({file2.name}): {sha2}")

    if sha1 == sha2:
        print("MATCH: Files are identical.")
    else:
        print("MISMATCH: Files are different.")

if __name__ == "__main__":
    main()

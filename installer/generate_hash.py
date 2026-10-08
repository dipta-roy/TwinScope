
import hashlib
import os
import sys


def calculate_sha256(filepath: str) -> str:
    """Calculates the SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest().lower()


def calculate_sha1(filepath: str) -> str:
    """Calculates the SHA1 hash of a file."""
    sha1_hash = hashlib.sha1()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha1_hash.update(byte_block)
    return sha1_hash.hexdigest().lower()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python generate_hash.py <file_path>")
        sys.exit(1)

    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f"Error: File '{filepath}' not found.")
        sys.exit(1)

    filename = os.path.basename(filepath)
    sha1_val = calculate_sha1(filepath)
    sha256_val = calculate_sha256(filepath)

    # Standard format: <hash>  <filename>
    sha1_output = f"{sha1_val}  {filename}"
    sha256_output = f"{sha256_val}  {filename}"

    print(f"SHA1:   {sha1_output}")
    print(f"SHA256: {sha256_output}")

    # Save .sha1 file
    sha1_file = filepath + ".sha1"
    with open(sha1_file, "w", encoding="utf-8") as f:
        f.write(sha1_output + "\n")
    print(f"SHA1 saved to: {sha1_file}")

    # Save .sha256.txt file
    sha256_file = filepath + ".sha256.txt"
    with open(sha256_file, "w", encoding="utf-8") as f:
        f.write(sha256_output + "\n")
    print(f"SHA256 saved to: {sha256_file}")


if __name__ == "__main__":
    main()


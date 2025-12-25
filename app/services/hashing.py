"""
Hashing service for file integrity verification.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import BinaryIO, Callable, Iterator, Optional


class HashAlgorithm(Enum):
    """Supported hash algorithms."""
    MD5 = auto()
    SHA1 = auto()
    SHA256 = auto()
    SHA512 = auto()
    XXH64 = auto()  # Fast non-cryptographic hash
    
    @property
    def name(self) -> str:
        return self._name_.lower()


@dataclass
class HashResult:
    """Result of a hash operation."""
    algorithm: HashAlgorithm
    hash_hex: str
    hash_bytes: bytes
    file_size: int
    
    def matches(self, other: 'HashResult') -> bool:
        """Check if this hash matches another."""
        return (self.algorithm == other.algorithm and 
                self.hash_hex == other.hash_hex)


@dataclass
class HashProgress:
    """Progress information for hashing operation."""
    bytes_processed: int
    total_bytes: int
    percent: float
    file_path: Optional[Path] = None


class HashingService:
    """Service for computing file hashes."""
    
    def __init__(
        self,
        default_algorithm: HashAlgorithm = HashAlgorithm.SHA256,
        chunk_size: int = 65536
    ):
        self.default_algorithm = default_algorithm
        self.chunk_size = chunk_size
        
        # Try to import xxhash for fast hashing
        try:
            import xxhash
            self._xxhash_available = True
        except ImportError:
            self._xxhash_available = False
    
    def hash_file(
        self,
        path: Path | str,
        algorithm: Optional[HashAlgorithm] = None,
        progress_callback: Optional[Callable[[HashProgress], None]] = None
    ) -> HashResult:
        """
        Compute hash of a file.
        
        Args:
            path: Path to the file
            algorithm: Hash algorithm to use
            progress_callback: Called with progress updates
            
        Returns:
            HashResult with the computed hash
        """
        path = Path(path)
        algorithm = algorithm or self.default_algorithm
        
        file_size = path.stat().st_size
        hasher = self._create_hasher(algorithm)
        
        bytes_processed = 0
        
        with open(path, 'rb') as f:
            while chunk := f.read(self.chunk_size):
                hasher.update(chunk)
                bytes_processed += len(chunk)
                
                if progress_callback:
                    progress = HashProgress(
                        bytes_processed=bytes_processed,
                        total_bytes=file_size,
                        percent=(bytes_processed / file_size * 100) if file_size > 0 else 100,
                        file_path=path
                    )
                    progress_callback(progress)
        
        if algorithm == HashAlgorithm.XXH64:
            hash_hex = hasher.hexdigest()
            hash_bytes = hasher.digest()
        else:
            hash_hex = hasher.hexdigest()
            hash_bytes = hasher.digest()
        
        return HashResult(
            algorithm=algorithm,
            hash_hex=hash_hex,
            hash_bytes=hash_bytes,
            file_size=file_size
        )
    
    def hash_bytes(
        self,
        data: bytes,
        algorithm: Optional[HashAlgorithm] = None
    ) -> HashResult:
        """Compute hash of bytes."""
        algorithm = algorithm or self.default_algorithm
        hasher = self._create_hasher(algorithm)
        hasher.update(data)
        
        return HashResult(
            algorithm=algorithm,
            hash_hex=hasher.hexdigest(),
            hash_bytes=hasher.digest(),
            file_size=len(data)
        )
    
    def hash_string(
        self,
        text: str,
        algorithm: Optional[HashAlgorithm] = None,
        encoding: str = 'utf-8'
    ) -> HashResult:
        """Compute hash of a string."""
        return self.hash_bytes(text.encode(encoding), algorithm)
    
    def compare_files_by_hash(
        self,
        path1: Path | str,
        path2: Path | str,
        algorithm: Optional[HashAlgorithm] = None
    ) -> bool:
        """Compare two files by their hash values."""
        hash1 = self.hash_file(path1, algorithm)
        hash2 = self.hash_file(path2, algorithm)
        return hash1.matches(hash2)
    
    def verify_hash(
        self,
        path: Path | str,
        expected_hash: str,
        algorithm: Optional[HashAlgorithm] = None
    ) -> bool:
        """Verify a file's hash against an expected value."""
        result = self.hash_file(path, algorithm)
        return result.hash_hex.lower() == expected_hash.lower()
    
    def hash_directory(
        self,
        path: Path | str,
        algorithm: Optional[HashAlgorithm] = None,
        include_names: bool = True,
        progress_callback: Optional[Callable[[HashProgress], None]] = None
    ) -> HashResult:
        """
        Compute a combined hash of all files in a directory.
        
        Args:
            path: Directory path
            algorithm: Hash algorithm
            include_names: Include file names in hash (order-independent if False)
            progress_callback: Progress callback
            
        Returns:
            Combined hash of all files
        """
        path = Path(path)
        algorithm = algorithm or self.default_algorithm
        
        # Collect all files
        files: list[Path] = []
        for root, dirs, filenames in os.walk(path):
            dirs.sort()  # Consistent ordering
            for filename in sorted(filenames):
                files.append(Path(root) / filename)
        
        # Calculate total size
        total_size = sum(f.stat().st_size for f in files)
        bytes_processed = 0
        
        # Hash all files
        combined_hasher = self._create_hasher(algorithm)
        
        for file_path in files:
            if include_names:
                # Include relative path in hash
                rel_path = file_path.relative_to(path)
                combined_hasher.update(str(rel_path).encode('utf-8'))
            
            file_hash = self.hash_file(file_path, algorithm)
            combined_hasher.update(file_hash.hash_bytes)
            
            bytes_processed += file_hash.file_size
            
            if progress_callback:
                progress = HashProgress(
                    bytes_processed=bytes_processed,
                    total_bytes=total_size,
                    percent=(bytes_processed / total_size * 100) if total_size > 0 else 100,
                    file_path=file_path
                )
                progress_callback(progress)
        
        return HashResult(
            algorithm=algorithm,
            hash_hex=combined_hasher.hexdigest(),
            hash_bytes=combined_hasher.digest(),
            file_size=total_size
        )
    
    def _create_hasher(self, algorithm: HashAlgorithm):
        """Create a hasher for the given algorithm."""
        if algorithm == HashAlgorithm.MD5:
            return hashlib.md5()
        elif algorithm == HashAlgorithm.SHA1:
            return hashlib.sha1()
        elif algorithm == HashAlgorithm.SHA256:
            return hashlib.sha256()
        elif algorithm == HashAlgorithm.SHA512:
            return hashlib.sha512()
        elif algorithm == HashAlgorithm.XXH64:
            if self._xxhash_available:
                import xxhash
                return xxhash.xxh64()
            else:
                # Fall back to SHA256
                return hashlib.sha256()
        else:
            raise ValueError(f"Unknown algorithm: {algorithm}")


class IncrementalHasher:
    """
    Incremental hasher for streaming data.
    
    Useful for hashing large files or network streams.
    """
    
    def __init__(
        self,
        algorithm: HashAlgorithm = HashAlgorithm.SHA256
    ):
        self.algorithm = algorithm
        self._service = HashingService()
        self._hasher = self._service._create_hasher(algorithm)
        self._size = 0
    
    def update(self, data: bytes) -> None:
        """Add data to the hash."""
        self._hasher.update(data)
        self._size += len(data)
    
    def finalize(self) -> HashResult:
        """Finalize and return the hash result."""
        return HashResult(
            algorithm=self.algorithm,
            hash_hex=self._hasher.hexdigest(),
            hash_bytes=self._hasher.digest(),
            file_size=self._size
        )
    
    def copy(self) -> 'IncrementalHasher':
        """Create a copy of the current state."""
        new_hasher = IncrementalHasher(self.algorithm)
        new_hasher._hasher = self._hasher.copy()
        new_hasher._size = self._size
        return new_hasher
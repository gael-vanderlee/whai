"""SSL context caching optimization for LiteLLM import performance.

This module patches ssl.create_default_context to cache SSL contexts,
significantly reducing LiteLLM import time on Windows (from ~4s to ~3s).

The optimization caches SSL contexts based on their parameters (cafile, capath, cadata),
avoiding expensive certificate reloading that happens 184 times during LiteLLM import.

This must be applied BEFORE importing litellm to be effective.
"""

import ssl
from typing import Optional, Tuple, Dict


# Original function
_original_create_default_context = ssl.create_default_context

# Cache for SSL contexts
_ssl_context_cache: Dict[Tuple[Optional[str], Optional[str], Optional[bytes]], ssl.SSLContext] = {}

# Track if patch is applied
_patch_applied = False


def _cached_create_default_context(
    cafile: Optional[str] = None,
    capath: Optional[str] = None,
    cadata: Optional[bytes] = None,
) -> ssl.SSLContext:
    """Cached version of ssl.create_default_context.
    
    Caches SSL contexts based on their parameters to avoid reloading
    certificates, which is very slow on Windows.
    
    Args:
        cafile: Path to certificate file
        capath: Path to certificate directory  
        cadata: Certificate data as bytes
        
    Returns:
        SSLContext instance (cached if previously created with same params)
    """
    # Create cache key from parameters
    cache_key = (cafile, capath, cadata)
    
    # Return cached context if available
    if cache_key in _ssl_context_cache:
        return _ssl_context_cache[cache_key]
    
    # Create new context using original function
    context = _original_create_default_context(cafile=cafile, capath=capath, cadata=cadata)
    
    # Cache it for future use
    _ssl_context_cache[cache_key] = context
    
    return context


def apply() -> None:
    """Apply the SSL context caching patch.
    
    This must be called BEFORE importing litellm to be effective.
    Safe to call multiple times (idempotent).
    """
    global _patch_applied
    
    if not _patch_applied:
        ssl.create_default_context = _cached_create_default_context
        _patch_applied = True


def is_applied() -> bool:
    """Check if the patch is currently applied."""
    return _patch_applied


def clear_cache() -> None:
    """Clear the SSL context cache (but keep patch applied)."""
    _ssl_context_cache.clear()


def get_cache_size() -> int:
    """Get the number of cached SSL contexts."""
    return len(_ssl_context_cache)


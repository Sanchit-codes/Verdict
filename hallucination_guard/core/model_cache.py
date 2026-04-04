"""
Model Cache System for HallucinationGuard SDK

Provides centralized model caching, preloading, and management to optimize
performance and avoid repeated model loading delays.
"""
import logging
import threading
import time
from typing import Dict, Optional, Any, Callable
from concurrent.futures import ThreadPoolExecutor, Future

logger = logging.getLogger(__name__)


class ModelCache:
    """Centralized cache for ML models with preloading and background loading capabilities."""
    
    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._loading_futures: Dict[str, Future] = {}
        self._preload_functions: Dict[str, Callable[[], Any]] = {}
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="model-loader")
        self._lock = threading.RLock()
        
    def register_model(self, name: str, load_function: Callable[[], Any], preload: bool = False):
        """Register a model with its loading function.
        
        Args:
            name: Unique model name/key
            load_function: Function that loads and returns the model
            preload: Whether to start preloading immediately in background
        """
        with self._lock:
            self._preload_functions[name] = load_function
            
            if preload:
                self._start_background_load(name)
    
    def get_model(self, name: str, timeout_ms: Optional[float] = None) -> Optional[Any]:
        """Get a model from cache, loading it if necessary.
        
        Args:
            name: Model name/key
            timeout_ms: Timeout in milliseconds for loading (None = wait indefinitely)
            
        Returns:
            Loaded model or None if loading failed/timeout
        """
        with self._lock:
            # Check if already cached
            if name in self._cache:
                return self._cache[name]
            
            # Check if currently loading
            if name in self._loading_futures:
                future = self._loading_futures[name]
                if timeout_ms is not None:
                    timeout_sec = timeout_ms / 1000.0
                else:
                    timeout_sec = None
                    
                try:
                    model = future.result(timeout=timeout_sec)
                    self._cache[name] = model
                    del self._loading_futures[name]
                    return model
                except TimeoutError:
                    logger.warning(f"Model '{name}' loading timeout after {timeout_ms}ms")
                    return None
                except Exception as e:
                    logger.error(f"Model '{name}' loading failed: {e}")
                    del self._loading_futures[name]
                    return None
            
            # Start synchronous loading
            if name in self._preload_functions:
                try:
                    start_time = time.perf_counter()
                    model = self._preload_functions[name]()
                    load_time = (time.perf_counter() - start_time) * 1000
                    
                    self._cache[name] = model
                    logger.info(f"Model '{name}' loaded in {load_time:.1f}ms")
                    return model
                    
                except Exception as e:
                    logger.error(f"Failed to load model '{name}': {e}")
                    return None
            
            return None
    
    def preload_model(self, name: str):
        """Start background preloading of a model.
        
        Args:
            name: Model name/key to preload
        """
        with self._lock:
            if name not in self._loading_futures and name not in self._cache:
                self._start_background_load(name)
    
    def preload_all(self):
        """Start background preloading of all registered models."""
        with self._lock:
            for name in self._preload_functions:
                if name not in self._loading_futures and name not in self._cache:
                    self._start_background_load(name)
    
    def clear_cache(self):
        """Clear all cached models."""
        with self._lock:
            self._cache.clear()
            # Cancel any ongoing loads
            for future in self._loading_futures.values():
                future.cancel()
            self._loading_futures.clear()
    
    def is_cached(self, name: str) -> bool:
        """Check if a model is currently cached."""
        with self._lock:
            return name in self._cache
    
    def is_loading(self, name: str) -> bool:
        """Check if a model is currently being loaded."""
        with self._lock:
            return name in self._loading_futures
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            return {
                "cached_models": list(self._cache.keys()),
                "loading_models": list(self._loading_futures.keys()),
                "registered_models": list(self._preload_functions.keys()),
                "cache_size": len(self._cache),
                "loading_count": len(self._loading_futures)
            }
    
    def _start_background_load(self, name: str):
        """Start background loading of a model."""
        if name not in self._preload_functions:
            return
            
        future = self._executor.submit(self._preload_functions[name])
        self._loading_futures[name] = future
        
        # Add callback to move to cache when done
        def on_complete(fut):
            try:
                if not fut.cancelled():
                    model = fut.result()
                    with self._lock:
                        self._cache[name] = model
                        if name in self._loading_futures:
                            del self._loading_futures[name]
                    logger.info(f"Model '{name}' preloaded successfully")
            except Exception as e:
                logger.error(f"Background loading failed for model '{name}': {e}")
                with self._lock:
                    if name in self._loading_futures:
                        del self._loading_futures[name]
        
        future.add_done_callback(on_complete)


# Global model cache instance
model_cache = ModelCache()


def get_model_cache() -> ModelCache:
    """Get the global model cache instance."""
    return model_cache


def preload_models():
    """Preload all commonly used models in background."""
    cache = get_model_cache()
    cache.preload_all()

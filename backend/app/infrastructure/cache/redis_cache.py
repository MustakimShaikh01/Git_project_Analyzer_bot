import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

class RedisCache:
    def __init__(self, url: str):
        try:
            import redis
            self.client = redis.from_url(url)
            # Test connection
            self.client.ping()
            logger.info("Connected to Redis at %s", url)
        except Exception as e:
            logger.warning("Could not connect to Redis: %s. Caching will be disabled.", e)
            self.client = None

    def get(self, key: str) -> Optional[str]:
        if not self.client:
            return None
        try:
            val = self.client.get(key)
            return val.decode("utf-8") if val else None
        except Exception as e:
            logger.error("Redis get error: %s", e)
            return None

    def setex(self, key: str, ttl: int, value: str):
        if not self.client:
            return
        try:
            self.client.setex(key, ttl, value)
        except Exception as e:
            logger.error("Redis setex error: %s", e)

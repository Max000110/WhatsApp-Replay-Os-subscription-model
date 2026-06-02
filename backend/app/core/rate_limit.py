import time
import uuid
from fastapi import Request, HTTPException, status
import redis.asyncio as aioredis
from app.config import settings

class RateLimiter:
    def __init__(self, limit: int, window: int, action: str):
        """
        Sliding-window Redis rate limiter with progressive IP-banning.
        :param limit: Allowed request count within the window.
        :param window: Window duration in seconds.
        :param action: Unique route/action key prefix.
        """
        self.limit = limit
        self.window = window
        self.action = action
        self.redis_client = aioredis.from_url(settings.REDIS_URL)

    async def __call__(self, request: Request):
        # Resolve real client IP considering reverse proxy headers
        ip = request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for") or request.client.host
        if "," in ip:
            ip = ip.split(",")[0].strip()

        # Check temporary IP bans
        ban_key = f"ip_ban:{ip}"
        is_banned = await self.redis_client.get(ban_key)
        if is_banned:
            ttl = await self.redis_client.ttl(ban_key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Your IP has been temporarily banned due to excessive rate limit violations. Retry in {ttl} seconds."
            )

        key = f"rate_limit:{self.action}:{ip}"
        now = time.time()
        clear_before = now - self.window
        unique_member = f"{now}-{uuid.uuid4()}"

        try:
            # Transaction block to execute atomic sliding window updates
            async with self.redis_client.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(key, 0, clear_before)
                pipe.zcard(key)
                pipe.zadd(key, {unique_member: now})
                pipe.expire(key, self.window + 10)
                res = await pipe.execute()
                
            current_requests = res[1]

            if current_requests >= self.limit:
                # Log violation count
                violation_key = f"rate_limit_violation:{ip}"
                violations = await self.redis_client.incr(violation_key)
                await self.redis_client.expire(violation_key, 600)
                
                # Check for brute force progressive ban
                if violations >= 5:
                    ban_duration = 300 * (violations - 4)  # progressive cooldown: 5min, 10min, 15min...
                    await self.redis_client.set(ban_key, "banned", ex=ban_duration)
                    await self.redis_client.delete(violation_key)
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=f"Too many requests. Your IP has been temporarily banned for {ban_duration} seconds."
                    )
                    
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please try again later."
                )
        except HTTPException:
            raise
        except Exception as e:
            # Graceful degradation if Redis becomes offline
            print(f"[RateLimiter] Error: {e}")
            return

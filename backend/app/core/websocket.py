import asyncio
import json
import redis
import redis.asyncio as aioredis
from fastapi import WebSocket
from app.config import settings

class ConnectionManager:
    def __init__(self):
        # tenant_id -> list of WebSocket connections
        self.active_connections: dict[str, list[WebSocket]] = {}
        self.redis_client = aioredis.from_url(settings.REDIS_URL)
        self.pubsub_tasks: dict[str, asyncio.Task] = {}

    async def connect(self, tenant_id: str, websocket: WebSocket):
        await websocket.accept()
        tenant_str = str(tenant_id)
        if tenant_str not in self.active_connections:
            self.active_connections[tenant_str] = []
            # Start pub/sub listener for this tenant
            task = asyncio.create_task(self.listen_redis_channel(tenant_str))
            self.pubsub_tasks[tenant_str] = task
        self.active_connections[tenant_str].append(websocket)
        print(f"[WebSocketManager] Client connected to tenant: {tenant_str}. Total active: {len(self.active_connections[tenant_str])}")

    def disconnect(self, tenant_id: str, websocket: WebSocket):
        tenant_str = str(tenant_id)
        if tenant_str in self.active_connections:
            if websocket in self.active_connections[tenant_str]:
                self.active_connections[tenant_str].remove(websocket)
            print(f"[WebSocketManager] Client disconnected from tenant: {tenant_str}")
            if not self.active_connections[tenant_str]:
                del self.active_connections[tenant_str]
                # Cancel pub/sub task
                if tenant_str in self.pubsub_tasks:
                    self.pubsub_tasks[tenant_str].cancel()
                    del self.pubsub_tasks[tenant_str]

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast_to_tenant(self, tenant_id: str, message: dict):
        tenant_str = str(tenant_id)
        if tenant_str in self.active_connections:
            disconnected = []
            for connection in self.active_connections[tenant_str]:
                try:
                    await connection.send_json(message)
                except Exception:
                    disconnected.append(connection)
            for conn in disconnected:
                self.disconnect(tenant_str, conn)

    async def listen_redis_channel(self, tenant_id: str):
        channel_name = f"tenant_events:{tenant_id}"
        pubsub = self.redis_client.pubsub()
        await pubsub.subscribe(channel_name)
        print(f"[WebSocketManager] Subscribed to Redis channel: {channel_name}")
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        await self.broadcast_to_tenant(tenant_id, data)
                    except Exception as e:
                        print(f"[WebSocketManager] Error processing Redis pubsub message: {e}")
        except asyncio.CancelledError:
            print(f"[WebSocketManager] Listener cancelled for Redis channel: {channel_name}")
        except Exception as e:
            print(f"[WebSocketManager] Redis PubSub listener error for tenant {tenant_id}: {e}")
        finally:
            try:
                await pubsub.unsubscribe(channel_name)
                await pubsub.close()
            except Exception:
                pass

    async def publish_event(self, tenant_id: str, event_type: str, data: dict):
        channel_name = f"tenant_events:{str(tenant_id)}"
        event = {"type": event_type, "data": data}
        try:
            await self.redis_client.publish(channel_name, json.dumps(event))
        except Exception as e:
            print(f"[WebSocketManager] Failed to publish event to Redis: {e}")

    async def broadcast_global_event(self, event_type: str, data: dict):
        """
        Broadcasts an event globally to all connected tenants.
        """
        event = {"type": event_type, "data": data}
        for tenant_id in list(self.active_connections.keys()):
            for connection in list(self.active_connections[tenant_id]):
                try:
                    await connection.send_json(event)
                except Exception:
                    pass
        for tenant_id in list(self.active_connections.keys()):
            channel_name = f"tenant_events:{str(tenant_id)}"
            try:
                await self.redis_client.publish(channel_name, json.dumps(event))
            except Exception:
                pass

websocket_manager = ConnectionManager()

def publish_tenant_event_sync(tenant_id: str, event_type: str, data: dict):
    """
    Synchronously publish a real-time event to a tenant's websocket channel.
    Useful from celery tasks or standard sync routes.
    """
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        channel_name = f"tenant_events:{str(tenant_id)}"
        event = {"type": event_type, "data": data}
        r.publish(channel_name, json.dumps(event))
    except Exception as e:
        print(f"[publish_tenant_event_sync] Failed to publish event: {e}")

import asyncio
import os
import logging

from typing import Optional

import aioredis
from sanic import Sanic, response

app = Sanic("ipset-app")
log = logging.getLogger(__name__)
KEY_EXPIRE_TIME = 60 * 60 * 24 * 7  # one week

@app.listener("before_server_start")
async def setup_redis(app, loop):
    app.redis = await aioredis.create_redis_pool("redis://localhost")

@app.listener("after_server_stop")
async def cleanup_redis(app, loop):
    app.redis.close()
    await app.redis.wait_closed()


async def check_redis(key: str) -> bool:
    return await app.redis.exists(key)


async def check_vault(key: str) -> bool:
    return False


CHECK_METHODS = [
    check_redis,
]


async def test_punch_key(key: str) -> bool:
    check_key = "ipset:" + key

    for check_method in CHECK_METHODS:
        key_exists = await check_method(check_key)
        if key_exists:
            break

    # Renew the key if the key exists.
    if key_exists:
        await app.redis.expire(check_key, KEY_EXPIRE_TIME)

    return key_exists


async def punch_hole(set_name: str, ip: str, timeout: Optional[int] = None) -> bool:
    args = [
        "add", str(set_name),
        "-exist",
        ip,
    ]

    # Add timeout if applicable.
    if timeout:
        args.extend(["timeout", str(timeout)])

    proc = await asyncio.create_subprocess_exec(
        "ipset",
        *args,
        stdout=asyncio.subprocess.PIPE,
    )

    await proc.wait()
    return proc.returncode == 0

 
@app.route("/")
async def test(request):
    return response.json({"hello": "world"})


@app.route("/punch", methods=["POST"])
async def punch(request):
    data = request.json

    # Handle missing key.
    if not request.json or "key" not in data:
        return response.json({"error": "key missing"}, status=500)

    # Handle invalid key.
    if not await test_punch_key(data["key"]):
        return response.json({"error": "key invalid"}, status=500)

    await punch_hole("vault-allow", request.ip)

    return response.text("", status=204)

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        debug="DEBUG" in os.environ
    )

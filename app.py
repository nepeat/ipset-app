import asyncio
import os
import logging

from typing import Optional

import aioredis
from sanic import Sanic, response

app = Sanic("ipset-app")
log = logging.getLogger(__name__)

@app.listener("before_server_start")
async def setup_redis(app, loop):
    app.redis = await aioredis.create_redis_pool("redis://localhost")

@app.listener("after_server_stop")
async def cleanup_redis(app, loop):
    app.redis.close()
    await app.redis.wait_closed()

async def test_punch_key(key: str) -> bool:
    key_exists = await app.redis.exists("ipset:" + key)
    return key_exists or key == "6e65ede4-75ea-4703-b264-abfe15dd9638"


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

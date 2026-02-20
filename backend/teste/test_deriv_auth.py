import asyncio
import json
import os
from dotenv import load_dotenv
import websockets

# Load .env from current folder (backend/)
load_dotenv()

async def main():
    app_id = os.getenv("DERIV__APP_ID", "1089")
    token = os.getenv("DERIV__API_TOKEN", "")

    url = f"wss://ws.derivws.com/websockets/v3?app_id={app_id}"

    print("URL:", url)
    print("TOKEN_LEN:", len(token))

    async with websockets.connect(url, ping_interval=None) as ws:
        await ws.send(json.dumps({"authorize": token, "req_id": 1}))
        resp = await ws.recv()
        print("RESP:", resp)

asyncio.run(main())

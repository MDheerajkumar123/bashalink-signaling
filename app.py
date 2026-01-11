from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# room_id -> list of websockets
rooms = {}

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(ws: WebSocket, room_id: str):
    await ws.accept()

    if room_id not in rooms:
        rooms[room_id] = []

    rooms[room_id].append(ws)
    print(f"Client joined room {room_id}")

    # 👇 First user becomes CALLER
    if len(rooms[room_id]) == 1:
        await ws.send_text(json.dumps({ "type": "join", "role": "caller" }))
    else:
        await ws.send_text(json.dumps({ "type": "join", "role": "receiver" }))

    try:
        while True:
            data = await ws.receive_text()
            for peer in rooms[room_id]:
                if peer != ws:
                    await peer.send_text(data)

    except WebSocketDisconnect:
        print(f"Client left room {room_id}")
        rooms[room_id].remove(ws)

        if len(rooms[room_id]) == 0:
            del rooms[room_id]

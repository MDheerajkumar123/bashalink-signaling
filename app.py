"""from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# room_id -> list of participants
rooms = {}

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(ws: WebSocket, room_id: str):
    await ws.accept()

    try:
        join_data = await ws.receive_json()

        if join_data["type"] != "join":
            await ws.close()
            return

        my_lang = join_data["myLang"]
        other_lang = join_data["otherLang"]

        if room_id not in rooms:
            rooms[room_id] = []

        # Store user info
        user = {
            "ws": ws,
            "myLang": my_lang,
            "otherLang": other_lang
        }

        rooms[room_id].append(user)

        # ❌ More than 2 users not allowed
        if len(rooms[room_id]) > 2:
            await ws.send_json({ "type": "room-full" })
            await ws.close()
            return

        # ✅ If two users joined → validate languages
        if len(rooms[room_id]) == 2:
            u1, u2 = rooms[room_id]

            valid = (
                u1["myLang"] == u2["otherLang"] and
                u1["otherLang"] == u2["myLang"]
            )

            if not valid:
                # ❌ Language mismatch → reject BOTH
                await u1["ws"].send_json({ "type": "lang-mismatch" })
                await u2["ws"].send_json({ "type": "lang-mismatch" })

                await u1["ws"].close()
                await u2["ws"].close()

                del rooms[room_id]
                return

            # ✅ Match OK
            await u1["ws"].send_json({ "type": "match-ok", "role": "caller" })
            await u2["ws"].send_json({ "type": "match-ok", "role": "callee" })

        # -------- SIGNALING RELAY --------
        while True:
            data = await ws.receive_text()

            for peer in rooms.get(room_id, []):
                if peer["ws"] != ws:
                    await peer["ws"].send_text(data)

    except WebSocketDisconnect:
        if room_id in rooms:
            rooms[room_id] = [
                u for u in rooms[room_id] if u["ws"] != ws
            ]
            if not rooms[room_id]:
                del rooms[room_id]"""


from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# callId -> call session data
calls = {}

# -----------------------------
# REQUEST MODEL
# -----------------------------
class StartCallRequest(BaseModel):
    callerId: str
    calleeId: str


# -----------------------------
# START CALL API
# -----------------------------
@app.post("/start-call")
async def start_call(data: StartCallRequest):

    call_id = str(uuid.uuid4())

    calls[call_id] = {
        "caller": data.callerId,
        "callee": data.calleeId,
        "participants": []
    }

    return {
        "callId": call_id
    }


# -----------------------------
# WEBSOCKET SIGNALING
# -----------------------------
@app.websocket("/ws/{call_id}")
async def websocket_endpoint(ws: WebSocket, call_id: str):

    await ws.accept()

    if call_id not in calls:
        await ws.close()
        return

    try:
        join_data = await ws.receive_json()

        phone = join_data["phone"]
        speak_lang = join_data["speakLang"]

        call = calls[call_id]

        # Only caller or callee allowed
        if phone not in [call["caller"], call["callee"]]:
            await ws.close()
            return

        user = {
            "ws": ws,
            "phone": phone,
            "speakLang": speak_lang
        }

        call["participants"].append(user)

        # If 2 users joined
        if len(call["participants"]) == 2:
            u1, u2 = call["participants"]

            # Auto language mapping
            await u1["ws"].send_json({
                "type": "match-ok",
                "otherLang": u2["speakLang"]
            })

            await u2["ws"].send_json({
                "type": "match-ok",
                "otherLang": u1["speakLang"]
            })

        # Relay signaling messages
        while True:
            data = await ws.receive_text()

            for peer in call["participants"]:
                if peer["ws"] != ws:
                    await peer["ws"].send_text(data)

    except WebSocketDisconnect:
        if call_id in calls:
            calls[call_id]["participants"] = [
                u for u in calls[call_id]["participants"] if u["ws"] != ws
            ]

            if not calls[call_id]["participants"]:
                del calls[call_id]


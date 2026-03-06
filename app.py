from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from twilio.rest import Client
import uuid
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

calls = {}
online_users = {}

# -----------------------------
# HEALTH CHECK
# -----------------------------
@app.get("/")
async def health():
    return {"status": "ok"}


# -----------------------------
# TWILIO ICE SERVERS
# -----------------------------
@app.get("/ice-servers")
async def get_ice_servers():
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")

    if not account_sid or not auth_token:
        return {"error": "Twilio credentials not set"}

    try:
        client = Client(account_sid, auth_token)
        token = client.tokens.create()

        return {"iceServers": token.ice_servers}

    except Exception as e:
        return {"error": str(e)}


# -----------------------------
# MODEL
# -----------------------------
class StartCallRequest(BaseModel):
    callerId: str
    calleeId: str


# -----------------------------
# PRESENCE SOCKET
# -----------------------------
@app.websocket("/ws/presence/{phone}")
async def presence_socket(ws: WebSocket, phone: str):
    await ws.accept()
    online_users[phone] = ws
    print("User connected:", phone)

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        print("User disconnected:", phone)
        online_users.pop(phone, None)


# -----------------------------
# START CALL
# -----------------------------
@app.post("/start-call")
async def start_call(data: StartCallRequest):

    if data.calleeId not in online_users:
        return {"error": "User offline"}

    call_id = str(uuid.uuid4())

    calls[call_id] = {
        "caller": data.callerId,
        "callee": data.calleeId,
        "participants": []
    }

    await online_users[data.calleeId].send_json({
        "type": "incoming-call",
        "callId": call_id,
        "from": data.callerId
    })

    return {"callId": call_id}


# -----------------------------
# CALL SOCKET
# -----------------------------
@app.websocket("/ws/{call_id}")
async def call_socket(ws: WebSocket, call_id: str):

    await ws.accept()

    if call_id not in calls:
        await ws.close()
        return

    call = calls[call_id]

    try:
        join_data = await ws.receive_json()

        if join_data.get("type") != "join":
            await ws.close()
            return

        language = join_data.get("language")

        # store websocket + language
        call["participants"].append({
            "ws": ws,
            "language": language
        })

        # when both users join
        if len(call["participants"]) == 2:

            p1 = call["participants"][0]
            p2 = call["participants"][1]

            # send peer language
            await p1["ws"].send_json({
                "type": "peer-language",
                "language": p2["language"]
            })

            await p2["ws"].send_json({
                "type": "peer-language",
                "language": p1["language"]
            })

            # notify both ready
            for p in call["participants"]:
                await p["ws"].send_json({"type": "ready"})

        # signaling relay
        while True:
            data = await ws.receive_text()

            for peer in call["participants"]:
                if peer["ws"] != ws:
                    await peer["ws"].send_text(data)

    except WebSocketDisconnect:

        call["participants"] = [
            p for p in call["participants"]
            if p["ws"] != ws
        ]

        if not call["participants"]:
            del calls[call_id]

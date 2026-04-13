from fastapi import FastAPI, Depends, HTTPException, Header, Body, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from database import AsyncSessionLocal, Chat, Stats, Settings, MemberAction
from datetime import datetime, timedelta
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import os
import json
from dotenv import load_dotenv

load_dotenv()
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

async def verify_token(x_token: str = Header(...)):
    if x_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(message))
            except Exception:
                pass

manager = ConnectionManager()

@app.websocket("/ws/stats")
async def websocket_endpoint(websocket: WebSocket, token: str = None):
    # Simple token check via query param for WS
    if token != ADMIN_TOKEN:
        await websocket.close(code=1008)
        return
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/api/notify", dependencies=[Depends(verify_token)])
async def notify_update(payload: dict = Body(...)):
    # Local endpoint for bot to trigger WS broadcast
    await manager.broadcast(payload)
    return {"status": "broadcasted"}

@app.get("/")
async def serve_index():
    return FileResponse("static/index.html")

@app.get("/api/chats", dependencies=[Depends(verify_token)])
async def get_chats():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Chat).options(selectinload(Chat.settings))
        )
        chats = result.scalars().all()
        return [
            {
                "id": c.id,
                "tg_id": c.tg_id,
                "title": c.title,
                "username": c.username,
                "type": c.type,
                "cleanup": c.settings.cleanup_enabled if c.settings else False
            } for c in chats
        ]

@app.get("/api/stats/{chat_id}", dependencies=[Depends(verify_token)])
async def get_chat_stats(chat_id: int):
    async with AsyncSessionLocal() as session:
        # Get last 30 days of stats
        thirty_days_ago = datetime.utcnow().date() - timedelta(days=30)
        result = await session.execute(
            select(Stats).where(Stats.chat_id == chat_id, Stats.date >= thirty_days_ago).order_by(Stats.date)
        )
        stats = result.scalars().all()
        
        # Member growth calculation
        growth_data = [{"date": s.date.isoformat(), "members": s.members_count, "posts": s.posts_count} for s in stats]
        
        # Simple forecast (Next 7 days)
        forecast = []
        if len(stats) > 1:
            avg_daily_growth = (stats[-1].members_count - stats[0].members_count) / len(stats)
            current_count = stats[-1].members_count
            for i in range(1, 8):
                forecast_date = (datetime.utcnow() + timedelta(days=i)).date()
                current_count += avg_daily_growth
                forecast.append({"date": forecast_date.isoformat(), "members": round(current_count)})
        
        # Member adders (Top 5)
        actions_result = await session.execute(
            select(MemberAction.added_by, func.count(MemberAction.id).label("total"))
            .where(MemberAction.chat_id == chat_id, MemberAction.added_by != None)
            .group_by(MemberAction.added_by)
            .order_by(func.count(MemberAction.id).desc())
            .limit(5)
        )
        adders = [{"user_id": a[0], "count": a[1]} for a in actions_result.all()]
        
        return {
            "history": growth_data,
            "forecast": forecast,
            "top_adders": adders
        }

@app.post("/api/settings/{chat_id}", dependencies=[Depends(verify_token)])
async def update_settings(chat_id: int, cleanup: bool = Body(..., embed=True)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Settings).where(Settings.chat_id == chat_id))
        settings = result.scalar_one_or_none()
        if settings:
            settings.cleanup_enabled = cleanup
            await session.commit()
            return {"status": "success"}
        raise HTTPException(status_code=404, detail="Chat settings not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

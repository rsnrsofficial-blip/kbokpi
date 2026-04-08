"""
KBO 인사평가 시스템 - FastAPI 백엔드
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import date
import os
from dotenv import load_dotenv

from crawler import crawl_player
from cache import get_cached, set_cached

load_dotenv()

app = FastAPI(title="KBO 인사평가 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "ok", "service": "KBO 인사평가 시스템"}


@app.get("/player")
async def get_player(name: str):
    if not name or len(name) < 2:
        raise HTTPException(status_code=400, detail="선수 이름을 입력하세요")

    today = date.today().isoformat()

    # 캐시 확인
    cached = await get_cached(name, today)
    if cached:
        return {**cached, "cached": True}

    # 크롤링 + AI 총평 생성
    data = crawl_player(name)
    if not data:
        raise HTTPException(status_code=404, detail=f"'{name}' 선수를 찾을 수 없습니다")

    # 캐시 저장
    await set_cached(name, today, data)

    return {**data, "cached": False}


@app.get("/health")
def health():
    return {"status": "healthy", "date": date.today().isoformat()}

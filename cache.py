"""
Supabase 캐시 — 선수 데이터를 날짜 기준으로 저장/조회
"""
import os
import json
from supabase import create_client, Client

_client: Client = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_ANON_KEY"]
        _client = create_client(url, key)
    return _client


async def get_cached(name: str, today: str) -> dict | None:
    try:
        res = get_client().table("player_cache") \
            .select("data") \
            .eq("name", name) \
            .eq("date", today) \
            .limit(1) \
            .execute()
        if res.data:
            return res.data[0]["data"]
    except Exception as e:
        print(f"[캐시 조회 오류] {e}")
    return None


async def set_cached(name: str, today: str, data: dict) -> None:
    try:
        get_client().table("player_cache").upsert({
            "name": name,
            "date": today,
            "data": data,
        }).execute()
    except Exception as e:
        print(f"[캐시 저장 오류] {e}")

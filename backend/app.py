import json
import math
import os
import asyncio
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from google import genai
from google.genai import types
from supabase import create_client, Client

from prompt import build_prompt
from reference_scripts import reference_scripts

load_dotenv()

app = Flask(__name__)

_supabase_client: Optional[Client] = None
_gemini_client: Optional[genai.Client] = None


def _get_supabase_client() -> Client:
    """
    Lazily create the Supabase client so the server can boot even if env vars are missing.
    We'll fail with a clear error only if/when we actually try to resolve NBA highlights.
    """
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    supabase_url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    supabase_key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    )
    if not supabase_url or not supabase_key:
        raise RuntimeError(
            "Missing Supabase env vars. Set SUPABASE_URL (or NEXT_PUBLIC_SUPABASE_URL) and "
            "SUPABASE_SERVICE_ROLE_KEY (or NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY / NEXT_PUBLIC_SUPABASE_ANON_KEY)."
        )

    _supabase_client = create_client(supabase_url, supabase_key)
    return _supabase_client


def _get_gemini_client() -> genai.Client:
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Server missing GEMINI_API_KEY")

    _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


@dataclass(frozen=True)
class Shot:
    """
    A single planned shot coming from the shot planner.

    source values expected by the resolver:
      - "generate_*"   -> generator (e.g. generate_interview, generate_image)
      - "nba_highlight"-> NBA highlights database
      - "real_clip"    -> generic clips database (day-to-day / b-roll)
    """

    shot_id: str
    source: str
    semantic_intent: str
    visual_description: str
    player_name: Optional[str] = None
    estimated_duration_seconds: float = 0.0
    clip_type: Optional[str] = None
    text_overlay: Any = None
    voiceover_hint: Any = None


@dataclass(frozen=True)
class ResolvedSegment:
    shot_id: str
    source: str
    status: str  # "ok" | "error"
    asset_url: Optional[str] = None
    local_video_path: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "shot_id": self.shot_id,
            "source": self.source,
            "status": self.status,
            "asset_url": self.asset_url,
            "local_video_path": self.local_video_path,
            "error": self.error,
        }


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class NbaHighlightsDB:
    async def find_best_match(self, shot: Shot) -> Optional[str]:
        if not (shot.player_name or "").strip():
            return None

        table = os.getenv("HIGHLIGHTS_TABLE", "Highlights")
        player_col = os.getenv("HIGHLIGHTS_PLAYER_COL", "player_name")
        length_col = os.getenv("HIGHLIGHTS_LENGTH_COL", "length")
        embed_col = os.getenv("HIGHLIGHTS_EMBED_COL", "embeddings")
        asset_col = os.getenv("HIGHLIGHTS_ASSET_COL", "asset_url")

        min_length = float(shot.estimated_duration_seconds or 0) - 1
        max_length = float(shot.estimated_duration_seconds or 0) + 1

        supabase = _get_supabase_client()

        # 1) Fetch candidate highlights
        res = (
            supabase.table(table)
            .select(f"{asset_col},{embed_col}")
            .eq(player_col, shot.player_name)
            .gt(length_col, min_length)
            .lt(length_col, max_length)
            .execute()
        )

        rows = getattr(res, "data", None) or []
        if not rows:
            return None

        # 2) Embed the query
        gemini_client = _get_gemini_client()
        q = f"{shot.semantic_intent} {shot.visual_description}".strip()
        emb_result = gemini_client.models.embed_content(
            model=os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
            contents=q,
            config=types.EmbedContentConfig(output_dimensionality=1536),
        )
        embeddings = getattr(emb_result, "embeddings", None) or []
        if not embeddings:
            return None
        [embedding_obj] = embeddings
        query_vector = list(embedding_obj.values)

        # 3) Find best match
        best_score = -1.0
        best_asset_url: Optional[str] = None
        for row in rows:
            highlight_vector = row.get(embed_col)
            if not highlight_vector:
                continue
            score = cosine_similarity(query_vector, highlight_vector)
            if score > best_score:
                best_score = score
                best_asset_url = row.get(asset_col)
        return best_asset_url


class ClipsDB:
    async def find_best_match(self, shot: Shot) -> str:
        # TODO: Replace with real search against your "real day-to-day" clips index.
        await asyncio.sleep(0)
        return f"clips://broll/best_match?q={_compact_query(shot)}"


class Generator:
    async def generate(self, shot: Shot) -> str:
        # TODO: Replace with calls to your generation service (RunPod, Replicate, internal worker, etc).
        await asyncio.sleep(0)
        return f"gen://rendered/shot/{shot.shot_id}?q={_compact_query(shot)}"


async def resolve_one_shot_async(
    shot: Shot,
    *,
    nba_db: NbaHighlightsDB,
    clips_db: ClipsDB,
    generator: Generator,
) -> ResolvedSegment:
    src = (shot.source or "").strip().lower()
    if src == "nba_highlight":
        asset_url = await nba_db.find_best_match(shot)
        if not asset_url:
            return ResolvedSegment(
                shot_id=shot.shot_id,
                source=shot.source,
                status="error",
                error="No matching NBA highlight found",
            )
        return ResolvedSegment(
            shot_id=shot.shot_id,
            source=shot.source,
            status="ok",
            asset_url=asset_url,
            local_video_path=None,
        )

    if src == "real_clip":
        asset_url = await clips_db.find_best_match(shot)
        return ResolvedSegment(
            shot_id=shot.shot_id,
            source=shot.source,
            status="ok",
            asset_url=asset_url,
            local_video_path=None,
        )

    asset_url = await generator.generate(shot)
    return ResolvedSegment(
        shot_id=shot.shot_id,
        source=shot.source,
        status="ok",
        asset_url=asset_url,
        local_video_path=None,
    )


async def resolve_shots_async(
    shots: list[Shot],
    *,
    max_concurrency: Optional[int] = None,
    timeout_seconds: Optional[float] = None,
) -> list[ResolvedSegment]:
    nba_db = NbaHighlightsDB()
    clips_db = ClipsDB()
    generator = Generator()

    if max_concurrency is None:
        max_concurrency = int(os.getenv("RESOLVER_MAX_CONCURRENCY", "8"))
    if timeout_seconds is None:
        timeout_seconds = float(os.getenv("RESOLVER_TIMEOUT_SECONDS", "30"))

    sem = asyncio.Semaphore(max(1, max_concurrency))

    async def _guarded(shot: Shot) -> ResolvedSegment:
        async with sem:
            try:
                coro = resolve_one_shot_async(
                    shot, nba_db=nba_db, clips_db=clips_db, generator=generator
                )
                return await asyncio.wait_for(coro, timeout=timeout_seconds)
            except Exception as e:
                return ResolvedSegment(
                    shot_id=shot.shot_id,
                    source=shot.source,
                    status="error",
                    error=str(e),
                )

    tasks = [asyncio.create_task(_guarded(s)) for s in shots]
    return await asyncio.gather(*tasks)


def run_async(coro):
    """
    Bridge helper for running async code from sync Flask routes.
    In normal WSGI Flask usage there is no running event loop, so asyncio.run is safe.
    """
    try:
        asyncio.get_running_loop()
        raise RuntimeError(
            "Cannot call run_async() while an event loop is already running. "
            "If you need async routes end-to-end, run the backend under an ASGI server "
            "(or migrate to an ASGI framework)."
        )
    except RuntimeError as e:
        if "no running event loop" in str(e).lower():
            return asyncio.run(coro)
        raise


def _compact_query(shot: Shot) -> str:
    parts = [
        (shot.clip_type or "").strip(),
        (shot.semantic_intent or "").strip(),
        (shot.visual_description or "").strip(),
    ]
    return "+".join([p.replace(" ", "_") for p in parts if p])[:240]


@app.after_request
def add_cors_headers(response):
    # Simple dev-friendly CORS so Next.js (localhost:3000) can call the backend.
    response.headers["Access-Control-Allow-Origin"] = os.getenv(
        "CORS_ALLOW_ORIGIN", "http://localhost:3000"
    )
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    return response


@app.route("/generate_video", methods=["POST", "OPTIONS"])
def generate_video():
    # This endpoint generates the *planned* trailer (JSON), plus a lightweight
    # "shots plan" that can later be handed to the async resolver.
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(silent=True) or {}
    user_prompt = (data.get("prompt") or "").strip()
    if not user_prompt:
        return jsonify({"error": "Missing required field: prompt"}), 400

    reference_trailers_str = json.dumps(reference_scripts, indent=2, ensure_ascii=False)
    target_duration_seconds = str(data.get("target_duration_seconds") or "30 seconds")
    rendered_prompt = build_prompt(
        user_prompt=user_prompt,
        target_duration_seconds=target_duration_seconds,
        reference_trailers=reference_trailers_str,
    )

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return jsonify({"error": "Server missing GEMINI_API_KEY"}), 500

    client = genai.Client(api_key=api_key)
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    try:
        result = client.models.generate_content(
            model=model,
            contents=rendered_prompt,
        )
        script_text = getattr(result, "text", None) or ""
        print(script_text)
        script = _parse_llm_json(script_text)
        shots_plan = plan_shots(script)
        # Default behavior: one click should do everything in one shot.
        # You can disable this by passing { "resolve": false }.
        resolve_flag = data.get("resolve")
        should_resolve = True if resolve_flag is None else bool(resolve_flag)
        if not should_resolve:
            return jsonify({"script": script, "shots": shots_plan})

        # Resolve immediately after planning shots (same logic as /resolve_shots).
        resolved = _resolve_shots_from_plan(shots_plan)
        return jsonify(
            {
                "script": script,
                "shots": shots_plan,
                "resolved": [r.to_dict() for r in resolved],
            }
        )
    except ValueError as e:
        return jsonify({"error": str(e), "raw_script": script_text}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _parse_llm_json(text: str) -> dict:
    """
    Gemini should return raw JSON, but this makes parsing resilient if it ever
    wraps it with stray text.
    """
    if not text:
        raise ValueError("Model returned empty response")
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Could not find JSON object in model response")
    try:
        return json.loads(text[start : end + 1])
    except Exception as e:
        raise ValueError(f"Invalid JSON returned by model: {e}")


def plan_shots(script: dict) -> list[dict]:
    """
    Lightweight shot planner. Returns array of shots with a chosen source plus
    the semantic intent used later by the resolver.
    """
    shots: list[dict] = []
    idx = 0
    shot_sources = {
        "NBA_GAME": "nba_highlight",
        "INTERVIEW": "generate_interview",
        "TITLE_CARD": "generate_image",
        "BLACK_SCREEN": "generate_image",
        "BROLL": "real_clip",
        "CROWD_REACTION": "real_clip",
    }
    for act in script.get("acts", []):
        for shot in act.get("shots", []):
            clip_type = shot.get("clip_type")
            # Prefer per-shot player_name; fall back to trailer-level player_name if present.
            player_name = shot.get("player_name")
            if player_name is None:
                player_name = script.get("player_name")
            shots.append(
                {
                    "shot_id": str(shot.get("shot_id") or idx),
                    "source": shot_sources.get(clip_type, "real_clip"),
                    "clip_type": clip_type,
                    "player_name": player_name,
                    "semantic_intent": shot.get("semantic_intent"),
                    "visual_description": shot.get("visual_description"),
                    "text_overlay": shot.get("text_overlay"),
                    "voiceover_hint": shot.get("voiceover_hint"),
                    "estimated_duration_seconds": shot.get("estimated_duration_seconds"),
                }
            )
            idx += 1
    return shots


def _resolve_shots_from_plan(shots_plan: list[dict]) -> list[ResolvedSegment]:
    shots: list[Shot] = []
    for s in shots_plan:
        if not isinstance(s, dict):
            continue
        shots.append(
            Shot(
                shot_id=str(s.get("shot_id") or ""),
                source=str(s.get("source") or "real_clip"),
                player_name=(s.get("player_name") if isinstance(s.get("player_name"), str) else None),
                semantic_intent=str(s.get("semantic_intent") or ""),
                visual_description=str(s.get("visual_description") or ""),
                estimated_duration_seconds=float(s.get("estimated_duration_seconds") or 0.0),
                clip_type=(s.get("clip_type") if isinstance(s.get("clip_type"), str) else None),
                text_overlay=s.get("text_overlay"),
                voiceover_hint=s.get("voiceover_hint"),
            )
        )
    return run_async(resolve_shots_async(shots))


@app.route("/resolve_shots", methods=["POST", "OPTIONS"])
def resolve_shots():
    """
    Runs the async resolver *after* shots have already been planned.
    This is intentionally split from /generate_video so the frontend can:
      1) generate script + shots
      2) resolve shots concurrently via asyncio
    """
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(silent=True) or {}
    shots_raw = data.get("shots") or []
    if not isinstance(shots_raw, list) or not shots_raw:
        return jsonify({"error": "Missing required field: shots (non-empty array)"}), 400

    try:
        resolved = _resolve_shots_from_plan(shots_raw)
        return jsonify({"resolved": [r.to_dict() for r in resolved]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
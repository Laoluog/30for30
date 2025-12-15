import asyncio
import os
from dataclasses import dataclass
from typing import Any, Optional


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


class NbaHighlightsDB:
    async def find_best_match(self, shot: Shot) -> str:
        # TODO: Replace with real vector/text search against your NBA highlights index.
        await asyncio.sleep(0)
        q = _compact_query(shot)
        return f"nba://highlights/best_match?q={q}"


class ClipsDB:
    async def find_best_match(self, shot: Shot) -> str:
        # TODO: Replace with real search against your "real day-to-day" clips index.
        await asyncio.sleep(0)
        q = _compact_query(shot)
        return f"clips://broll/best_match?q={q}"


class Generator:
    async def generate(self, shot: Shot) -> str:
        # TODO: Replace with calls to your generation service (RunPod, Replicate, internal worker, etc).
        await asyncio.sleep(0)
        q = _compact_query(shot)
        return f"gen://rendered/shot/{shot.shot_id}?q={q}"


async def resolve_shots_async(
    shots: list[Shot],
    *,
    max_concurrency: Optional[int] = None,
    timeout_seconds: Optional[float] = None,
) -> list[ResolvedSegment]:
    """
    Resolve shots concurrently using asyncio.

    Concurrency is capped so you can safely call external services / DBs.
    """
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
                seg = await asyncio.wait_for(coro, timeout=timeout_seconds)
                return seg
            except Exception as e:
                return ResolvedSegment(
                    shot_id=shot.shot_id,
                    source=shot.source,
                    status="error",
                    error=str(e),
                )

    tasks = [asyncio.create_task(_guarded(s)) for s in shots]
    return await asyncio.gather(*tasks)


async def resolve_one_shot_async(
    shot: Shot,
    *,
    nba_db: NbaHighlightsDB,
    clips_db: ClipsDB,
    generator: Generator,
) -> ResolvedSegment:
    """
    The core routing logic for your resolver:
      1) generator
      2) NBA highlights database
      3) day-to-day clips database
    """
    src = (shot.source or "").strip().lower()
    if src == "nba_highlight":
        asset_url = await nba_db.find_best_match(shot)
        # TODO: download/transcode to local path if needed.
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

    # Default: treat everything else as generation.
    asset_url = await generator.generate(shot)
    return ResolvedSegment(
        shot_id=shot.shot_id,
        source=shot.source,
        status="ok",
        asset_url=asset_url,
        local_video_path=None,
    )


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
        # If the error came from get_running_loop() there's no running loop, so we can run.
        if "no running event loop" in str(e).lower():
            return asyncio.run(coro)
        raise


def _compact_query(shot: Shot) -> str:
    # Small helper for building a stable text query payload.
    parts = [
        (shot.clip_type or "").strip(),
        (shot.semantic_intent or "").strip(),
        (shot.visual_description or "").strip(),
    ]
    return "+".join([p.replace(" ", "_") for p in parts if p])[:240]



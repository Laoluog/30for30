import json
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from google import genai

from prompt import build_prompt
from reference_scripts import reference_scripts
from resolver import Shot, resolve_shots_async, run_async

load_dotenv()

app = Flask(__name__)


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
        # Always resolve (one click should produce the full resolved payload).
        shots = [
            Shot(
                shot_id=str(s.get("shot_id") or ""),
                source=str(s.get("source") or "real_clip"),
                semantic_intent=str(s.get("semantic_intent") or ""),
                visual_description=str(s.get("visual_description") or ""),
                estimated_duration_seconds=float(s.get("estimated_duration_seconds") or 0.0),
                clip_type=(s.get("clip_type") if isinstance(s.get("clip_type"), str) else None),
                text_overlay=s.get("text_overlay"),
                voiceover_hint=s.get("voiceover_hint"),
            )
            for s in shots_plan
            if isinstance(s, dict)
        ]
        resolved = run_async(resolve_shots_async(shots))
        return jsonify(
            {"script": script, "shots": shots_plan, "resolved": [r.to_dict() for r in resolved]}
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
            shots.append(
                {
                    "shot_id": str(shot.get("shot_id") or idx),
                    "source": shot_sources.get(clip_type, "real_clip"),
                    "clip_type": clip_type,
                    "semantic_intent": shot.get("semantic_intent"),
                    "visual_description": shot.get("visual_description"),
                    "text_overlay": shot.get("text_overlay"),
                    "voiceover_hint": shot.get("voiceover_hint"),
                    "estimated_duration_seconds": shot.get("estimated_duration_seconds"),
                }
            )
            idx += 1
    print(shots)
    return shots


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

    shots: list[Shot] = []
    for s in shots_raw:
        if not isinstance(s, dict):
            continue
        shots.append(
            Shot(
                shot_id=str(s.get("shot_id") or ""),
                source=str(s.get("source") or "real_clip"),
                semantic_intent=str(s.get("semantic_intent") or ""),
                visual_description=str(s.get("visual_description") or ""),
                estimated_duration_seconds=float(s.get("estimated_duration_seconds") or 0.0),
                clip_type=(s.get("clip_type") if isinstance(s.get("clip_type"), str) else None),
                text_overlay=s.get("text_overlay"),
                voiceover_hint=s.get("voiceover_hint"),
            )
        )

    try:
        resolved = run_async(resolve_shots_async(shots))
        return jsonify({"resolved": [r.to_dict() for r in resolved]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
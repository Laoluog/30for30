import json
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from google import genai

from prompt import build_prompt
from reference_scripts import reference_scripts

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


@app.route("/create_script", methods=["POST", "OPTIONS"])
def create_script():
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(silent=True) or {}
    user_prompt = (data.get("prompt") or "").strip()
    if not user_prompt:
        return jsonify({"error": "Missing required field: prompt"}), 400

    # Always use our curated reference scripts for structural inspiration.
    reference_trailers_str = json.dumps(reference_scripts, indent=2, ensure_ascii=False)

    target_duration_seconds = "30 seconds"
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
        return jsonify({"script": script_text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
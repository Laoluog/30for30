import os
import sys

from supabase import create_client, Client
from dotenv import load_dotenv
from google import genai
from google.genai import types
import httpx


def main() -> int:
    load_dotenv()

    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        print("Missing GEMINI_API_KEY.", file=sys.stderr)
        return 2

    supabase_url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    # Prefer service role for server-side scripts; fall back to publishable/anon if that's all you have.
    supabase_key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    )
    
    if not supabase_url or not supabase_key:
        print(
            "Missing SUPABASE_URL (or NEXT_PUBLIC_SUPABASE_URL) and/or SUPABASE_SERVICE_ROLE_KEY.",
            file=sys.stderr,
        )
        return 6

    table = os.getenv("HIGHLIGHTS_TABLE", "Auxillary")
    id_col = os.getenv("HIGHLIGHTS_ID_COL", "id")
    desc_col = os.getenv("HIGHLIGHTS_DESC_COL", "Description")
    # Your table uses `embedding` (singular) based on your Supabase REST logs.
    embed_col = os.getenv("HIGHLIGHTS_EMBED_COL", "embedding")
    # Default to embedding rows id 2..15. Override with HIGHLIGHTS_ID_START/HIGHLIGHTS_ID_END if desired.
    id_start = int(os.getenv("HIGHLIGHTS_ID_START", "1"))
    id_end = int(os.getenv("HIGHLIGHTS_ID_END", "3"))

    supabase = create_client(supabase_url, supabase_key)
    gemini = genai.Client(api_key=gemini_key)

    updated = 0
    skipped = 0
    failed = 0

    for row_id in range(id_start, id_end + 1):
        # 1) Read the target row
        resp = (
            supabase.table(table)
            .select(f"{id_col},{desc_col},{embed_col}")
            .eq(id_col, row_id)
            .limit(1)
            .execute()
        )
        rows = getattr(resp, "data", None) or []
        if not rows:
            print(f"[id={row_id}] Not found; skipping.", file=sys.stderr)
            skipped += 1
            continue

        row = rows[0]
        description = (row.get(desc_col) or "").strip()
        if not description:
            print(f"[id={row_id}] Empty {desc_col!r}; skipping.", file=sys.stderr)
            skipped += 1
            continue

        # 2) Embed the description
        try:
            result = gemini.models.embed_content(
                model=os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
                contents=description,
                config=types.EmbedContentConfig(output_dimensionality=1536),
            )
        except httpx.HTTPError as e:
            print(f"[id={row_id}] Network/HTTP error calling Gemini embeddings API: {e}", file=sys.stderr)
            failed += 1
            continue
        except Exception as e:
            print(f"[id={row_id}] Unexpected error calling Gemini embeddings API: {e}", file=sys.stderr)
            failed += 1
            continue

        embeddings = getattr(result, "embeddings", None) or []
        if not embeddings:
            print(f"[id={row_id}] No embeddings returned from API; skipping.", file=sys.stderr)
            failed += 1
            continue

        [embedding_obj] = embeddings
        embedding_values = [float(x) for x in list(embedding_obj.values)]
        if len(embedding_values) != 1536:
            print(f"[id={row_id}] Unexpected embedding dim={len(embedding_values)}; skipping.", file=sys.stderr)
            failed += 1
            continue

        # 3) Write embedding back to Supabase
        supabase.table(table).update({embed_col: embedding_values}).eq(id_col, row_id).execute()
        updated += 1
        print(f"[id={row_id}] Updated {table}.{embed_col} (dim={len(embedding_values)})")

    print(f"Done. updated={updated} skipped={skipped} failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
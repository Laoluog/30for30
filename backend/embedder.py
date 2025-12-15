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
    supabase_key = os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
    
    if not supabase_url or not supabase_key:
        print(
            "Missing SUPABASE_URL (or NEXT_PUBLIC_SUPABASE_URL) and/or SUPABASE_SERVICE_ROLE_KEY.",
            file=sys.stderr,
        )
        return 6

    table = os.getenv("HIGHLIGHTS_TABLE", "Highlights")
    id_col = os.getenv("HIGHLIGHTS_ID_COL", "id")
    desc_col = os.getenv("HIGHLIGHTS_DESC_COL", "Description")
    embed_col = os.getenv("HIGHLIGHTS_EMBED_COL", "embedding")  # set to "embeddings" if that's your column name
    row_id = os.getenv("HIGHLIGHTS_ROW_ID")  # optional

    supabase = create_client(supabase_url, supabase_key)
    gemini = genai.Client(api_key=gemini_key)

    # 1) Read a row (either specific id, or first row missing an embedding)
    q = supabase.table(table).select(f"{id_col},{desc_col}")
    if row_id:
        q = q.eq(id_col, row_id)
    else:
        q = q.is_(embed_col, "null")

    resp = q.limit(1).execute()
    rows = getattr(resp, "data", None) or []
    if not rows:
        print(f"No matching row found in {table!r}.", file=sys.stderr)
        return 7

    row = rows[0]
    row_id_val = row.get(id_col)
    description = (row.get(desc_col) or "").strip()
    if not description:
        print(f"Row {row_id_val!r} has empty {desc_col!r}.", file=sys.stderr)
        return 8

    # 2) Embed the description
    try:
        result = gemini.models.embed_content(
            model="gemini-embedding-001",
            contents=description,
            config=types.EmbedContentConfig(output_dimensionality=1536),
        )
    except httpx.HTTPError as e:
        print(f"Network/HTTP error calling Gemini embeddings API: {e}", file=sys.stderr)
        return 4
    except Exception as e:
        print(f"Unexpected error calling Gemini embeddings API: {e}", file=sys.stderr)
        return 5

    if not getattr(result, "embeddings", None):
        print("No embeddings returned from API.", file=sys.stderr)
        return 3

    [embedding_obj] = result.embeddings
    embedding_values = list(embedding_obj.values)

    # 3) Write embedding back to Supabase
    supabase.table(table).update({embed_col: embedding_values}).eq(id_col, row_id_val).execute()
    print(f"Updated {table}.{embed_col} for {id_col}={row_id_val!r} (dim={len(embedding_values)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
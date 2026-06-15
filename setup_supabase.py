#!/usr/bin/env python3
"""Apply supabase_schema.sql via the Supabase Management API.

Runs the schema over HTTPS (no psql, no DB connection string). The project
ref is derived from SUPABASE_URL; the only extra secret is a Supabase
personal access token (SUPABASE_ACCESS_TOKEN, ``sbp_...``). Both are read
from the environment or a project-root ``.env``.

The schema is idempotent, so this is safe to re-run.
"""

import os
import pathlib
import re
import sys

import httpx
from dotenv import load_dotenv

SCHEMA_PATH = pathlib.Path(__file__).parent / "supabase_schema.sql"


def main() -> int:
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    token = os.environ.get("SUPABASE_ACCESS_TOKEN")
    if not url or not token:
        print(
            "SUPABASE_URL and SUPABASE_ACCESS_TOKEN required (.env or env)",
            file=sys.stderr,
        )
        return 1

    match = re.match(r"https?://([^.]+)\.supabase\.", url.strip())
    if not match:
        print(f"could not derive project ref from SUPABASE_URL={url!r}", file=sys.stderr)
        return 1
    ref = match.group(1)

    sql = SCHEMA_PATH.read_text()
    resp = httpx.post(
        f"https://api.supabase.com/v1/projects/{ref}/database/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": sql},
        timeout=30,
    )
    if resp.is_error:
        print(f"schema failed ({resp.status_code}): {resp.text}", file=sys.stderr)
        return 1
    print(f"schema applied to project {ref}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

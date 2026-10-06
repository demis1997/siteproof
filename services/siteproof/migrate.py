import hashlib
import json
from pathlib import Path

from .config import settings
from .db import connection


def main():
    with connection() as conn:
        conn.execute(Path("infra/001_initial.sql").read_text())
        corpus = json.loads(Path("knowledge/guidance.json").read_text())
        for tenant in settings.tenant_keys():
            conn.execute("INSERT INTO tenants(id,name) VALUES(%s,%s) ON CONFLICT(id) DO NOTHING", (tenant, tenant))
            for document in corpus["documents"]:
                identifier = tenant + ":" + document["id"]
                conn.execute(
                    "INSERT INTO knowledge_documents(id,tenant_id,collection,source,version,reuse_notes) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET source=excluded.source,version=excluded.version,reuse_notes=excluded.reuse_notes",
                    (identifier, tenant, "guidance", document["source"], document["version"], document["reuse_notes"]),
                )
                content = document["text"]
                digest = hashlib.sha256(content.encode()).hexdigest()
                conn.execute(
                    "INSERT INTO knowledge_chunks(id,tenant_id,document_id,content,content_hash) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET content=excluded.content,content_hash=excluded.content_hash,embedding=CASE WHEN knowledge_chunks.content_hash IS DISTINCT FROM excluded.content_hash THEN NULL ELSE knowledge_chunks.embedding END,embedding_model=CASE WHEN knowledge_chunks.content_hash IS DISTINCT FROM excluded.content_hash THEN NULL ELSE knowledge_chunks.embedding_model END",
                    (identifier + "-chunk", tenant, identifier, content, digest),
                )


if __name__ == "__main__":
    main()

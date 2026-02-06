"""Project memory store with embedding support."""
import hashlib
import json
import os
from datetime import datetime
from typing import Any, Optional

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False


class ProjectMemory:
    """Store and retrieve project knowledge with optional embeddings.

    Works with or without embeddings - falls back to keyword search.
    """

    def __init__(
        self,
        project_id: int,
        database_url: Optional[str] = None,
    ):
        self.project_id = project_id
        self.database_url = database_url or os.environ.get(
            "DATABASE_URL", "postgresql://wfhub:wfhub@localhost:5433/agentic"
        )
        self._engine = None
        self._Session = None

    def _get_session(self):
        """Lazy init database session."""
        if not HAS_SQLALCHEMY:
            raise ImportError("SQLAlchemy required for database operations")
        if self._engine is None:
            self._engine = create_engine(self.database_url)
            self._Session = sessionmaker(bind=self._engine)
        return self._Session()

    def store(
        self,
        content_type: str,
        content: str,
        file_path: Optional[str] = None,
        summary: Optional[str] = None,
        metadata: Optional[dict] = None,
        embedding: Optional[list[float]] = None,
    ) -> dict:
        """Store a knowledge item.

        Args:
            content_type: Type of content ('code', 'doc', 'solution', 'error')
            content: The actual content to store
            file_path: Source file path if applicable
            summary: LLM-generated summary
            metadata: Additional context
            embedding: Pre-computed embedding vector

        Returns:
            {"success": True, "id": record_id} or {"success": False, "error": msg}
        """
        try:
            session = self._get_session()
            # Convert embedding list to pgvector string format
            embedding_str = None
            if embedding:
                embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

            result = session.execute(
                text("""
                    INSERT INTO project_knowledge
                    (project_id, content_type, file_path, content, summary, extra_data, embedding, created_at, updated_at)
                    VALUES (:project_id, :content_type, :file_path, :content, :summary, :extra_data, CAST(:embedding AS vector), NOW(), NOW())
                    RETURNING id
                """),
                {
                    "project_id": self.project_id,
                    "content_type": content_type,
                    "file_path": file_path,
                    "content": content,
                    "summary": summary,
                    "extra_data": json.dumps(metadata) if metadata else None,
                    "embedding": embedding_str,
                },
            )
            record_id = result.scalar()
            session.commit()
            session.close()
            return {"success": True, "id": record_id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def search(
        self,
        query: str,
        content_type: Optional[str] = None,
        limit: int = 5,
        embedding: Optional[list[float]] = None,
        mode: str = "hybrid",
    ) -> dict:
        """Search for relevant knowledge using hybrid search.

        Args:
            query: Search query (used for full-text search)
            content_type: Filter by type
            limit: Max results
            embedding: Query embedding for semantic search
            mode: Search mode - "hybrid" (text + embedding), "text", or "embedding"

        Returns:
            {"success": True, "results": [...]} or {"success": False, "error": msg}
        """
        try:
            session = self._get_session()
            params = {"project_id": self.project_id, "limit": limit}

            if mode == "hybrid" and embedding and query:
                # Hybrid search: combine full-text rank + embedding similarity
                embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                params["embedding"] = embedding_str
                params["query"] = query

                sql = """
                    SELECT id, content_type, file_path, content, summary, extra_data,
                           (
                               0.4 * ts_rank(search_vector, plainto_tsquery('english', :query)) +
                               0.6 * (1 - (embedding <=> CAST(:embedding AS vector)))
                           ) as score
                    FROM project_knowledge
                    WHERE project_id = :project_id
                      AND (
                          search_vector @@ plainto_tsquery('english', :query)
                          OR embedding IS NOT NULL
                      )
                """
                if content_type:
                    sql += " AND content_type = :content_type"
                    params["content_type"] = content_type
                sql += " ORDER BY score DESC LIMIT :limit"

            elif mode == "text" or (not embedding and query):
                # Full-text search only (fast, no embedding needed)
                params["query"] = query

                sql = """
                    SELECT id, content_type, file_path, content, summary, extra_data,
                           ts_rank(search_vector, plainto_tsquery('english', :query)) as score
                    FROM project_knowledge
                    WHERE project_id = :project_id
                      AND search_vector @@ plainto_tsquery('english', :query)
                """
                if content_type:
                    sql += " AND content_type = :content_type"
                    params["content_type"] = content_type
                sql += " ORDER BY score DESC LIMIT :limit"

            elif embedding:
                # Embedding-only search
                embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                params["embedding"] = embedding_str

                sql = """
                    SELECT id, content_type, file_path, content, summary, extra_data,
                           1 - (embedding <=> CAST(:embedding AS vector)) as score
                    FROM project_knowledge
                    WHERE project_id = :project_id
                      AND embedding IS NOT NULL
                """
                if content_type:
                    sql += " AND content_type = :content_type"
                    params["content_type"] = content_type
                sql += " ORDER BY embedding <=> CAST(:embedding AS vector) LIMIT :limit"

            else:
                # Fallback: recent items
                sql = """
                    SELECT id, content_type, file_path, content, summary, extra_data, 0.0 as score
                    FROM project_knowledge
                    WHERE project_id = :project_id
                """
                if content_type:
                    sql += " AND content_type = :content_type"
                    params["content_type"] = content_type
                sql += " ORDER BY updated_at DESC LIMIT :limit"

            result = session.execute(text(sql), params)
            rows = result.fetchall()
            session.close()

            results = []
            for row in rows:
                results.append({
                    "id": row[0],
                    "content_type": row[1],
                    "file_path": row[2],
                    "content": row[3][:500] + "..." if len(row[3]) > 500 else row[3],
                    "summary": row[4],
                    "extra_data": json.loads(row[5]) if row[5] else None,
                    "score": float(row[6]) if row[6] else 0.0,
                })

            return {"success": True, "results": results, "count": len(results), "mode": mode}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete(self, record_id: int) -> dict:
        """Delete a knowledge item."""
        try:
            session = self._get_session()
            session.execute(
                text("DELETE FROM project_knowledge WHERE id = :id AND project_id = :project_id"),
                {"id": record_id, "project_id": self.project_id},
            )
            session.commit()
            session.close()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_context(
        self,
        query: str,
        embedding: Optional[list[float]] = None,
        max_tokens: int = 2000,
    ) -> str:
        """Get relevant context for an LLM prompt.

        Returns formatted context string suitable for injecting into prompts.
        """
        results = self.search(query, embedding=embedding, limit=10)
        if not results.get("success") or not results.get("results"):
            return ""

        context_parts = []
        total_chars = 0
        char_limit = max_tokens * 4  # Rough estimate

        for item in results["results"]:
            content = item["content"]
            if total_chars + len(content) > char_limit:
                break

            if item["file_path"]:
                context_parts.append(f"### {item['file_path']}\n{content}")
            else:
                context_parts.append(f"### {item['content_type']}\n{content}")
            total_chars += len(content)

        return "\n\n".join(context_parts)

    def prune(
        self,
        max_age_days: int = 90,
        max_entries: int = 1000,
        similarity_threshold: float = 0.95,
    ) -> dict:
        """Prune old, unused, and duplicate entries from the knowledge base.

        Args:
            max_age_days: Remove entries older than this many days
            max_entries: Keep at most this many entries per project
            similarity_threshold: Remove entries with similarity above this (dedup)

        Returns:
            {"success": True, "pruned": {"stale": N, "excess": N, "duplicates": N}}
        """
        try:
            results = {
                "stale": self._prune_stale(max_age_days),
                "excess": self._prune_excess(max_entries),
            }
            # Duplicate detection is expensive, only run if embeddings are available
            # results["duplicates"] = self._prune_duplicates(similarity_threshold)
            results["duplicates"] = 0  # Disabled by default

            total = sum(results.values())
            return {"success": True, "pruned": results, "total": total}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _prune_stale(self, max_age_days: int) -> int:
        """Remove entries older than max_age_days."""
        try:
            session = self._get_session()
            result = session.execute(
                text("""
                    DELETE FROM project_knowledge
                    WHERE project_id = :project_id
                    AND created_at < NOW() - INTERVAL ':days days'
                    RETURNING id
                """.replace(":days", str(int(max_age_days)))),
                {"project_id": self.project_id},
            )
            deleted = len(result.fetchall())
            session.commit()
            session.close()
            return deleted
        except Exception:
            return 0

    def _prune_excess(self, max_entries: int) -> int:
        """Remove oldest entries if over max_entries limit."""
        try:
            session = self._get_session()
            # Count current entries
            count_result = session.execute(
                text("SELECT COUNT(*) FROM project_knowledge WHERE project_id = :project_id"),
                {"project_id": self.project_id},
            )
            current_count = count_result.scalar()

            if current_count <= max_entries:
                session.close()
                return 0

            # Delete oldest entries beyond the limit
            to_delete = current_count - max_entries
            result = session.execute(
                text("""
                    DELETE FROM project_knowledge
                    WHERE id IN (
                        SELECT id FROM project_knowledge
                        WHERE project_id = :project_id
                        ORDER BY created_at ASC
                        LIMIT :limit
                    )
                    RETURNING id
                """),
                {"project_id": self.project_id, "limit": to_delete},
            )
            deleted = len(result.fetchall())
            session.commit()
            session.close()
            return deleted
        except Exception:
            return 0

    def _prune_duplicates(self, similarity_threshold: float) -> int:
        """Remove entries with very similar embeddings (deduplication).

        Note: This is expensive and requires pgvector.
        """
        try:
            session = self._get_session()
            # Find duplicate pairs using cosine similarity
            result = session.execute(
                text("""
                    WITH duplicates AS (
                        SELECT a.id AS id_to_keep, b.id AS id_to_delete
                        FROM project_knowledge a
                        JOIN project_knowledge b ON a.id < b.id
                        WHERE a.project_id = :project_id
                        AND b.project_id = :project_id
                        AND a.embedding IS NOT NULL
                        AND b.embedding IS NOT NULL
                        AND 1 - (a.embedding <=> b.embedding) > :threshold
                    )
                    DELETE FROM project_knowledge
                    WHERE id IN (SELECT id_to_delete FROM duplicates)
                    RETURNING id
                """),
                {"project_id": self.project_id, "threshold": similarity_threshold},
            )
            deleted = len(result.fetchall())
            session.commit()
            session.close()
            return deleted
        except Exception:
            return 0

    def stats(self) -> dict:
        """Get statistics about the knowledge base.

        Returns:
            {"success": True, "stats": {"total": N, "by_type": {...}, "oldest": date, "newest": date}}
        """
        try:
            session = self._get_session()

            # Total count
            total = session.execute(
                text("SELECT COUNT(*) FROM project_knowledge WHERE project_id = :project_id"),
                {"project_id": self.project_id},
            ).scalar()

            # Count by type
            type_counts = session.execute(
                text("""
                    SELECT content_type, COUNT(*)
                    FROM project_knowledge
                    WHERE project_id = :project_id
                    GROUP BY content_type
                """),
                {"project_id": self.project_id},
            ).fetchall()

            # Date range
            dates = session.execute(
                text("""
                    SELECT MIN(created_at), MAX(created_at)
                    FROM project_knowledge
                    WHERE project_id = :project_id
                """),
                {"project_id": self.project_id},
            ).fetchone()

            session.close()

            return {
                "success": True,
                "stats": {
                    "total": total,
                    "by_type": {row[0]: row[1] for row in type_counts},
                    "oldest": dates[0].isoformat() if dates[0] else None,
                    "newest": dates[1].isoformat() if dates[1] else None,
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

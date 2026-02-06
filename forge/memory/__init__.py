"""Forge Memory - Project knowledge storage and retrieval with embeddings.

This module provides semantic search over stored code snippets, documentation,
and solutions using pgvector embeddings.

Usage:
    from forge.memory import ProjectMemory

    memory = ProjectMemory(project_id=1)
    memory.store("code", content="def hello(): pass", file_path="hello.py")
    results = memory.search("greeting function")
"""
from forge.memory.store import ProjectMemory

__all__ = ["ProjectMemory"]

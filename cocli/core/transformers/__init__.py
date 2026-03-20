"""
Transformers: From-model-to-model transformation modules.

Each module implements a specific transformation between two data models,
following the WAL (Write-Ahead Log) compaction pattern.
"""

from .gm_list_to_checkpoint import compact_gm_list_results

__all__ = ["compact_gm_list_results"]

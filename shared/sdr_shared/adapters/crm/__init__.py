"""Adaptadores da porta de CRM."""
from .ausente import CRMAusente
from .via_mcp import CRMviaMCP

__all__ = ["CRMAusente", "CRMviaMCP"]

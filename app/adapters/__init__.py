from .registry import build_adapter, register_adapter

gateway = build_adapter()

__all__ = ["gateway", "build_adapter", "register_adapter"]

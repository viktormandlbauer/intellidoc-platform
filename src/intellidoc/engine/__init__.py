"""The processing engine: one document in, one typed and gated result out.

Each stage is a package behind an interface (`parsing.Parser`, `classification.Classifier`) and
`pipeline.DocumentPipeline` wires them. The engine knows nothing about queues, users or
repositories; the worker and the service build on it.
"""
from .config import ConfigError, Settings, load_settings
from ..contracts.results import ClassificationResult
from .pipeline import DocumentPipeline

__all__ = ["ClassificationResult", "ConfigError", "DocumentPipeline", "Settings", "load_settings"]

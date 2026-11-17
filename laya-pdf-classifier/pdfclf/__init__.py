"""PDF classification prototype built on Laya."""
from .classifier import PdfClassifier, Result
from .config import Config, load_config

__all__ = ["PdfClassifier", "Result", "Config", "load_config"]
__version__ = "0.1.0"

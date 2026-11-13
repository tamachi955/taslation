"""TASlation - self-contained, offline manga translation for books you own.

Everything happens on this machine: window capture, text detection, OCR,
translation (through a local Ollama server) and rendering. Page images only
ever live in memory; the only thing written to disk is a text-only cache of
your translations keyed by page fingerprints. See ``taslation.netguard`` for
how the "nothing leaves the machine" rule is enforced at the socket layer.
"""

__version__ = "0.1.0"

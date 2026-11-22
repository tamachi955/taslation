"""TASlation - self-contained, offline manga translation for books you own.

Everything happens on this machine: window capture, text detection, OCR,
translation (through a local Ollama server) and rendering. Page images only
ever live in memory; what is written to disk is text (the translations keyed
by page fingerprints and what docs/MANUAL.md lists beside them). See
``taslation.netguard`` for how this program's own network calls are refused
while it reads.
"""

__version__ = "0.9.8"

# scrapers/__init__.py

# Monkey-patch Twisted's line length limits to prevent ValueError/unpacking errors
# when parsing extremely long response headers (e.g. Yahoo Finance Link headers).
try:
    from twisted.protocols.basic import LineReceiver, LineOnlyReceiver
    LineReceiver.MAX_LENGTH = 1048576  # 1MB
    LineOnlyReceiver.MAX_LENGTH = 1048576
except ImportError:
    pass

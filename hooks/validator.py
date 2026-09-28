#!/usr/bin/env python3
"""Backwards compatibility wrapper for hooks.tribunal."""
import os
import sys

_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from hooks.tribunal import *
from hooks.tribunal import _plugin_root

if __name__ == "__main__":
    from hooks.tribunal import main
    main()

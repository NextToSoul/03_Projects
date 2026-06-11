#!/usr/bin/env python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.app import main

if __name__ == "__main__":
    sys.exit(main())

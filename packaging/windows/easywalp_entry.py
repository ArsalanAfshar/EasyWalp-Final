# PyInstaller entry script: a top-level module that imports the EasyWalp package.
# (A package-internal __main__.py would lose its package context when frozen.)
import sys

from easywalp.__main__ import main

if __name__ == "__main__":
    # .easywalp files arrive as argv[1] (file association / drag & drop onto the exe).
    sys.exit(main())

"""入口：python run.py [--mock] [--no-gui] [--port N]"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))

from main import main  # noqa: E402

if __name__ == "__main__":
    main()

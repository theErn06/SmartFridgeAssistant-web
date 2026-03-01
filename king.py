import subprocess
import sys
import os

BASE = os.path.dirname(os.path.abspath(__file__))

p1 = subprocess.Popen([sys.executable, os.path.join(BASE, "fridge_assistant2_5.py")])
p2 = subprocess.Popen([sys.executable, os.path.join(BASE, "watcher2.py")])
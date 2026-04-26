import sys
import os


def get_base_dir() -> str:
    if getattr(sys, 'frozen', False):
        # --onefile: bundled data files extract to sys._MEIPASS
        # --onedir:  bundled data files sit next to the exe
        if hasattr(sys, '_MEIPASS'):
            return sys._MEIPASS
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

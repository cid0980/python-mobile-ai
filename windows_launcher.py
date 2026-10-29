"""Keep Windows background launch failures visible and persistent."""
import ctypes
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys


def main():
    log_dir = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'SpecDeck' / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / 'app.log'
    handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=3, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    # uvicorn expects writable streams even when invoked without a console.
    with log_path.open('a', encoding='utf-8', buffering=1) as stream:
        sys.stdout = sys.stderr = stream
        try:
            from app import main as run_app
            run_app()
            return 0
        except BaseException:
            logging.exception('SpecDeck launch failed')
            if os.name == 'nt':
                ctypes.windll.user32.MessageBoxW(None,
                    f'SpecDeck could not start. See {log_path}\n'
                    'Run start_windows.bat --console for diagnostics.',
                    'SpecDeck startup error', 0x10)
            return 1


if __name__ == '__main__':
    raise SystemExit(main())

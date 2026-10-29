import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import autostart_manager as manager


class WindowsSetupTests(unittest.TestCase):
    def test_shortcut_handles_apostrophes_spaces_and_unicode(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / 'Startup' / 'SpecDeck.lnk'
            with patch.object(manager, 'PROJECT_DIR', Path("C:/Users/O'Brien/தமிழ் Project")), patch.object(manager.subprocess, 'run') as run:
                manager._create_windows_link(destination)
            args = run.call_args.args[0]
            command = base64.b64decode(args[-1]).decode('utf-16le')
            self.assertIn("O''Brien", command)
            self.assertIn('தமிழ் Project', command)
            self.assertIn('--silent', command)
            self.assertIn('$ErrorActionPreference', command)
            self.assertNotIn('wscript.exe', command)

    def test_shortcut_failure_propagates(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(manager.subprocess, 'run', side_effect=RuntimeError('denied')):
                with self.assertRaisesRegex(RuntimeError, 'denied'):
                    manager._create_windows_link(Path(temp) / 'app.lnk')

    def test_batch_preserves_actual_exit_code(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / 'start_windows.bat').read_text()
        self.assertIn('set "RESULT=%ERRORLEVEL%"', text)
        self.assertIn('exit /b %RESULT%', text)
        self.assertNotIn('pythonw', text)


if __name__ == '__main__':
    unittest.main()

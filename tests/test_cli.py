from __future__ import annotations

import sys
import unittest

from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pbi_agent import cli


class DefaultWebCommandTests(unittest.TestCase):
    def test_main_defaults_to_web_for_global_options_only(self) -> None:
        with patch("pbi_agent.cli._handle_web_command", return_value=17) as mock_web:
            rc = cli.main(["--api-key", "test-key"])

        self.assertEqual(rc, 17)
        args, settings = mock_web.call_args.args
        self.assertEqual(args.command, "web")
        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 8000)
        self.assertEqual(settings.api_key, "test-key")

    def test_main_inserts_web_before_web_specific_flags(self) -> None:
        with patch("pbi_agent.cli._handle_web_command", return_value=23) as mock_web:
            rc = cli.main(
                ["--api-key", "test-key", "--host", "0.0.0.0", "--port", "9001"]
            )

        self.assertEqual(rc, 23)
        args, settings = mock_web.call_args.args
        self.assertEqual(args.command, "web")
        self.assertEqual(args.host, "0.0.0.0")
        self.assertEqual(args.port, 9001)
        self.assertEqual(settings.api_key, "test-key")

    def test_argv_with_default_command_keeps_root_help(self) -> None:
        parser = cli.build_parser()

        self.assertEqual(cli._argv_with_default_command(parser, ["--help"]), ["--help"])


if __name__ == "__main__":
    unittest.main()

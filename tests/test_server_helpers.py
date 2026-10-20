"""Tests the web-specific formatting without downloading Maia model.

The tests deliberately do not replace full python-chess game integration tests.
"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from opening_book import BookCandidate, BookChoice


class WebFormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The web project declares python-chess as an installation requirement.
        # CI without third-party dependencies can still verify probability math.
        if importlib.util.find_spec("chess") is None:
            fake = types.ModuleType("chess")
            fake.Board = MagicMock()
            fake.engine = types.ModuleType("chess.engine")
            fake.engine.SimpleEngine = MagicMock()
            fake.pgn = types.ModuleType("chess.pgn")
            sys.modules["chess"] = fake
            sys.modules["chess.engine"] = fake.engine
            sys.modules["chess.pgn"] = fake.pgn
            cls._injected = True
        else:
            cls._injected = False
        sys.path.insert(0, str(Path(__file__).parent.parent))
        import server
        cls.server = server

    @classmethod
    def tearDownClass(cls):
        if cls._injected:
            for name in ("chess", "chess.engine", "chess.pgn", "server"):
                sys.modules.pop(name, None)

    def test_report_includes_actual_selected_and_alternatives(self):
        board = MagicMock()
        board.san.side_effect = lambda move: move
        choice = BookChoice(
            move="e4", count=520, returned_total=950, position_total=1000,
            candidates=(BookCandidate("e4", 520), BookCandidate("d4", 280), BookCandidate("Nf3", 150)),
        )
        opts = self.server.GameOptions(elo=1500, speed="blitz")
        report = self.server.book_report(board, choice, opts)
        self.assertEqual(report["source"], "lichess")
        self.assertEqual(report["selected"]["percent"], 52.0)
        self.assertEqual(report["alternatives"][0]["percent"], 28.0)
        self.assertEqual(report["coverage_percent"], 95.0)
        self.assertEqual(report["rating_bucket"], 1400)

    def test_report_uses_total_position_not_returned_candidates(self):
        board = MagicMock()
        board.san.side_effect = lambda move: move
        choice = BookChoice(
            move="e5", count=50, returned_total=90, position_total=100,
            candidates=(BookCandidate("e5", 50), BookCandidate("c5", 40)),
        )
        report = self.server.book_report(board, choice, self.server.GameOptions())
        self.assertEqual(report["selected"]["percent"], 50.0)
        self.assertEqual(report["coverage_percent"], 90.0)

    def test_reject_invalid_game_settings(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            self.server.GameOptions(elo=900)
        with self.assertRaises(ValidationError):
            self.server.GameOptions(min_games=0)


if __name__ == "__main__":
    unittest.main()

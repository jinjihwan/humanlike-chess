import random
import unittest

from opening_book import BookCandidate, BookChoice, OpeningBook, format_book_statistics, rating_bucket


class FakeResponse:
    status_code = 200

    def __init__(self, data, status=200):
        self.data = data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def json(self):
        return self.data


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = 0
        self.headers = {}
        self.last_params = {}

    def get(self, url, params, timeout):
        self.calls += 1
        self.last_params = params
        return self.response

    def close(self):
        pass


class FakeBoard:
    def __init__(self, moves_count=0):
        self.move_stack = [None] * moves_count
        self.legal_moves = {"e2e4", "d2d4"}

    def fen(self):
        return "starting position"

    def parse_uci(self, uci):
        if uci not in self.legal_moves:
            raise ValueError("not a legal move")
        return uci

    def san(self, move):
        return {"e2e4": "e4", "d2d4": "d4"}[move]


def data(count_e4=70, count_d4=30, rest=0):
    return {
        "white": count_e4 + count_d4 + rest,
        "draws": 0,
        "black": 0,
        "moves": [
            {"uci": "e2e4", "white": count_e4, "draws": 0, "black": 0},
            {"uci": "d2d4", "white": count_d4, "draws": 0, "black": 0},
        ],
    }


class TestOpeningBook(unittest.TestCase):
    def test_rating_bucket(self):
        self.assertEqual(rating_bucket(1500), 1400)
        self.assertEqual(rating_bucket(1600), 1600)
        self.assertEqual(rating_bucket(2599), 2500)
        self.assertEqual(rating_bucket(800), 0)

    def test_sampling_matches_human_counts_and_caches(self):
        session = FakeSession(FakeResponse(data()))
        book = OpeningBook(elo=1500, session=session)
        board = FakeBoard()
        rng = random.Random(42)
        sampled = [book.choose(board, rng).move for _ in range(4000)]
        fraction = sampled.count("e2e4") / 4000
        self.assertGreater(fraction, 0.68)
        self.assertLess(fraction, 0.72)
        self.assertEqual(session.calls, 1)
        self.assertEqual(session.last_params["ratings"], "1400")

    def test_book_choice_keeps_ranked_human_candidates(self):
        book = OpeningBook(session=FakeSession(FakeResponse(data(30, 70))))
        choice = book.choose(FakeBoard(), random.Random(1))
        self.assertEqual([(c.move, c.count) for c in choice.candidates], [
            ("d2d4", 70), ("e2e4", 30)
        ])

    def test_stats_use_full_position_denominator_not_renormalized_sample(self):
        choice = BookChoice(
            move="e2e4", count=40, returned_total=100, position_total=120,
            candidates=(BookCandidate("d2d4", 60), BookCandidate("e2e4", 40))
        )
        msg = format_book_statistics(FakeBoard(), choice, alternatives=3)
        self.assertIn("선택한 수: e4 — 33.3% (40/120판)", msg)
        self.assertIn("다른 주요 후보: d4 50.0% (60판)", msg)
        self.assertIn("전체 120판의 83.3%", msg)
        self.assertNotIn("e4 33.3% (40판)", msg)  # selected move not duplicated

    def test_can_disable_alternatives(self):
        choice = BookChoice(
            move="e2e4", count=100, returned_total=100, position_total=100,
            candidates=(BookCandidate("e2e4", 100),)
        )
        msg = format_book_statistics(FakeBoard(), choice, alternatives=0)
        self.assertNotIn("다른 주요 후보", msg)
        self.assertNotIn("참고:", msg)

    def test_only_one_legal_candidate(self):
        choice = BookChoice(
            move="e2e4", count=100, returned_total=100, position_total=100,
            candidates=(BookCandidate("e2e4", 100),)
        )
        self.assertIn("집계된 다른 합법적 수 없음", format_book_statistics(FakeBoard(), choice))

    def test_fallback_on_small_sample(self):
        book = OpeningBook(min_games=100, session=FakeSession(FakeResponse(data(7, 3))))
        self.assertIsNone(book.choose(FakeBoard(), random.Random()))

    def test_fallback_on_truncated_coverage(self):
        book = OpeningBook(coverage=0.90, session=FakeSession(FakeResponse(data(45, 35, 20))))
        self.assertIsNone(book.choose(FakeBoard(), random.Random()))

    def test_fallback_after_opening_length(self):
        session = FakeSession(FakeResponse(data()))
        book = OpeningBook(max_plies=6, session=session)
        self.assertIsNone(book.choose(FakeBoard(moves_count=6), random.Random()))
        self.assertEqual(session.calls, 0)

    def test_rate_limit_disables_api(self):
        session = FakeSession(FakeResponse({}, status=429))
        book = OpeningBook(session=session)
        self.assertIsNone(book.choose(FakeBoard(), random.Random()))
        self.assertIsNotNone(book.disabled_reason)
        self.assertIsNone(book.choose(FakeBoard(), random.Random()))
        self.assertEqual(session.calls, 1)

    def test_illegal_moves_are_discarded(self):
        p = data(90, 0)
        p["moves"].append({"uci": "f7f5", "white": 10, "draws": 0, "black": 0})
        p["white"] += 10
        book = OpeningBook(coverage=0.80, session=FakeSession(FakeResponse(p)))
        choice = book.choose(FakeBoard(), random.Random(1))
        self.assertEqual(choice.move, "e2e4")


if __name__ == "__main__":
    unittest.main()

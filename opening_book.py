"""Lichess Opening Explorer client and empirical human-move sampler.

This module deliberately does not use game results as an evaluation score.
It samples moves from their observed frequencies at a chosen rating band.
"""
from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from typing import Any

import requests

EXPLORER_URL = "https://explorer.lichess.org/lichess"
RATING_BUCKETS = (0, 1000, 1200, 1400, 1600, 1800, 2000, 2200, 2500)
STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def rating_bucket(elo: int) -> int:
    """Map a target Elo to Lichess's discrete rating buckets."""
    return max(bucket for bucket in RATING_BUCKETS if bucket <= elo) if elo >= 0 else 0


@dataclass(frozen=True)
class BookCandidate:
    move: Any  # chess.Move
    count: int  # games in which this move was played


@dataclass(frozen=True)
class BookChoice:
    move: Any  # chess.Move; avoid coupling this module to python-chess at import time
    count: int  # number of games with this move
    returned_total: int  # games represented by returned legal candidates
    position_total: int  # all games for the position in the selected band
    candidates: tuple[BookCandidate, ...]  # candidates ranked by real game frequency


def format_book_statistics(board: Any, choice: BookChoice, alternatives: int = 3) -> str:
    """Describe what humans played in this position, not move quality.

    Percentages use *all* games observed at this position, not just the
    returned candidate list. SAN must be calculated before the move is pushed.
    """
    if alternatives < 0:
        raise ValueError("alternatives must be >= 0")
    total = choice.position_total
    if total <= 0:
        raise ValueError("position_total must be positive")

    selected_san = board.san(choice.move)
    lines = [
        f"  선택한 수: {selected_san} — {choice.count / total:.1%} "
        f"({choice.count:,}/{total:,}판)",
    ]
    others = [item for item in choice.candidates if item.move != choice.move]
    if alternatives > 0:
        if others:
            descriptions = [
                f"{board.san(item.move)} {item.count / total:.1%} ({item.count:,}판)"
                for item in others[:alternatives]
            ]
            lines.append("  다른 주요 후보: " + " | ".join(descriptions))
        else:
            lines.append("  다른 주요 후보: 집계된 다른 합법적 수 없음")
    if choice.returned_total < total:
        lines.append(
            f"  참고: 반환된 후보는 전체 {total:,}판의 "
            f"{choice.returned_total / total:.1%}를 포함 (그 외 수는 미표시)"
        )
    return "\n".join(lines)


class OpeningBook:
    def __init__(
        self,
        elo: int = 1500,
        speed: str = "rapid",
        min_games: int = 100,
        max_plies: int = 24,
        coverage: float = 0.90,
        max_moves: int = 16,
        timeout: float = 20.0,
        session: Any = None,
        token: str | None = None,
    ) -> None:
        self.elo = elo
        self.speed = speed
        self.min_games = min_games
        self.max_plies = max_plies
        self.coverage = coverage
        self.max_moves = max_moves
        self.timeout = timeout
        self.session = session if session is not None else requests.Session()
        self.session.headers.update({"User-Agent": "HumanlikeChessBot/0.2 (personal chess study)"})
        # Since April 2026, Lichess Opening Explorer requires OAuth authentication.
        # A personal access token with no extra OAuth scopes is sufficient for
        # personal use. Never embed this secret in frontend JavaScript or Git.
        self._auth_token = token.strip() if token is not None else os.environ.get("LICHESS_TOKEN", "").strip()
        if self._auth_token:
            self.session.headers.update({"Authorization": f"Bearer {self._auth_token}"})
        self._cache: dict[str, dict[str, Any]] = {}
        self.disabled_reason: str | None = None
        self.last_reason: str | None = None

    def choose(self, board: Any, rng: random.Random) -> BookChoice | None:
        """Return a human-frequency weighted move, or None for Maia fallback.

        board supports `fen()`, `move_stack`, `parse_uci()`, `legal_moves`.
        Network errors/429 disable further explorer queries for this session.
        """
        self.last_reason = None
        if self.disabled_reason:
            self.last_reason = self.disabled_reason
            return None
        if len(board.move_stack) >= self.max_plies:
            self.last_reason = f"오프닝 깊이 제한({self.max_plies}반수)에 도달했습니다."
            return None

        fen = board.fen()
        if fen not in self._cache:
            # For a normal game from the standard start position, prefer the
            # official `play` parameter (a sequence of UCI moves). The FEN
            # request remains available as a safe alternative for transient
            # 5xx errors and games that started from custom positions.
            params = {
                "variant": "standard",
                "ratings": str(rating_bucket(self.elo)),
                "speeds": self.speed,
                "moves": self.max_moves,
                "topGames": 0,
                "recentGames": 0,
            }
            moves = getattr(board, "move_stack", [])
            can_use_play = False
            if moves and callable(getattr(board, "root", None)):
                try:
                    can_use_play = board.root().fen() == STARTING_FEN
                except (ValueError, AttributeError, TypeError):
                    pass
            if can_use_play:
                params["play"] = ",".join(move.uci() for move in moves)
            else:
                params["fen"] = fen

            for attempt in range(2):
                try:
                    response = self.session.get(EXPLORER_URL, params=params, timeout=self.timeout)
                    if response.status_code == 401:
                        self.last_reason = (
                            "Lichess 오프닝 API 인증 실패(HTTP 401). "
                            + ("LICHESS_TOKEN이 서버에 전달되었는지, 토큰이 유효한지 확인하세요."
                               if self._auth_token else "LICHESS_TOKEN 환경 변수가 설정되지 않았습니다. 인증 토큰을 등록한 뒤 서버를 재시작하세요.")
                        )
                        return None
                    if response.status_code == 403:
                        self.last_reason = "Lichess API 접근 거부(HTTP 403). 토큰 권한/상태와 Lichess 정책을 확인하세요."
                        return None
                    if response.status_code == 429:
                        self.disabled_reason = "Lichess API 요청 제한(HTTP 429)으로 이 대국의 조회를 중단했습니다."
                        self.last_reason = self.disabled_reason
                        return None
                    if 500 <= response.status_code <= 599:
                        if attempt == 0:
                            # A second request with the alternate documented
                            # parameter may overcome a transient backend error.
                            if "play" in params:
                                del params["play"]
                                params["fen"] = fen
                            time.sleep(0.75)
                            continue
                        self.last_reason = (
                            f"Lichess 서버 오류(HTTP {response.status_code}). "
                            "재시도도 실패했습니다. Lichess 측 장애 여부를 확인하거나 잠시 후 다시 시도하세요."
                        )
                        return None
                    response.raise_for_status()
                    data = response.json()
                    if not isinstance(data, dict):
                        raise ValueError("Unexpected Lichess JSON structure")
                    self._cache[fen] = data
                    break
                except (requests.RequestException, ValueError) as exc:
                    self.last_reason = (
                        f"Lichess 통계 API 조회 실패 ({type(exc).__name__}): {str(exc)[:180]}"
                    )
                    return None

        data = self._cache[fen]
        position_total = sum(max(0, int(data.get(key, 0))) for key in ("white", "draws", "black"))
        if position_total < self.min_games:
            self.last_reason = (
                f"현재 포지션의 대국 표본이 {position_total:,}판으로 "
                f"최소 기준 {self.min_games:,}판보다 적습니다."
            )
            return None

        candidates: list[Any] = []
        weights: list[int] = []
        for entry in data.get("moves", []):
            try:
                move = board.parse_uci(entry["uci"])
                if move not in board.legal_moves:
                    continue
                count = sum(max(0, int(entry.get(key, 0))) for key in ("white", "draws", "black"))
            except (ValueError, KeyError, TypeError):
                continue
            if count > 0:
                candidates.append(move)
                weights.append(count)

        returned_total = sum(weights)
        # Explorer returns only the top N moves; do not silently renormalize
        # a severely truncated distribution.
        if not candidates:
            self.last_reason = "Lichess가 현재 포지션에서 합법적인 후보 수를 반환하지 않았습니다."
            return None
        if returned_total / position_total < self.coverage:
            self.last_reason = (
                f"조회된 후보의 표본 포함 비율이 {returned_total / position_total:.1%}로 "
                f"요구 기준 {self.coverage:.0%}보다 낮습니다."
            )
            return None

        index = rng.choices(range(len(candidates)), weights=weights, k=1)[0]
        ranked = tuple(
            sorted(
                (BookCandidate(move, count) for move, count in zip(candidates, weights)),
                key=lambda item: item.count,
                reverse=True,
            )
        )
        return BookChoice(
            candidates[index], weights[index], returned_total, position_total, ranked
        )

    def close(self) -> None:
        if hasattr(self.session, "close"):
            self.session.close()

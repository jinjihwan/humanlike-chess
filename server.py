"""Mobile-friendly Lichess + Maia-3 human-move chess website.

Run from this directory: python -m uvicorn server:app --host 0.0.0.0 --port 8000
For personal use; do not expose to the public without auth/rate limiting.
"""
from __future__ import annotations

import importlib.util
import random
import secrets
import sys
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

import chess
import chess.engine
import chess.pgn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from opening_book import OpeningBook, BookChoice, rating_bucket

ROOT = Path(__file__).resolve().parent
TTL_SECONDS = 2 * 60 * 60
MAX_SESSIONS = 12


class GameOptions(BaseModel):
    elo: int = Field(default=1500, ge=1000, le=2500)
    color: Literal["white", "black"] = "white"
    speed: Literal["bullet", "blitz", "rapid", "classical"] = "blitz"
    model: Literal["5m", "23m", "79m"] = "5m"
    min_games: int = Field(default=500, ge=1, le=100000)
    book_plies: int = Field(default=30, ge=0, le=100)


class UserMove(BaseModel):
    uci: str = Field(min_length=4, max_length=5)


@dataclass
class Session:
    id: str
    options: GameOptions
    board: chess.Board = field(default_factory=chess.Board)
    lock: threading.RLock = field(default_factory=threading.RLock)
    rng: random.Random = field(default_factory=random.Random)
    book: OpeningBook | None = None
    engine: chess.engine.SimpleEngine | None = None
    last_report: dict | None = None
    resignation: str | None = None
    touched: float = field(default_factory=time.monotonic)

    def __post_init__(self):
        self.book = OpeningBook(
            elo=self.options.elo,
            speed=self.options.speed,
            min_games=self.options.min_games,
            max_plies=self.options.book_plies,
            coverage=0.90,
            max_moves=16,
            timeout=20.0,
        )

    @property
    def human_white(self) -> bool:
        return self.options.color == "white"

    def close(self) -> None:
        if self.book is not None:
            self.book.close()
        if self.engine is not None:
            try:
                self.engine.close()
            except Exception:
                pass
            self.engine = None

    def ready_engine(self) -> chess.engine.SimpleEngine:
        if self.engine is not None:
            return self.engine
        if importlib.util.find_spec("maia3") is None:
            raise HTTPException(
                status_code=503,
                detail="Maia-3가 서버에 설치되지 않았습니다. README의 Maia-3 설치 단계를 실행해 주세요.",
            )
        cmd = [
            sys.executable, "-m", "maia3.uci", "--model", f"maia3-{self.options.model}",
            "--use-uci-history", "--elo", str(self.options.elo),
            "--temperature", "1.0", "--top-p", "1.0",
            "--seed", str(secrets.randbelow(2**31)),
        ]
        try:
            self.engine = chess.engine.SimpleEngine.popen_uci(cmd, timeout=180)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Maia-3 실행 오류: {str(exc)[:240]}. 모델을 미리 다운로드했는지 확인해 주세요.",
            ) from exc
        return self.engine

    def status(self) -> tuple[str, str]:
        if self.resignation:
            return "resigned", self.resignation
        outcome = self.board.outcome(claim_draw=False)
        if outcome is not None:
            return "finished", outcome.result()
        return "playing", "*"

    def view(self) -> dict:
        board = self.board
        status, result = self.status()
        squares = {chess.square_name(sq): piece.symbol() for sq, piece in board.piece_map().items()}
        human_turn = status == "playing" and board.turn == self.human_white
        moves = []
        if human_turn:
            for move in board.legal_moves:
                moves.append({
                    "from": chess.square_name(move.from_square),
                    "to": chess.square_name(move.to_square),
                    "promotion": chess.piece_symbol(move.promotion) if move.promotion else None,
                    "uci": move.uci(),
                })
        replay = chess.Board()
        history = []
        for move in board.move_stack:
            history.append({
                "number": replay.fullmove_number,
                "color": "white" if replay.turn == chess.WHITE else "black",
                "san": replay.san(move),
            })
            replay.push(move)
        last = board.peek() if board.move_stack else None
        check_sq = board.king(board.turn) if board.is_check() else None
        return {
            "id": self.id,
            "options": self.options.model_dump(),
            "fen": board.fen(),
            "pieces": squares,
            "turn": "white" if board.turn else "black",
            "human_turn": human_turn,
            "legal_moves": moves,
            "history": history,
            "last_move": (
                {"from": chess.square_name(last.from_square), "to": chess.square_name(last.to_square)}
                if last else None
            ),
            "check_square": chess.square_name(check_sq) if check_sq is not None else None,
            "status": status,
            "result": result,
            "last_bot": self.last_report,
            "book_issue": self.book.disabled_reason if self.book else None,
        }


def book_report(board: chess.Board, choice: BookChoice, options: GameOptions) -> dict:
    """All percentages use the *position* denominator; no invented Maia stats."""
    total = choice.position_total
    def candidate(move, count):
        return {"san": board.san(move), "count": count, "percent": round(count * 100 / total, 2)}
    selected = candidate(choice.move, choice.count)
    alternatives = [
        candidate(item.move, item.count)
        for item in choice.candidates if item.move != choice.move
    ][:4]
    return {
        "source": "lichess",
        "move": selected["san"],
        "selected": selected,
        "alternatives": alternatives,
        "total_games": total,
        "coverage_percent": round(choice.returned_total * 100 / total, 2),
        "rating_bucket": rating_bucket(options.elo),
        "speed": options.speed,
    }


_registry: dict[str, Session] = {}
_registry_lock = threading.RLock()


def clear_expired() -> None:
    """Release resources of inactive games and avoid unlimited Maia processes."""
    now = time.monotonic()
    with _registry_lock:
        for key, item in list(_registry.items()):
            if now - item.touched > TTL_SECONDS:
                if item.lock.acquire(blocking=False):
                    try:
                        del _registry[key]
                        item.close()
                    finally:
                        item.lock.release()


def game_or_404(game_id: str) -> Session:
    clear_expired()
    with _registry_lock:
        game = _registry.get(game_id)
        if game is None:
            raise HTTPException(404, "대국을 찾을 수 없습니다. 새 대국을 시작해 주세요.")
        game.touched = time.monotonic()
        return game


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    with _registry_lock:
        for game in _registry.values():
            game.close()
        _registry.clear()


app = FastAPI(title="Humanlike Chess", version="1.0", lifespan=lifespan)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/static/{name}", include_in_schema=False)
def assets(name: str):
    # Only allow two explicitly shipped files; no user-controlled paths.
    if name not in ("app.js", "style.css"):
        raise HTTPException(404)
    file = ROOT / "static" / name
    return FileResponse(file, media_type="text/javascript" if name.endswith(".js") else "text/css")


@app.get("/api/health")
def health():
    return {"ok": True, "maia_installed": importlib.util.find_spec("maia3") is not None}


@app.post("/api/games")
def create_game(options: GameOptions):
    clear_expired()
    with _registry_lock:
        if len(_registry) >= MAX_SESSIONS:
            raise HTTPException(429, "이 서버에서 진행할 수 있는 대국 수를 초과했습니다.")
        token = secrets.token_urlsafe(22)
        game = Session(id=token, options=options)
        _registry[token] = game
    return game.view()


@app.get("/api/games/{game_id}")
def get_game(game_id: str):
    game = game_or_404(game_id)
    with game.lock:
        return game.view()


@app.post("/api/games/{game_id}/move")
def user_move(game_id: str, request: UserMove):
    game = game_or_404(game_id)
    with game.lock:
        state, _ = game.status()
        if state != "playing" or game.board.turn != game.human_white:
            raise HTTPException(409, "지금은 내 차례가 아닙니다.")
        try:
            move = chess.Move.from_uci(request.uci.strip().lower())
        except ValueError:
            raise HTTPException(422, "UCI 수 형식이 올바르지 않습니다.")
        if move not in game.board.legal_moves:
            raise HTTPException(422, "합법적인 수가 아닙니다.")
        game.board.push(move)
        return game.view()


@app.post("/api/games/{game_id}/bot")
def bot_move(game_id: str):
    game = game_or_404(game_id)
    with game.lock:
        state, _ = game.status()
        if state != "playing" or game.board.turn == game.human_white:
            raise HTTPException(409, "지금은 봇의 차례가 아닙니다.")
        board = game.board
        choice = game.book.choose(board, game.rng) if game.book else None
        if choice is not None:
            move = choice.move
            report = book_report(board, choice, game.options)
        else:
            engine = game.ready_engine()
            try:
                response = engine.play(board, chess.engine.Limit(nodes=1))
            except Exception as exc:
                game.engine = None
                try:
                    engine.close()
                except Exception:
                    pass
                raise HTTPException(503, f"Maia-3 착수 오류: {str(exc)[:240]}") from exc
            move = response.move
            report = (
                {
                    "source": "maia",
                    "move": board.san(move),
                    "reason": game.book.last_reason if game.book else "오프닝 통계 엔진이 없습니다.",
                }
                if move is not None else None
            )
        if move is None or move not in board.legal_moves:
            raise HTTPException(503, "봇이 합법적 수를 반환하지 않았습니다.")
        board.push(move)
        game.last_report = report
        return game.view()


@app.post("/api/games/{game_id}/undo")
def undo_turn(game_id: str):
    game = game_or_404(game_id)
    with game.lock:
        if game.resignation:
            raise HTTPException(409, "기권한 대국은 되돌릴 수 없습니다.")
        if not game.board.move_stack:
            raise HTTPException(409, "되돌릴 수 있는 수가 없습니다.")
        # Normal: human's turn -> undo bot + human. Bot's turn -> undo human only.
        game.board.pop()
        if game.board.move_stack and game.board.turn != game.human_white:
            game.board.pop()
        game.last_report = None
        return game.view()


@app.post("/api/games/{game_id}/resign")
def resign(game_id: str):
    game = game_or_404(game_id)
    with game.lock:
        if game.status()[0] != "playing":
            raise HTTPException(409, "이미 종료된 대국입니다.")
        game.resignation = "0-1" if game.human_white else "1-0"
        return game.view()


@app.get("/api/games/{game_id}/pgn")
def download_pgn(game_id: str):
    game = game_or_404(game_id)
    with game.lock:
        pgn = chess.pgn.Game()
        pgn.headers.update({
            "Event": "Humanlike Chess Web",
            "Site": "Local",
            "Date": datetime.now().strftime("%Y.%m.%d"),
            "White": "Human" if game.human_white else "HybridBot",
            "Black": "HybridBot" if game.human_white else "Human",
            "Result": game.status()[1],
            "BotTargetElo": str(game.options.elo),
        })
        node = pgn
        for move in game.board.move_stack:
            node = node.add_variation(move)
        text = str(pgn) + "\n"
        return PlainTextResponse(text, media_type="application/x-chess-pgn", headers={
            "Content-Disposition": 'attachment; filename="humanlike-game.pgn"',
        })


@app.delete("/api/games/{game_id}")
def delete_game(game_id: str):
    with _registry_lock:
        game = _registry.get(game_id)
        if game is None:
            return {"ok": True}
        with game.lock:
            del _registry[game_id]
            game.close()
    return {"ok": True}

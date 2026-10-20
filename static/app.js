"use strict";

const $ = (name) => document.getElementById(name);
const PIECES = {k:"♚",q:"♛",r:"♜",b:"♝",n:"♞",p:"♟",K:"♚",Q:"♛",R:"♜",B:"♝",N:"♞",P:"♟"};
const NAMES = {k:"킹",q:"퀸",r:"룩",b:"비숍",n:"나이트",p:"폰"};
const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR";
const SPEED_LABELS = {bullet:"불릿",blitz:"블리츠",rapid:"래피드",classical:"클래시컬"};
const KEYS = ["q", "r", "b", "n"];

let game = null;
let activeColor = "white";
let selected = null;
let busy = false;
let promotionOptions = null;

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (x) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
}

async function api(path, method = "GET", body = null) {
  let response;
  try {
    response = await fetch(path, {method, headers: {"Content-Type":"application/json"}, body: body === null ? undefined : JSON.stringify(body), cache:"no-store"});
  } catch (_err) {
    throw new Error("웹 서버에 연결하지 못했습니다. 서버가 실행 중인지 확인해 주세요.");
  }
  let data;
  try { data = await response.json(); }
  catch (_err) { throw new Error(`서버 응답을 읽을 수 없습니다. (HTTP ${response.status})`); }
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(typeof detail === "string" ? detail : `요청 오류 (HTTP ${response.status})`);
  }
  return data;
}

function parsePlacement(fen) {
  const map = {};
  const ranks = fen.split("/");
  ranks.forEach((row, index) => {
    let file = 0;
    for (const item of row) {
      if (/^[1-8]$/.test(item)) { file += Number(item); }
      else { map["abcdefgh"[file] + String(8 - index)] = item; file += 1; }
    }
  });
  return map;
}

function pieceLabel(code) {
  return `${code === code.toUpperCase() ? "백" : "흑"} ${NAMES[code.toLowerCase()] || "기물"}`;
}

function currentColor() { return game?.options?.color ?? activeColor; }

function renderBoard() {
  const map = game ? game.pieces : parsePlacement(START_FEN);
  const whiteBottom = currentColor() === "white";
  const ranks = whiteBottom ? [8,7,6,5,4,3,2,1] : [1,2,3,4,5,6,7,8];
  const files = whiteBottom ? "abcdefgh".split("") : "hgfedcba".split("");
  const canMove = game && game.human_turn && !busy;
  const targets = new Set(selected && canMove ? game.legal_moves.filter(m => m.from === selected).map(m => m.to) : []);
  const board = $("board");
  const fragment = document.createDocumentFragment();
  ranks.forEach((rank, r) => {
    files.forEach((file, f) => {
      const square = file + String(rank);
      const pieceCode = map[square];
      const light = ("abcdefgh".indexOf(file) + rank) % 2 === 0;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `square ${light ? "light" : "dark"}`;
      btn.dataset.square = square;
      if (selected === square) btn.classList.add("selected");
      if (game?.last_move && (game.last_move.from === square || game.last_move.to === square)) btn.classList.add("last-move");
      if (game?.check_square === square) btn.classList.add("checked");
      if (targets.has(square)) btn.classList.add("legal-target");
      if (pieceCode) {
        btn.classList.add("occupied");
        const piece = document.createElement("span");
        piece.className = "piece " + (pieceCode === pieceCode.toUpperCase() ? "white-piece" : "black-piece");
        piece.textContent = PIECES[pieceCode];
        btn.appendChild(piece);
      }
      btn.setAttribute("aria-label", `${square}, ${pieceCode ? pieceLabel(pieceCode) : "빈 칸"}${targets.has(square) ? ", 이동 가능" : ""}`);
      if (f === 0) {
        const c = document.createElement("span"); c.className = "coordinate rank"; c.textContent = String(rank); btn.appendChild(c);
      }
      if (r === 7) {
        const c = document.createElement("span"); c.className = "coordinate file"; c.textContent = file; btn.appendChild(c);
      }
      btn.addEventListener("click", () => clickSquare(square));
      fragment.appendChild(btn);
    });
  });
  board.replaceChildren(fragment);
}

function clickSquare(square) {
  if (busy || !game || !game.human_turn || game.status !== "playing") return;
  const available = game.legal_moves;
  if (selected) {
    const possibilities = available.filter(m => m.from === selected && m.to === square);
    if (possibilities.length === 1) {
      selected = null;
      void submitMove(possibilities[0].uci);
      return;
    }
    if (possibilities.length > 1) {
      promotionOptions = possibilities;
      showPromotion();
      return;
    }
  }
  selected = available.some(m => m.from === square) ? square : null;
  renderBoard();
}

function showPromotion() {
  $("promotion-modal").classList.remove("hidden");
  const choices = $("promotion-choices");
  choices.replaceChildren();
  for (const kind of KEYS) {
    const move = promotionOptions.find(m => m.promotion === kind);
    if (!move) continue;
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = PIECES[currentColor() === "white" ? kind.toUpperCase() : kind];
    b.setAttribute("aria-label", NAMES[kind] + "으로 승격");
    b.addEventListener("click", () => {
      closePromotion();
      selected = null;
      void submitMove(move.uci);
    });
    choices.appendChild(b);
  }
  choices.querySelector("button")?.focus();
}

function closePromotion() { $("promotion-modal").classList.add("hidden"); promotionOptions = null; }

function getOptions() {
  return {
    elo: Number($("elo").value),
    color: activeColor,
    speed: $("speed").value,
    model: $("model").value,
    min_games: Number($("min-games").value),
    book_plies: 30,
  };
}

function showError(message, retry = false) {
  const box = $("alert");
  box.replaceChildren();
  const line = document.createElement("span");
  line.textContent = message;
  box.appendChild(line);
  if (retry && game && game.turn !== game.options.color && game.status === "playing") {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "text-button";
    btn.style.cssText = "display:block;color:#fff0ca;margin-top:8px;text-decoration:underline";
    btn.textContent = "봇 착수 다시 시도 →";
    btn.addEventListener("click", () => void playBot());
    box.appendChild(btn);
  }
  box.classList.remove("hidden");
}
function clearError() { $("alert").classList.add("hidden"); }

function setBusy(flag, bot = false) {
  busy = flag;
  $("board-wait").classList.toggle("hidden", !flag || !bot);
  $("start-button").disabled = flag;
  $("top-new").disabled = flag;
  renderBoard();
  renderControls();
}

function applyGame(data) {
  game = data;
  selected = null;
  activeColor = data.options.color;
  localStorage.setItem("humanlike_chess_game", data.id);
  render();
}

async function newGame() {
  if (busy) return;
  const previousId = game?.id;
  setBusy(true);
  clearError();
  try {
    const response = await api("/api/games", "POST", getOptions());
    applyGame(response);
    if (previousId) { void api(`/api/games/${encodeURIComponent(previousId)}`, "DELETE").catch(() => {}); }
    if (!response.human_turn && response.status === "playing") {
      // Do not let another user move happen while first bot move is pending.
      await playBotInternal();
    }
  } catch (error) {
    showError(error.message, Boolean(game && !game.human_turn));
  } finally { setBusy(false); render(); }
}

async function playBotInternal() {
  if (!game || game.human_turn || game.status !== "playing") return;
  $("board-wait").classList.remove("hidden");
  try {
    const response = await api(`/api/games/${encodeURIComponent(game.id)}/bot`, "POST");
    applyGame(response);
  } catch (error) {
    showError(error.message, true);
  } finally { $("board-wait").classList.add("hidden"); }
}

async function playBot() {
  if (busy || !game) return;
  setBusy(true, true);
  clearError();
  try { await playBotInternal(); }
  finally { setBusy(false); render(); }
}

async function submitMove(uci) {
  if (busy || !game) return;
  setBusy(true);
  clearError();
  try {
    const response = await api(`/api/games/${encodeURIComponent(game.id)}/move`, "POST", {uci});
    applyGame(response);
    if (response.status === "playing" && !response.human_turn) {
      setBusy(true, true);
      await playBotInternal();
    }
  } catch (error) { showError(error.message); }
  finally { setBusy(false); render(); }
}

async function resign() {
  if (busy || !game || game.status !== "playing") return;
  if (!window.confirm("정말 기권하시겠습니까?")) return;
  setBusy(true);
  clearError();
  try { applyGame(await api(`/api/games/${encodeURIComponent(game.id)}/resign`, "POST")); }
  catch (error) { showError(error.message); }
  finally { setBusy(false); render(); }
}

async function undo() {
  if (busy || !game) return;
  setBusy(true);
  clearError();
  try { applyGame(await api(`/api/games/${encodeURIComponent(game.id)}/undo`, "POST")); }
  catch (error) { showError(error.message); }
  finally { setBusy(false); render(); }
}

function renderControls() {
  if (!game) {
    $("top-player").textContent = "Humanlike Bot";
    $("turn-pill").textContent = "대국 대기 중";
    $("move-feedback").textContent = "새 대국을 시작하세요";
    $("undo-button").disabled = true;
    $("pgn-button").disabled = true;
    $("resign-button").disabled = true;
    $("start-button").innerHTML = '대국 시작하기 <span aria-hidden="true">→</span>';
    return;
  }
  const isBlack = game.options.color === "black";
  $("top-player").textContent = `Humanlike Bot · ${game.options.elo}`;
  $("top-player-sub").textContent = `Maia3-${game.options.model.toUpperCase()} + Lichess`;
  $("bottom-player-sub").textContent = isBlack ? "흑으로 플레이" : "백으로 플레이";
  if (game.status !== "playing") {
    $("turn-pill").textContent = "대국 종료";
    $("move-feedback").textContent = game.result === "1/2-1/2" ? "무승부" : (game.result === (isBlack ? "0-1" : "1-0") ? "승리" : "패배");
  } else {
    $("turn-pill").textContent = game.turn === "white" ? "백 차례" : "흑 차례";
    $("move-feedback").textContent = game.human_turn ? (game.check_square ? "체크 · 내 차례" : "내 차례") : "봇 차례";
  }
  // Avoid offering undo when the only move is the bot's initial white move.
  const minUndo = isBlack ? 2 : 1;
  $("undo-button").disabled = busy || game.status !== "playing" || game.history.length < minUndo;
  $("pgn-button").disabled = busy || game.history.length === 0;
  $("resign-button").disabled = busy || game.status !== "playing";
  $("start-button").innerHTML = '새 대국 시작하기 <span aria-hidden="true">→</span>';
}

function renderStats() {
  const container = $("stats-content");
  const sourceTag = $("source-tag");
  const report = game?.last_bot;
  if (!report) {
    sourceTag.textContent = "대기";
    container.innerHTML = '<div class="empty-insight"><div class="empty-icon">◈</div><strong>착수 데이터가 여기에 표시돼요</strong><p>봇이 수를 두면 실제 선택 빈도와 다른 주요 후보를 확인할 수 있습니다.</p></div>';
    return;
  }
  if (report.source === "maia") {
    sourceTag.textContent = "MAIA-3";
    const reason = report.reason
      ? `전환 사유: ${escapeHtml(report.reason)}`
      : "오프닝 통계 부족 또는 오프닝 깊이 제한 (이전 버전의 대국일 수 있습니다).";
    container.innerHTML = `<div class="maia-note"><h3>${escapeHtml(report.move)} <span style="font-size:11px;color:#acd1c4">· Maia-3</span></h3><p>${reason}</p><p>이 수의 Lichess 실전 선택 비율은 제공하지 않습니다.</p></div>`;
    return;
  }
  sourceTag.textContent = "LICHESS DATA";
  const row = (candidate, isSelected) => `<div class="stat-row"><span class="name">${escapeHtml(candidate.san)}</span><div class="stat-bar"><div class="stat-fill ${isSelected ? "selected-fill" : ""}" style="width:${Math.max(0,Math.min(100,candidate.percent))}%"></div></div><span class="pct">${candidate.percent.toFixed(1)}%</span></div>`;
  const selected = report.selected;
  container.innerHTML = `
    <div class="insight-heading"><div><small>봇이 선택한 수</small><strong>${escapeHtml(selected.san)}</strong></div><span class="insight-percent">${selected.percent.toFixed(1)}%</span></div>
    <p class="insight-desc">실제 ${Number(selected.count).toLocaleString("ko-KR")} / ${Number(report.total_games).toLocaleString("ko-KR")}판에서 선택</p>
    ${row(selected,true)}
    <div class="alternative-title">다른 주요 후보</div>
    ${report.alternatives?.length ? report.alternatives.map(x => row(x,false)).join("") : '<p class="insight-desc">집계된 다른 주요 후보 없음</p>'}
    <div class="insight-footer">${escapeHtml(SPEED_LABELS[report.speed] || report.speed)} · 레이팅 ${report.rating_bucket} 구간 · 표본 ${Number(report.total_games).toLocaleString("ko-KR")}판<br />전체 표본 중 조회된 후보가 차지하는 비율 ${report.coverage_percent.toFixed(1)}%<br />수 선택 빈도이며 승률·정확도가 아닙니다.</div>`;
}

function renderHistory() {
  const list = $("move-list");
  const history = game?.history || [];
  $("move-count").textContent = `${history.length}반수`;
  if (!history.length) { list.innerHTML = '<p class="empty-moves">아직 진행한 수가 없습니다.</p>'; return; }
  const chunks = [];
  for (let i=0; i<history.length; i += 2) {
    const a = history[i];
    const b = history[i+1];
    chunks.push(`<div class="move-row"><span class="move-number">${a.number}.</span><span class="move-san ${i===history.length-1?'latest':''}">${escapeHtml(a.san)}</span><span class="move-san ${i+1===history.length-1?'latest':''}">${b ? escapeHtml(b.san) : '—'}</span></div>`);
  }
  list.innerHTML = chunks.join("");
  list.scrollTop = list.scrollHeight;
}

function render() { renderBoard(); renderControls(); renderStats(); renderHistory(); }

async function init() {
  render();
  $("elo").addEventListener("input", () => $("elo-label").textContent = $("elo").value);
  for (const btn of document.querySelectorAll("[data-color]")) {
    btn.addEventListener("click", () => {
      activeColor = btn.dataset.color;
      document.querySelectorAll("[data-color]").forEach(x => {
        x.classList.toggle("active", x === btn);
        x.setAttribute("aria-pressed", String(x === btn));
      });
      if (!game) renderBoard();
    });
  }
  $("start-button").addEventListener("click", () => void newGame());
  $("top-new").addEventListener("click", () => void newGame());
  $("undo-button").addEventListener("click", () => void undo());
  $("resign-button").addEventListener("click", () => void resign());
  $("pgn-button").addEventListener("click", () => {
    if (!game) return;
    const a = document.createElement("a");
    a.href = `/api/games/${encodeURIComponent(game.id)}/pgn`;
    a.download = "humanlike-game.pgn";
    document.body.appendChild(a); a.click(); a.remove();
  });
  $("promotion-cancel").addEventListener("click", () => {closePromotion(); renderBoard();});
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && promotionOptions) {closePromotion(); renderBoard();}
  });
  try {
    await api("/api/health");
    $("server-indicator").classList.add("online");
    $("server-indicator").querySelector("span").textContent = "서버 연결됨";
  } catch (error) {
    $("server-indicator").classList.add("offline");
    $("server-indicator").querySelector("span").textContent = "서버 연결 불가";
    showError(error.message);
    return;
  }
  const saved = localStorage.getItem("humanlike_chess_game");
  if (saved && /^[A-Za-z0-9_-]+$/.test(saved)) {
    try {
      const loaded = await api(`/api/games/${encodeURIComponent(saved)}`);
      applyGame(loaded);
    } catch (_err) { localStorage.removeItem("humanlike_chess_game"); }
  }
}

void init();

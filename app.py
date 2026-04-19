import base64, io, json, math, os, queue, re, tempfile, threading, time, wave
from functools import wraps

import numpy as np, pymysql, pymysql.cursors, requests, torch, sounddevice as sd
from dotenv import load_dotenv
from PIL import ImageGrab
from pydub import AudioSegment
from flask import (Flask, Response, jsonify, redirect, render_template,
                   request, send_from_directory, session, stream_with_context)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-me-in-production")
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB

VOICES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voices")

# ── DB ─────────────────────────────────────────────────────────────────────────
_DB = dict(
    host=os.getenv("DB_HOST", "localhost"), port=int(os.getenv("DB_PORT", 3306)),
    user=os.getenv("DB_USER", "acore"),     password=os.getenv("DB_PASS", "acore"),
    database=os.getenv("DB_NAME", "voice_assistant"),
    charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
)

def get_db():   return pymysql.connect(**_DB)

def q1(sql, args=()):
    with get_db() as c:
        with c.cursor() as cur: cur.execute(sql, args); return cur.fetchone()

def qall(sql, args=()):
    with get_db() as c:
        with c.cursor() as cur: cur.execute(sql, args); return cur.fetchall()

def exe(sql, args=()):
    conn = get_db()
    with conn:
        with conn.cursor() as cur: cur.execute(sql, args); conn.commit(); return cur.lastrowid

def get_settings() -> dict:
    try:    return {r["key_name"]: r["value"] for r in qall("SELECT key_name,value FROM settings")}
    except: return {}

def get_provider(pid) -> dict | None:
    try:    return q1("SELECT * FROM providers WHERE id=%s AND is_active=1", (pid,))
    except: return None

# ── Auth ───────────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def _(*a, **kw):
        if "user_id" not in session: return redirect("/login")
        return f(*a, **kw)
    return _

def admin_required(f):
    @wraps(f)
    def _(*a, **kw):
        if "user_id" not in session: return redirect("/login")
        if session.get("role") != "admin": return jsonify({"error": "Forbidden"}), 403
        return f(*a, **kw)
    return _

# ── VAD globals ────────────────────────────────────────────────────────────────
SAMPLE_RATE      = 16000
CHUNK_SIZE       = 512
SPEECH_ON_CHUNKS = 3
_pipeline_gen    = 0
_cancel_event    = threading.Event()
_vad_running     = False
_vad_thread      = None

# ── SSE ────────────────────────────────────────────────────────────────────────
_sse_queues: list[queue.Queue] = []
_sse_lock = threading.Lock()

def broadcast(etype, data):
    msg = {"type": etype, "data": data}
    with _sse_lock:
        dead = []
        for q in _sse_queues:
            try:    q.put_nowait(msg)
            except: dead.append(q)
        for q in dead: _sse_queues.remove(q)

# ── Load Silero VAD ─────────────────────────────────────────────────────────────
print("Carregando Silero VAD...", flush=True)
_vad_model, _ = torch.hub.load("snakers4/silero-vad", "silero_vad",
                                force_reload=False, verbose=False)
_vad_model.eval()
print("VAD pronto.", flush=True)

# ── Helpers ────────────────────────────────────────────────────────────────────
def take_screenshot() -> str:
    img = ImageGrab.grab(); buf = io.BytesIO()
    img.save(buf, "PNG"); buf.seek(0)
    return base64.b64encode(buf.read()).decode()

def chunks_to_wav(chunks) -> io.BytesIO:
    audio = np.concatenate(chunks).astype(np.float32)
    pcm   = (audio * 32767).clip(-32768, 32767).astype(np.int16)
    buf   = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE); wf.writeframes(pcm.tobytes())
    buf.seek(0); return buf

def _log(step, status, elapsed, extra=""):
    mark = "✓" if status == 200 else "✗"
    print(f"  [{mark}] {step:<18} HTTP {status}  {elapsed:.2f}s  {extra}", flush=True)

def split_tts_chunks(text: str, words_per_chunk: int = 80) -> list:
    """Split text into chunks of words_per_chunk words — never mid-word."""
    words = text.split()
    return [" ".join(words[i:i + words_per_chunk])
            for i in range(0, len(words), words_per_chunk)] or [text.strip()]

def _wav_duration(b64_str: str) -> float:
    """Return actual playback duration (seconds) of a base64-encoded WAV."""
    try:
        buf = io.BytesIO(base64.b64decode(b64_str))
        with wave.open(buf) as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        return 2.0

# ── Pipeline ───────────────────────────────────────────────────────────────────
def process_audio(chunks: list, my_gen: int, provider: dict, cfg: dict, voice_path: str = ""):
    broadcast("status", "processing")
    t_total = time.time()
    print(f"\n{'─'*52}\n  [>>] Pipeline gen={my_gen} | {provider.get('name','?')}", flush=True)

    def cancelled():
        if _cancel_event.is_set():
            print(f"  [!] gen={my_gen} cancelado", flush=True); return True
        return False

    try:
        if cancelled(): return
        wav = chunks_to_wav(chunks)

        # 1 ── Whisper ──────────────────────────────────────────────────────────
        t0 = time.time()
        r = requests.post(
            cfg.get("whisper_url", ""),
            auth=(cfg.get("whisper_user", ""), cfg.get("whisper_pass", "")),
            files={"audio": ("a.wav", wav, "audio/wav")},
            data={"model": cfg.get("whisper_model", "small"),
                  "language": cfg.get("language", "Portuguese")},
            timeout=30,
        )
        _log("Whisper", r.status_code, time.time() - t0)
        if cancelled(): return
        if r.status_code != 200:
            broadcast("error", {"api": "Whisper", "status": r.status_code, "detail": r.text[:300]}); return
        transcript = r.json().get("text", "").strip()
        if not transcript:
            print("  [!] Transcrição vazia", flush=True); return
        print(f'  [>] "{transcript}"', flush=True)
        broadcast("transcript", transcript)
        if cancelled(): return

        # 2 ── LLM ─────────────────────────────────────────────────────────────
        vision_on = (os.getenv("VISION", "no").lower() == "yes") and bool(provider.get("vision"))
        sys_prompt = cfg.get("system_prompt", "")
        max_tok    = int(cfg.get("max_output_tokens", 400))
        temp       = float(cfg.get("temperature", 0.7))

        if vision_on:
            print("  [vis] Capturando screenshot...", flush=True)
            img_b64 = take_screenshot()
            lm_url  = f"{provider['base_url']}/api/v1/chat"
            lm_body = {
                "model": provider["model"], "system_prompt": sys_prompt,
                "input": [
                    {"type": "text",  "content": f"{transcript}\n\n[Screenshot da tela anexado]"},
                    {"type": "image", "data_url": f"data:image/png;base64,{img_b64}"},
                ],
                "max_output_tokens": max_tok, "temperature": temp,
            }
        else:
            lm_url  = f"{provider['base_url']}/v1/chat/completions"
            lm_body = {
                "model": provider["model"],
                "messages": [{"role": "system", "content": sys_prompt},
                              {"role": "user",   "content": transcript}],
                "max_tokens": max_tok, "temperature": temp,
            }

        t0 = time.time()
        r  = requests.post(
            lm_url,
            headers={"Authorization": f"Bearer {provider.get('api_key','')}",
                     "Content-Type": "application/json"},
            json=lm_body, timeout=60,
        )
        _log("LLM", r.status_code, time.time() - t0,
             f"model={provider['model']}  vision={vision_on}")
        if cancelled(): return
        if r.status_code != 200:
            broadcast("error", {"api": "LLM", "status": r.status_code, "detail": r.text[:300]}); return

        rj  = r.json(); raw = rj.get("output", "")
        if isinstance(raw, list):
            ai_text = next((x["content"] for x in raw if x.get("type") == "message"), "").strip()
        else:
            ai_text = (raw or rj.get("choices",[{}])[0].get("message",{}).get("content","")).strip()

        print(f'  [>] IA: "{ai_text[:100]}{"..." if len(ai_text)>100 else ""}"', flush=True)
        broadcast("ai_text", ai_text)
        if cancelled(): return

        # 3 ── Voice (streaming chunks + adaptive buffer) ─────────────────────
        ref = voice_path or cfg.get("voice_ref_audio", "")
        if ref and os.path.exists(ref):
            tts_parts  = split_tts_chunks(ai_text)
            total      = len(tts_parts)
            start_after = 1          # default; recalculated after first chunk
            print(f"  [tts] {total} chunk(s)", flush=True)
            for i, part in enumerate(tts_parts):
                if cancelled(): break
                t0 = time.time()
                with open(ref, "rb") as fref:
                    r = requests.post(
                        cfg.get("voice_url", ""),
                        data={"text": part, "language": cfg.get("language", "Portuguese"),
                              "num_step": cfg.get("num_step", "10"),
                              "speed":    cfg.get("speed", "1.0")},
                        files={"ref_audio": ("ref.wav", fref, "audio/wav")},
                        timeout=90,
                    )
                t_gen = time.time() - t0
                _log(f"Voice [{i+1}/{total}]", r.status_code, t_gen, f'words={len(part.split())}')
                if r.status_code != 200:
                    broadcast("error", {"api": "Voice API", "status": r.status_code, "detail": r.text[:300]})
                    break
                if r.status_code == 200:
                    chunk_b64 = r.json().get("audio_base64")
                    if chunk_b64:
                        if i == 0:
                            # Adaptive: how many chunks must be buffered before playback?
                            # buffer_needed = ceil(t_gen / play_duration) + 1 safety margin
                            play_dur   = _wav_duration(chunk_b64)
                            start_after = min(total, max(1, math.ceil(t_gen / max(play_dur, 0.01)) + 1))
                            print(f"  [tts] t_gen={t_gen:.2f}s play={play_dur:.2f}s "
                                  f"→ start_after={start_after}", flush=True)
                        broadcast("audio_chunk", {
                            "index":       i,
                            "total":       total,
                            "audio":       chunk_b64,
                            "last":        i == total - 1,
                            "start_after": start_after if i == 0 else None,
                        })

        print(f"  [<<] {time.time()-t_total:.2f}s total\n{'─'*52}", flush=True)

    except Exception as e:
        print(f"  [!] {e}", flush=True); broadcast("error", str(e))
    finally:
        if not _cancel_event.is_set(): broadcast("status", "listening")

# ── VAD loop ───────────────────────────────────────────────────────────────────
def _vad_loop(provider_id: int, voice_id: int = None):
    global _vad_running, _pipeline_gen
    cfg      = get_settings()
    provider = get_provider(provider_id) or {}
    # resolve voice file path
    try:
        vrow = q1("SELECT file_path FROM voices WHERE id=%s AND is_active=1", (voice_id,)) if voice_id else None
        if not vrow:
            vrow = q1("SELECT file_path FROM voices WHERE is_default=1 AND is_active=1 LIMIT 1")
        _voice_path = vrow["file_path"] if vrow else cfg.get("voice_ref_audio", "")
    except Exception:
        _voice_path = cfg.get("voice_ref_audio", "")
    threshold   = float(cfg.get("speech_threshold", 0.5))
    end_chunks  = int(cfg.get("silence_chunks_end", 56))

    chunks: list = []; triggered = False; speech_cnt = 0; silence_cnt = 0
    _vad_model.reset_states()
    broadcast("status", "listening")

    def cb(indata, frames, ti, status):
        nonlocal chunks, triggered, speech_cnt, silence_cnt
        global _pipeline_gen
        if not _vad_running: raise sd.CallbackStop()
        chunk = indata[:, 0].copy()
        with torch.no_grad():
            prob = _vad_model(torch.from_numpy(chunk).float(), SAMPLE_RATE).item()
        if prob >= threshold:
            speech_cnt += 1; silence_cnt = 0
            if not triggered and speech_cnt >= SPEECH_ON_CHUNKS:
                triggered = True; chunks = []
                _cancel_event.set(); broadcast("status", "recording")
                print("  [mic] Fala detectada — acumulando", flush=True)
        else:
            speech_cnt = 0
            if triggered:
                silence_cnt += 1
                if silence_cnt >= end_chunks:
                    triggered = False; silence_cnt = 0
                    if chunks:
                        data = chunks.copy(); chunks = []
                        _pipeline_gen += 1; gen = _pipeline_gen
                        _cancel_event.clear()
                        run_cfg = get_settings()
                        print(f"  [mic] Silêncio final — {len(data)} chunks gen={gen}", flush=True)
                        threading.Thread(
                            target=process_audio,
                            args=(data, gen, provider, run_cfg, _voice_path),
                            daemon=True,
                        ).start()
                    else:
                        _cancel_event.clear(); broadcast("status", "listening")
        if triggered: chunks.append(chunk)

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                            blocksize=CHUNK_SIZE, callback=cb):
            while _vad_running: time.sleep(0.05)
    except Exception as e:
        broadcast("error", str(e))
    finally:
        _vad_model.reset_states(); broadcast("status", "stopped")

# ── Auth routes ────────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "")
        p = request.form.get("password", "")
        row = q1("SELECT * FROM users WHERE username=%s", (u,))
        if row and check_password_hash(row["password_hash"], p):
            session["user_id"]  = row["id"]
            session["username"] = row["username"]
            session["role"]     = row["role"]
            return redirect("/")
        return render_template("login.html", error="Usuário ou senha inválidos")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear(); return redirect("/login")

# ── Main ────────────────────────────────────────────────────────────────────────
@app.route("/static/icon.png")
def serve_icon():
    return send_from_directory(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "imagens"),
        "icon.png"
    )

@app.route("/")
@login_required
def index():
    return render_template("index.html",
                           username=session["username"],
                           role=session["role"])

@app.route("/api/me")
@login_required
def me():
    return jsonify({"username": session["username"], "role": session["role"]})

@app.route("/api/providers")
@login_required
def api_providers():
    rows = qall("SELECT id,name,model,vision FROM providers WHERE is_active=1 ORDER BY name")
    return jsonify(rows)

# ── Admin routes ───────────────────────────────────────────────────────────────
@app.route("/admin/settings", methods=["GET", "PUT"])
@admin_required
def admin_settings():
    if request.method == "GET":
        return jsonify(get_settings())
    for k, v in (request.json or {}).items():
        exe("INSERT INTO settings (key_name,value) VALUES (%s,%s) "
            "ON DUPLICATE KEY UPDATE value=%s", (k, v, v))
    return jsonify({"ok": True})

@app.route("/admin/providers", methods=["GET", "POST"])
@admin_required
def admin_providers():
    if request.method == "GET":
        return jsonify(qall("SELECT * FROM providers ORDER BY name"))
    d   = request.json or {}
    pid = exe(
        "INSERT INTO providers (name,base_url,api_key,model,vision,is_active) VALUES (%s,%s,%s,%s,%s,%s)",
        (d["name"], d["base_url"], d.get("api_key",""), d["model"],
         int(d.get("vision", 0)), int(d.get("is_active", 1))),
    )
    return jsonify({"id": pid})

@app.route("/admin/providers/<int:pid>", methods=["PUT", "DELETE"])
@admin_required
def admin_provider(pid):
    if request.method == "DELETE":
        exe("UPDATE providers SET is_active=0 WHERE id=%s", (pid,))
        return jsonify({"ok": True})
    d = request.json or {}
    if d.get("api_key"):  # only overwrite key if a new one was provided
        exe("UPDATE providers SET name=%s,base_url=%s,api_key=%s,model=%s,vision=%s,is_active=%s WHERE id=%s",
            (d["name"], d["base_url"], d["api_key"], d["model"],
             int(d.get("vision", 0)), int(d.get("is_active", 1)), pid))
    else:
        exe("UPDATE providers SET name=%s,base_url=%s,model=%s,vision=%s,is_active=%s WHERE id=%s",
            (d["name"], d["base_url"], d["model"],
             int(d.get("vision", 0)), int(d.get("is_active", 1)), pid))
    return jsonify({"ok": True})

@app.route("/admin/users", methods=["GET", "POST"])
@admin_required
def admin_users():
    if request.method == "GET":
        return jsonify(qall("SELECT id,username,role,created_at FROM users ORDER BY username"))
    d   = request.json or {}
    uid = exe(
        "INSERT INTO users (username,password_hash,role) VALUES (%s,%s,%s)",
        (d["username"], generate_password_hash(d["password"]), d.get("role","normal")),
    )
    return jsonify({"id": uid})

@app.route("/admin/users/<int:uid>", methods=["PUT", "DELETE"])
@admin_required
def admin_user(uid):
    if request.method == "DELETE":
        if uid == session["user_id"]:
            return jsonify({"error": "Não pode deletar a si mesmo"}), 400
        exe("DELETE FROM users WHERE id=%s", (uid,))
        return jsonify({"ok": True})
    d = request.json or {}
    if d.get("password"):
        exe("UPDATE users SET username=%s,role=%s,password_hash=%s WHERE id=%s",
            (d["username"], d["role"], generate_password_hash(d["password"]), uid))
    else:
        exe("UPDATE users SET username=%s,role=%s WHERE id=%s",
            (d["username"], d["role"], uid))
    return jsonify({"ok": True})

# ── VAD control ────────────────────────────────────────────────────────────────
@app.route("/start", methods=["POST"])
@login_required
def start():
    global _vad_running, _vad_thread
    if _vad_running: return jsonify({"ok": True})
    pid = 1; vid = None
    if request.is_json:
        pid = request.json.get("provider_id", 1)
        vid = request.json.get("voice_id")
    _vad_running = True
    _vad_thread  = threading.Thread(target=_vad_loop, args=(pid, vid), daemon=True)
    _vad_thread.start()
    return jsonify({"ok": True})

@app.route("/stop", methods=["POST"])
@login_required
def stop():
    global _vad_running
    _vad_running = False
    return jsonify({"ok": True})

# ── Voice routes ───────────────────────────────────────────────────────────────
@app.route("/api/voices")
@login_required
def api_voices():
    rows = qall("SELECT id,name,is_default FROM voices WHERE is_active=1 ORDER BY is_default DESC, name")
    return jsonify(rows)

@app.route("/admin/voices", methods=["GET", "POST"])
@admin_required
def admin_voices_route():
    if request.method == "GET":
        return jsonify(qall("SELECT * FROM voices ORDER BY is_default DESC, name"))
    f = request.files.get("audio")
    if not f: return jsonify({"error": "Sem arquivo"}), 400
    name   = request.form.get("name", "").strip() or os.path.splitext(f.filename)[0]
    is_def = int(request.form.get("is_default", 0))
    os.makedirs(VOICES_DIR, exist_ok=True)
    suffix = os.path.splitext(secure_filename(f.filename))[-1] or ".bin"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    f.save(tmp.name); tmp.close()
    try:
        audio = AudioSegment.from_file(tmp.name)
        safe  = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        out   = os.path.join(VOICES_DIR, f"{safe}.wav")
        audio.export(out, format="wav")
    finally:
        os.unlink(tmp.name)
    if is_def: exe("UPDATE voices SET is_default=0")
    vid = exe("INSERT INTO voices (name,file_path,is_default) VALUES (%s,%s,%s)", (name, out, is_def))
    return jsonify({"id": vid})

@app.route("/admin/voices/<int:vid>", methods=["PUT", "DELETE"])
@admin_required
def admin_voice(vid):
    if request.method == "DELETE":
        exe("UPDATE voices SET is_active=0 WHERE id=%s", (vid,))
        return jsonify({"ok": True})
    d = request.json or {}
    if d.get("is_default"): exe("UPDATE voices SET is_default=0")
    exe("UPDATE voices SET name=%s,is_default=%s,is_active=%s WHERE id=%s",
        (d["name"], int(d.get("is_default", 0)), int(d.get("is_active", 1)), vid))
    return jsonify({"ok": True})

# ── SSE ────────────────────────────────────────────────────────────────────────
@app.route("/events")
@login_required
def events():
    q = queue.Queue(maxsize=50)
    with _sse_lock: _sse_queues.append(q)
    def stream():
        try:
            while True:
                try:    yield f"data: {json.dumps(q.get(timeout=20))}\n\n"
                except queue.Empty: yield ": ping\n\n"
        except GeneratorExit:
            with _sse_lock:
                try:    _sse_queues.remove(q)
                except ValueError: pass
    return Response(stream_with_context(stream()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ── Startup ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from init_db import init_db
    init_db()
    port = int(os.getenv("PORT", 5000))
    app.run(debug=False, port=port, threaded=True)

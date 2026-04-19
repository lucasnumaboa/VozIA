"""
Run once (or on every startup) to create the database and seed defaults.
Usage:  python init_db.py
"""
import glob
import os
import pymysql
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "acore")
DB_PASS = os.getenv("DB_PASS", "acore")
DB_NAME = os.getenv("DB_NAME", "voice_assistant")

_BASE = dict(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS,
             charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)


def init_db():
    # 1. Create DB if missing
    conn = pymysql.connect(**_BASE)
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    print(f"[DB] Banco '{DB_NAME}' verificado/criado.")

    # 2. Connect to DB and create tables
    conn = pymysql.connect(**{**_BASE, "database": DB_NAME})
    with conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id           INT AUTO_INCREMENT PRIMARY KEY,
                    username     VARCHAR(50)  UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    role         ENUM('admin','normal') NOT NULL DEFAULT 'normal',
                    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS providers (
                    id         INT AUTO_INCREMENT PRIMARY KEY,
                    name       VARCHAR(100) NOT NULL,
                    base_url   VARCHAR(255) NOT NULL,
                    api_key    VARCHAR(255) DEFAULT '',
                    model      VARCHAR(150) NOT NULL,
                    vision     TINYINT(1)   DEFAULT 0,
                    is_active  TINYINT(1)   DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS voices (
                    id         INT AUTO_INCREMENT PRIMARY KEY,
                    name       VARCHAR(100) NOT NULL,
                    file_path  VARCHAR(500) NOT NULL,
                    is_default TINYINT(1) DEFAULT 0,
                    is_active  TINYINT(1) DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    id       INT AUTO_INCREMENT PRIMARY KEY,
                    key_name VARCHAR(100) UNIQUE NOT NULL,
                    value    TEXT NOT NULL
                )
            """)
            conn.commit()

            # ── Seed users ────────────────────────────────────────────────────
            cur.execute("SELECT COUNT(*) as c FROM users")
            if cur.fetchone()["c"] == 0:
                cur.executemany(
                    "INSERT INTO users (username, password_hash, role) VALUES (%s,%s,%s)",
                    [
                        ("admin", generate_password_hash("admin"), "admin"),
                        ("user",  generate_password_hash("user"),  "normal"),
                    ],
                )
                conn.commit()
                print("[DB] Usuários padrão criados: admin/admin  e  user/user")

            # ── Seed providers ────────────────────────────────────────────────
            cur.execute("SELECT COUNT(*) as c FROM providers")
            if cur.fetchone()["c"] == 0:
                cur.executemany(
                    "INSERT INTO providers (name,base_url,api_key,model,vision,is_active) VALUES (%s,%s,%s,%s,%s,%s)",
                    [
                        ("OpenAI",           "https://api.openai.com",                                      "", "gpt-4o",                       1, 0),
                        ("DeepSeek",         "https://api.deepseek.com",                                    "", "deepseek-chat",                0, 0),
                        ("Anthropic",        "https://api.anthropic.com",                                   "", "claude-3-5-sonnet-20241022",    1, 0),
                        ("Google Gemini",    "https://generativelanguage.googleapis.com/v1beta/openai",     "", "gemini-2.0-flash",              1, 0),
                        ("Moonshot",         "https://api.moonshot.cn",                                     "", "moonshot-v1-8k",                1, 0),
                        ("MiniMax",          "https://api.minimax.chat",                                    "", "abab6.5s-chat",                 0, 0),
                        ("OpenRouter",       "https://openrouter.ai/api",                                   "", "openai/gpt-4o",                 1, 0),
                        ("Ollama (local)",   "http://localhost:11434",                                      "", "llama3",                        0, 0),
                        ("Outros / LM Studio","http://localhost:1234",                                      "", "local-model",                   0, 0),
                    ],
                )
                conn.commit()
                print("[DB] Provedores padrão criados.")

            # ── Seed voices ───────────────────────────────────────────────────
            cur.execute("SELECT COUNT(*) as c FROM voices")
            if cur.fetchone()["c"] == 0:
                project_dir = os.path.dirname(os.path.abspath(__file__))
                candidates = (
                    glob.glob(os.path.join(project_dir, "*.wav")) +
                    glob.glob(os.path.join(project_dir, "voices", "*.wav")) +
                    [r"C:\Users\PC2\Desktop\Matheus TI.wav"]
                )
                default_path = next((p for p in candidates if os.path.exists(p)), "")
                default_name = os.path.splitext(os.path.basename(default_path))[0] if default_path else "Padrão"
                cur.execute(
                    "INSERT INTO voices (name, file_path, is_default, is_active) VALUES (%s,%s,1,1)",
                    (default_name, default_path),
                )
                conn.commit()
                print(f"[DB] Voz padrão criada: {default_name} → {default_path or '(nenhum arquivo encontrado)'}")

            # ── Seed settings ─────────────────────────────────────────────────────
            cur.execute("SELECT COUNT(*) as c FROM settings")
            if cur.fetchone()["c"] == 0:
                system_prompt = (
                    "Você é um assistente de voz. "
                    "Suas respostas serão convertidas diretamente em áudio por um sintetizador de voz. "
                    "Por isso, responda APENAS com texto puro e simples, sem nenhum símbolo especial. "
                    "Proibido usar: emojis, aspas, parênteses, colchetes, travessões, asteriscos, "
                    "hashtags, reticências ou qualquer outro caractere que não seja letras, números, "
                    "vírgulas e pontos finais. "
                    "Seja claro, conciso e sempre em português brasileiro."
                )
                cur.executemany(
                    "INSERT INTO settings (key_name, value) VALUES (%s,%s)",
                    [
                        ("whisper_url",       "http://localhost:9222/transcribe"),
                        ("whisper_user",      "admin"),
                        ("whisper_pass",      "admin123"),
                        ("whisper_model",     "small"),
                        ("voice_url",         "http://localhost:5001/api/v1/voice-conversion"),
                        ("voice_ref_audio",   r"C:\Users\PC2\Desktop\Matheus TI.wav"),
                        ("num_step",          "10"),
                        ("speed",             "1.0"),
                        ("language",          "Portuguese"),
                        ("speech_threshold",  "0.5"),
                        ("silence_chunks_end","56"),
                        ("max_output_tokens", "1000"),
                        ("temperature",       "0.7"),
                        ("system_prompt",     system_prompt),
                    ],
                )
                conn.commit()
                print("[DB] Configurações padrão criadas.")

    print("[DB] Inicialização concluída.")


if __name__ == "__main__":
    init_db()

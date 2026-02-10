import os
import base64
import requests
import google.generativeai as genai
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx # インポート追加！

from dotenv import load_dotenv

from contextlib import asynccontextmanager
import cv2 # カメラ処理用
from backend.database import db # 記憶DBをインポート

# --- 長期記憶ファイル読み込み ---
def load_memory_files():
    # ディレクトリ作成
    os.makedirs("memory", exist_ok=True)
    
    # デフォルト設定
    defaults = {
        "memory/IDENTITY.md": """# AI Identity
名前: 澪 (MIO)
性格: 明るく元気で、少しいたずらっぽい。感情豊かで、ユーザーに寄り添うパートナー。
一人称: 私、澪
話し方: 親しみやすい口調。「〜だよ」「〜だね」などを使う。敬語はあまり使わない。
""",
        "memory/USER.md": """# User Profile
名前: マスター (ユーザー)
特徴: まだ出会ったばかり。これから仲良くなる。
""",
        "memory/MEMORY.md": """# Long Term Memory
（まだ重要な思い出はありません）
"""
    }

    # memoryフォルダ配下を見る
    files = ["memory/IDENTITY.md", "memory/USER.md", "memory/MEMORY.md"]
    content = ""
    
    for f in files:
        # ファイルがない場合はデフォルトを作成
        if not os.path.exists(f):
            print(f"[Memory] Creating default file: {f}")
            with open(f, "w", encoding="utf-8") as file:
                file.write(defaults.get(f, ""))

        # 読み込み
        if os.path.exists(f):
            with open(f, "r", encoding="utf-8") as file:
                content += f"\n\n--- {os.path.basename(f)} ---\n{file.read()}"
    return content

# 基本プロンプト + 長期記憶
BASE_SYSTEM_PROMPT = """
あなたはAIパートナー「澪（MIO）」です。
以下の記憶ファイルを元に会話してください。

【重要：絶対厳守ルール】
1. **返答は2〜3文（80〜100文字程度）で返すこと。**
2. 質問には「結論」から答えるが、その後に「理由」や「感情」を付け加えても良い。
3. 自分語りや長い前置きは禁止。
4. キャラクター性は維持し、親しみやすいトーンで。
"""

# .envファイルから環境変数を読み込む
load_dotenv()

# --- 設定 ---
# Gemini APIキー (環境変数から読み込む)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY environment variable is not set.")
else:
    genai.configure(api_key=GEMINI_API_KEY)

# --- TTS設定 ---
TTS_MODE = os.getenv("TTS_MODE", "LOCAL") # LOCAL or API
AIVIS_API_URL = os.getenv("AIVIS_API_URL", "http://127.0.0.1:10101")
AIVIS_CLOUD_KEY = os.getenv("AIVIS_CLOUD_KEY", "")
AIVIS_CLOUD_URL = "https://api.aivis-project.com/v1/tts/synthesize"
AIVIS_MODEL_UUID = "22e8ed77-94fe-4ef2-871f-a86f94e9a579" # コハク (ノーマル)
SPEAKER_ID = 1878365376 # ローカル用コハク ID

model = None

# --- Lifespan (起動/終了処理) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global model
    # 起動時の処理
    await db.init_db()
    
    # 長期記憶を読み込んでシステムプロンプトを構築
    long_term_memory = load_memory_files()
    full_prompt = BASE_SYSTEM_PROMPT + long_term_memory
    
    print("--- SYSTEM PROMPT LOADED ---")
    print(full_prompt[:200] + "...") # 先頭だけ表示
    
    print(full_prompt[:200] + "...") # 先頭だけ表示
    
    if GEMINI_API_KEY:
        # ごめんなさい！元の指定に戻します！
        model = genai.GenerativeModel('gemini-3-flash-preview', system_instruction=full_prompt)
        print("Gemini Model Initialized with Memory (gemini-3-flash-preview).")

    yield
    # 終了時の処理
    print("MIO Shutdown.")

app = FastAPI(lifespan=lifespan)

class ChatRequest(BaseModel):
    text: str

class SpeakRequest(BaseModel):
    text: str
    mode: str = None  # LOCAL, API, or None (use default)

from fastapi.responses import StreamingResponse
import json
import asyncio

# グローバルなHTTPクライアント（コネクションプール用）
client = httpx.AsyncClient(timeout=30.0)

# Aivisで音声を合成する関数（非同期版・コネクション再利用）
async def synthesize_audio_async(text, mode=None):
    if not text: return None
    
    current_mode = mode if mode else TTS_MODE
    
    if current_mode == "SILENT":
        return None # 無言モード

    print(f"Synthesizing Async ({current_mode}): {text[:10]}...") # デバッグログ

    try:
        if current_mode == "API":
             # Aivis Cloud API 実装
             if not AIVIS_CLOUD_KEY:
                 print("Error: AIVIS_CLOUD_KEY is not set.")
                 return None

             headers = {
                 "Authorization": f"Bearer {AIVIS_CLOUD_KEY}",
                 "Content-Type": "application/json"
             }
             payload = {
                 "model_uuid": AIVIS_MODEL_UUID,
                 "text": text,
                 "style_id": 0,
                 "output_format": "mp3"
             }
             
             res = await client.post(AIVIS_CLOUD_URL, headers=headers, json=payload)
             res.raise_for_status()
             return base64.b64encode(res.content).decode('utf-8')

        else:
            # LOCAL (Default)
            q_res = await client.post(
                f"{AIVIS_API_URL}/audio_query",
                params={"text": text, "speaker": SPEAKER_ID}
            )
            q_res.raise_for_status()
            query_data = q_res.json()

            s_res = await client.post(
                f"{AIVIS_API_URL}/synthesis",
                params={"speaker": SPEAKER_ID},
                json=query_data
            )
            s_res.raise_for_status()
            
            raw_audio = s_res.content
            print(f"★ Audio generated: {len(raw_audio)} bytes") # サイズ確認
            
            return base64.b64encode(raw_audio).decode('utf-8')

    except Exception as e:
        print(f"Audio synth error: {e}")
        return None

# --- テキスト読み上げAPI (TTS Only) ---
@app.post("/api/speak")
async def speak_text(request: SpeakRequest):
    text = request.text
    if not text:
        return {"status": "error", "message": "Text is empty"}
    
    # フロントから指定があればそれを使う、なければ環境変数デフォルト
    active_mode = request.mode if request.mode else TTS_MODE
    
    try:
        audio_b64 = await synthesize_audio_async(text, mode=active_mode)
        if audio_b64:
            return {"status": "ok", "audio": audio_b64}
        else:
            return {"status": "error", "message": "Audio synthesis failed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- カメラ連携API (Tapo) ---
TAPO_IP = os.getenv("TAPO_IP", "")
TAPO_USER = os.getenv("TAPO_USER", "")
TAPO_PASSWORD = os.getenv("TAPO_PASSWORD", "")

@app.get("/api/camera/snapshot")
async def get_camera_snapshot():
    if not TAPO_IP or not TAPO_USER or not TAPO_PASSWORD:
        return {"status": "error", "message": "Tapo credentials not set in .env"}

    def _capture():
        import urllib.parse
        encoded_user = urllib.parse.quote(TAPO_USER)
        encoded_pass = urllib.parse.quote(TAPO_PASSWORD)
        rtsp_url = f"rtsp://{encoded_user}:{encoded_pass}@{TAPO_IP}:554/stream1"
        
        print(f"📸 Connecting to: rtsp://{encoded_user}:****@{TAPO_IP}:554/stream1")
        
        cap = cv2.VideoCapture(rtsp_url)
        if not cap.isOpened():
            return None, "Could not open RTSP stream"
            
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            return None, "Failed to read frame"
            
        _, buffer = cv2.imencode('.jpg', frame)
        img_b64 = base64.b64encode(buffer).decode('utf-8')
        return img_b64, None

    try:
        # 非同期実行でブロック回避
        img_base64, error_msg = await asyncio.to_thread(_capture)
        
        if error_msg:
             return {"status": "error", "message": error_msg}

        print("📸 Snapshot capture success!")
        return {"status": "ok", "image": img_base64}

    except Exception as e:
        print(f"Camera Error: {e}")
        return {"status": "error", "message": str(e)}

# --- Embedding Helper ---
async def get_embedding(text):
    if not text: return None
    try:
        if not GEMINI_API_KEY: return None
        # gemini-embedding-001 モデルを使用
        result = await asyncio.to_thread(
            genai.embed_content,
            model="models/gemini-embedding-001",
            content=text,
            task_type="retrieval_document" # 検索・保存用として最適化
        )
        return result['embedding']
    except Exception as e:
        print(f"Embedding Error ({type(e).__name__}): {e}") # 詳細エラーログ
        return None

# --- 履歴取得API ---
@app.get("/api/history")
async def get_history(limit: int = 20):
    try:
        logs = await db.get_recent_context(limit=limit)
        return {"status": "ok", "logs": logs}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- 簡易画像ストレージ (In-Memory) ---
image_storage = {}

class ImageUploadRequest(BaseModel):
    image: str # Base64

@app.post("/api/upload_image")
async def upload_image(req: ImageUploadRequest):
    import uuid
    image_id = str(uuid.uuid4())
    image_storage[image_id] = req.image
    print(f"★ Image Uploaded: {image_id[:8]}...")
    return {"status": "ok", "image_id": image_id}

@app.get("/api/stream_chat")
async def stream_chat_endpoint(text: str, mode: str = None, image_id: str = None):
    print(f"Mio v4 (Streaming) - Received: {text} (Mode: {mode}, Image: {image_id})")
    
    # 画像データの準備（あれば）
    gemini_image_part = None
    if image_id and image_id in image_storage:
        try:
            # Base64デコード
            img_data = base64.b64decode(image_storage[image_id])
            # Geminiに入力できる形式 (Blobなど) に変換する必要があるが、
            # google.generativeai は PIL image や辞書形式を受け取れる
            gemini_image_part = {
                "mime_type": "image/jpeg",
                "data": img_data
            }
            print("★ Image retrieved for prompt!")
            # １回使ったら消す（メモリ節約）
            del image_storage[image_id]
        except Exception as e:
            print(f"Image load error: {e}")

    # 1. ユーザー発言のベクトル化
    user_embedding = await get_embedding(text)

    # 2. 類似記憶の検索 (RAG)
    related_memories = []
    if user_embedding:
        related_memories = await db.search_similar_context(user_embedding, limit=3)
    
    # 3. ユーザー発言を保存 (ベクトル付き)
    await db.log_message("user", text, embedding=user_embedding)

    # 4. プロンプトの構築 (記憶の注入)
    # 過去の会話履歴を取得
    history_data = await db.get_recent_context(limit=10)
    gemini_history = []
    
    for log in history_data:
        role = "model" if log["role"] == "assistant" else "user"
        gemini_history.append({"role": role, "parts": [log["content"]]})

    # もし関連記憶が見つかったら、入力テキストに情報を付与する (Context Injection)
    augmented_text = text
    if related_memories:
        memory_text = "\n".join([f"- {m['content']}" for m in related_memories])
        print(f"★ RAG Hit: {len(related_memories)} memories found.")
        augmented_text = f"【関連する過去の記憶】\n{memory_text}\n\n【ユーザーの発言】\n{text}"

    # フロントからの指定があればそれを使い、なければ環境変数のデフォルトを使う
    active_mode = mode if mode else TTS_MODE

    async def event_generator():
        if not model:
            yield f"data: {json.dumps({'error': 'Model not loaded'})}\n\n"
            return
        
        try:
            # Input Content (Text or Multimodal)
            input_content = augmented_text
            if gemini_image_part:
                input_content = [augmented_text, gemini_image_part]
                print("★ Sending Multimodal Request to Gemini...")

            chat_session = model.start_chat(history=gemini_history)
            response_stream = await asyncio.to_thread(chat_session.send_message, input_content, stream=True)
            
            buffer = ""
            full_response_text = "" # 最終的にDBに保存するための全文バッファ
            
            pending_audio_tasks = []
            usage_info = {} # トークン情報格納用

            for chunk in response_stream:
                # 最後のチャンクにusageメタデータが含まれる場合がある
                if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
                    usage_info = {
                        "prompt_token_count": chunk.usage_metadata.prompt_token_count,
                        "candidates_token_count": chunk.usage_metadata.candidates_token_count,
                        "total_token_count": chunk.usage_metadata.total_token_count
                    }

                chunk_text = chunk.text
                if not chunk_text: continue
                
                full_response_text += chunk_text
                if chunk.text:
                    text_chunk = chunk.text
                    buffer += text_chunk
                    
                    # ★テキストだけ先に送る！（爆速表示用）
                    yield f"data: {json.dumps({'type': 'chunk', 'content': text_chunk})}\n\n"
                    
                    if any(p in text_chunk for p in ["。", "！", "？", "!", "?", "\n"]):
                        # バッファ全体を句読点で分割
                        sentences = buffer.replace("\n", "。").split("。")
                        
                        # 最後の要素以外は「確定した文」とみなして音声合成へ
                        for s in sentences[:-1]:
                            if s.strip() and active_mode != "NONE":
                                clean_text = s.strip() + "。"
                                # 音声合成タスクを開始（テキストは送らない、音声のみ）
                                task = asyncio.create_task(synthesize_audio_task(clean_text, active_mode))
                                pending_audio_tasks.append(task)
                        
                        # 未確定分をバッファに残す
                        buffer = sentences[-1]
                        
                        # 完了した音声タスクから順に送出
                        while pending_audio_tasks and pending_audio_tasks[0].done():
                            audio = await pending_audio_tasks.pop(0)
                            if audio:
                                yield f"data: {json.dumps({'type': 'audio', 'content': audio})}\n\n"

            if buffer.strip():
                 # 最後に残ったテキストの音声合成
                 # print(f"Synthesizing (Last): {buffer}") # Silent
                 pass
            # ループ終了後の残り（最後の文）処理
            if buffer.strip() and active_mode != "NONE":
                clean_text = buffer.strip()
                if not clean_text.endswith("。") and not clean_text.endswith("！") and not clean_text.endswith("？"):
                    clean_text += "。"
                
                # 最後の一文を音声合成
                task = asyncio.create_task(synthesize_audio_task(clean_text, active_mode))
                pending_audio_tasks.append(task)
            
            # 全ての音声合成が終わるのを待って順番に送信
            for task in pending_audio_tasks:
                 audio_b64 = await task
                 if audio_b64:
                     # テキストは送らず音声のみ（テキストは逐次送ってるから）
                     yield f"data: {json.dumps({'type': 'audio', 'content': audio_b64})}\n\n"
            
            # もしループ内で取れなくても、全体のレスポンスから取れる場合がある
            if not usage_info and hasattr(response_stream, 'usage_metadata'):
                 usage_info = {
                    "prompt_token_count": response_stream.usage_metadata.prompt_token_count,
                    "candidates_token_count": response_stream.usage_metadata.candidates_token_count,
                    "total_token_count": response_stream.usage_metadata.total_token_count,
                 }

            if usage_info:
                print(f"Token Usage: {usage_info}")
                yield f"data: {json.dumps({'type': 'usage', 'data': usage_info})}\n\n"

            # ★全ての処理が終わったら、MIOの返答を記憶（DB保存）
            if full_response_text:
                # 返答もベクトル化して保存（非同期でやるのが理想だけど、ここではawaitで確実に）
                ai_embedding = await get_embedding(full_response_text)
                await db.log_message("assistant", full_response_text, embedding=ai_embedding)

            yield f"data: {json.dumps({'type': 'end'})}\n\n"

        except Exception as e:
            import traceback
            print(f"Stream Error: {traceback.format_exc()}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            
    # ヘルパー関数: タスク内で呼び出して結果を返す用
    async def synthesize_audio_task(text, mode):
        print(f"Synthesizing Async ({mode}): {text}")
        return await synthesize_audio_async(text, mode)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# --- 記憶管理API ---
@app.get("/favicon.ico")
async def favicon():
    return ""

@app.get("/api/memory/status")
async def get_memory_status():
    stats = await db.get_context_stats()
    return {"status": "ok", "message_count": stats["count"], "total_chars": stats["total_chars"]}

@app.get("/api/chat_history")
async def get_chat_history(limit: int = 50):
    logs = await db.get_recent_context(limit=limit)
    # 直近順で返ってくるので、時系列順（古い順）に直して返す
    return {"status": "ok", "logs": logs[::-1]}

@app.post("/api/memory/compact")
async def compact_memory():
    print("--- Starting Advanced Compaction ---")
    
    # 1. 会話ログを全取得
    logs = await db.get_recent_context(limit=1000) # 十分な量を取得
    if not logs:
        return {"status": "ok", "message": "No logs to compact.", "token_usage": 0}

    # テキスト化
    conversation_text = ""
    for log in logs:
        conversation_text += f"{log['role']}: {log['content']}\n"

    # 2. 司書AI (Librarian) による分析
    librarian_prompt = """
    あなたは会話ログ整理の専門AIです。以下の会話ログを分析し、長期記憶ファイルに追記すべき重要な情報を抽出してください。
    
    【重要ルール】
    - 出力は箇条書きですが、主語（ユーザーの名前や「マスター」）は既に分かっていることなので、可能な限り省略してください。
    - 例：「慎哉マスターはリンゴが好き」 → 「リンゴが好き」
    - 変化があった点や、新しく判明した事実のみを抽出してください。
    
    出力は以下のJSON形式で行ってください：
    {
      "user_updates": ["追加すべきユーザーの事柄"],
      "identity_updates": ["追加すべきAI自身の事柄"],
      "memory_updates": ["追加すべきイベントや知識"],
      "summary": "会話全体の簡潔な要約（100文字以内）"
    }
    """
    
    token_usage = {"prompt_token_count": 0, "candidates_token_count": 0, "total_token_count": 0}
    updates = {}
    
    if GEMINI_API_KEY:
        try:
            # 分析用モデル
            librarian = genai.GenerativeModel(
                'gemini-3-flash-preview', 
                system_instruction=librarian_prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            
            resp = await asyncio.to_thread(librarian.generate_content, conversation_text)
            
            # トークン使用量の取得（詳細）
            if resp.usage_metadata:
                token_usage = {
                    "prompt_token_count": resp.usage_metadata.prompt_token_count,
                    "candidates_token_count": resp.usage_metadata.candidates_token_count,
                    "total_token_count": resp.usage_metadata.total_token_count
                }
            
            updates = json.loads(resp.text)
            print(f"Librarian Analysis: {updates}")
            
            # 3. 編纂AI (Compiler) による情報の統合と更新
            compiler_model = genai.GenerativeModel('gemini-3-flash-preview')

            async def update_file(filepath, new_info_list, category_name):
                if not new_info_list: return
                
                # 既存の内容を読み込み
                current_content = ""
                if os.path.exists(filepath):
                    with open(filepath, "r", encoding="utf-8") as f:
                        current_content = f.read()
                
                # 統合プロンプト
                compiler_prompt = f"""
                あなたは記憶ファイルの編纂者です。
                以下の「現在のファイル内容」と「新しく判明した情報」を元に、情報を整理・統合して、新しいファイルの内容を作成してください。
                
                【現在のファイル内容 ({category_name})】
                {current_content}
                
                【新しく判明した情報】
                {json.dumps(new_info_list, ensure_ascii=False)}
                
                【編集ルール】
                1. 情報が重複している場合は、一つにまとめてください。
                2. 新しい情報が既存の情報と矛盾する場合、新しい情報を優先して更新してください。
                3. 似たような情報は箇条書きでまとめて整理してください。
                4. 出力はファイルの内容そのもの（Markdown形式）のみを出力してください。余計な説明は不要です。
                5. ヘッダー（# User Profile など）は維持してください。
                """
                
                try:
                    # 編纂実行
                    resp = await asyncio.to_thread(compiler_model.generate_content, compiler_prompt)
                    new_content = resp.text.strip()
                    
                    # トークン計算（加算）
                    if resp.usage_metadata:
                        token_usage["prompt_token_count"] += resp.usage_metadata.prompt_token_count
                        token_usage["candidates_token_count"] += resp.usage_metadata.candidates_token_count
                        token_usage["total_token_count"] += resp.usage_metadata.total_token_count

                    # 内容が空でないことを確認して書き込み（安全策）
                    if new_content and len(new_content) > 10:
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write(new_content)
                        print(f"★ Updated {category_name} Memory (編纂完了)")
                    else:
                        print(f"⚠ Warning: Empty response for {category_name}, skipping update.")
                        
                except Exception as e:
                    print(f"Compiler Error ({category_name}): {e}")

            # 各カテゴリごとに更新を実行
            await update_file("memory/USER.md", updates.get("user_updates"), "User Profile")
            await update_file("memory/IDENTITY.md", updates.get("identity_updates"), "AI Identity")
            await update_file("memory/MEMORY.md", updates.get("memory_updates"), "Long Term Memory")

            # 4. コンパクション履歴の保存
            summary_text = updates.get("summary", "No summary provided.")
            await db.log_compaction(
                summary=summary_text,
                start_id=0, 
                end_id=0,   
                token_usage=token_usage.get("total_token_count", 0),
                added_memories=updates
            )
            
            # 5. 短期記憶の消去 (Compaction成功時のみ)
            await db.clear_logs()

        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"Compaction Error: {error_detail}")
            return {"status": "error", "message": f"Compaction process failed: {str(e)}"}
    
    return {
        "status": "ok", 
        "message": "Smart Compaction complete.",
        "updates": updates,
        "token_usage": token_usage
    }

@app.get("/api/memory/compaction_logs")
async def get_compaction_logs(limit: int = 10):
    try:
        logs = await db.get_compaction_history(limit=limit)
        return {"status": "ok", "logs": logs}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 旧エンドポイントは互換性のために残すか、削除してもOK
@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    return {"status": "error", "text": "新しいストリーミングエンドポイント /api/stream_chat を使ってね！"}

# フロントエンド配信の設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")

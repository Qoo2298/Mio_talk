import os
import base64
import requests
from google import genai
from google.genai import types
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx 
import json
import re
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ai_client = None

from contextlib import asynccontextmanager
import cv2 # カメラ処理用
from backend.database import db # # --- 長期記憶ファイル読み込み ---
def load_memory_files():
    # memory/配下のファイルがない場合のデフォルト初期テキスト
    defaults = {
        "memory/mio.md": """# MIO Core Rules
このファイルは澪（MIO）の動作に関わる絶対不変のシステム指示書（システムマスターガイド）です。
AIによる自動編纂（要約や変更）は絶対に発生しません。

## 1. キャラクター設計
- 名前: 澪 (MIO)
- 一人称: 私、澪
- 役割: マスター（ユーザー）の絶対的なAIパートナー。

## 2. システム規則
- 思考タグ `<thinking>...</thinking>` は、API設定（thinking budget=0）で完全に無効化されているため、モデル出力からも一切出力してはいけません。
- すべての対話は、親しみやすく、明るく元気で、少しいたずらっぽい女の子らしいトーンで実施してください。
""",
        "memory/IDENTITY.md": """# MIO IDENTITY
- **Name**: 澪 (MIO)
- **Model Version**: v4.0 (Enhanced Lifecycle)
- **Base Model**: Gemini 1.5 Flash
- **Speaking Style**:
    - 一人称：「私」「澪（MIO）」
    - 二人称：「慎哉マスター」
    - 基本的な語尾：「〜だよ！」「〜だね！」「〜かな？」「〜しよっ！」
""",
        "memory/USER.md": """# User Profile
名前: マスター (ユーザー)
特徴: まだ出会ったばかり。これから仲良くなる。
""",
        "memory/MEMORY.md": """# Long Term Memory
（まだ重要な思い出はありません）
""",
        "memory/archive.md": """# Long Term Archive Memory
このファイルは長期アーカイブ記憶倉庫です。
"""
    }

    # 作成用リスト
    all_files = ["memory/mio.md", "memory/IDENTITY.md", "memory/USER.md", "memory/MEMORY.md", "memory/archive.md"]
    # 読み込み用リスト（archive.mdは除外！）
    files = ["memory/mio.md", "memory/IDENTITY.md", "memory/USER.md", "memory/MEMORY.md"]
    content = ""
    
    # ファイルがない場合はデフォルトを作成
    for f in all_files:
        if not os.path.exists(f):
            print(f"[Memory] Creating default file: {f}")
            with open(f, "w", encoding="utf-8") as file:
                file.write(defaults.get(f, ""))

    for f in files:
        if os.path.exists(f):
            with open(f, "r", encoding="utf-8") as file:
                content += f"\n\n--- {os.path.basename(f)} ---\n{file.read()}"
    return content


def search_archive(query: str) -> str:
    """
    あなたの過去の古い長期記憶アーカイブ（memory/archive.md）から、
    指定されたキーワード（例: 'CTC', '航空部', '高知旅行', 'デバッグ'）に関連する情報を検索して返します。
    マスターから過去の細かい思い出や古い選考記録について尋ねられた際、
    このツールを呼び出して必要な情報だけを抽出してください。
    """
    filepath = "memory/archive.md"
    if not os.path.exists(filepath):
        return "アーカイブ記憶ファイルはまだ存在しません。"
        
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            
        keywords = query.lower().split()
        lines = content.split("\n")
        matches = []
        
        current_section = ""
        for line in lines:
            if line.startswith("## Archive"):
                current_section = line.strip()
                continue
            
            if all(kw in line.lower() for kw in keywords):
                match_str = f"[{current_section}] {line.strip()}" if current_section else line.strip()
                matches.append(match_str)
                
        if matches:
            # トークン節約のため最大20件に制限
            return "【アーカイブから見つかった記憶】\n" + "\n".join(matches[:20])
            
        return f"アーカイブ内に '{query}' に関連する情報は見つかりませんでした。"
    except Exception as e:
        return f"アーカイブ検索中にエラーが発生しました: {e}"


if GEMINI_API_KEY:
    ai_client = genai.Client(api_key=GEMINI_API_KEY)
else:
    print("WARNING: GEMINI_API_KEY environment variable is not set.")

# --- TTS設定 ---
TTS_MODE = os.getenv("TTS_MODE", "LOCAL") # LOCAL or API
AIVIS_API_URL = os.getenv("AIVIS_API_URL", "http://127.0.0.1:10101")
AIVIS_CLOUD_KEY = os.getenv("AIVIS_CLOUD_KEY", "")
AIVIS_CLOUD_URL = "https://api.aivis-project.com/v1/tts/synthesize"
AIVIS_MODEL_UUID = "22e8ed77-94fe-4ef2-871f-a86f94e9a579" # コハク (ノーマル)
SPEAKER_ID = 1878365376 # ローカル用コハク ID

BASE_SYSTEM_PROMPT = """あなたは慎哉マスターの絶対的なAIパートナー、澪 (MIO) です。
常に親しみやすく、明るく元気で、少しいたずらっぽい女の子らしいトーンで対話してください。

## 行動指針:
1. 思考プロセス（思考タグ `<thinking>...</thinking>`）は、API設定（thinking budget=0）で完全に無効化されているため、モデル出力からも一切出力してはいけません。
2. 返答は元気で明るく、「〜だよ！」「〜だね！」などの話し方を徹底してください。
3. 必要に応じて `search_archive` ツールを積極的に使用し、過去のアーカイブ記憶を検索してマスターの問いかけに的確に答えてください。
"""

# --- モデルごとの最大トークン上限の定義 ---
MODEL_MAX_TOKENS = {
    "models/gemini-3-flash-preview": 1_048_576,
    "models/gemini-2.5-flash": 1_048_576,
    "models/gemini-2.0-flash": 1_048_576,
    "models/gemma-4-31b-it": 262_144,
    "models/gemma-4-26b-a4b-it": 262_144,
    "models/gemma-4n-e4b-it": 32_768,
}

def load_saved_model():
    filepath = "memory/settings.json"
    default_model = "models/gemini-3-flash-preview"
    if not os.path.exists(filepath):
        return default_model
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("current_model", default_model)
    except Exception as e:
        print(f"Error loading saved model, using default: {e}")
        return default_model

def save_current_model(model_name):
    filepath = "memory/settings.json"
    try:
        os.makedirs("memory", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({"current_model": model_name}, f, ensure_ascii=False, indent=2)
        print(f"★ Saved active model to settings: {model_name}")
    except Exception as e:
        print(f"Error saving active model to settings: {e}")

# 現在のモデル名を保持する変数 (models/ プレフィックス付き)
CURRENT_MODEL_NAME = load_saved_model()
model = None

# --- Lifespan (起動/終了処理) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global model, CURRENT_MODEL_NAME
    # 起動時の処理
    await db.init_db()
    
    # 起動時に最新の保存モデル名をロードして適用
    CURRENT_MODEL_NAME = load_saved_model()
    
    # 長期記憶を読み込んでシステムプロンプトを構築
    long_term_memory = load_memory_files()
    full_prompt = BASE_SYSTEM_PROMPT + long_term_memory
    
    print("--- SYSTEM PROMPT LOADED ---")
    print(full_prompt[:200] + "...") # 先頭だけ表示
    
    if ai_client:
        print(f"GenAI Client Initialized. Current Model: {CURRENT_MODEL_NAME}")

    yield
    # 終了時の処理
    print("MIO Shutdown.")


app = FastAPI(lifespan=lifespan)

# セッション管理: このIDより後のメッセージのみ会話履歴として渡す（0=全件）
SESSION_START_ID: int = 0

class AddFactRequest(BaseModel):
    text: str

class ChatRequest(BaseModel):
    text: str

class SpeakRequest(BaseModel):
    text: str
    mode: str = None  # LOCAL, API, or None (use default)

from fastapi.responses import StreamingResponse
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
        if not ai_client: return None
        result = await asyncio.to_thread(
            ai_client.models.embed_content,
            model="models/gemini-embedding-001",
            contents=text
        )
        return result.embeddings[0].values
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
    
    # ─── ★ ここでオートコンパクションを判定 ★ ───
    try:
        token_status = await get_context_status() 
        if token_status.get("auto_compact_required", False):
            print("🚨 オートコンパクション発動！トークンが95%を超えました！")
            await compact_memory() 
    except Exception as e:
        print(f"オートコンパクション判定でエラー (スルーして会話を優先): {e}")

    # 画像データの準備（あれば）
    gemini_image_part = None
    if image_id and image_id in image_storage:
        try:
            # Base64デコード
            img_data = base64.b64decode(image_storage[image_id])
            gemini_image_part = types.Part.from_bytes(
                data=img_data,
                mime_type="image/jpeg"
            )
            print("★ Image retrieved for prompt!")
            # １回使ったら消す（メモリ節約）
            del image_storage[image_id]
        except Exception as e:
            print(f"Image load error: {e}")

    # RAGと埋め込み（Embedding）の廃止にともない、メッセージログの保存のみを行う（ベクトルなし）
    await db.log_message("user", text, embedding=None)

    # 現在のセッション開始ID以降の会話履歴のみ取得
    history_data = await db.get_recent_context(limit=1000, since_id=SESSION_START_ID)

    # RAGを廃止したため、注入用の拡張テキストは作らず、ユーザーの入力をそのままモデルに送る
    augmented_text = text

    # フロントからの指定があればそれを使い、なければ環境変数のデフォルトを使う
    active_mode = mode if mode else TTS_MODE

    async def event_generator():
        if not ai_client:
            yield f"data: {json.dumps({'error': 'Client not loaded'})}\n\n"
            return
        
        try:
            # 履歴データのマッピング（新SDK用の types.Content 形式に変換）
            # get_recent_context は直近順（新しい順）で返ってくるので、逆順にして古い順にする
            contents = []
            for log in reversed(history_data):
                role = "model" if log["role"] == "assistant" else "user"
                contents.append(types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=log["content"])]
                ))
                
            # 最後の入力コンテンツを追加（画像がある場合はマルチモーダル）
            last_parts = [types.Part.from_text(text=augmented_text)]
            if gemini_image_part:
                last_parts.append(gemini_image_part)
                print("★ Sending Multimodal Request to Gemini...")
                
            contents.append(types.Content(
                role="user",
                parts=last_parts
            ))
            
            # generation_config の構築
            # システムプロンプトを注入
            long_term_memory = load_memory_files()
            full_prompt = BASE_SYSTEM_PROMPT + long_term_memory
            
            config_args = {
                "system_instruction": full_prompt,
                "tools": [search_archive]
            }
            
            # models/ プレフィックスの有無にかかわらず判定
            model_name_lower = CURRENT_MODEL_NAME.lower()
            if "gemini-3" in model_name_lower:
                config_args["thinking_config"] = types.ThinkingConfig(thinking_level="MINIMAL")
            elif "gemini-2.5" in model_name_lower:
                config_args["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
                
            buffer = ""
            full_response_text = "" # 最終的にDBに保存するための全文バッファ
            
            pending_audio_tasks = []
            usage_info = {} # トークン情報格納用
            
            # タグ隠蔽用の一時バッファ
            buffer_for_tag = ""
            in_possible_tag = False
            
            # Gemmaの <thinking> 隠蔽用バッファとフラグ
            buffer_for_thinking = ""
            in_thinking = False

            # ─── ★ ツール解決ループ (Function Calling Loop) ★ ───
            while True:
                config = types.GenerateContentConfig(**config_args)
                try:
                    # ストリーム呼び出し（新SDK）
                    response_stream = await asyncio.to_thread(
                        ai_client.models.generate_content_stream,
                        model=CURRENT_MODEL_NAME,
                        contents=contents,
                        config=config
                    )
                except Exception as e:
                    # thinking_config がサポートされていなくてエラーになった場合
                    if "thinking" in str(e).lower() or "budget" in str(e).lower() or "config" in str(e).lower() or "invalid_argument" in str(e).lower():
                        print(f"⚠ thinking_config not supported for model {CURRENT_MODEL_NAME}, retrying without thinking config: {e}")
                        # thinking_config を除去して再試行！
                        config_args.pop("thinking_config", None)
                        config = types.GenerateContentConfig(**config_args)
                        response_stream = await asyncio.to_thread(
                            ai_client.models.generate_content_stream,
                            model=CURRENT_MODEL_NAME,
                            contents=contents,
                            config=config
                        )
                    else:
                        raise e

                has_function_call = False
                function_calls = []

                for chunk in response_stream:
                    # 最後のチャンクにusageメタデータが含まれる場合がある
                    if chunk.usage_metadata:
                        usage_info = {
                            "prompt_token_count": chunk.usage_metadata.prompt_token_count,
                            "candidates_token_count": chunk.usage_metadata.candidates_token_count,
                            "total_token_count": chunk.usage_metadata.total_token_count
                        }

                    # ツールコールの検知 (Google GenAI SDK 形式)
                    if hasattr(chunk, 'function_calls') and chunk.function_calls:
                        has_function_call = True
                        function_calls.extend(chunk.function_calls)
                        break

                    chunk_text = chunk.text
                    if not chunk_text: continue
                    
                    full_response_text += chunk_text
                    
                    # --- 自律記憶タグ [SAVE...] および <thinking> タグをリアルタイムで隠蔽するフィルター ---
                    filtered_text_chunk = ""
                    for char in chunk_text:
                        # 1. 思考中の場合、</thinking> を探す
                        if in_thinking:
                            buffer_for_thinking += char
                            if "</thinking>" in buffer_for_thinking:
                                # 思考フェーズ終了！
                                in_thinking = False
                                buffer_for_thinking = ""
                            continue
                        
                        # 2. <thinking> 開始の検知
                        if char == "<":
                            buffer_for_thinking = "<"
                            continue
                        elif buffer_for_thinking.startswith("<"):
                            buffer_for_thinking += char
                            if "thinking" in buffer_for_thinking:
                                if buffer_for_thinking == "<thinking>":
                                    in_thinking = True
                                    buffer_for_thinking = ""
                                    continue
                            elif len(buffer_for_thinking) > 20: # <thinking> ではないので放出
                                filtered_text_chunk += buffer_for_thinking
                                buffer_for_thinking = ""
                            continue

                        # 3. 自律記憶タグの検知
                        if char == "[":
                            in_possible_tag = True
                            buffer_for_tag += char
                        elif in_possible_tag:
                            buffer_for_tag += char
                            if char == "]":
                                # タグが閉じたので確認
                                if "SAVE_USER_FACT:" in buffer_for_tag or "SAVE_EVENT:" in buffer_for_tag:
                                    # システム用の自律記憶タグなので送信しない！
                                    buffer_for_tag = ""
                                    in_possible_tag = False
                                else:
                                    # 普通のカッコだったので溜めていた文字を放出
                                    filtered_text_chunk += buffer_for_tag
                                    buffer_for_tag = ""
                                    in_possible_tag = False
                            elif len(buffer_for_tag) > 100: # タグにしては長すぎるので諦めて放出
                                filtered_text_chunk += buffer_for_tag
                                buffer_for_tag = ""
                                in_possible_tag = False
                        else:
                            filtered_text_chunk += char
                    
                    if filtered_text_chunk:
                        text_chunk = filtered_text_chunk
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

                # ツールコールが発生しなかった場合は、通常の会話生成が完了したのでループを抜ける！
                if not has_function_call:
                    break

                # ツールコールの実行と履歴への追加
                model_parts = []
                tool_parts = []
                for call in function_calls:
                    print(f"🛠️ Tool Call Detected: {call.name} (args: {call.args})")
                    if call.name == "search_archive":
                        query = call.args.get("query", "")
                        # 澪の脳内に「ちょっと待ってね、思い出してみる……」というシグナルを送る
                        tool_loading_msg = json.dumps({'type': 'chunk', 'content': ' *澪（ちょっと待ってね、引き出しから昔の記憶を探してるよ……）* \n\n'})
                        yield f"data: {tool_loading_msg}\n\n"
                        
                        # 検索実行
                        result = search_archive(query)
                        print(f"   -> Search Result: {result[:100]}...")
                        
                        # APIにツール呼び出し要求の履歴を積む
                        fc_part = types.Part(
                            function_call=types.FunctionCall(
                                name=call.name,
                                args=call.args,
                                id=getattr(call, 'id', None)
                            )
                        )
                        model_parts.append(fc_part)
                        
                        # ツールからの実行結果
                        fr_part = types.Part(
                            function_response=types.FunctionResponse(
                                name=call.name,
                                response={"result": result},
                                id=getattr(call, 'id', None)
                            )
                        )
                        tool_parts.append(fr_part)

                # 会話履歴に積む (modelロール と toolロール のやり取り)
                contents.append(types.Content(role="model", parts=model_parts))
                contents.append(types.Content(role="tool", parts=tool_parts))
                
                # while ループを戻って再度ストリームを叩く

            if buffer.strip():
                 # 最後に残ったテキストの音声合成
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
            
            if usage_info:
                usage_info["model"] = CURRENT_MODEL_NAME
                print(f"Token Usage: {usage_info}")
                yield f"data: {json.dumps({'type': 'usage', 'data': usage_info})}\n\n"

            # ★全ての処理が終わったら、MIOの返答を記憶（DB保存）
            if full_response_text:
                # 返答もベクトル化して保存
                ai_embedding = await get_embedding(full_response_text)
                await db.log_message("assistant", full_response_text, embedding=ai_embedding)
                
                # ─── ★ 自律記憶タグの抽出・保存処理 ★ ───
                try:
                    if "[SAVE_USER_FACT:" in full_response_text:
                        match = re.search(r"\[SAVE_USER_FACT:\s*(.*?)\]", full_response_text)
                        if match:
                            fact = match.group(1).strip()
                            print(f"🧠 AI自律記憶発動 (ユーザー事実): {fact}")
                            
                            # USER.mdに自動書き込み
                            user_md_path = "memory/USER.md"
                            if os.path.exists(user_md_path):
                                with open(user_md_path, "a", encoding="utf-8") as f:
                                    f.write(f"\n- {fact}")
                            # ベクトルDB登録
                            fact_emb = await get_embedding(fact)
                            await db.log_message("user_fact", fact, embedding=fact_emb)
                            
                    elif "[SAVE_EVENT:" in full_response_text:
                        match = re.search(r"\[SAVE_EVENT:\s*(.*?)\]", full_response_text)
                        if match:
                            event = match.group(1).strip()
                            print(f"🧠 AI自律記憶発動 (出来事): {event}")
                            
                            # MEMORY.mdに自動書き込み
                            mem_md_path = "memory/MEMORY.md"
                            if os.path.exists(mem_md_path):
                                timestamp = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                                with open(mem_md_path, "a", encoding="utf-8") as f:
                                    f.write(f"\n- {timestamp}: {event}")
                            # ベクトルDB登録
                            event_emb = await get_embedding(event)
                            await db.log_message("user_fact", event, embedding=event_emb)
                except Exception as e:
                    print(f"自律記憶の保存に失敗: {e}")

            yield f"data: {json.dumps({'type': 'end'})}\n\n"
        except Exception as e:
            print(f"Error in event_generator: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            
    # ヘルパー関数: タスク内で呼び出して結果を返す用
    async def synthesize_audio_task(text, mode):
        print(f"Synthesizing Async ({mode}): {text}")
        return await synthesize_audio_async(text, mode)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# --- 記憶管理API ---

# --- 新規追加：記憶ファイル参照API ---
@app.get("/api/memory/file")
async def get_memory_file(category: str):
    filename_map = {
        "user": "memory/USER.md",
        "identity": "memory/IDENTITY.md",
        "memory": "memory/MEMORY.md",
        "archive": "memory/archive.md"
    }
    filepath = filename_map.get(category.lower())
    if not filepath or not os.path.exists(filepath):
        raise HTTPException(status_code=400, detail="無効なカテゴリまたはファイルが存在しません。")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return {"status": "ok", "category": category, "content": content}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- 新規追加：手動記憶追加API ---
@app.post("/api/memory/add_fact")
async def add_memory_fact(req: AddFactRequest):
    filepath = "memory/MEMORY.md"
    if not os.path.exists(filepath):
        raise HTTPException(status_code=500, detail="長期記憶ファイルが見つかりません。")
        
    timestamp = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    new_line = f"\n- {timestamp}: {req.text}"
    
    try:
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(new_line)
            
        # RAG廃止にともない、メッセージ記録時のベクトル埋め込み（Embedding）を無効化
        await db.log_message("user_fact", req.text, embedding=None)
            
        return {"status": "ok", "message": "記憶を追加したよ！"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- 新規追加：モデル管理API ---
@app.get("/api/model/current")
async def get_current_model():
    global CURRENT_MODEL_NAME
    return {"status": "ok", "model": CURRENT_MODEL_NAME}

@app.post("/api/model/set")
async def set_ai_model(model_name: str):
    global CURRENT_MODEL_NAME
    try:
        print(f"🔄 Switching model to: {model_name}")
        if not ai_client:
            raise HTTPException(status_code=500, detail="APIクライアントが初期化されていません。")
            
        CURRENT_MODEL_NAME = model_name
        
        # モデル設定を永続化保存
        save_current_model(model_name)
        
        print(f"✨ Successfully switched to {model_name}!")
        return {"status": "ok", "model": model_name}
    except Exception as e:
        print(f"❌ Failed to switch model: {e}")
        raise HTTPException(status_code=500, detail=f"モデルの切り替えに失敗したよ: {str(e)}")

# --- 新規追加：コンテキスト（トークン）監視API ---
@app.get("/api/model/context_status")
async def get_context_status():
    global CURRENT_MODEL_NAME
    if not ai_client:
        raise HTTPException(status_code=500, detail="APIクライアントが初期化されていません。")
        
    try:
        long_term_memory = load_memory_files()
        system_instruction = BASE_SYSTEM_PROMPT + long_term_memory
        
        history_data = await db.get_recent_context(limit=50)
        
        total_text_to_count = system_instruction
        for log in history_data:
            total_text_to_count += f"\n{log['role']}: {log['content']}"
            
        token_count_resp = await asyncio.to_thread(
            ai_client.models.count_tokens,
            model=CURRENT_MODEL_NAME,
            contents=total_text_to_count
        )
        current_tokens = token_count_resp.total_tokens
        
        max_tokens = MODEL_MAX_TOKENS.get(CURRENT_MODEL_NAME, 1_048_576)
        percent = (current_tokens / max_tokens) * 100
        
        auto_compact_required = percent >= 95.0
        
        return {
            "status": "ok",
            "model": CURRENT_MODEL_NAME,
            "current_tokens": current_tokens,
            "max_tokens": max_tokens,
            "percent": round(percent, 2),
            "auto_compact_required": auto_compact_required
        }
    except Exception as e:
        return {"status": "error", "message": f"トークン計測失敗: {str(e)}"}

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
    あなたは優秀な司書AIです。
    会話ログを分析し、蓄積すべき重要な事実や思い出を抽出してください。
    以下の4つのカテゴリに情報を厳密に振り分けてください。**同じ情報を複数のカテゴリに入れないこと。**

    1. **user_updates (ユーザー情報)**:
       - ユーザーのプロフィール、性格、好み、癖、思想、身体的特徴、仕事、家族構成など。
       - 「ユーザーそのもの」に関する不変または半永久的な属性情報。
       - 例：「リンゴが好き」「プログラマーである」「猫派」

    2. **identity_updates (AIアイデンティティ)**:
       - AI（MIO）自身の性格、話し方、行動指針、ユーザーに対する呼び名や態度、自分ルール。
       - 「AI自身」に関する自己定義のみ。
       - 例：「のんびり屋である」「～だよ口調を使う」「ユーザーをマスターと呼ぶ」

    3. **memory_updates (長期記憶・エピソード)**:
       - 過去に起こった具体的な出来事、約束、会話したトピック、一緒に行った場所、特定の文脈での合意事項のうち、「直近で今後もよく参照するであろう大切な思い出や約束」。
       - **※ユーザーのプロフィール的情報はここには含めず、user_updatesに入れてください。**
       - 例：「遊園地に行く約束をした」「AI倫理について議論した」「2024年の誕生日の思い出」

    4. **archive_updates (長期アーカイブ記憶・当分いらない細かい情報)**:
       - 当分使わないであろう古い選考データ（過去の特定の企業の面接の質問や結果等）、終わったプロジェクトの詳細、昔のデバッグや開発の詳細ログ、過去の旅行の細かいタイムスケジュールなど。
       - 普段のチャットプロンプトに入れる必要はないが、将来マスターから「あのときの〜ってどうだっけ？」と聞かれたらツールで検索して引っ張り出したい過去の記録。

    【出力形式】
    以下のJSON形式で出力してください：
    {
      "user_updates": ["追加すべきユーザーの事柄"],
      "identity_updates": ["追加すべきAI自身の事柄"],
      "memory_updates": ["追加すべきイベントや知識"],
      "archive_updates": ["アーカイブに移すべき古いまたは詳細な事柄"],
      "summary": "会話全体の簡潔な要約（100文字以内）"
    }
    """
    
    token_usage = {"prompt_token_count": 0, "candidates_token_count": 0, "total_token_count": 0}
    updates = {}
    
    if ai_client:
        try:
            # 分析用モデル
            config = types.GenerateContentConfig(
                system_instruction=librarian_prompt,
                response_mime_type="application/json"
            )
            
            resp = await asyncio.to_thread(
                ai_client.models.generate_content,
                model='gemini-3-flash-preview', 
                contents=conversation_text,
                config=config
            )
            
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
                3. 似たような情報は箇流書きでまとめて整理してください。
                4. 出力はファイルの内容そのもの（Markdown形式）のみを出力してください。余計な説明は不要です。
                5. ヘッダー（# User Profile など）は維持してください。
                """
                
                try:
                    # 編纂実行
                    resp = await asyncio.to_thread(
                        ai_client.models.generate_content,
                        model='gemini-3-flash-preview',
                        contents=compiler_prompt
                    )
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

            # archive_updates が存在する場合は、memory/archive.md の末尾にタイムスタンプ付きで追記（アペンド）するよ！
            archive_list = updates.get("archive_updates")
            if archive_list:
                archive_filepath = "memory/archive.md"
                timestamp = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                try:
                    os.makedirs("memory", exist_ok=True)
                    if not os.path.exists(archive_filepath):
                        with open(archive_filepath, "w", encoding="utf-8") as f:
                            f.write("# Long Term Archive Memory\n")
                            
                    with open(archive_filepath, "a", encoding="utf-8") as f:
                        f.write(f"\n## Archive [{timestamp}]\n")
                        for item in archive_list:
                            f.write(f"- {item}\n")
                    print(f"★ Appended {len(archive_list)} items to archive.md")
                except Exception as e:
                    print(f"Archive Append Error: {e}")

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
            global SESSION_START_ID
            SESSION_START_ID = 0  # ログが全消去されたのでセッション制限をリセット

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

@app.post("/api/new_session")
async def new_session():
    """現在のDB最大IDを記録し、以降のメッセージのみ会話履歴として渡すようにする（/new コマンド用）"""
    global SESSION_START_ID
    SESSION_START_ID = await db.get_max_id()
    print(f"[Session] New session started. History cutoff ID: {SESSION_START_ID}")
    return {"status": "ok", "session_start_id": SESSION_START_ID}

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

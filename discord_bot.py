"""
MIO Discord Bot - Phase 1: Chat Mirroring (Real-time Streaming)
ブラウザ版MIOとDiscordを双方向で繋ぐBot
"""
import os
import asyncio
import aiohttp
import discord
import time
from discord.ext import commands
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

# --- 設定 ---
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
MIO_CHANNEL_ID = int(os.getenv("MIO_CHANNEL_ID", "0"))
MIO_API_BASE = os.getenv("MIO_API_BASE", "http://127.0.0.1:8000")

# Bot設定
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
http_session: aiohttp.ClientSession = None

@bot.event
async def on_ready():
    global http_session
    http_session = aiohttp.ClientSession()
    print(f"✨ MIO Discord Bot (Real-time) 起動完了！")
    print(f"   Bot Name: {bot.user.name}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.channel.id != MIO_CHANNEL_ID:
        return
    
    user_text = message.content.strip()
    if not user_text:
        return

    # コンパクションコマンド対応
    if user_text.lower() in ["!compact", "!コンパクション", "コンパクション"]:
        await handle_compaction(message)
        return
    
    print(f"📩受信: {user_text}")

    async with message.channel.typing():
        bot_message = None
        full_text = ""
        token_info_str = ""
        last_edit_time = 0
        message_chunks = []  # 2000文字超え対応用のリスト

        try:
            # ジェネレーターから逐次受け取る
            async for item in call_mio_streaming_generator(user_text):
                if item["type"] == "content":
                    content_chunk = item["data"]
                    full_text += content_chunk
                    
                    # 現在の表示用テキストを作成
                    current_display_text = full_text
                    
                    # 2000文字制限の簡易対応（表示用）
                    if len(current_display_text) > 1950:
                        current_display_text = current_display_text[:1950] + "..."

                    now = time.time()
                    # 初回送信
                    if bot_message is None:
                        bot_message = await message.channel.send(current_display_text)
                        last_edit_time = now
                    # 更新（レート制限考慮: 1.0秒間隔）
                    elif now - last_edit_time > 1.0:
                        try:
                            await bot_message.edit(content=current_display_text)
                            last_edit_time = now
                        except discord.errors.HTTPException:
                            pass # 編集失敗は無視して次へ

                elif item["type"] == "usage":
                    token_usage = item["data"]
                    if isinstance(token_usage, dict):
                        input_tokens = token_usage.get("prompt_token_count", 0)
                        output_tokens = token_usage.get("candidates_token_count", 0)
                    else:
                        input_tokens = int(token_usage * 0.7)
                        output_tokens = int(token_usage * 0.3)
                    
                    # コスト計算
                    input_cost = (input_tokens / 1_000_000) * 0.50 * 155
                    output_cost = (output_tokens / 1_000_000) * 3.00 * 155
                    total_cost = input_cost + output_cost
                    
                    token_info_str = f"\n`入力: {input_tokens} / 出力: {output_tokens} (¥{total_cost:.4f})`"

            # === 最終確定 ===
            final_text = full_text + token_info_str
            
            # 2000文字を超える場合の分割送信
            if len(final_text) > 2000:
                # 最初のメッセージを上限まで埋める
                chunk1 = final_text[:2000]
                if bot_message:
                    await bot_message.edit(content=chunk1)
                else:
                    await message.channel.send(chunk1)
                
                # 残りを新規メッセージで送る
                remaining = final_text[2000:]
                while remaining:
                    chunk = remaining[:2000]
                    await message.channel.send(chunk)
                    remaining = remaining[2000:]
            else:
                if bot_message:
                    await bot_message.edit(content=final_text)
                else:
                    await message.channel.send(final_text)

        except Exception as e:
            print(f"❌ Error: {e}")
            await message.channel.send(f"⚠️ エラー: {str(e)[:100]}")

async def call_mio_streaming_generator(text: str):
    """MIOからの応答を逐次yieldするジェネレーター"""
    import json
    from urllib.parse import quote
    
    url = f"{MIO_API_BASE}/api/stream_chat?text={quote(text)}&mode=NONE"
    buffer = ""
    
    try:
        print(f"Connecting to MIO API: {url}")
        async with http_session.get(url) as response:
            print(f"API Response: {response.status}")
            
            # チャンク読み込み
            async for chunk in response.content.iter_any():
                chunk_str = chunk.decode('utf-8', errors='ignore')
                buffer += chunk_str
                
                # バッファ内の改行ごとに処理
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    if not line:
                        continue # 空行スキップ
                    
                    # print(f"DEBUG Line: {line[:50]}...") # デバッグ用

                    if line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            data = json.loads(data_str)
                            
                            if data.get("type") == "chunk":
                                content = data.get("content", "")
                                if content:
                                    yield {"type": "content", "data": content}
                            
                            elif data.get("usage"): # トークン情報
                                yield {"type": "usage", "data": data.get("usage")}
                                
                            elif data.get("type") == "end":
                                return
                            
                            elif data.get("error"):
                                print(f"API Error: {data.get('error')}")
                                yield {"type": "content", "data": f"\n[Error: {data.get('error')}]"}
                                
                        except json.JSONDecodeError as e:
                            print(f"JSON Error: {e} in {data_str}")
                            continue
                            
            # ループ終了後
            print("Stream finished.")

    except Exception as e:
        print(f"Streaming Error: {e}")
        yield {"type": "content", "data": f"\n[System Error: {e}]"}

async def handle_compaction(message: discord.Message):
    # コンパクション処理（変更なし・既存ロジック流用）
    import json
    await message.channel.send("🧠 記憶をコンパクション中...")
    try:
        async with http_session.post(f"{MIO_API_BASE}/api/memory/compact") as response:
            data = await response.json()
            if data.get("status") != "ok":
                await message.channel.send(f"⚠️ 失敗: {data.get('message')}")
                return
            
            updates = data.get("updates", {})
            token_usage = data.get("token_usage", {})
            timestamp = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

            if isinstance(token_usage, dict):
                input_tokens = token_usage.get("prompt_token_count", 0)
                output_tokens = token_usage.get("candidates_token_count", 0)
            else:
                input_tokens = int(token_usage * 0.7)
                output_tokens = int(token_usage * 0.3)
            
            cost = (input_tokens / 1000000) * 0.5 * 155 + (output_tokens / 1000000) * 3.0 * 155
            
            result_lines = [
                f"**{timestamp}**",
                f"`入力: {input_tokens} / 出力: {output_tokens} (¥{cost:.4f})`",
                updates.get("summary", "要約なし"),
            ]
            if updates.get("user_updates"): result_lines.append(f"👤 User: {', '.join(updates['user_updates'])}")
            if updates.get("identity_updates"): result_lines.append(f"🤖 Identity: {', '.join(updates['identity_updates'])}")
            if updates.get("memory_updates"): result_lines.append(f"🧠 Memory: {', '.join(updates['memory_updates'])}")
            
            await message.channel.send("\n".join(result_lines))
    except Exception as e:
        await message.channel.send(f"⚠️ エラー: {e}")

@bot.event
async def on_close():
    if http_session:
        await http_session.close()

if __name__ == "__main__":
    if not DISCORD_TOKEN or not MIO_CHANNEL_ID:
        print("❌ 設定不足: .envを確認してください")
        exit(1)
    
    print("🚀 MIO Discord Bot 起動中...")
    bot.run(DISCORD_TOKEN)

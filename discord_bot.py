"""
MIO Discord Bot - スラッシュコマンド＆記憶・モデル・コンテキスト管理機能 搭載版
"""
import os
import asyncio
import aiohttp
import discord
import time
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from datetime import datetime
from typing import Literal

load_dotenv()

# --- 設定 ---
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
MIO_CHANNEL_ID = int(os.getenv("MIO_CHANNEL_ID", "0"))
MIO_API_BASE = os.getenv("MIO_API_BASE", "http://127.0.0.1:8000")

# モデル価格設定テーブル (1Mトークンあたりの米ドル単価)
MODEL_PRICING = {
    "gemini-3-flash-preview": {"input": 0.075, "output": 0.30},
    "gemini-2.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-2.0-flash": {"input": 0.075, "output": 0.30},
    "gemma-4-31b-it": {"input": 0.0, "output": 0.0},
    "gemma-4-26b-a4b-it": {"input": 0.0, "output": 0.0},
    "gemma-4n-e4b-it": {"input": 0.0, "output": 0.0},
}

# Bot設定
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
http_session: aiohttp.ClientSession = None

@bot.event
async def on_ready():
    global http_session
    http_session = aiohttp.ClientSession()
    print(f"✨ MIO Discord Bot 起動完了！")
    print(f"   Bot Name: {bot.user.name}")
    
    # スラッシュコマンドをDiscordに登録・同期するよ！
    try:
        synced = await bot.tree.sync()
        print(f"🔄 スラッシュコマンド同期完了: {len(synced)}個のコマンド")
    except Exception as e:
        print(f"❌ スラッシュコマンド同期失敗: {e}")

# --- ① /compact コマンド ---
@bot.tree.command(name="compact", description="今までの会話履歴をコンパクションして要約・整理するよ！")
async def slash_compact(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    try:
        async with http_session.post(f"{MIO_API_BASE}/api/memory/compact") as response:
            data = await response.json()
            if data.get("status") != "ok":
                await interaction.followup.send(f"⚠️ 失敗しちゃった: {data.get('message')}")
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
            
            # Cost Calculation (Input $0.50/1M, Output $3.00/1M)
            cost = (input_tokens / 1_000_000) * 0.50 * 155 + (output_tokens / 1_000_000) * 3.00 * 155
            
            result_lines = [
                f"🧠 **記憶のコンパクションが完了したよ！** ({timestamp})",
                f"`消費: {input_tokens} / {output_tokens} tokens (¥{cost:.4f})`",
                f"📝 **要約**: {updates.get('summary', '要約なし')}"
            ]
            if updates.get("user_updates"): result_lines.append(f"👤 **マスターのこと**: {', '.join(updates['user_updates'])}")
            if updates.get("identity_updates"): result_lines.append(f"🤖 **私のこと**: {', '.join(updates['identity_updates'])}")
            if updates.get("memory_updates"): result_lines.append(f"📚 **出来事**: {', '.join(updates['memory_updates'])}")
            
            await interaction.followup.send("\n".join(result_lines))
    except Exception as e:
        await interaction.followup.send(f"⚠️ エラーが発生したよ: {e}")

# --- ①-2 /new コマンド ---
@bot.tree.command(name="new", description="これまでの会話履歴をリセットして、新しい会話セッションを始めるよ！")
async def slash_new(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    try:
        async with http_session.post(f"{MIO_API_BASE}/api/new_session") as response:
            data = await response.json()
            if data.get("status") != "ok":
                await interaction.followup.send(f"⚠️ 失敗しちゃった: {data.get('message', '不明なエラー')}")
                return
            
            await interaction.followup.send("✨ **新しい会話セッションを開始したよ！**\nこれまでの会話履歴を一度リセットして、新鮮な気持ちでお話ししよっ！(o^^o)")
    except Exception as e:
        await interaction.followup.send(f"⚠️ エラーが発生したよ: {e}")

# --- ② /memory コマンドグループ ---
memory_group = app_commands.Group(name="memory", description="MIOの記憶を管理・確認するコマンドだよ")

@memory_group.command(name="status", description="現在の短期記憶の蓄積状況とトークン使用率を確認するよ！")
async def memory_status(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    try:
        # FastAPIから記憶件数とトークンコンテキストサイズを取得する
        async with http_session.get(f"{MIO_API_BASE}/api/memory/status") as res_mem, \
                   http_session.get(f"{MIO_API_BASE}/api/model/context_status") as res_tok:
                   
            data_mem = await res_mem.json()
            data_tok = await res_tok.json()
            
            if data_mem.get("status") == "ok" and data_tok.get("status") == "ok":
                msg_count = data_mem.get("message_count", 0)
                
                # トークンコンテキスト状態
                current_tokens = data_tok.get("current_tokens", 0)
                max_tokens = data_tok.get("max_tokens", 0)
                percent = data_tok.get("percent", 0.0)
                model_name = data_tok.get("model", "不明").replace("models/", "")
                
                # 視覚的なプログレスバーを作成 (例: [████░░░░░░] 40%)
                bar_length = 10
                filled_length = int(round(bar_length * percent / 100))
                filled_length = min(filled_length, bar_length)
                bar = "█" * filled_length + "░" * (bar_length - filled_length)
                
                # MIO脳内メッセージの生成
                status_msg = "脳内はスッキリ！まだまだ余裕でお話しできるよ！"
                if percent >= 90.0:
                    status_msg = "🚨 **警告: 記憶容量が限界寸前だよ！** すぐに `/compact` してね！(次のお話で自動整理されるよ)"
                elif percent >= 75.0:
                    status_msg = "⚠️ **注意: 脳みそが少しパンパンになってきたかも！** そろそろ `/compact` してくれると嬉しいな？"
                
                await interaction.followup.send(
                    f"🧠 **MIOの脳内コンテキスト状況**\n"
                    f"⚙️ 稼働中モデル: `{model_name}`\n"
                    f"💬 短期記憶内の会話数: `{msg_count}件`\n"
                    f"📊 トークン使用率: `[{bar}] {percent}%`\n"
                    f"🔑 使用量: `{current_tokens:,} / {max_tokens:,} tokens`\n\n"
                    f"💡 澪からのメッセージ: {status_msg}"
                )
            else:
                await interaction.followup.send("⚠️ 脳内ステータスの取得に失敗しちゃった。")
    except Exception as e:
        await interaction.followup.send(f"⚠️ エラーだよ: {e}")

@memory_group.command(name="view", description="MIOの長期記憶ファイルの中身を覗き見るよ！")
async def memory_view(interaction: discord.Interaction, category: Literal["USER (マスターの情報)", "IDENTITY (澪の設定)", "MEMORY (思い出・出来事)"]):
    await interaction.response.defer(thinking=True)
    cat_key = "user"
    if "IDENTITY" in category: cat_key = "identity"
    elif "MEMORY" in category: cat_key = "memory"
    try:
        async with http_session.get(f"{MIO_API_BASE}/api/memory/file", params={"category": cat_key}) as response:
            data = await response.json()
            if data.get("status") == "ok":
                content = data.get("content", "")
                if len(content) > 1900:
                    content = content[:1900] + "\n\n...(長すぎるから省略したよ)"
                await interaction.followup.send(f"📚 **長期記憶ファイル [{category}] の中身だよ**\n```markdown\n{content}\n```")
            else:
                await interaction.followup.send("⚠️ ファイルの読み込みに失敗しちゃった。")
    except Exception as e:
        await interaction.followup.send(f"⚠️ エラーだよ: {e}")

@memory_group.command(name="add", description="MIOの長期記憶に新しい思い出や出来事を手動で追加するよ！")
@app_commands.describe(text="記憶させたい出来事や事実（例: マスターは来週誕生日、など）")
async def memory_add(interaction: discord.Interaction, text: str):
    await interaction.response.defer(thinking=True)
    try:
        async with http_session.post(f"{MIO_API_BASE}/api/memory/add_fact", json={"text": text}) as response:
            data = await response.json()
            if data.get("status") == "ok":
                await interaction.followup.send(f"✨ **記憶に刻んだよ！**\n「`{text}`」を忘れないように長期記憶に記録しておいたからね！( *´艸｀)")
            else:
                await interaction.followup.send("⚠️ 記憶の追加に失敗しちゃった。")
    except Exception as e:
        await interaction.followup.send(f"⚠️ エラーだよ: {e}")

bot.tree.add_command(memory_group)

# --- ③ /model コマンドグループ ---
model_group = app_commands.Group(name="model", description="MIOのAIモデルを管理・切り替えするコマンドだよ")

@model_group.command(name="status", description="現在使用しているAIモデルを確認するよ！")
async def model_status(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    try:
        async with http_session.get(f"{MIO_API_BASE}/api/model/current") as response:
            data = await response.json()
            if data.get("status") == "ok":
                current_model = data.get("model", "不明").replace("models/", "")
                await interaction.followup.send(f"🤖 現在の澪の思考エンジンは **`{current_model}`** だよ！")
            else:
                await interaction.followup.send("⚠️ モデル情報の取得に失敗しちゃった。")
    except Exception as e:
        await interaction.followup.send(f"⚠️ エラーだよ: {e}")

@model_group.command(name="set", description="MIOのAIモデルを切り替えるよ！")
@app_commands.describe(model_name="切り替え先のAIモデルを選択してね")
async def model_set(
    interaction: discord.Interaction, 
    model_name: Literal[
        "gemini-3-flash-preview", 
        "gemini-2.5-flash", 
        "gemini-2.0-flash", 
        "gemma-4-31b-it", 
        "gemma-4-26b-a4b-it",
        "gemma-4n-e4b-it"
    ]
):
    await interaction.response.defer(thinking=True)
    
    # API送信用に models/ プレフィックスを付ける
    full_model_name = f"models/{model_name}"
    
    try:
        async with http_session.post(f"{MIO_API_BASE}/api/model/set", params={"model_name": full_model_name}) as response:
            data = await response.json()
            if response.status == 200 and data.get("status") == "ok":
                await interaction.followup.send(f"✨ **モデルを切り替えたよ！**\nこれからは **`{model_name}`** の脳みそでマスターとお話しするね！お楽しみに！(ノ＞▽＜)ノ")
            else:
                await interaction.followup.send(f"⚠️ 切り替えに失敗しちゃった: {data.get('detail', 'エラー')}")
    except Exception as e:
        await interaction.followup.send(f"⚠️ エラーだよ: {e}")

bot.tree.add_command(model_group)


# --- ④ /archive コマンドグループ ---
archive_group = app_commands.Group(name="archive", description="MIOの長期アーカイブ記憶を管理・確認するコマンドだよ")

@archive_group.command(name="list", description="過去にアーカイブした古い記憶の一覧を確認するよ！")
async def archive_list(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    try:
        async with http_session.get(f"{MIO_API_BASE}/api/memory/file", params={"category": "archive"}) as response:
            data = await response.json()
            if data.get("status") == "ok":
                content = data.get("content", "")
                # 初期状態テキストのみ、または空の場合の判定
                clean_content = content.replace("## Long Term Archive Memory", "").replace("# Long Term Archive Memory", "").strip()
                if not clean_content or "このファイルは長期アーカイブ記憶倉庫です。" in clean_content and len(clean_content) < 50:
                    await interaction.followup.send("📦 **長期アーカイブ記憶倉庫はまだ空っぽだよ！**\n会話が自動整理（コンパクション）されたとき、当分使わない古い情報がここに移されるからね！")
                    return
                    
                if len(content) > 1900:
                    content = content[:1900] + "\n\n...(長すぎるから省略したよ)"
                await interaction.followup.send(f"📦 **長期アーカイブ記憶倉庫（archive.md）の中身だよ**\n```markdown\n{content}\n```")
            else:
                await interaction.followup.send("⚠️ アーカイブファイルの読み込みに失敗しちゃった。")
    except Exception as e:
        await interaction.followup.send(f"⚠️ エラーが発生したよ: {e}")

bot.tree.add_command(archive_group)


# --- 会話中継 (on_message) ---
@bot.event
async def on_message(message: discord.Message):
    # Bot自身や対象外チャンネルはスルー
    if message.author.bot or message.channel.id != MIO_CHANNEL_ID:
        return
    
    user_text = message.content.strip()
    if not user_text:
        return

    # 古い!プレフィックスの互換性用（スラッシュコマンドを推奨するメッセージを送るのも親切）
    if user_text.lower() in ["!compact", "!コンパクション", "コンパクション"]:
        await message.channel.send("💡 今度からはスラッシュコマンド `/compact` を使ってね！")
        # 一応そのまま動かす
        await handle_compaction(message)
        return
    
    print(f"📩 受信: {user_text}")

    async with message.channel.typing():
        bot_message = None
        full_text = ""
        token_info_str = ""
        last_edit_time = 0

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
                        raw_model = token_usage.get("model", "gemini-3-flash-preview")
                    else:
                        input_tokens = int(token_usage * 0.7)
                        output_tokens = int(token_usage * 0.3)
                        raw_model = "gemini-3-flash-preview"
                    
                    # models/ などのプレフィックスを取り除く
                    model_key = raw_model.replace("models/", "")
                    pricing = MODEL_PRICING.get(model_key, {"input": 0.075, "output": 0.30})
                    
                    # コスト計算 (USD単価を円に換算)
                    input_cost = (input_tokens / 1_000_000) * pricing["input"] * 155
                    output_cost = (output_tokens / 1_000_000) * pricing["output"] * 155
                    total_cost = input_cost + output_cost
                    
                    model_label = model_key.replace("-preview", "").lower()
                    token_info_str = f"\n`[{model_label}] 入力: {input_tokens} / 出力: {output_tokens} (¥{total_cost:.4f})`"

            # === 最終確定 ===
            final_text = full_text + token_info_str
            
            if not final_text:
                return

            # 2000文字を超える場合の分割送信
            if len(final_text) > 2000:
                chunk1 = final_text[:2000]
                if bot_message:
                    await bot_message.edit(content=chunk1)
                else:
                    await message.channel.send(chunk1)
                
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
        async with http_session.get(url) as response:
            async for chunk in response.content.iter_any():
                chunk_str = chunk.decode('utf-8', errors='ignore')
                buffer += chunk_str
                
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    if not line:
                        continue

                    if line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            data = json.loads(data_str)

                            if data.get("type") == "chunk":
                                content = data.get("content", "")
                                if content:
                                    yield {"type": "content", "data": content}
                            
                            elif data.get("type") == "usage":
                                token_usage = data.get("data")
                                yield {"type": "usage", "data": token_usage}
                            
                            elif data.get("type") == "end":
                                return
                            
                            elif data.get("error"):
                                yield {"type": "content", "data": f"\n[Error: {data.get('error')}]"}
                                
                        except json.JSONDecodeError as e:
                            continue
    except Exception as e:
        yield {"type": "content", "data": f"\n[System Error: {e}]"}

async def handle_compaction(message: discord.Message):
    # 古いプレフィックス用の互換性メソッド
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
            
            cost = (input_tokens / 1_000_000) * 0.50 * 155 + (output_tokens / 1_000_000) * 3.00 * 155
            
            result_lines = [
                f"🧠 **記憶のコンパクション完了！** ({timestamp})",
                f"`消費: {input_tokens} / {output_tokens} tokens (¥{cost:.4f})`",
                updates.get("summary", "要約なし"),
            ]
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

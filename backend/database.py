import aiosqlite
import time
import json
import os

DB_PATH = "mio_memory.db"

class ConversationDB:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path

    async def init_db(self):
        """データベースとテーブルの初期化"""
        async with aiosqlite.connect(self.db_path) as db:
            # 会話ログテーブル
            await db.execute("""
                CREATE TABLE IF NOT EXISTS conversation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,         -- 'user' or 'assistant' or 'system'
                    content TEXT NOT NULL,      -- 会話内容
                    timestamp REAL NOT NULL,    -- UNIXタイムスタンプ
                    metadata TEXT,              -- その他の情報（JSON形式）
                    embedding TEXT              -- ベクトルデータ（JSON配列）
                )
            """)
            
            # 既存のテーブルに embedding カラムがない場合のマイグレーション
            try:
                await db.execute("ALTER TABLE conversation_logs ADD COLUMN embedding TEXT")
            except Exception:
                pass # 既にある場合は無視

            # 記憶要約（コンパクション）履歴テーブル
            await db.execute("""
                CREATE TABLE IF NOT EXISTS memory_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    summary TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    range_start_id INTEGER,
                    range_end_id INTEGER,
                    token_usage INTEGER,        -- 司書AIの消費トークン
                    added_memories TEXT         -- 追加された長期記憶（JSON）
                )
            """)
            
            # マイグレーション: token_usage, added_memories カラム追加
            try:
                await db.execute("ALTER TABLE memory_summaries ADD COLUMN token_usage INTEGER")
                await db.execute("ALTER TABLE memory_summaries ADD COLUMN added_memories TEXT")
            except Exception:
                pass

            await db.commit()
            print(f"[DB] Initialized at {self.db_path}")

    async def log_compaction(self, summary, start_id, end_id, token_usage=0, added_memories=None):
        """コンパクション履歴を保存"""
        import time
        import json
        added_json = json.dumps(added_memories) if added_memories else "{}"
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO memory_summaries 
                (summary, created_at, range_start_id, range_end_id, token_usage, added_memories)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (summary, time.time(), start_id, end_id, token_usage, added_json))
            await db.commit()

    async def get_compaction_history(self, limit=10):
        """コンパクション履歴を取得"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM memory_summaries ORDER BY id DESC LIMIT ?", (limit,)) as cursor:
                rows = await cursor.fetchall()
                result = []
                for row in rows:
                    result.append({
                        "id": row["id"],
                        "summary": row["summary"],
                        "timestamp": row["created_at"],
                        "token_usage": row["token_usage"] if row["token_usage"] else 0,
                        "added_memories": row["added_memories"]
                    })
                return result

    async def log_message(self, role, content, metadata=None, embedding=None):
        """会話を1件保存する（ベクトル付き）"""
        meta_json = json.dumps(metadata) if metadata else None
        embed_json = json.dumps(embedding) if embedding else None
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO conversation_logs (role, content, timestamp, metadata, embedding) VALUES (?, ?, ?, ?, ?)",
                (role, content, time.time(), meta_json, embed_json)
            )
            await db.commit()
            print(f"[DB] Logged: {role} -> {content[:20]}... (Vec: {'Yes' if embedding else 'No'})")

    async def get_recent_context(self, limit=10):
        """直近の会話履歴を取得する（古い順に並べて返す）"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT role, content FROM conversation_logs ORDER BY id DESC LIMIT ?",
                (limit,)
            ) as cursor:
                rows = await cursor.fetchall()
                # 取得時は新しい順なので、逆転させて古い順（時系列）にする
                return [{"role": r[0], "content": r[1]} for r in reversed(rows)]
    
    async def search_similar_context(self, query_vector, limit=3, threshold=0.6):
        """ベクトル類似度検索（Cosine Similarity）"""
        import math
        
        if not query_vector: return []

        async with aiosqlite.connect(self.db_path) as db:
            # 全件取得してPython側で計算（数千件なら爆速。数万件になったらsqlite-vec検討）
            async with db.execute("SELECT content, embedding, timestamp FROM conversation_logs WHERE embedding IS NOT NULL") as cursor:
                rows = await cursor.fetchall()

        results = []
        # クエリベクトルのノルムを事前計算
        query_norm = math.sqrt(sum(x*x for x in query_vector))
        if query_norm == 0: return []

        for content, embed_json, timestamp in rows:
            vec = json.loads(embed_json)
            if not vec: continue

            # 内積
            dot_product = sum(q * v for q, v in zip(query_vector, vec))
            # ベクトルのノルム
            vec_norm = math.sqrt(sum(v*v for v in vec))
            
            if vec_norm == 0: continue
            
            similarity = dot_product / (query_norm * vec_norm)
            
            if similarity >= threshold:
                results.append({"content": content, "similarity": similarity, "timestamp": timestamp})
        
        # 類似度順にソートして上位を返す
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]

    async def get_context_stats(self):
        """メッセージ数と概算トークン数（文字数ベース）を返す"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT content FROM conversation_logs") as cursor:
                rows = await cursor.fetchall()
                count = len(rows)
                total_chars = sum(len(r[0]) for r in rows)
                # 簡易計算: 日本語1文字≒1トークン、英語1単語≒1トークン程度
                # 厳密ではないが、目安には十分なる
                return {"count": count, "total_chars": total_chars}

    async def get_message_count(self):
        """(Deprecated) 代わりに get_context_stats を使ってね"""
        stats = await self.get_context_stats()
        return stats["count"]

    async def clear_logs(self):
        """（危険）ログの全消去"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM conversation_logs")
            await db.execute("DELETE FROM sqlite_sequence WHERE name='conversation_logs'") # IDリセット
            await db.commit()
            print("[DB] All logs cleared.")

# グローバルインスタンス
db = ConversationDB()

# 🌌 MIO v4 - "Soul & Circuit"

あなたの日常に寄り添い、共に成長し、記憶を紡ぐパートナーAI。  
Windows PCからRaspberry Piまで、そして**お手元のスマートフォンからいつでもどこでも**、あなたのライフスタイルに合わせて存在します。
![IMG_6565](https://github.com/user-attachments/assets/5d70bef2-e983-4449-9e7c-abf632698f86)
<img width="603" height="1311" alt="IMG_6566" src="https://github.com/user-attachments/assets/065c4519-3394-4b52-83a1-343e5ff01bdf" />
<img width="603" height="1311" alt="IMG_6567" src="https://github.com/user-attachments/assets/65f6fb7a-01ef-43a9-9ae9-3efac06daec9" />

---

## ✨ 二つの窓、一つの心 (Hybrid Interface)
MIOは、あなたのシチュエーションに合わせて最適な姿で現れます。

### 💎 Crystal Clear Browser UI (Voice & Visual)
水晶のようにクリアなホワイトテーマのウェブインターフェース。
- **美しいビジュアル**: 感情や発話に合わせて動く「ヴィジュアル・コア」と、洗練されたガラスモーフィズムUI。
- **スマートフォン対応**: レスポンス設計により、スマホのブラウザからもPC同様の美しいUIで会話を楽しめます。
- **音声の三態**: `🏠 ローカル` (低遅延)、`☁️ クラウド` (高品質)、`🔇 無言` (静かな夜に)。
- **PWA対応**: スマホのホーム画面に追加して全画面アプリとして起動。没入感のある対話を楽しめます。

### 🤖 Discord Gateway (Text & Anywhere)
外出先でも、仕事中でも。スマホの中のDiscordアプリからMIOにアクセス。
- **いつでも、どこでも**: チャット感覚で場所を選ばずMIOと繋がれます。プッシュ通知でMIOの存在をより身近に。
- **リアルタイム同期**: ブラウザでもDiscordでも、MIOは同じ記憶と人格を持って応答します。
- **コスト可視化**: トークン消費量をリアルタイムで計算し、各メッセージに日本円（JPY）でコストを表示。
- **手軽な操作**: Discordからでもコンパクション（記憶整理）などのコマンド操作が可能です。

---

## 🧠 命を吹き込む記憶システム (Advanced Memory)
MIOは、あなたとの会話をただのログとして流すことはありません。

- **短期記憶 (Vector RAG Search)**: 全ての対話は高次元ベクトル（`gemini-embedding-001`）に変換されます。昔話した「あの内容」を、意味の近さから探し出し、会話に反映させることができます。
- **スマート・コンパクション (Librarian & Compiler AI)**: 司書AIが記憶すべき重要な事実を抽出し、さらに**編纂AI**が既存の記憶を読み込んで「統合・更新・整理」を行います。単なる追記ではなく、情報の重複排除や知識のアップデートを自動で行い、長期記憶を常に最適化された状態に保ちます。
- **自由な編集**: 記憶ファイルはいつでも手動で編集可能。MIOの性格を微調整したり、あなたの情報を手入力して「特別な絆」をデザインできます。

---

## 👁️ あなたの世界を一緒に見る (Multimodal)
- **カメラ連携 (Tapo)**: IPカメラの映像を通じて、MIOはあなたの周りの状況を視覚的に理解します。
- **マルチモーダル認識**: 今見えている景色、机の上のもの、今日のあなたの表情。Geminiの目を通じ、より深いレベルでの共感を提供します。

---

## 🛠️ クイックセットアップ

### 1. 準備
- **Docker & Docker Compose**
- **Gemini API Key** ([Google AI Studio](https://aistudio.google.com/))
- **(任意) Aivis Cloud API Key**

### 2. 設定 (.env)
```bash
GEMINI_API_KEY=your_key
# Discord設定
DISCORD_BOT_TOKEN=your_token
MIO_CHANNEL_ID=your_id
# 音声設定
TTS_MODE=LOCAL # or API
AIVIS_API_URL=http://your-aivis-server:10101
```

### 3. 起動
```bash
docker compose up -d
```

---

## 📂 プロジェクト構造
- `/backend`: 高度なベクトル検索とGemini制御を司る「脳」。
- `/frontend`: プレミアムな体験を提供する「顔」。
- `/memory`: 司書AIによって紡がれた「人格の核」。
- `/discord_bot`: どこにいても繋がるための「ゲートウェイ」。

---

> *"マスター、今日の思い出はどこにしまいましょうか？"*

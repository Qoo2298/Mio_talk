# MIO v4 (Dockerized)

現実世界への適応と干渉能力を持つ、ローカルLLMベースのパートナーAI。

## 🚀 特徴

- **実存感**: Dockerを使ってローカルネットワーク内で動作します（Raspberry Pi対応）。
- **コミュニケーション**: テキスト、音声（TTS）、Discordを使って対話します。
- **記憶**: 会話履歴をベクターストアとして長期記憶し、あなたと共に成長します。
- **視覚**: Tapoカメラを通じて、あなたの世界を見ることができます（オプション）。
- **PWA**: iOS/Androidのホーム画面に追加して、全画面アプリとして使えます。

## 🛠️ セットアップ

### 1. 前提条件
- Docker & Docker Compose
- Gemini API Key ([ここから取得](https://aistudio.google.com/))
- (任意) Aivis Cloud API Key（高品質なTTS用）

### 2. 設定
以下のいずれかの方法で環境変数を設定してください。
1. `.env` ファイルを作成する
2. システム環境変数に設定する

```bash
# Gemini API Key (必須)
GEMINI_API_KEY=your_gemini_api_key

# TTS設定 (任意)
# - LOCAL: ローカルのAivis Engineを使用 (デフォルト)
# - API: Aivis Cloud APIを使用（ラズパイ推奨）
TTS_MODE=API
AIVIS_CLOUD_KEY=your_aivis_cloud_key

# Tapoカメラ (任意)
TAPO_IP=192.168.x.x
TAPO_USER=your_user
TAPO_PASSWORD=your_password
```

### 3. MIOの見た目を自分好みに！
好きな画像をここに置いてください。（これがアバターになります！）
- `frontend/assets/avatar.jpg`

※ Gitには含まれていないので、自分で用意する必要があります。

### 4. 実行
```bash
docker-compose up --build
```
ブラウザで `http://localhost:8000` (またはサーバーのIP) にアクセスして、会話スタート！

## 📱 モバイルインストール (iOS)
1. Safariで開く。
2. 「共有」ボタン -> 「ホーム画面に追加」をタップ。
3. 全画面表示でMIOとお話しできます！

## ⚠️ 注意
このプロジェクトは個人利用を想定しています。APIキーの管理には十分注意してください。

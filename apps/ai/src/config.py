"""アプリ全体の設定値（環境変数 → typed Settings）。

このファイルが扱う AI 概念：

* **pydantic-settings** — 環境変数や ``.env`` ファイルから値を読んで型付き
  オブジェクトに落とす。型ヒント = バリデーションになるので、
  ``embedding_dim: int = 1024`` を書いた瞬間に文字列で渡された値は弾かれる。
* **モノレポでの ``.env`` 探索順** — ルート ``.env`` と ``apps/ai/.env`` の
  両方を読む。リスト後ろの方が優先されるので、AI アプリ固有の上書きが効く。
* **フィーチャーフラグ運用** — ``rag_enabled`` / ``rerank_enabled`` を環境変数で
  切り替え可能にして、評価実験（A/B）と障害時縮退の両方に使う。
* **モデル次元の不変条件** — ``embedding_dim=1024`` は ``voyage-3`` の出力次元と
  一致している必要がある（DB の vector(1024) スキーマとも整合）。
  違うモデルに変えるならスキーマ移行も必要。
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """環境変数から読み込む設定値の型付きコンテナ。"""

    model_config = SettingsConfigDict(
        env_file=[
            # parents[3] = リポジトリルート（``apps/ai/src/config.py`` から 3 階層上）
            Path(__file__).resolve().parents[3] / ".env",
            # parents[2] = ``apps/ai/.env``（アプリ固有の上書きをここに置く）
            Path(__file__).resolve().parents[2] / ".env",
        ],
        env_file_encoding="utf-8",
        # ``.env`` に未定義キーが入っていてもエラーにしない（共有 .env を使うため）。
        extra="ignore",
    )

    # === Anthropic Claude ===
    # 必須。未設定なら起動時に ValidationError で落ちて気付ける。
    anthropic_api_key: str
    # claude-opus-4-7（このプロジェクトの規定モデル）。eval で他モデルに切り替え可。
    anthropic_model: str = "claude-opus-4-7"
    # 1 リクエストあたりの上限。長文契約レビューでも収まる程度に設定。
    max_tokens: int = 4096

    # === RAG（法令引用） ===
    # False にすると RAG ブロックの注入をスキップ（LLM 単独で動く）。
    rag_enabled: bool = True
    # 検索結果の件数。多いほど引用網羅性は上がるがプロンプトが膨れる。
    rag_top_k: int = 5
    # pgvector + HNSW で構築された PostgreSQL の接続文字列。
    database_url: str = "postgresql://legal_ai:legal_ai_password@localhost:5432/legal_ai"
    # e-Gov 法令 API v2 のベース URL（取り込み専用）。
    egov_api_base: str = "https://laws.e-gov.go.jp/api/2"

    # === Voyage embeddings ===
    # voyage-3 は 1024 次元。モデルを変える場合は embedding_dim と DB スキーマも揃える。
    embedding_model: str = "voyage-3"
    embedding_dim: int = 1024
    # 取り込み・検索の両方で必要。空文字だと API 呼び出しが 401 で失敗する。
    voyage_api_key: str = ""

    # === Reranker（オプトイン） ===
    # True にすると dense → rerank の 2 段検索になる（精度↑コスト↑遅延↑）。
    rerank_enabled: bool = False
    rerank_model: str = "rerank-2"
    # rerank 用に dense 段で何倍多めに引くか。3 だと top_k=5 のとき 15 件取得 → 5 件に絞る。
    rerank_candidate_multiplier: int = 3

    # === Langfuse (LLM observability, self-hosted) ===
    # tracing_enabled が False、または public/secret キーが空のときは
    # 計装が完全に no-op 化する（Langfuse 未起動でもアプリは正常動作）。
    langfuse_tracing_enabled: bool = False
    langfuse_host: str = "http://localhost:3030"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    # UI URL の組み立てにのみ使う (Langfuse は /project/{id}/... 配下に画面が並ぶ)。
    # 空ならフォールバックで host だけを印字する。
    langfuse_project_id: str = ""


# プロセス内で 1 度だけ生成。型チェッカは BaseSettings の動的フィールドを
# 推論できないため call-arg 警告を抑制する。
settings = Settings()  # type: ignore[call-arg]

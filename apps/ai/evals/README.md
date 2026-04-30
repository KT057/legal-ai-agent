# Eval Harness

法務 AI Agent (`legal_chat` / `research_agent`) の回答品質を、再現可能な golden データセットと 2 軸スコアリングで定量評価する仕組み。

## なぜ必要か

エージェント開発で一番効くのは **「変えたら良くなったか」を毎回測れること**。
"良くなった気がする" を許すと、agent は静かに退化する。Eval が無いと、

- prompt をいじって回答が変わったが、それは改善か退化か?
- reranker を入れたら本当に精度が上がったのか?
- モデルを下位に切り替えてもユースケースは満たすか?

…を全部"勘"で判断することになる。Eval があれば回帰チェックと改善検証の両方が
1 コマンドで回る。

## 構成

```
evals/
├── dataset.jsonl    # golden 質問 (id / question / expected_keywords / must_cite)
├── run.py           # 1) 走らせる 2) スコアリング 3) レポート生成
└── runs/            # 各実行のアウトプット (gitignore 推奨)
    └── <timestamp>-<agent>/
        ├── traces.jsonl   # 各質問の生 trace
        ├── scores.jsonl   # スコアリング結果
        └── report.md      # 集計サマリ
```

## スコアリング軸

1. **Keyword hit rate (heuristic)** — `expected_keywords` のうち、回答テキストに
   含まれる割合。安価で速く、回帰検知に向く。
2. **LLM-as-judge (1〜5)** — 別呼び出しの Claude に質問+回答を読ませ、JSON で
   スコアを出させる。正確だがコストがかかる。`--skip-judge` で省略可能。

## 実行

```bash
cd apps/ai

# 全件 / legal_chat
uv run python -m evals.run --agent legal_chat

# 3 件だけ + judge スキップ (CI / dry-run 向き)
uv run python -m evals.run --agent legal_chat --limit 3 --skip-judge

# ReAct 版を試す
uv run python -m evals.run --agent research_agent --limit 3
```

実行ごとに `evals/runs/<timestamp>-<agent>/report.md` が生成される。CI で前回比較
させたい場合は `report.md` の数値だけ抜き出して比較すれば良い。

## データセット拡張のコツ

- **質問は具体的に**: "労働法について教えて" は採点不能。"36協定の届出先は?" のように、
  キーワードと回答範囲が一意に決まるものを足す。
- **カテゴリを散らす**: 1 つの法令に偏ると過学習しやすい。`category` フィールドで分散
  チェック。
- **must_cite は本気で**: 引用しないと不正解、というケースを必ず混ぜる。

## 今後の拡張ポイント (= 練習問題)

- citation の正確性チェック (引用 ID が実在するか / 関連条文か) — `scorer.py` 追加
- コスト計算 (トークン → ドル換算) — `usage` フィールドは既に出ている
- 前回 run との diff 表示 (`runs/` を 2 つ比較)
- judge を別モデル (Sonnet) で行うことでバイアスを減らす
- 並列実行 (`asyncio.gather` でスループット向上)

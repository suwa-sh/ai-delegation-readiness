# ai-delegation-readiness

![アイキャッチ](docs/assets/eyecatch.png)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 🇬🇧 English version: [README.md](README.md)

高リスクな定型業務を AI エージェントに委任して良いかを **診断するツールと
拡張可能なフレームワーク**です。本番稼働中の実例(味の素グループの経理 AI
エージェント、2026 年 2 月本番稼働)の **事例記事から骨格を抽出しています**。

clone すると、次の 3 つが手に入ります。

1. **CLI 診断ツール** — `bin/aidr check-readiness` / `score-delegation` /
   `validate-audit-log`(1 分で動きます)
2. **機械可読のフレームワーク**(`definitions/*.yaml` / `schemas/*.json`) — AI
   エージェントの system prompt に載せたり、CI パイプラインから直接叩けます
3. **オーバーレイの拡張点** — 各社の独自規定や厳格化した閾値を
   **フォークせず追加できます**

## Quick start(3 分で動かす)

```bash
git clone https://github.com/suwa-sh/ai-delegation-readiness.git
cd ai-delegation-readiness
pip install -r requirements.txt

# 1. 4 層 + 効果測定 フレームで業務を採点
bin/aidr check-readiness examples/business/sample-expense-approval.yaml

# 2. 委任マトリクスで 5 判定を採点
bin/aidr score-delegation examples/judgments/sample-judgments.yaml

# 3. 監査ログを J-SOX グレードの extended スキーマで検証
bin/aidr validate-audit-log examples/audit-log-sample.json --level extended

# 4. オーバーレイのマージ規則違反を検証
bin/aidr check-overlay examples/overlays/sample-company/extra-rules.yaml

# 5. ロード中の定義(土台 + オーバーレイ)を表示
bin/aidr list-definitions
```

各コマンドは決定的な終了コードを返します(0 = ok、1 = partial / yellow、
2 = block / red、3 = overlay error)。これにより CI で診断結果に応じてゲートできます。

## Who this is for

| あなたが... | まず読むもの |
|---|---|
| **業務側の意思決定者**(経理部長 / CFO / コンプラ責任者)で AI 化を検討中 | [`docs/01_four_layer_framework.md`](docs/01_four_layer_framework.md) — `bin/aidr check-readiness` で業務を採点します |
| **実装エンジニア**で高リスク承認業務向け AI エージェントを設計中 | [`schemas/audit-log.schema.json`](schemas/audit-log.schema.json) + [`docs/02_audit_log_schema.md`](docs/02_audit_log_schema.md) — スキーマをロガーに組み込みます |
| **運用担当**で既存 AI 基盤のログを点検したい | [`docs/04_agent_loop_audit_gap.md`](docs/04_agent_loop_audit_gap.md) — 5 ステップ手法を自社 SQL スキーマに当てます |
| **コンサル / 提案者** | `docs/` 全部 + オーバーレイ拡張モデル — clone してプライベートにフォークし、顧客固有の採点を提示します |

## What's in this repo

```
ai-delegation-readiness/
├── definitions/                 # 機械可読の正本フレームワーク(YAML)
│   ├── four-layer.yaml          #   4 層 + 効果測定 + extension_points
│   └── delegation-matrix.yaml   #   2 軸 + 領域マップ + extension_points
├── schemas/
│   └── audit-log.schema.json    # JSON Schema with $defs: minimum (A) / extended (B)
├── src/adr/                     # Python 診断ツール(pip 不要)
├── bin/aidr                     # CLI エントリポイント(単一コマンド、5 サブコマンド)
├── examples/
│   ├── business/                # check-readiness のサンプル入力
│   ├── judgments/               # score-delegation のサンプル入力
│   ├── audit-log-sample.json    # サンプル監査ログ(extended 有効)
│   ├── overlays/                # オーバーレイサンプル(Acme Corp)
│   └── skills/                  # Claude Code skill サンプル 2 種
└── docs/
    ├── 01_four_layer_framework.md
    ├── 02_audit_log_schema.md
    ├── 03_delegation_matrix.md
    └── 04_agent_loop_audit_gap.md
```

## How to extend(フレームワークの意図)

各社の独自ルールは **オーバーレイで追加します**(正本ファイルはフォークしません)。
雛形は [`examples/overlays/sample-company/extra-rules.yaml`](examples/overlays/sample-company/extra-rules.yaml) を参照してください。

```yaml
version: 1
extends: four-layer-delegation-readiness

layers:
  - id: L4
    add_questions:
      - id: ACME_L4Q6
        text: 監査ログは tamper-evident store に保存されているか
        weight: 1.0
    strengthen_thresholds:
      revise: 0.8       # 元 0.6 → 強化のみ可
```

そして `--overlay` 付きで診断します。

```bash
bin/aidr check-readiness mybiz.yaml --overlay /path/to/our-rules.yaml
```

**フレームワーク再利用の 3 経路**:

- **AI エージェント**: `definitions/four-layer.yaml` や
  `schemas/audit-log.schema.json` を system prompt や tool context にロードします。
  [`examples/skills/`](examples/skills/) に Claude Code skill のラッパー 2 種を用意しています
- **CI パイプライン**: 出力ログ 1 件ごとに `bin/aidr validate-audit-log` を呼び、
  exit code でゲートします
- **社内フォーク**: 自社固有のオーバーレイをプライベートリポで管理し、
  `--overlay` で適用します。本リポはクリーンな upstream として pull できます

## The framework's invariants

正本フレームワーク(`definitions/*.yaml` / `schemas/*.json`)は **全社で
一貫**を保ちます。オーバーレイで可能なのは、次の 2 つだけです。

- **`add`**: 配列要素の追加(既存要素は read-only)
- **`strengthen`**: 数値閾値の **強化方向のみ**(緩和は不可)

削除・置換・緩和は merge violation として `aidr check-overlay` が機械的に検出します。
これによりフォークせず安全に拡張できます。

## Background

本フレームワークは **味の素自身ではなく、事例記事から抽出しています**。
リポメンテナが公開報道をもとに分析記事を書き、その分析記事から本フレームワークを
抽出した、という来歴です(公開報道 → 分析記事 → 本フレームワーク)。
メンテナは味の素・AFS の内部情報にはアクセスしていません。

**味の素フィナンシャル・ソリューションズ(AFS)× ファーストアカウンティング** の
経理 AI エージェント(2026 年 2 月本番稼働)について、事例記事で公表されている
検証では、ドメイン特化エージェント = **93.3%**、汎用 LLM 単体 = **53.3%** という
40 ポイント差が報告されています(領収書必須項目 / インボイス制度準拠 / 税務上の
交際費判定の 3 タスク)。

差を生んだのはモデルの賢さではなく、**業務ロジックを LLM の周りで構造化**した
ことだと示されています。下層の標準化・構造化がモデル選定より重要なのはこのためです。

**正直な留保**: 広く引用される「工数 76% 削減」見出しは、**事例記事に分母・
基準値・スコープが明示されていません**。本リポは効果数値を保証せず、観測の観点だけを
保持します(`docs/01` の効果測定軸を参照してください)。

### 出典

- **メンテナによる分析記事**(直接の抽出元): [「味の素の経理AIエージェントに学ぶ 承認業務をAIに委任する前提条件」](https://suwa-sh.github.io/zenn-contents/articles/ajinomoto-accounting-agent_20260621/)

### 分析記事が引用している報道

- [ファーストアカウンティング公式プレスリリース (2026-04-24)](https://www.fastaccounting.jp/news/20260424/15929/)
- [ITmedia「工数 76% 削減」(2026-06-19)](https://www.itmedia.co.jp/business/articles/2606/19/news033.html)

## ライセンス

[MIT](LICENSE) を採用しています。

## セキュリティ

脆弱性報告は [SECURITY.md](SECURITY.md) を参照してください。

# 04. 既存ログ基盤を 5 観点で点検する(自社事例つき)

## TL;DR

「他人の DB スキーマに同じ点検手法を当てる」ための **worked example**。本リポ作者の
自社運用基盤 `agent-loop` の SQL スキーマを Who/When/What/Why/Result の 5 観点で
点検した結果と、`ALTER TABLE` での改修案を示す。**本書の手順は他社環境に持ち込める** —
冒頭の 5 ステップが手順、後半が agent-loop での具体例。

## When to use this

- 既に動いている AI エージェント基盤の統制ログに穴がないか点検したい
- 自社の `agent_outcomes` 相当テーブルが Who/When/What/Why/Result を満たすか確認したい
- 内部監査・J-SOX 評価の前に統制設計の弱点を可視化したい

## Apply this method to your own env(5 ステップ)

1. **対象テーブルを集める** — エージェントの実行ログ / 成果ログ / 対話ログの列定義を
   `\d <table>`(PostgreSQL)や `DESCRIBE <table>`(MySQL)で集める

2. **5 観点で列を分類する** — `docs/02_audit_log_schema.md` の Who/When/What/Why/Result
   の最小項目を観点に、各列が「充足 / 部分 / 欠け / 不適」のどれかを判定する

3. **「不適」の理由を型・意味論レベルで説明する** — 「自由形式 TEXT に書けば書ける」と
   妥協しない。CHECK 制約や enum がないと監査クエリの信頼性が慣習依存になる

4. **改修案を CHECK 制約・JSONB・別テーブル のどれで実現するか設計する** — 業務 Result の
   ような離散値は CHECK 制約付き enum、参照規定 + バージョンは JSONB or 別カラム、
   人間関与の補正ログは別テーブル

5. **改修の優先順位を引く** — 業務 Result の構造化 > 規定バージョン固定 > 委譲権限の
   ライフサイクル管理 > その他、の順で投資対効果が大きい

## Worked example: agent-loop schema

### 観測の前提

- 観測事実 = `agent-loop` リポの SQL スキーマ
  ([`tools/agent-loop/sql/init.sql`](https://github.com/suwa-sh/pkm/blob/main/tools/agent-loop/sql/init.sql))の列定義
- 設計提案 = 本書での改修案(コードは触らず、別 issue 化する想定)
- 対象は **承認・判定を伴う業務エージェント**(marketer / bookkeeper など)

agent-loop は記録の責務を 5 テーブルに分けている: `agent_runs` / `agent_costs` /
`agent_outcomes` / `dialogue_logs` / `execution_logs`。

### 現行スキーマ(関連 3 テーブルの列定義)

#### `agent_runs`

| 列 | 型 | 内容 |
|---|---|---|
| `id` | SERIAL | run の一意ID |
| `agent_name` | TEXT NOT NULL | エージェント名 |
| `skill_name` | TEXT | 実行スキル名 |
| `started_at` / `finished_at` | TIMESTAMPTZ | 実行時刻 |
| `status` | TEXT CHECK IN ('running','success','failure','partial') | **ジョブの実行成否のみ** |
| `token_input` / `token_output` | INTEGER | トークン |
| `error_message` | TEXT | 失敗時メッセージ |

#### `agent_outcomes`

| 列 | 型 | 内容 |
|---|---|---|
| `id` | SERIAL | outcome の一意ID |
| `run_id` | INTEGER REFERENCES agent_runs(id) | 親 run |
| `agent_name` | TEXT NOT NULL | エージェント名 |
| `metric_name` | TEXT NOT NULL | 成果メトリクス名(自由文字列) |
| `metric_value` | **REAL** | **連続値**(件数・スコアなど) |
| `metric_detail` | TEXT | 自由形式の補足 |
| `recorded_at` | TIMESTAMPTZ NOT NULL | 記録時刻 |

#### `dialogue_logs`

| 列 | 型 | 内容 |
|---|---|---|
| `id` | SERIAL | dialogue の一意ID |
| `agent_name` | TEXT NOT NULL | エージェント名 |
| `human_message` | TEXT | 人間の発話 |
| `ai_response` | TEXT | AI の応答 |
| `action_taken` | TEXT | **対話の結果として取られたアクション(自由文字列)** |
| `logged_at` | TIMESTAMPTZ NOT NULL | 記録時刻 |

### Mapping to 5 viewpoints

| 観点 | 充足度 | 現状の記録手段 | 欠け |
|---|---|---|---|
| **Who** | 部分 | `agent_outcomes.agent_name` + `agent_runs.id`、Kestra 経由なら `kestra_execution_id` | **承認権限を委譲した人間**の記録列が無い |
| **When** | 充足 | `agent_runs.started_at` / `finished_at` / `agent_outcomes.recorded_at` | なし |
| **What** | 部分 | `agent_outcomes.metric_name` + `metric_detail TEXT`(自由形式) | **判定対象の業務オブジェクト ID** が構造化されていない |
| **Why** | 欠け | `metric_detail TEXT` の自由形式に押し込める | **参照規定 + 規定バージョン + チェック項目** の構造化記録が無い |
| **Result** | ⚠ **未充足** | (該当列なし。下記分析参照) | **承認/差し戻し/エスカレーションの離散 enum が型安全に表現できない** |

### The Result-untyped problem(精密分析)

3 テーブルを合算しても、業務 Result(`approved`/`rejected`/`escalated` の離散 enum)を
**型安全に表現できる列は存在しない**。「自由テキストに書こうと思えば書ける」余地は
あるが、CHECK 制約が無いため監査クエリの信頼性は慣習依存になる。

| テーブル/列 | SQL から導ける評価 | 制約の限界 |
|---|---|---|
| `agent_outcomes.metric_value` | REAL の連続値、その列単独では離散 enum を型安全に表現できない | 「`1.0=approved`」のような慣習導入は可能だが、`WHERE decision='escalated'` と書けない |
| `agent_outcomes.metric_detail` | TEXT の自由形式で慣習で書ける | **CHECK 制約が無い**ため typo・表記揺れで集計が壊れる |
| `agent_runs.status` | CHECK 制約あり(`running/success/failure/partial`)。**ジョブの実行成否**の軸 | 業務承認の `approved/rejected/escalated` とは取りうる値集合が異なる |
| `dialogue_logs.action_taken` | TEXT の自由形式。同テーブルに `human_message` / `ai_response` 同居 | テーブル構成から対話起点の記録に使われていることは読めるが、**対話なしの自動承認の Result 記録には設計上向かない** |

## Proposed refactor

【設計提案】① の最小スキーマで業務承認を扱う場合、以下の改修が必要。

### A. `agent_outcomes` に統制カラムを追加

```sql
ALTER TABLE agent_outcomes
  ADD COLUMN business_object_id TEXT,              -- What: 判定対象の業務オブジェクト ID
  ADD COLUMN rule_ref            JSONB,            -- Why: 参照規定(id / version / section の構造化)
  ADD COLUMN checked_items       JSONB,            -- Why: [{"item":..., "outcome":"pass|fail|uncertain", "note":...}]
  ADD COLUMN business_result     TEXT
    CHECK (business_result IN ('approved', 'rejected', 'escalated')),  -- Result: 離散 enum
  ADD COLUMN escalated_to        TEXT,             -- Result: エスカレーション先 (human_id)
  ADD COLUMN human_delegator     TEXT;             -- Who: 承認権限を委譲した人間 (human_id)
```

理由:

- `business_object_id` で What を構造化(`metric_detail` 自由テキスト依存を脱却)
- `rule_ref` JSONB で Why の中核を構造化(規定 id / 版 / 条番号)
- `business_result` を CHECK 制約付き enum にすることで集計クエリの信頼性を担保
- `escalated_to` + `human_delegator` で職務分掌と説明責任の所在をログ単独で追える
- `checked_items` JSONB で `WHERE checked_items @> '[{"outcome":"uncertain"}]'` の
  クエリが書ける(escalate 候補抽出)

### B. 別テーブル `human_overrides` で誤承認補正フローをログ化

```sql
CREATE TABLE IF NOT EXISTS human_overrides (
  id              SERIAL PRIMARY KEY,
  outcome_id      INTEGER REFERENCES agent_outcomes(id),
  overridden_by   TEXT NOT NULL,                  -- 補正した人間
  original_result TEXT NOT NULL,                  -- 元の business_result
  new_result      TEXT NOT NULL
    CHECK (new_result IN ('approved', 'rejected', 'escalated')),
  reason          TEXT NOT NULL,                  -- 補正理由
  rule_ref_at_correction JSONB,                   -- 補正時の参照規定(版が変わっている場合)
  recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

誤承認の補正は元の判定を **上書きしない**(両方が監査追跡で必要)。
`original_result` + `new_result` で「何を覆したか」が追える。

## なぜ agent-loop が現状こうなっているか(背景)

agent-loop は **マーケ自動化プラットフォーム**として設計され、主要エージェントは
記事配信・SNS 投稿などの **「承認業務」ではない領域**で運用されてきた。そのため:

- ジョブ実行成否(`agent_runs.status`)で十分だった
- 成果メトリクスは件数・PV など連続値が中心で `metric_value REAL` で扱えた
- 承認/差し戻しのような離散判定が業務として登場しなかった

bookkeeper のような **承認・判定を伴う業務エージェント**を本格運用する段階で、本書の
改修が必要になる。これは agent-loop の設計が悪いわけではなく、**スコープ拡張に伴う
統制層の補強**という話。

## References

- 正本(本リポ側): [`schemas/audit-log.schema.json`](../schemas/audit-log.schema.json)
- 観測対象: [agent-loop sql/init.sql](https://github.com/suwa-sh/pkm/blob/main/tools/agent-loop/sql/init.sql)
- 関連 doc: [`02_audit_log_schema.md`](02_audit_log_schema.md)(本書の前提)

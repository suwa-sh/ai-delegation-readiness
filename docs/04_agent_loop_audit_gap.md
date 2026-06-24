# 04. 自社運用基盤(agent-loop)の④統制層 点検メモ

これは **本リポ作者の自社運用基盤(agent-loop)固有** の点検結果である。
他者が真似するためのテンプレ部は `docs/01`〜`docs/03` + `examples/` で完結しており、
本書は「実在する運用基盤を 4 層フレームの④で点検したらどうなるか」の **適用例**として
読む。

## 観測の前提

- 観測事実 = `agent-loop` リポの SQL スキーマ(`tools/agent-loop/sql/init.sql`)の列定義
- 設計提案 = 本書での改修案(コードは触らず、別 issue 化する想定)
- 対象は **承認・判定を伴う業務エージェント**(marketer / bookkeeper など)の統制設計

【観測事実】agent-loop は記録の責務を 5 テーブルに分けている:

- `agent_runs` — いつ・誰が(エージェント名)・成否(`success/failure/partial/running`)・トークン数
- `agent_costs` — コスト(USD)
- `agent_outcomes` — ドメイン成果(metric_name / metric_value REAL / metric_detail TEXT)
- `dialogue_logs` — 人間⇔AI 対話のアクション記録(action_taken)
- `execution_logs` — Step 単位の進捗 trace(JSONB の detail)

## 現行スキーマ(関連 3 テーブルの列定義)

`tools/agent-loop/sql/init.sql` から関連列を抜粋:

### `agent_runs`

| 列 | 型 | 内容 |
|---|---|---|
| `id` | SERIAL | run の一意ID |
| `agent_name` | TEXT NOT NULL | エージェント名(marketer / bookkeeper など) |
| `skill_name` | TEXT | 実行スキル名 |
| `started_at` | TIMESTAMPTZ NOT NULL | 開始時刻 |
| `finished_at` | TIMESTAMPTZ | 終了時刻 |
| `status` | TEXT NOT NULL CHECK (status IN ('running','success','failure','partial')) | **ジョブの実行成否のみ** |
| `token_input` / `token_output` | INTEGER | 入出力トークン |
| `error_message` | TEXT | 失敗時のメッセージ |
| `trace_id` / `span_id` / `kestra_execution_id` | TEXT | OTel 相関 |

### `agent_outcomes`

| 列 | 型 | 内容 |
|---|---|---|
| `id` | SERIAL | outcome の一意ID |
| `run_id` | INTEGER REFERENCES agent_runs(id) | 親 run |
| `agent_name` | TEXT NOT NULL | エージェント名 |
| `metric_name` | TEXT NOT NULL | 成果メトリクス名(自由文字列) |
| `metric_value` | **REAL** | **連続値**(件数・スコアなど) |
| `metric_detail` | TEXT | 自由形式の補足 |
| `recorded_at` | TIMESTAMPTZ NOT NULL | 記録時刻 |

### `dialogue_logs`

| 列 | 型 | 内容 |
|---|---|---|
| `id` | SERIAL | dialogue の一意ID |
| `agent_name` | TEXT NOT NULL | エージェント名 |
| `human_message` | TEXT | 人間の発話 |
| `ai_response` | TEXT | AI の応答 |
| `action_taken` | TEXT | **対話の結果として取られたアクション(自由文字列)** |
| `logged_at` | TIMESTAMPTZ NOT NULL | 記録時刻 |

## Who/When/What/Why/Result の 5 観点マッピング

`docs/02_audit_log_schema.md` の最小スキーマに対し、agent-loop の現行スキーマが
どこまで充足しているかを観点別に整理する。

| 観点 | 充足度 | 現状の記録手段 | 欠け |
|---|---|---|---|
| **Who** | 部分 | `agent_outcomes.agent_name` + `agent_runs.id`、Kestra 経由なら `kestra_execution_id` | **承認権限を委譲した人間**の記録列が無い |
| **When** | 充足 | `agent_runs.started_at` / `finished_at` / `agent_outcomes.recorded_at` | なし |
| **What** | 部分 | `agent_outcomes.metric_name` + `metric_detail TEXT`(自由形式) | **判定対象の業務オブジェクト ID** が構造化されていない(自由テキスト依存) |
| **Why** | 欠け | `metric_detail TEXT` の自由形式に押し込めるが構造列なし | **参照規定 + 規定バージョン + チェック項目** の構造化記録が無い |
| **Result** | ⚠ **未充足** | (該当列なし。下記分析参照) | **承認/差し戻し/エスカレーションの離散 enum が記録できない** |

### Result が未充足である理由(精密分析)

3 テーブルを合算しても、業務 Result(`approved`/`rejected`/`escalated` の離散 enum)を
**型安全に表現できる列は存在しない**。「自由テキストに書こうと思えば書ける」余地は
あるが、CHECK 制約が無いため監査クエリの信頼性は慣習依存になる。

| テーブル/列 | SQL から導ける評価 | 制約の限界 |
|---|---|---|
| `agent_outcomes.metric_value` | **REAL 型の連続値**であり、その列単独では離散 enum を型安全に表現できない | 数値での代用は可能だが「`1.0=approved`」のような慣習を導入する形になり、集計クエリで `WHERE decision = 'escalated'` と書けない |
| `agent_outcomes.metric_detail` | TEXT の自由形式で慣習で書ける | **CHECK 制約が無い**ため typo・表記揺れで集計が壊れる。型安全性は無い |
| `agent_runs.status` | CHECK 制約あり(`running/success/failure/partial`)。**ジョブの実行成否を表す軸** | 業務承認の `approved/rejected/escalated` とは取りうる値集合が異なり、同じ列に同居させると意味が混線する |
| `dialogue_logs.action_taken` | TEXT の自由形式。同テーブルに `human_message` / `ai_response` が同居 | テーブル構成から **対話起点の記録に使われている**ことは読めるが、`action_taken` 単独の用途を「人間対話専用」と断定するのは SQL からは導けない。**対話なしの自動承認の Result 記録には現状不向き**(設計上の用途と一致しない) |

つまり **3 テーブル合算でも業務 Result の構造化(CHECK 制約付き enum)記録は欠け** ている。

【観測事実】各 skill が自前で `metric_name='approval_decision'`、`metric_detail='approved'`
などの慣習で書くことは可能だが、スキーマレベルの制約がないため監査クエリの信頼性は
慣習依存になる。

## 改修案(別 issue 化、本セッションでは agent-loop コードは触らない)

【設計提案】① の最小スキーマで業務承認を扱う場合、以下の改修が必要:

### A. `agent_outcomes` に統制カラムを追加

```sql
ALTER TABLE agent_outcomes
  ADD COLUMN business_object_id TEXT,           -- What: 判定対象の業務オブジェクトID
  ADD COLUMN rule_ref            TEXT,          -- Why: 参照規定(URI/版/条番号 JSON)
  ADD COLUMN business_result     TEXT
    CHECK (business_result IN ('approved', 'rejected', 'escalated')),  -- Result: 離散 enum
  ADD COLUMN escalated_to        TEXT,          -- Result: エスカレーション先(human_id)
  ADD COLUMN human_delegator     TEXT;          -- Who: 承認権限を委譲した人間(human_id)
```

理由:

- `business_object_id` は What を構造化(`metric_detail` 自由テキスト依存を脱却)
- `rule_ref` は Why の中核を構造化(JSON で `{"id":..., "version":..., "section":...}`)
- `business_result` は CHECK 制約で表記揺れを防ぐ(集計クエリの信頼性)
- `escalated_to` + `human_delegator` で職務分掌と説明責任の所在をログ単独で追える

### B. 別テーブル `human_overrides` で誤承認補正フローをログ化

```sql
CREATE TABLE IF NOT EXISTS human_overrides (
  id              SERIAL PRIMARY KEY,
  outcome_id      INTEGER REFERENCES agent_outcomes(id),
  overridden_by   TEXT NOT NULL,                -- 補正した人間
  original_result TEXT NOT NULL,                -- 元の business_result
  new_result      TEXT NOT NULL
    CHECK (new_result IN ('approved', 'rejected', 'escalated')),
  reason          TEXT NOT NULL,                -- 補正理由(人間説明)
  rule_ref_at_correction TEXT,                  -- 補正時の参照規定(版が変わっている場合)
  recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

理由:

- 誤承認の補正は元の判定を**上書きしない**(両方が監査追跡で必要)
- `original_result` + `new_result` で「何を覆したか」が追える
- `rule_ref_at_correction` で規定改定後の遡及判定にも対応

### C. `Why.checked_items` の構造化(JSONB 列の追加)

```sql
ALTER TABLE agent_outcomes
  ADD COLUMN checked_items JSONB;  -- [{"item":..., "outcome":"pass|fail|uncertain", "note":...}]
```

`metric_detail TEXT` に押し込むより、JSONB で配列構造を持たせる方が監査クエリで扱える
(`WHERE checked_items @> '[{"outcome":"uncertain"}]'` で escalate 候補を抽出可能)。

## 改修案の【観測事実】/【設計提案】区分

| 区分 | 内容 |
|---|---|
| **【観測事実】** 現行スキーマで取れている | When の 3 タイムスタンプ / agent identity / トークン数 / ジョブ実行成否 / 自由形式の補足 |
| **【設計提案】** 改修で取れるようになる | 業務オブジェクト ID / 規定 + バージョン + 条番号 / 離散業務 Result / エスカレーション先 / 委譲した人間 / チェック項目の構造化 / 誤承認補正の追跡 |

## なぜ agent-loop が現状こうなっているか(背景)

agent-loop は **マーケ自動化プラットフォーム**として設計されており、当初の主要エージェントは
記事配信・SNS 投稿などの **「承認業務」ではない領域**で運用されてきた。そのため:

- ジョブ実行成否(`agent_runs.status`)で十分だった
- 成果メトリクスは件数・PV など連続値が中心で `metric_value REAL` で扱えた
- 承認/差し戻しのような離散判定が業務として登場しなかった

bookkeeper のような **承認・判定を伴う業務エージェント**を本格運用する段階で、本書の
改修が必要になる。これは agent-loop の設計が悪いというより、**スコープが拡張した結果**
として統制層の補強が要るという話である。

## 自分の環境で同じ点検をする方法

他社の DB スキーマに本書の手法を当てる手順:

1. 監査対象テーブル(エージェントの実行ログ / 成果ログ / 対話ログ)の列定義を集める
2. `docs/02_audit_log_schema.md` の Who/When/What/Why/Result の最小項目を観点に取る
3. 列ごとに「充足 / 部分 / 欠け / 不適」を判定する
4. 「不適」と判定した列について、不適である理由を**型・意味論レベルで説明**する
   (本書の `metric_value` REAL の例のように)
5. 改修案を **CHECK 制約・JSONB・別テーブル** のいずれで実現するかを設計する

ポイントは **「自由形式 TEXT 列があるから書けば書ける」と妥協しない**こと。
監査クエリの信頼性は型強制と CHECK 制約に依存するので、慣習依存の自由テキストは
J-SOX 観点で「欠け」と扱う。

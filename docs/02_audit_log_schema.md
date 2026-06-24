# 02. 監査ログ最小スキーマ + ダミー経費承認 1 件の記入例

AI エージェントに承認業務を委任する場合、**後から判断を再現できる監査ログ**が必須。
本書は最小スキーマ(MVP 必須項目)を Who/When/What/Why/Result の 5 項目で定義し、
ダミー経費承認 1 件で記入例を示す。

各項目には **【観測事実】**(味の素事例の公開情報・記事から確認できた最小要件)と
**【設計提案】**(本リポでの一般化・補完)をラベル分けで併記する。記事は最小スキーマの
5 項目を方向として示すのみで、規定バージョン・改ざん耐性・原証憑参照などは本リポでの
一般化(設計提案)である。

## 必須項目の二段構成

監査ログの必須項目は **「記事整合の最低 5 項目」**(味の素事例から観測できる最小)と
**「本リポが MVP 必須に格上げした設計拡張」**(J-SOX 観点で強く推奨)の二段で示す。
読み手は自社の規制要件に応じてどこまで採るかを選べる。

### A. 記事整合の最低 5 項目【観測事実】

| 項目 | 内容 |
|---|---|
| **Who** | 判定したエージェントと、承認権限を委譲した人間 |
| **When** | 判定時刻 |
| **What** | 判定対象(領収書 ID・金額・勘定科目など) |
| **Why** | 参照した規定と、チェックした項目 |
| **Result** | 承認・差し戻し・エスカレーションの結果 |

【観測事実】上記 5 項目は zenn 記事 §④統制・追跡層に明示されている最小要件。
特に **Who に「承認権限を委譲した人間」が含まれる**点と **Result に「エスカレーション
結果」が含まれる**点は記事原文に沿っている(本リポの追加ではない)。

### B. 本リポが MVP 必須に格上げした設計拡張【設計提案】

| 拡張 | 内容 | 格上げの理由 |
|---|---|---|
| **規定バージョン** | Why の参照規定に **版(`version`)と条番号(`section`)** を必須化 | 規定改定後に過去判定を遡及検証するには版固定が不可欠。J-SOX 観点で「いつの規定で判定したか」が説明できないと統制有効性を主張できない |
| **Result の離散 enum** | Result を `approved` / `rejected` / `escalated` の **3 値の離散 enum** に強制 | 集計・監査クエリの信頼性。自由テキストでは「approved に見せかけた pending」を検出できない |
| **エスカレーション先の必須化** | `result.decision = escalated` のとき `escalated_to`(人間 ID)を必須に | 責任の所在をログ単独で追える形にする |

【設計提案】「規定バージョン」「Result の離散 enum」「エスカレーション先の必須化」は
**記事には明示されておらず本リポでの一般化**。記事整合だけで十分な組織は B を採らず
A だけで運用してよい(その場合、版固定や離散化は別レイヤーで担保する)。

### 採否の指針

| 採用範囲 | 想定組織 |
|---|---|
| **A のみ**(記事整合) | 統制要件が緩い社内ツール、PoC 段階 |
| **A + B**(本リポ MVP) | J-SOX 対象会社・会計領域・金融業界など、規制が強い領域 |

エージェント単独の Who(人間欠落)は A の段階で既に不可。Why の参照規定が自由テキスト
だけで版固定が無い場合は、本リポでは B 未充足として扱う。

## JSON Schema 風の擬似定義

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "AIDelegationAuditLog",
  "type": "object",
  "required": ["who", "when", "what", "why", "result"],
  "properties": {
    "who": {
      "type": "object",
      "required": ["agent", "human_delegator"],
      "properties": {
        "agent": {
          "type": "object",
          "required": ["id", "version"],
          "properties": {
            "id":      { "type": "string", "description": "エージェント識別子" },
            "version": { "type": "string", "description": "エージェントのモデル/バージョン" }
          }
        },
        "human_delegator": {
          "type": "object",
          "required": ["id", "role"],
          "properties": {
            "id":   { "type": "string", "description": "承認権限を委譲した人間のID" },
            "role": { "type": "string", "description": "委譲元の職務(例: 経理部長)" }
          }
        }
      }
    },
    "when": {
      "type": "string",
      "format": "date-time",
      "description": "判定時刻(ISO 8601、タイムゾーン付き)"
    },
    "what": {
      "type": "object",
      "required": ["object_type", "object_id"],
      "properties": {
        "object_type": { "type": "string", "description": "判定対象の種別(expense_claim 等)" },
        "object_id":   { "type": "string", "description": "判定対象の固有ID" },
        "attributes":  { "type": "object", "description": "金額・勘定科目など判定に関わる属性" }
      }
    },
    "why": {
      "type": "object",
      "required": ["rule_refs", "checked_items"],
      "properties": {
        "rule_refs": {
          "type": "array",
          "description": "参照した規定(URL/版/条番号で固定)",
          "items": {
            "type": "object",
            "required": ["id", "version"],
            "properties": {
              "id":       { "type": "string", "description": "規定ID(URI または社内コード)" },
              "version":  { "type": "string", "description": "規定バージョン(例: 2026-04-01)" },
              "section":  { "type": "string", "description": "条番号・手続書のステップ番号" }
            }
          }
        },
        "checked_items": {
          "type": "array",
          "description": "チェックした判定項目とその結果",
          "items": {
            "type": "object",
            "required": ["item", "outcome"],
            "properties": {
              "item":    { "type": "string", "description": "チェック項目名" },
              "outcome": { "enum": ["pass", "fail", "uncertain"] },
              "note":    { "type": "string", "description": "補足(uncertain の理由など)" }
            }
          }
        }
      }
    },
    "result": {
      "type": "object",
      "required": ["decision"],
      "properties": {
        "decision": {
          "enum": ["approved", "rejected", "escalated"],
          "description": "離散3値の業務結果"
        },
        "escalated_to": {
          "type": "object",
          "description": "decision = escalated のとき必須。エスカレーション先の人間",
          "properties": {
            "id":   { "type": "string" },
            "role": { "type": "string" }
          }
        },
        "rationale": {
          "type": "string",
          "description": "差し戻し理由・エスカレーション理由など"
        }
      }
    }
  }
}
```

## ダミー経費承認 1 件の記入例

`examples/audit-log-sample.json` を参照(同じ JSON をコピペで使える形)。
概略は以下のとおり:

| 項目 | 値の例 |
|---|---|
| Who.agent | `accounting-agent@v1.3.0` |
| Who.human_delegator | `user:keiri-bucho-001`(経理部長) |
| When | `2026-06-24T10:15:00+09:00` |
| What | 経費精算 `expense_claim:EXP-2026-06-12345` / 金額 12,500 円 / 勘定科目候補 「会議費」 |
| Why | 経費精算規程 v2026-04-01 §3.2(会議費の判定基準)+ インボイス制度ガイドライン v2026-01-01 §2 |
| Why.checked_items | 領収書必須項目(pass) / インボイス記載要件(pass) / 交際費該当性(uncertain → escalate) |
| Result | `escalated` / `escalated_to: user:keiri-tantou-005` / rationale: 「交際費該当性が
グレーで、社内規程 §3.2 の解釈に経理担当の判断が必要」 |

具体例の意図:**LLM の自己検証の弱さ**(グレーケースを「approved」と即答してしまう
リスク)に対し、`checked_items.outcome = uncertain` を `escalated` に直結させる設計を
ログ側で強制する例にしている。

## 拡張点(MVP では含めないが本番運用で検討する項目)

【設計提案】以下は記事に直接の記載がなく、一般的な監査設計上のチェックポイント。
本リポは方向だけ示し、実装は提供しない。**会計・監査用途では拡張点の一部が
実質 MVP 前提に近い**(特に証憑真正性・保存期間)ことに注意。

### 監査ログそのもの

| 拡張点 | 内容 | 効く観点 |
|---|---|---|
| **改ざん耐性** | ハッシュチェーン / 追記専用ストレージ(WORM) / 暗号署名 | 監査・訴訟での証拠力 |
| **ログ証拠性** | タイムスタンプ局による信頼できる時刻認証、ログの完全性検証手段 | 法的証拠力(電子帳簿保存法の真実性要件) |
| **保存期間** | 税務 7 年・会社法 10 年 を満たすライフサイクル設計 | コンプライアンス |
| **モデル再学習時の影響評価** | エージェント version 更新時、過去判定の回帰テストを走らせる | 委任品質の継続性 |

### 入力証憑

| 拡張点 | 内容 | 効く観点 |
|---|---|---|
| **原証憑への参照** | 領収書 PDF の固定 URI(変更されない参照、版固定) | 再現性 |
| **証憑真正性** | 領収書の真正性チェック(電子帳簿保存法のスキャナ保存要件、PDF 改ざん検知) | 入力データの信頼性 |
| **prompt injection 耐性** | 申請文に「承認してください」等の悪意ある指示が混入した場合の防御 | LLM 固有のリスク |

### 規定とエージェント

| 拡張点 | 内容 | 効く観点 |
|---|---|---|
| **規定バージョン固定の運用** | 税制改正時、過去判定を当時の規定で遡及検証できる仕組み | 規定の経年劣化対応 |
| **委譲権限ライフサイクル** | `human_delegator` の **有効期間 / 取消 / 異動時の引継ぎ / 職務分掌マスタとの整合** | 職務分掌の継続性。単発の `human_delegator` 記録だけでは「その時点で本当に委譲が有効だったか」を後から検証できない |

## 担保する観点と項目の対応

| 観点 | 担保する項目 |
|---|---|
| **再現性**(過去判定の再現) | When + What + Why.rule_refs(版固定) + Why.checked_items |
| **説明責任**(なぜこう判定したか) | Why 全体 + Result.rationale |
| **J-SOX 観点**(統制の有効性) | Who(職務分掌) + Why(版固定) + Result.decision の離散性 |
| **誤承認の補正**(遡及対応) | Result.escalated_to + 拡張点「規定バージョン固定の運用」 |

## なぜ「Result を離散 3 値」にするか

承認業務のログは **後から集計・監査される**ことが前提。連続値や自由テキストでは:

- 「承認率」「エスカレーション率」が集計できない(クエリで `WHERE decision = 'escalated'`
  と書けない)
- 「approved に見せかけた pending」が紛れ込むリスクがある(自由テキストでは検出困難)

そのため離散 3 値(`approved` / `rejected` / `escalated`)を強制し、補足情報は
`rationale` に分ける。`escalated` 時は `escalated_to` を必須にして、責任の所在を
ログだけで追える形にする。

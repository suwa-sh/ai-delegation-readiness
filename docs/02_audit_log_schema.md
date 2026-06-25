# 02. 監査ログを Who/When/What/Why/Result で設計する

## TL;DR

AI エージェントに承認業務を委任するなら、後から判断を再現できる **監査ログ**が
必須。最小スキーマは **Who/When/What/Why/Result** の 5 項目。本リポは 2 段階で
提供する: **A. 記事整合の最低**(味の素事例から観測できる最小)と
**B. J-SOX グレードの設計拡張**(規定バージョン固定・離散 Result enum・
エスカレーション先必須化)。

正本は [`schemas/audit-log.schema.json`](../schemas/audit-log.schema.json)
(JSON Schema Draft 2020-12)。

## When to use this

- 監査ログ DB の列定義を新規設計する
- 既存ログ基盤が J-SOX 観点で説明可能性を満たすか点検する
- AI エージェントが書き出すログを CI で検証したい
- 監査人やコンプライアンス担当に「設計が型安全であること」を示したい

## Quick use

サンプルログを **extended** レベルで検証:

```bash
bin/aidr validate-audit-log examples/audit-log-sample.json --level extended
# [OK] schema=audit_log_extended: valid
```

自社ログで試すなら、`examples/audit-log-sample.json` を雛形にして JSON を作り、
同じコマンドに食わせる。違反は JSON パスで報告される。

CI 連携例(GitHub Actions snippet):

```yaml
- run: pip install -r requirements.txt
- run: find audit-logs/ -name '*.json' | xargs -I {} bin/aidr validate-audit-log {} --level extended
```

## The minimum (A): 記事整合の最低 5 項目

【観測事実】Zenn 記事の④統制・追跡層に明示されている最小要件。

| 項目 | 内容 |
|---|---|
| **Who** | 判定したエージェント + **承認権限を委譲した人間**(両方必須) |
| **When** | 判定時刻(ISO 8601、タイムゾーン付き) |
| **What** | 判定対象(領収書 ID・金額・勘定科目など) |
| **Why** | 参照した規定と、チェックした項目 |
| **Result** | 承認・差し戻し・エスカレーションの結果 |

JSON Schema 上は [`$defs/audit_log_minimum`](../schemas/audit-log.schema.json) に
対応する。エージェント単独の Who(人間欠落)は最小段階で既に不可。

## The recommended extensions (B): J-SOX グレード

【設計提案】規制が強い領域(J-SOX 対象会社・会計領域・金融業界)では、A に加えて
以下を必須に格上げする。記事には明示されていないが、本リポでの一般化。

| 拡張 | 内容 | 理由 |
|---|---|---|
| **規定バージョン** | Why の参照規定に **版(`version`)と条番号(`section`)** を必須化 | 規定改定後に過去判定を遡及検証するには版固定が不可欠。J-SOX 観点で「いつの規定で判定したか」を説明できないと統制有効性を主張できない |
| **Result の離散 enum** | Result を `approved` / `rejected` / `escalated` の **3 値の離散 enum** に強制 | 集計・監査クエリの信頼性。自由テキストでは「approved に見せかけた pending」を検出できない |
| **エスカレーション先の必須化** | `decision = escalated` のとき `escalated_to`(人間 ID)を必須に | 責任の所在をログ単独で追える形にする |

JSON Schema 上は [`$defs/audit_log_extended`](../schemas/audit-log.schema.json) に
対応する。`audit_log_minimum` を `allOf` で内包しつつ Why と Result を厳格化している。

### 採否の指針

| 採用範囲 | 想定組織 |
|---|---|
| **A のみ** | 統制要件が緩い社内ツール、PoC 段階 |
| **A + B** | J-SOX 対象会社・会計領域・金融業界など、規制が強い領域 |

## Use the schema from your own code

```python
import json
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

schema = json.load(open("schemas/audit-log.schema.json"))
res = Resource.from_contents(schema, default_specification=DRAFT202012)
reg = Registry().with_resource(schema["$id"], res)
validator = Draft202012Validator(
    {"$ref": f"{schema['$id']}#/$defs/audit_log_extended"},
    registry=reg,
)
for err in validator.iter_errors(your_log_dict):
    print(err.json_path, err.message)
```

## Extension roadmap(本リポでは方向のみ提示、実装は提供しない)

【設計提案】会計・監査用途では一部が実質 MVP 前提に近い:

### 監査ログそのもの

| 拡張点 | 効く観点 |
|---|---|
| **改ざん耐性**(ハッシュチェーン / WORM / 暗号署名) | 監査・訴訟での証拠力 |
| **ログ証拠性**(信頼できる時刻認証・完全性検証) | 電子帳簿保存法の真実性要件 |
| **保存期間**(税務 7 年・会社法 10 年のライフサイクル) | コンプライアンス |
| **モデル再学習時の影響評価**(過去判定の回帰テスト) | 委任品質の継続性 |

### 入力証憑

| 拡張点 | 効く観点 |
|---|---|
| **原証憑への参照**(領収書 PDF の固定 URI) | 再現性 |
| **証憑真正性**(電帳法スキャナ保存要件、PDF 改ざん検知) | 入力データの信頼性 |
| **prompt injection 耐性**(申請文の悪意指示防御) | LLM 固有のリスク |

### 規定とエージェント

| 拡張点 | 効く観点 |
|---|---|
| **規定バージョン固定の運用**(税制改正時の遡及判定) | 規定の経年劣化対応 |
| **委譲権限ライフサイクル**(有効期間 / 取消 / 異動時の引継ぎ / 職務分掌マスタ整合) | 単発の `human_delegator` 記録では不足 |

## なぜ「Result を離散 3 値」にするか

承認業務のログは **後から集計・監査される**ことが前提。連続値や自由テキストでは:

- 「承認率」「エスカレーション率」が集計できない
- 「approved に見せかけた pending」が紛れ込むリスクがある
- typo・表記揺れで集計が壊れる(`metric_value REAL` への代入は型安全ではない)

そのため離散 3 値(`approved` / `rejected` / `escalated`)を CHECK 制約相当の
スキーマで強制する。

## References

- 正本: [`schemas/audit-log.schema.json`](../schemas/audit-log.schema.json)
- サンプル: [`examples/audit-log-sample.json`](../examples/audit-log-sample.json)(`escalated` ケース)
- CLI: `bin/aidr validate-audit-log --help`
- 関連 doc: [`01_four_layer_framework.md`](01_four_layer_framework.md) の④統制層 / [`04_agent_loop_audit_gap.md`](04_agent_loop_audit_gap.md)(自社運用基盤への適用例)
- 出典: [Zenn 記事 §④統制・追跡層](https://github.com/suwa-sh/pkm/blob/main/notes/zenn/articles/ajinomoto-accounting-agent_20260621.md)

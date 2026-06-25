# 03. 委任マトリクスで判定単位の領域を決める

## TL;DR

**2 軸**(検証可能性 × 正解定義可能性)を **各 3 採点質問**で測り、過半数 yes を
「高」とする二値判定。(高 × 高)= 🟢 委任 OK、(高 × 低)or (低 × 高)= 🟡 LLM 推論補助、
(低 × 低)= 🔴 人間に残す。境界事例(2/3 yes)は委任 OK でも `escalated` 比率が
上がる前提で設計する。

正本は [`definitions/delegation-matrix.yaml`](../definitions/delegation-matrix.yaml)。

## When to use this

- 業務リストの 1 判定単位を、AI 委任 / LLM 補助 / 人間最終 のどれに割り当てるか決めたい
- 「これは AI に任せて大丈夫?」の社内議論に客観的な採点根拠が欲しい
- 既存の委任設計を見直す(AI モデル更新時 / 税制改正時)

## Quick use

```bash
bin/aidr score-delegation examples/judgments/sample-judgments.yaml
```

サンプル 5 判定の出力(抜粋):

```
[GREEN ] receipt_mandatory_items_check: GREEN  (verifiability=high(3/3), answer_definability=high(3/3))
[GREEN ] invoice_scheme_compliance:     GREEN  (verifiability=high(3/3), answer_definability=high(3/3))
[GREEN ] entertainment_expense_judgment:GREEN  (verifiability=high(2/3), answer_definability=high(2/3))
[RED   ] new_hire_decision:             RED    (verifiability=low(0/3),  answer_definability=low(0/3))
[YELLOW] discriminatory_language_detection: YELLOW (verifiability=high(2/3), answer_definability=low(1/3))
```

自社判定リストを `examples/judgments/sample-judgments.yaml` から複製して採点する。

## The 2 axes

### 検証可能性(verifiability)

判定の正誤を後から機械的に検証できるかを問う。

| 採点質問 | 答え yes ならポイント |
|---|---|
| V1: 第三者が同一入力で同じ判定を採点できるか | 1 |
| V2: 正誤判定に必要な情報が入力データ + 規定文書だけで揃うか(個人の経験に依存しないか) | 1 |
| V3: 判定結果を機械的に再実行可能なテストに落とせるか | 1 |

**2 つ以上 yes => 高**、それ以下は低。

### 正解定義可能性(answer_definability)

判定の「正解」を一意に決められるかを問う。

| 採点質問 | 答え yes ならポイント |
|---|---|
| A1: 判定の根拠となる規定の条番号(または SOP のステップ番号)を引けるか | 1 |
| A2: 判定の妥当性がケース個別の文脈ではなく規定で決まるか | 1 |
| A3: ベテランの暗黙知に頼らず判定理由を文書化できるか | 1 |

**2 つ以上 yes => 高**、それ以下は低。

## The region map

|   | **正解定義可能性 高** | **正解定義可能性 低** |
|---|---|---|
| **検証可能性 高** | 🟢 **委任 OK**(エージェント最終判定) | 🟡 **LLM 推論補助**(LLM 候補出し → 人間最終) |
| **検証可能性 低** | 🟡 **LLM 推論補助**(LLM 叩き台 → 人間判定) | 🔴 **人間に残す**(LLM は参考意見) |

| 領域 | 行動指針 |
|---|---|
| 🟢 委任 OK | 監査ログの Result を `approved` / `rejected` / `escalated` の離散 enum で記録。`uncertain` ケースは `escalated` に直結 |
| 🟡 LLM 推論補助 | LLM が候補を出し、**人間が最終判定**。最終判定者を Who に記録し、LLM の貢献は Why に「補助証拠」として記録(権威ではなく) |
| 🔴 人間に残す | 人間が判定。LLM 出力は参考のみ、決定権限ではない。LLM 使用も透明性のため Why に残す |

## Worked examples

`definitions/delegation-matrix.yaml` の `examples` に 9 件登録済み。
味の素事例 3 件 + コーディング委任 2 件 + 倫理・採用・ポリシー策定など。

| 判定 | 検証可能性 | 正解定義可能性 | 領域 |
|---|---|---|---|
| 領収書必須項目チェック(味の素事例) | 高(3/3) | 高(3/3) | 🟢 委任 OK |
| インボイス制度準拠チェック(味の素事例) | 高(3/3) | 高(3/3) | 🟢 委任 OK |
| 税務上の交際費判定(味の素事例) | 高(2/3、境界) | 高(2/3、境界) | 🟢 委任 OK(`escalated` 比率高) |
| コーディング委任(機械的リファクタ) | 高(3/3) | 高(2/3、境界) | 🟢 委任 OK |
| コーディング委任(新規アーキテクチャ設計) | 低(1/3) | 低(1/3) | 🔴 人間に残す |
| 倫理判断(差別表現検出) | 高(2/3、境界) | 低(1/3) | 🟡 LLM 推論補助 |
| 採用面接の合否判定 | 低(0/3) | 低(0/3) | 🔴 人間に残す |
| 新規ポリシー策定 | 低(0/3) | 低(0/3) | 🔴 人間に残す |
| 経費勘定科目候補提示(最終人間) | 高(2/3、境界) | 高(2/3、境界) | 🟡(運用方針で 🟢→🟡 降格) |

【観測事実】記事から観測できるのは「ベンダーが委任対象として 3 判定を選定し、規定に基づく
検証可能性を公表した」事実のみ。

【設計提案】上表の象限分類は **本マトリクスへの当てはめ**(本リポでの設計解釈)。
他の例(コーディング委任・倫理判断・採用面接など)は完全に本リポでの一般化。

## When to re-score(見直しトリガー)

委任 OK の判定でも、以下のイベント時には再採点が必要:

| トリガー | リスク | 対応 |
|---|---|---|
| **税制改正・新会計基準** | 規定が陳腐化、過去判定が現行規定とずれる | 規定バージョンを固定して遡及検証 |
| **AI モデル変更**(バージョン更新) | 同一入力に対する判定がリグレッション | 過去ログから回帰テストセットを作って差分確認 |
| **業務範囲の追加**(新申請種別 / 新取引先) | 標準化が追いついていない領域に AI が踏み込む | ①〜④ 層を再点検後に委任 |
| **誤承認の発見** | ④統制層の欠けが露出 | 補正フロー → ログ追記 → 採点質問の見直し |

## References

- 正本: [`definitions/delegation-matrix.yaml`](../definitions/delegation-matrix.yaml)
- サンプル入力: [`examples/judgments/sample-judgments.yaml`](../examples/judgments/sample-judgments.yaml)
- CLI: `bin/aidr score-delegation --help`
- 関連 doc: [`01_four_layer_framework.md`](01_four_layer_framework.md) の③委任範囲層 / [`02_audit_log_schema.md`](02_audit_log_schema.md)

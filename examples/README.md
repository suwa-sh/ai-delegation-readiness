# examples/ — サンプルの歩き方

このディレクトリのサンプルは、架空の会社 **ミドリ精機株式会社** の物語でつながっています。
読者は 1 つの会社の状況を追いかけるだけで、本線 6 ステップ + 拡張(overlay)の全コマンドを
体験できます。

## ミドリ精機株式会社(架空)のプロファイル

**このプロファイルが物語の正本です**。docs や README はここへの参照だけを置き、
設定を二重に書きません。

| 項目 | 設定 |
|---|---|
| 会社 | ミドリ精機株式会社(**架空の会社です**。実在の企業・事例とは関係ありません) |
| 業種・規模 | 産業機械部品の中堅製造業。従業員約 800 名 |
| 統制環境 | 上場企業のグループ会社で J-SOX(内部統制報告制度)の対象 |
| 主人公 | 経理部。経営会議で「経理業務に AI を活用せよ」と指示を受けた |
| 物語の始まり | 「何から手を付ければよいか」をタスク群のスクリーニングで決めるところから始まる |

### 物語の時間軸(重要)

ミドリ精機の物語は **一直線に成功しません**。診断で一度 BLOCK(委任不可)になり、
不足を改善してから次へ進みます。これは「診断はゲートであり、BLOCK のまま先へ
進んではいけない」というこのツールの中心思想を体験するための設計です。

```text
1 スクリーニング   経理・営業事務・設備保全のタスク群を 4 類型に振り分ける
2 初回診断        経費精算承認業務を診断 → L1/L2/L4 に穴 → BLOCK(ここで一度止まる)
   ↓ 規定の整備・判定ロジックの構造化・統制層の設計を実施
2' 再診断         改善後の経費精算承認業務 → PASS(ようやく次へ進める)
3 判定の振り分け   経費の判定単位を 委任 OK / LLM 補助 / 人間 に振り分ける
4 タスク契約      委任する経費チェックタスクの契約(意図・境界・証跡・採点者)を点検する
5 監査ログ        運用開始後、エージェントが書いたログを検証する
6 パッチ受入      AI 生成差分の所有コスト・テスト完全性・高リスク境界を検査する
拡張(任意)      ミドリ精機の独自ルールを overlay で追加する
```

## サンプル一覧(本線)

| 物語のステップ | コマンド | サンプル |
|---|---|---|
| 1 スクリーニング | `aidr screen-transition` | [`task-groups/sample-task-groups.csv`](task-groups/sample-task-groups.csv) |
| 2 初回診断(BLOCK) | `aidr check-readiness` | [`business/sample-expense-approval.csv`](business/sample-expense-approval.csv) |
| 2' 再診断(PASS) | `aidr check-readiness` | [`business/sample-expense-approval-after.csv`](business/sample-expense-approval-after.csv) |
| 3 判定の振り分け | `aidr score-delegation` | [`judgments/sample-judgments.csv`](judgments/sample-judgments.csv) |
| 4 タスク契約(充足 / 委任不可) | `aidr check-task-contract` | [`task-contracts/sample-green.csv`](task-contracts/sample-green.csv) / [`task-contracts/sample-red-ai-judge.csv`](task-contracts/sample-red-ai-judge.csv) |
| 5 監査ログ | `aidr validate-audit-log` | [`audit-log-sample.json`](audit-log-sample.json) |
| 6 パッチ受入(GREEN / YELLOW / RED) | `aidr check-patch-ownership` | [`patches/sample-cheap-green.csv`](patches/sample-cheap-green.csv) / [`patches/sample-never-cheap-yellow.csv`](patches/sample-never-cheap-yellow.csv) / [`patches/sample-hollow-green-red.csv`](patches/sample-hollow-green-red.csv) |
| 拡張(任意) | `aidr check-overlay` → 各コマンド `--overlay` | [`overlays/sample-company/extra-rules.yaml`](overlays/sample-company/extra-rules.yaml) |

補足:

- **各サンプル CSV のメモ列には「ミドリ精機ではこういう状況だから yes / no」という回答理由を記載しています**。
  問いだけでは想定回答を読み取れないため、メモが各質問の生きた回答例になります。
  before/after ペア(経費精算の BLOCK→PASS など)では、before の no メモが「何が欠けているか」、
  after の対応する yes メモが「改善: 何を整備したか」を書いており、**2 つの CSV のメモを見比べる
  だけで何がどう変わって判定が動いたかが読めます**(構成比較のサンプル群も同じ流儀です)
- 自社ルール overlay を適用して再診断する場合は、追加質問への回答込みの
  [`business/sample-expense-approval-after-with-overlay.csv`](business/sample-expense-approval-after-with-overlay.csv)
  を使います(CSV は typo 防止のため、適用していない overlay の質問 id を
  受け付けません。overlay あり・なしで入力ファイルを分けています)
- ステップ 3 のサンプルには、経費の 3 判定に加えて **境界比較のための 2 判定**
  (採用面接の合否・差別表現の検出)が入っています。経費以外の判定にも同じ物差しが
  使えることを示す比較例です。
- AI エージェントからサンプルと同じ流れを使う例は [`skills/`](skills/) にあります
  (Claude Code skill のラッパー 6 種)。

## 運用ループ(拡張・任意)

ステップ 6(パッチ受入)の GREEN/YELLOW/RED は人間が採否を決める最低条件です。
その採否を決定記録として残し、月次で振り返るループが `docs/12` です。本線 6 ステップは
このループがあってもなくても変わりません。

| コマンド | サンプル |
|---|---|
| `aidr check-patch-ownership --emit-decision-record` | [`patches/sample-cheap-green.csv`](patches/sample-cheap-green.csv) → 決定記録を追記 |
| `aidr summarize-patch-decisions` | [`patch-decisions/sample-midori-2026-07.jsonl`](patch-decisions/sample-midori-2026-07.jsonl)(ミドリ精機・7 月分) |

## 組織リスクアーキテクチャ(拡張・任意)

経理エージェントを多段自律実行に広げたミドリ精機が、「委任を受けて運用する組織の側」に
失敗を検知・抑制・エスカレーションする体制があるかを採点する拡張です(`docs/13`)。
サンプルは AI-native 帯 + 境界シナリオが Low + boundary channel owner 不在で
**BLOCK** になる回答例です。

| コマンド | サンプル |
|---|---|
| `aidr assess-risk-architecture` | [`business/sample-risk-architecture.csv`](business/sample-risk-architecture.csv)(組織側の体制採点 → BLOCK) |

## スプレッドシートで記入する

サンプルはすべて CSV(UTF-8 BOM 付き。Excel でそのまま開けます)です。
自社の記入は次の流れが最短です。

1. `aidr init --target <対象> --format csv > my-<対象>.csv` でテンプレートを生成する
2. Google Sheets(ファイル → インポート)か Excel で開く
3. 問いの隣の 回答 セルに `yes` / `no`(はい / いいえ でも可)を記入する。
   タスク群・判定を増やすときは**列を複製**する(横持ち形式)
4. CSV 形式でエクスポートし、`aidr <コマンド> my-<対象>.csv` に渡す

**YAML でも同じ内容を書けます**(エンジニア / CI 向け)。記入例は
[`business/sample-expense-approval.yaml`](business/sample-expense-approval.yaml)
(CSV 版との双子。同値性はテストで固定)の 1 本だけ残しています。

## 応用例(ミドリ精機の別部門)

特定ドメイン向けの拡張(ドメイン overlay)も、読者が 1 社だけを想定すれば済むよう
**ミドリ精機の別部門**を題材にしています。本線の物語(経理部の時間軸)には含まれない
独立したエピソードです。実在事例の分析(味の素グループ)だけは実名のまま応用例に置きます。

| 応用例 | 題材 | サンプル |
|---|---|---|
| 組織 readiness の実事例 | 味の素グループの分析記事由来。業務は整っているが組織が未成熟なチーム | [`business/ajinomoto-discovery-team.csv`](business/ajinomoto-discovery-team.csv) / [`overlays/organization-readiness-ajinomoto.yaml`](overlays/organization-readiness-ajinomoto.yaml) |
| 高責任ドメイン(知財/法務/薬事) | ミドリ精機 知財部門。成立条件 4 つのハードゲート層 L5 + 慎重側の閾値強化 | [`business/sample-ip-agent-readiness.csv`](business/sample-ip-agent-readiness.csv) / [`judgments/sample-ip-judgments.csv`](judgments/sample-ip-judgments.csv) / [`overlays/high-stakes-domain/`](overlays/high-stakes-domain/) |
| 内製化の判断責任 | ミドリ精機 DX推進室。「どの判断責任を社内に残すか」を並列軸で採点 | [`business/sample-insourcing-readiness.csv`](business/sample-insourcing-readiness.csv) / [`overlays/insourcing-judgment/`](overlays/insourcing-judgment/) |
| エージェント権限設計 | ミドリ精機 顧客サポート部門。能力軸と同意軸を独立した並列軸 2 本で採点 + 境界要素の閾値強化 | [`business/sample-agent-authz-readiness.csv`](business/sample-agent-authz-readiness.csv) / [`task-contracts/sample-agent-authz-contract.csv`](task-contracts/sample-agent-authz-contract.csv) / [`overlays/agent-authorization/`](overlays/agent-authorization/) |
| アカウント常駐・無人実行 | ミドリ精機 営業部門。実行面軸と監督面軸を独立した並列軸 2 本で採点し、同一部門条件で 3 つの実行基盤(Cowork / ChatGPT tasks / 自前 Kestra)を見比べる | [`business/sample-unattended-cowork.csv`](business/sample-unattended-cowork.csv) / [`business/sample-unattended-chatgpt-tasks.csv`](business/sample-unattended-chatgpt-tasks.csv) / [`business/sample-unattended-selfhosted.csv`](business/sample-unattended-selfhosted.csv) / [`overlays/account-resident-execution/`](overlays/account-resident-execution/) |
| 長時間稼働の軌跡単位統制 | ミドリ精機 情報システム部門。強制力軸(非相殺: 1 問 no で BLOCK)と監視軸の並列軸 2 本で採点し、同一業務のまま「基盤付属ゲートを信頼した構成」と「外部 admission point 構成」を見比べる | [`business/sample-trajectory-framework-gate.csv`](business/sample-trajectory-framework-gate.csv) / [`business/sample-trajectory-chokepoint.csv`](business/sample-trajectory-chokepoint.csv) / [`overlays/trajectory-oversight/`](overlays/trajectory-oversight/) |
| 委任台帳の責任とコスト | ミドリ精機 経理部。責任軸とコスト軸の並列軸 2 本で台帳の能力(記録・取り出し・集計・検知)を採点し、同一の委任群のまま「従来チケット運用のまま構成」と「説明文テンプレート + 抽出スクリプト構成」を見比べる(方式でなく能力が採点される実例) | [`business/sample-ledger-scattered.csv`](business/sample-ledger-scattered.csv) / [`business/sample-ledger-managed.csv`](business/sample-ledger-managed.csv) / [`overlays/delegation-ledger/`](overlays/delegation-ledger/) |
| パッチ受入の決定記録(機能デモ) | 既存の回顧検証 fixture(実コミット 5 件)から生成した `summarize-patch-decisions` の入力例。**運用実績の証拠ではありません**(全件マージ済みコミットから選ばれているため破棄率 0% は選択条件からほぼ自明で、5 件中 2 件は別リポジトリ pkm のコミットです) | [`patch-decisions/demo-from-fixtures.jsonl`](patch-decisions/demo-from-fixtures.jsonl) |

## definitions/ 内の examples について

正本定義(`definitions/*.yaml`)の中にも `examples` group があります(領収書チェック・
コーディング委任・看護・配管工など)。これらは **各分類の判定基準を例示する
リファレンスケース**で、ミドリ精機の物語とは独立です。日本語化・物語統一の対象外として
原文のまま維持しています(多くの例には confidence ラベル
= observed_fact / design_proposal が付いています。ラベルの無い一部の例は
定義追加時の記載のままです)。

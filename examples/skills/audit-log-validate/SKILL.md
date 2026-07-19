---
name: audit-log-validate
description: Validate an AI delegation audit log JSON against schemas/audit-log.schema.json. Picks the minimum (article-aligned) or extended (J-SOX-grade) schema level per the user's intent, runs the aidr validator, and reports violations by JSON path. Use when the user wants to check whether an audit log meets the schema, or asks to "validate the log" or "check this audit log."
---

# audit-log-validate

監査ログの JSON ファイルを本リポジトリのスキーマで検証し、違反を平易な言葉で
説明します。`aidr validate-audit-log` の薄いラッパーです。

## いつ使うか

- ユーザーが監査ログ JSON(またはその内容)を渡して、スキーマに適合するか
  確認したいとき
- 監査ログの書き出し処理を設計中で、minimum / extended どちらのスキーマを
  通るか素早く確認したいとき
- J-SOX グレードの検証を求められたとき(→ `extended` を使う)

## ユーザーから受け取るもの

- 監査ログ JSON のパス(または内容)
- 検証するスキーマレベル: `minimum`(既定・記事整合)または
  `extended`(J-SOX グレード: 規定バージョン固定・離散 decision enum・
  escalated 時の escalated_to 必須)

## 手順

1. どちらのスキーマレベルで検証するかをユーザーに確認する。J-SOX・監査・
   コンプライアンス・「本番」という言葉が出たら `extended` を既定にし、
   理由を添える。

2. ユーザーがパスでなく JSON の中身を貼った場合は
   `/tmp/aidr-log-<timestamp>.json` に書き出す。

3. `bin/aidr validate-audit-log <path> --level <level> --format json` を実行し、
   stdout と exit code を取得する。

4. exit code が 0 なら、使ったレベルを添えて 1 行で成功を報告し、次の行動を
   提案する(例: 「取り込み可能」「次は `extended` で検証」)。

5. 違反があれば、トップレベルのフィールド(who / when / what / why / result)で
   グループ化し、JSON Schema のメッセージを平易な説明に訳す:
   - 「result.decision must be one of approved/rejected/escalated」→
     「decision は離散 enum が必須。自由テキストを除去する」
   - 「why.rule_refs[0]/version required」→「extended スキーマは判定時点の
     規定バージョン(日付かタグ)の固定を要求する」
   - 「result/escalated_to required」→「decision が `escalated` のときは
     エスカレーション先(人間)の記録が必須」

6. 具体的な次の一手で締める:「この N 項目を直して、`aidr validate-audit-log` を
   再実行して確認してください」。

## 出力の作法

- 結論(`[OK]` または `[NG] N violations`)を先頭に置く。
- JSON パスは原文どおり示す(ユーザーが自分のログを grep できるように)。
- 監査ログの中身をユーザーに言い換えて返さない(自分の JSON は読める前提)。

## 失敗時の扱い

- ファイルが無い: パスを伝えて止まる。推測しない。
- JSON 構文エラー: パーサのエラーを提示して止まる。意図を推測しない。
- レベルの選び間違い(自由テキストの decision を `minimum` で検証など):
  検証は通るが、minimum は意図的に緩いスキーマである旨を警告する。

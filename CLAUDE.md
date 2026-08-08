# CLAUDE.md

## このリポジトリの正体

**ai-delegation-readiness** — 高リスクな定型業務を AI に委任するための
**診断ツール + 拡張可能なフレームワーク**。MIT の OSS。

味の素グループ(AFS)の経理 AI エージェント事例から再現可能な骨格(4 層フレーム +
委任マトリクス + 監査ログ最小スキーマ)を抽出し、

- **機械可読の正本**(`definitions/` の YAML / `schemas/` の JSON Schema)
- **診断ツール**(`bin/aidr` + `src/adr/`)
- **AI エージェント連携サンプル**(`examples/skills/`)
- **AI 生成パッチの所有コスト受入ゲート**(`definitions/patch-ownership.yaml` / `aidr check-patch-ownership`)

の 4 点セットとして提供する。各社は **オーバーレイ**(`examples/overlays/` 参照)で
自社固有の規定・閾値・追加チェック項目を足してフォークではなく **追加運用**できる。

## 正本の所在(二重保持しない)

| 種類 | 正本パス | 役割 |
|---|---|---|
| ルール定義 | `definitions/*.yaml` | 4 層フレーム / 委任マトリクスの構造的正本 |
| データ契約 | `schemas/audit-log.schema.json` | 監査ログの JSON Schema(`$defs/audit_log_minimum` と `audit_log_extended`) |
| 説明書 | `docs/*.md` | 上記の解説。**定義の値は二重保持しない**(リンクで参照する) |
| 動く入口 | `bin/aidr` / `src/adr/` / `examples/` | 上記を消費する CLI と入力サンプル |

定義値を変えるときは **必ず `definitions/` か `schemas/` の正本を編集**し、
doc は説明としてリンクし直す。

パッチ受入ゲートの固定契約:

- 全 question は明示 yes/no。曖昧・欠落・未知 ID・重複 YAML key は exit 3
- `hollow_green` は `H1 AND (H2 OR H3)`。overlay で変更不可
- `never_cheap` が 1 件でも真なら GREEN 禁止。高リスク統制不足は RED
- 証拠参照は content-addressed 形式のみ。CLI は参照先を取得しない
- 回顧 fixture に raw diff、secret、存在しなかった test/review 証拠を入れない

## オーバーレイのマージ規則(一貫性の保護)

各社のオーバーレイで可能なのは以下の 2 操作のみ:

- **`add`**: 配列要素(`questions` / `examples` 等)の追加。**既存要素の上書き・削除は不可**
- **`strengthen`**: 数値閾値の **強化方向のみ**(緩和は不可)

違反は `aidr check-overlay <path>` で即検出される。**変更を加えるときは必ず
`check-overlay` を回す**。

### `extension_points` 宣言はエンジンがランタイムで解釈する(overlay.py は存在しない)

`definitions/*.yaml` の `extension_points` ブロックは **読み手と AI エージェント向けの
self-documenting** であると同時に、**マージ規則の実体**でもある。マージロジックは
別配布の pip パッケージ `overlay-scoring-skeleton`(`import overlay_scoring`)に切り出され、
`_parse_extension_points()` が **宣言から add/strengthen 規則を導出**する。旧 `src/adr/overlay.py`
のハードコード分岐は撤去済みで、このリポには存在しない。

**これがあるため**: 新しい定義(例 `task-contract.yaml`)を追加しても、`extension_points` を
宣言すればエンジンがコード追加なしでマージする。定義側の変更に追従すべき「ハードコード分岐」は
無い。overlay 規則の検証は `tests/test_overlay.py`(定義ごとの add/strengthen/weaken/非拡張拒否)
が担う。エンジン本体の pin は `pyproject.toml` の `overlay-scoring-skeleton==<ver>`。

## doc の段階的開示テンプレ

すべての doc は以下の順で構成する(テクニカルライティング):

1. **TL;DR**(20〜30 秒で何が分かるか。**読者の問いから書き起こし、軸名・閾値などの
   仕組み用語を並べない**)
2. **前提**(知識ゼロの読者向け。2〜4 項目 + docs/00 への戻り導線 + 物語上の位置。
   専門用語はここか初出箇所で 1 行説明する)
3. **When to use this**(誰が・どんな状況で読むか)
4. **Quick use / 事例**(ミドリ精機の事例でコマンド → `入力: <ファイルへのリンク>` →
   出力 → **出力の 1 行ずつの読み方**の順に示す)
5. **Concept**(本論。**外側から内側の順**で掘り下げる:
   ①出力・結果の意味 → ②仕組み(軸・決定木など)→ ③質問と閾値の詳細 →
   ④運用指針 → ⑤出典と限界 → ⑥■構造 / ■データ(機械可読の内側)→ ⑦拡張。
   仕組みの説明から始めない — 読者は結果の意味を知る前に構造を読まされると迷子になる)
6. **References**(関連 doc / 正本ファイル / 出典 / `次のステップ:` 導線)

補足の書き方: **見出し・ラベル・リンク行に説明句を重ねない**。
「前提(これだけ知っていれば読めます)」でなく「前提」、
「入力: <リンク>(問いと回答が 1 ファイルで読めます)」でなく「入力: <リンク>」、
「物語の前後: 前のステップは…次のステップは…」でなく「次のステップ: <リンク>」。
繰り返し現れる注記(text_ja の所在など)は README で 1 回説明し、各 doc では繰り返さない。

書き方の原則:

- **タスク指向見出し**(「4 層フレーム」より「対象業務が委任に耐えるかを点検する」)
- **能動・短文**(「〜することができます」→「〜する」「〜を実行する」)
- **箇条書きの並列性**(同じ文法構造で揃える)
- **逆ピラミッド**(結論を先、根拠を後)
- **観測事実 / 設計提案 のラベル分け**(味の素事例の公開情報から確認できる範囲と、本リポでの一般化を明示的に分ける。④統制層は記事の公開情報が薄いため設計提案が大半になる)

## 編集規約

- **本文は日本語**(タイトル・識別子・コード断片の言語は対象に合わせる)。
  英語 README(`README.md`)は canonical entry、日本語(`README.ja.md`)が原典
- 図は **mermaid** で書き、追加・変更したら `npx md-mermaid-lint <ファイル>` で検証
- 章立てを変えるときは 4 層フレーム(`definitions/four-layer.yaml`)との対応関係が
  崩れないか確認する
- **主要サンプルはミドリ精機(架空)の物語に統一する**。物語の正本は
  `examples/README.md`(会社プロファイル + 本線 6 ステップ + 拡張の対応表)。
  実事例由来・ドメイン特化のサンプルは物語に混ぜず「応用例」として同 README の
  応用章に載せる。**definitions 内の examples group はリファレンスケース**
  (各分類の判定基準の例示)であり、物語統一・日本語化の対象外
- **質問文は `text`(英)と `text_ja`(日)を併記する**。text_ja の完全性は
  `tests/test_definitions_i18n.py` が検証する
- **同梱 examples の入力は CSV が主、YAML は 1 例だけ**(`business/sample-expense-approval.yaml`
  = CSV 版との双子。結果同値は `tests/test_io_input.py` が固定): CSV は
  「`aidr init --format csv` で生成した体」で書き、質問列 = text_ja の複製。ドリフトは
  `tests/test_init_input.py` のドリフト検査が検出する。
  **全回答行のメモ列に、シナリオの具体的な状況描写(想定回答の理由)を書く**。
  書き方の正本は `examples/README.md` の「メモ列の書き方」節と「システム環境」表
  (問いの言い換え禁止 / 部分充足の描写 / ペア対応。overlay・サンプル追加時も必須)。
  **CSV は未知の質問 id を拒否する**(typo 防止)ため、overlay の追加質問に回答する例は
  別ファイル(`*-with-overlay.csv`)に分ける。変換の同値性は
  `tests/fixtures/normalized_inputs.json`(変換前 YAML の正規化 dict)が正本

## 変更完了チェックリスト

変更を完了と報告する前に、次を順に確認する。

1. **対象リポジトリ**: `git rev-parse --show-toplevel`、branch、`git status --short` を確認し、
   別リポジトリやユーザーの既存差分を巻き込んでいない
2. **本線の横断整合**: 本線のステップ、主要機能、CLI subcommand を追加・削除した場合、
   `README.md` / `README.ja.md` / `docs/00_overview.md` / 各 `docs/NN` の前提と次ステップ /
   `examples/README.md` / CLI help・一覧 / `examples/skills` を更新する。ステップ数、列挙数、
   目次、リンクの古い表記を `rg` で検索する
3. **正本と複製**: `definitions/` / `schemas/` を先に更新し、doc・CSV 質問列・サンプルは
   正本への参照またはドリフトテストで追従させる
4. **規約と検証**: 新規・変更テストが命名 / AAA / parametrize ID 規約を満たすことを
   `tests/test_test_conventions.py` で検査する。pytest、`qlty check`、文書リンク検査、
   変更した mermaid の lint を実行する
5. **公開状態**: version や README の配布タグを先に更新した場合、利用者向け README にも
   pending を明示する。対応タグ・Release・image の実体確認が終わるまでは **release pending** と
   報告し、version 更新をリリース完了と扱わない。実体確認後に pending 表示を外す

## 更新運用

- 味の素事例の④統制層は公開情報が薄い。続報(誤承認補正フロー・人間最終承認の置き場所・
  規定バージョン管理運用)が出た時点で `definitions/four-layer.yaml` の case_evidence と
  `docs/02` を更新する
- 監査ログの「拡張点」(改ざん耐性・保存期間・原証憑参照・規定バージョン固定)は
  読者から実装提案が来た時点で `schemas/audit-log.schema.json` に追加する
- 既存ログ基盤の点検メモ(`docs/07`)は、ある自社運用エージェント基盤を題材にした
  worked example。他者は同じ手法を自社環境に当てる(冒頭の 6 ステップ参照)
- **移行 4 類型スクリーニング**(`definitions/transition-screening.yaml` / `docs/01`)の職種
  worked example は米国版フレームの公表例からの当てはめ(design_proposal)。OpenAI が EU 版の
  職種リスト詳細を公開したら `examples` group と docs/01 の職種例を更新する
- **ドメイン overlay**(`examples/overlays/high-stakes-domain/`)は base を変えずに
  高責任専門業務(知財/法務/薬事)向けの L5 ゲート層・閾値強化を足す実例(`docs/08`)。
  新ドメインを足すときは同じ形(overlay ディレクトリ + サンプル入力 + docs/NN)を踏襲する。
  case_evidence の出典が更新されたら overlay 側も追随する

## テスト規約

pkm の新規リポ規約([`p3-new-repo-claude-md.md`](https://github.com/suwa-sh/pkm) のテスト規約節)を
Python / pytest 向けに翻案したもの。**新規・変更するテストは必ずこの形で書く**。

- **AAA パターン**: テスト本文を `# Arrange` `# Act` `# Assert` のコメントで 3 区画に分ける
  (準備・実行・検証を混ぜない)。準備が不要なテストは `# Arrange` を省いてよい。
  空の区画にコメントだけ置かない
  - `pytest.raises` のテストは Act と Assert が同一文になるので `# Act & Assert` に統合する
- **テスト関数名**: `test_{テスト対象}_{XXXの場合}_{YYYであること}` 形式
  - テスト対象 = 関数・メソッド名(英語のまま)、条件と期待は日本語
  - 例: `test_score_overlayで閾値を強化した場合_境界例がyellowに落ちること`
  - **テスト対象は実際に呼んでいる関数に合わせる**。ファイル名から機械的に決めない
    (`test_score_delegation.py` の中で `apply_overlays` を検証するテストは `test_apply_overlays_...`)
  - **CLI を実プロセス起動するテストは `aidr_<subcommand>` を対象にする**
    (例: `test_aidr_check_readiness_...`)。同名の Python 関数のテストと混ざらないようにするため
  - `test_` 接頭辞は pytest の既定収集規則に合わせるため必須(`python_functions` は設定しない)
  - 識別子に使えない記号(`「」` 等)は名前に入れない
  - `@pytest.mark.parametrize` の `ids` も「{XXXの場合}_{YYYであること}」に合わせる
- **1 テスト 1 主張**: 条件と期待が 2 つ以上あるなら関数を分ける。名前が書けないテストは
  スコープが広すぎる合図
- **docstring は「なぜそう振る舞うべきか」を書く**。関数名で言い切れる「何を確認するか」は
  繰り返さない(名前と docstring の二重保持を避ける)
- **I/O 境界は実体でテストする**(一時ディレクトリ・実ファイル・実プロセス)。モックで
  誤魔化さない。CLI は `subprocess` で実際に起動して exit code を確認する
- **バグ修正は再現テストを先に書く**
- **doc からテストを参照するときは関数名でなくファイル単位にする**
  (`tests/test_init_input.py` のドリフト検査が検出する、のように書く)。
  テスト名を `::` 付きで書くと改名のたびに doc が壊れる — 実際に本規約への移行で 2 度陳腐化した
- **リファクタで出力が変わらないことを主張するテストは、出力そのものを固定する**
  (前後の diff を取る等)。「例外が出ないこと」だけでは退行を捕まえられない
- 命名・AAA・parametrize ID は [`tests/test_test_conventions.py`](tests/test_test_conventions.py) で
  機械検査する。規約を文章に追加しただけで完了にせず、検査も同じ変更で更新する

`tests/` は qlty の解析対象外(`.qlty/qlty.toml` の `exclude_patterns`)。pytest は assert で
テストを書き、smoke テストで CLI を実プロセス起動するため、bandit の指摘は所見でなくノイズになる。
出荷コード側は全面解析のままで `qlty check` 指摘ゼロを維持する。

## リリース手順(タグ push だけ。Release は手動作成しない)

`.github/workflows/release.yml` が **`v*` タグの push を契機に** マルチアーチ
イメージ(GHCR)push と **GitHub Release 作成(`gh release create --generate-notes`)を自ら行う**。

- **リリースは `git tag -a vX.Y.Z` + `git push origin vX.Y.Z` だけで完結する。**
  手動で `gh release create` を打たない — workflow の Release 作成ステップと衝突し
  HTTP 422 "Release.tag_name already exists" で release ジョブが赤くなる(v0.4.0 で発生)。
- 自動生成 notes ではなく手書き notes を載せたいときは、**タグ push 後に**
  `gh release edit vX.Y.Z --notes-file <file>` で上書きする(create は workflow に任せる)。
- workflow は Release が既存なら作成をスキップする(idempotent)ので、手動先行があっても
  イメージ push は通るが、上の原則(create しない)を守るのが正。
- `pyproject.toml` の `version` とタグを一致させる(`aidr --version` と OCI label がタグ由来)。
- `pyproject.toml` や README の image tag を次版へ進めた時点は **release pending** であり、
  リリース完了ではない。対応する annotated tag、GitHub Release、GHCR image の実体確認が
  すべて終わって初めて released と報告する
- **タグ push は、CI green を別コマンドで確認してから行う**。`gh run watch --exit-status ... | tail`
  のようにパイプすると exit code が tail のものになり、`&&` 連結でも CI red のまま
  タグが走る(v0.10.0 で実際に発生し、v0.10.1 で差し替えた)。watch はパイプせず単体で
  実行し、結論(全 matrix job success)を見てからタグを打つ。

## 横断的な注意点

- 秘密情報・ハードコード認証情報の混入なきこと(`examples/audit-log-sample.json` の
  URL は `internal.example.com` のダミー)
- README の売り(「診断ツール + 拡張可能なフレームワーク」)と本文の整合を保つ
- 本リポを参考に派生実装を作る場合、味の素事例の数値(「76%」削減率)は記事に定義が
  明示されていない旨を引用すること(誤って絶対値として伝播させない)

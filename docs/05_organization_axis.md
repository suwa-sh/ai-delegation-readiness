# 05. 組織 readiness 軸で「組織が委任を受け止められるか」を診断する

## TL;DR

業務プロセスが委任に耐えても(4 層が pass)、**組織**がその委任を受け止められなければ
運用は続きません。**組織 readiness 軸**は、撤退判断の権限・受け皿となるリテラシー層・
知識移転契約・漸進分割の設計・bus factor 対策の 6 条件を、4 層や効果測定と**並列**に
採点します。並列軸なので層のゲートには関与せず、「業務は委任できるが組織が未成熟」を
独立した穴として表面化させます。

本軸は **味の素モデルの分析記事「6 条件チェックリスト + 反証 5」** から骨格を抽出しています。
事実と一般化はラベル分けで示します:**【観測事実】** / **【設計提案】**。

## When to use this

- 4 層(業務プロセス)の診断は済み、**組織側の受け皿**を点検したい
- 新規事業フェーズで少人数フルスタックに AI を入れる前のセルフチェックをしたい
- AI 導入提案で「ベンダー比較」でなく「組織の障害」を材料にしたい

## Quick use

```bash
bin/aidr check-readiness examples/business/ajinomoto-discovery-team.yaml
```

*業務*は整っているが*組織*が未成熟なチームの結果です。

```text
[OK] L1 業務標準化層: PASS (100%)
[OK] L2 判断構造化層: PASS (100%)
[OK] L3 委任範囲層: PASS (100%)
[OK] L4 統制・追跡層: PASS (100%)
[OK] efficacy 効果測定: PASS (100%)
[NG] organization 組織 readiness層: BLOCK (33%)
    no: organization.C2, organization.C4, organization.C5, organization.C6

Conclusion: BLOCK
```

全ての業務層が PASS でも、総合判定は BLOCK です。組織軸が受け皿・知識移転・漸進分割・
bus factor の不足を表面化させます。

## Concept

### 6 条件(組織 readiness の問い)

正本は [`definitions/four-layer.yaml`](../definitions/four-layer.yaml) の `organization` group
(`organization.C1`〜`C6`)です。値はここに二重保持しません。

| id | 条件 | 確認の観点 | ラベル |
|---|---|---|---|
| C1 | 撤退判断の権限と文化 | 8-12 ヶ月以内に「やめる」決定ができる権限がある | 【観測事実】LaboMe® 約 8.5 ヶ月で撤退 |
| C2 | 全社リテラシー層 | 受け皿となるビジネス側人材が 2 桁人数で育っている | 【観測事実】味の素はビジネス DX 人財 2,200 名 |
| C3 | AI ツール基盤の定着 | 個人レベルで Copilot / 社内チャット / RAG が定着 | 【観測事実】AJI AI Chat 月間アクティブ率 約 70% |
| C4 | 知識移転契約 | SI/ベンダー契約で内面化(I)を KPI 化できる | 【設計提案】IPA モデル契約を起点に |
| C5 | 漸進分割の設計 | Stream-aligned → Complicated Subsystem/Platform の剥がし方を事前設計 | 【設計提案】Team Topologies 漸進分割 |
| C6 | bus factor 対策 | ペアプロ / ADR / Knowledge Transfer Day を運用 | 【設計提案】意図的な知識分散 |

合否基準(base): **pass 1.0(6/6)** / **revise 0.66(4/6 以上)**。記事の「4 つ以上なら試行は妥当、
3 つ以下ならまず受け皿作り」に一致します(6 問等重みで 4/6=0.667≥0.66、3/6=0.5<0.66 → block)。

### 反証 5(軸の根拠)

軸の閾値を厳しめに置く根拠として、`organization` group の `case_evidence` に記録しています。
**記事が数値の再確認を留保した反証 1・2 は `claim_needs_verification` とし、事実断定しません**。

| # | 反証 | confidence |
|---|---|---|
| 1 | AI 委譲モードで技能 ~17% 低下(Anthropic 研究、要再確認) | claim_needs_verification |
| 2 | ジュニア雇用 ~20% 減(Stanford payroll、要再確認) | claim_needs_verification |
| 3 | bus factor 1 のリポジトリは ~16% が消滅 | observed_fact |
| 4 | 10→50 人 inflection で 40-60% velocity decline | observed_fact |
| 5 | METR 2026/02 改定(19% 遅延結論を 2026 に引かない) | gap_in_source |

### ■構造(採点コンポーネントの振り分け)

`check-readiness` は定義の全 group を読み、header の `role` で**ゲート層**と**並列軸**に
振り分けます。組織軸は efficacy と同じ並列軸で、層のゲート(`blocked_from`)には関与しません。

```mermaid
flowchart TD
    Def["four-layer.yaml<br/>items 平坦リスト"] --> GI["group_items<br/>id のセパレータで group 化"]
    GI --> Role{"header.role で分類"}
    Role -->|"role 未指定 = gating"| Layers["ゲート層<br/>L1 → L2 → L3 → L4<br/>積み上げ blocked_from"]
    Role -->|"role: parallel"| Axes["並列軸<br/>efficacy / organization<br/>層をゲートしない"]
    Layers --> Concl["conclusion<br/>層 + 並列軸 の合否で PASS/REVISE/BLOCK"]
    Axes --> Concl
    Role -->|"未知の role 値"| Err["ValueError<br/>静かな降格を防ぐ"]
```

- **ゲート層**: `L1`〜`L4`。下層が pass でないと `blocked_from` を立て、上層点検の前提を示す。
- **並列軸**: `efficacy` / `organization`。単独で採点し conclusion に寄与するが、層のゲートには
  関与しない。leaf 0 個の並列軸は「未評価」としてスキップし、誤 BLOCK を防ぐ。
- **未知 role**: `paralell` のような typo は静かにゲート層へ降格させず、`ValueError` で落とす。

### ■データ(定義の概念モデル)

```mermaid
classDiagram
    class Definition {
      name
      extension_points
    }
    class Group {
      id
      role : gating | parallel
      pass
      revise
    }
    class Leaf {
      id
      text
      weight
    }
    class CaseEvidence {
      text
      confidence
      source
    }
    Definition "1" --> "*" Group : group_items
    Group "1" --> "*" Leaf : leaves
    Group "1" --> "*" CaseEvidence : case_evidence
```

- **Group.role** が振り分けの唯一のキー。`organization` は `role: parallel`。
- **overlay** は `extension_points` の宣言に従い、`organization` group への `add`(質問追加)と
  `strengthen`(閾値の強化方向のみ)ができる。緩和・上書き・削除は `aidr check-overlay` が拒否する。

## References

- 正本: [`definitions/four-layer.yaml`](../definitions/four-layer.yaml) の `organization` group / `extension_points`
- 採点: [`src/adr/check_readiness.py`](../src/adr/check_readiness.py)(`axis_role` / 層と並列軸の振り分け)
- サンプル: [`examples/business/ajinomoto-discovery-team.yaml`](../examples/business/ajinomoto-discovery-team.yaml) /
  [`examples/overlays/organization-readiness-ajinomoto.yaml`](../examples/overlays/organization-readiness-ajinomoto.yaml)
- 関連: [`01_four_layer_framework.md`](01_four_layer_framework.md)(4 層 + 効果測定)

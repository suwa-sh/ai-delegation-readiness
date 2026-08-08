"""Overlay merge rule tests for the canonical engine.

Covers add / strengthen (leaf + group, group-scoped), every boundary
condition, source-order preservation, opaque-payload preservation, and a
round-trip against the real four-layer.yaml overlay sample. Also covers
delegation-matrix axes / examples / regions overlay cases that the old
per-DSL tests never exercised.
"""
from __future__ import annotations

from copy import deepcopy

import overlay_scoring as ov
from conftest import (
    authz_overlay_four_layer_path,
    authz_overlay_task_contract_path,
    four_layer_path,
    hs_overlay_four_layer_path,
    hs_overlay_matrix_path,
    insourcing_overlay_path,
    ledger_overlay_four_layer_path,
    matrix_path,
    patch_decision_path,
    risk_architecture_path,
    sample_overlay_path,
    task_contract_path,
    trajectory_overlay_four_layer_path,
    transition_path,
    unattended_overlay_four_layer_path,
)


def four_layer() -> dict:
    return ov.load_yaml(four_layer_path())


def matrix() -> dict:
    return ov.load_yaml(matrix_path())


def task_contract() -> dict:
    return ov.load_yaml(task_contract_path())


def transition() -> dict:
    return ov.load_yaml(transition_path())


def patch_decision() -> dict:
    return ov.load_yaml(patch_decision_path())


def _ids(defn: dict) -> list[str]:
    return [it["id"] for it in defn["items"]]


# --- base integrity ---------------------------------------------------------

def test_validate_definition_正規の基本定義の場合_バリデーションエラーが出ないこと():
    # Act & Assert
    assert ov.validate_definition(four_layer()) == []
    assert ov.validate_definition(matrix()) == []
    assert ov.validate_definition(transition()) == []


def test_validate_definition_親group未宣言のleafの場合_unknown_groupで拒否されること():
    # Arrange
    defn = {"version": 1, "name": "x", "items": [{"id": "A.child"}]}
    # Act
    kinds = {v.kind for v in ov.validate_definition(defn)}
    # Assert
    assert "unknown_group" in kinds


def test_validate_definition_idが重複した場合_id_collisionで拒否されること():
    # Arrange
    defn = {"version": 1, "name": "x", "items": [{"id": "A"}, {"id": "A"}]}
    # Act
    kinds = {v.kind for v in ov.validate_definition(defn)}
    # Assert
    assert "id_collision" in kinds


# --- add (four-layer) --------------------------------------------------------

def test_apply_overlay_既存layerにleafをaddした場合_mergeに追加されること():
    # Arrange
    overlay = {"extends": "four-layer-delegation-readiness",
               "add": [{"id": "L1.Q5", "text": "extra", "weight": 1.0}]}
    # Act
    r = ov.apply_overlay(four_layer(), overlay)
    # Assert
    assert r.ok, r.violations
    assert "L1.Q5" in _ids(r.merged)


def test_apply_overlay_selectorに一致するが未宣言groupへaddした場合_unknown_groupで拒否されること():
    # Arrange
    overlay = {"extends": "four-layer-delegation-readiness",
               "add": [{"id": "LZ.Q1", "text": "x", "weight": 1.0}]}
    # Act
    r = ov.apply_overlay(four_layer(), overlay)
    # Assert
    # LZ matches selector "L*" but there is no LZ header
    assert not r.ok
    assert {v.kind for v in r.violations} == {"unknown_group"}


def test_apply_overlay_拡張点でないgroupへaddした場合_unsupported_opで拒否されること():
    # Arrange
    overlay = {"extends": "four-layer-delegation-readiness",
               "add": [{"id": "XYZ.q", "text": "x"}]}
    # Act
    r = ov.apply_overlay(four_layer(), overlay)
    # Assert
    assert {v.kind for v in r.violations} == {"unsupported_op"}


def test_apply_overlay_base側と重複するidをaddした場合_id_collisionで拒否されること():
    # Arrange
    overlay = {"extends": "four-layer-delegation-readiness",
               "add": [{"id": "L1.Q1", "text": "dup", "weight": 1.0}]}
    # Act
    r = ov.apply_overlay(four_layer(), overlay)
    # Assert
    assert {v.kind for v in r.violations} == {"id_collision"}


def test_apply_overlay_同一overlay内でidが重複した場合_id_collisionで拒否されること():
    # Arrange
    overlay = {"extends": "four-layer-delegation-readiness",
               "add": [{"id": "L1.NEW", "text": "a", "weight": 1.0},
                       {"id": "L1.NEW", "text": "b", "weight": 1.0}]}
    # Act
    r = ov.apply_overlay(four_layer(), overlay)
    # Assert
    assert {v.kind for v in r.violations} == {"id_collision"}


def test_apply_overlay_新規layerのheaderとleafを同時にaddした場合_両方がmergeに追加されること():
    # Arrange
    overlay = {"extends": "four-layer-delegation-readiness",
               "add": [{"id": "L5", "name": "extra_layer", "pass": 1.0, "revise": 0.7},
                       {"id": "L5.Q1", "text": "q", "weight": 1.0}]}
    # Act
    r = ov.apply_overlay(four_layer(), overlay)
    # Assert
    assert r.ok, r.violations
    assert "L5" in _ids(r.merged) and "L5.Q1" in _ids(r.merged)


def test_apply_overlay_idにセパレータを2つ含む場合_invalid_overlayで拒否されること():
    # Arrange
    overlay = {"extends": "four-layer-delegation-readiness",
               "add": [{"id": "L1.Q1.deep", "text": "x", "weight": 1.0}]}
    # Act
    r = ov.apply_overlay(four_layer(), overlay)
    # Assert
    assert {v.kind for v in r.violations} == {"invalid_overlay"}


def test_apply_overlay_idを持たないitemをaddした場合_invalid_overlayで拒否されること():
    # Arrange
    overlay = {"extends": "four-layer-delegation-readiness", "add": [{"text": "no id"}]}
    # Act
    r = ov.apply_overlay(four_layer(), overlay)
    # Assert
    assert {v.kind for v in r.violations} == {"invalid_overlay"}


# --- strengthen (four-layer) -------------------------------------------------

def test_apply_overlay_group値をbaseより強い値でstrengthenした場合_受理されること():
    # Arrange
    overlay = {"extends": "four-layer-delegation-readiness",
               "strengthen": {"L4": {"revise": 0.8}}}
    # Act
    r = ov.apply_overlay(four_layer(), overlay)
    # Assert
    assert r.ok, r.violations
    l4 = next(i for i in r.merged["items"] if i["id"] == "L4")
    assert l4["revise"] == 0.8


def test_apply_overlay_group値をbaseと同値でstrengthenした場合_受理されること():
    # Arrange
    overlay = {"extends": "four-layer-delegation-readiness",
               "strengthen": {"L4": {"revise": 0.6}}}  # base L4 revise is 0.6
    # Act
    r = ov.apply_overlay(four_layer(), overlay)
    # Assert
    assert r.ok, r.violations


def test_apply_overlay_group値をbaseより弱い値でstrengthenした場合_weakening_rejectedで拒否されること():
    # Arrange
    overlay = {"extends": "four-layer-delegation-readiness",
               "strengthen": {"L4": {"revise": 0.4}}}  # 0.6 -> 0.4 is weaker
    # Act
    r = ov.apply_overlay(four_layer(), overlay)
    # Assert
    assert {v.kind for v in r.violations} == {"weakening_rejected"}


def test_apply_overlay_strengthen値が非数値の場合_invalid_overlayで拒否されること():
    # Arrange
    overlay = {"extends": "four-layer-delegation-readiness",
               "strengthen": {"L4": {"revise": "soon"}}}
    # Act
    r = ov.apply_overlay(four_layer(), overlay)
    # Assert
    assert {v.kind for v in r.violations} == {"invalid_overlay"}


def test_apply_overlay_strengthen拡張点として未宣言のfieldを指定した場合_unsupported_opで拒否されること():
    # Arrange
    # weight is a leaf field but not declared strengthen-able in four-layer
    overlay = {"extends": "four-layer-delegation-readiness",
               "strengthen": {"L1.Q1": {"weight": 2.0}}}
    # Act
    r = ov.apply_overlay(four_layer(), overlay)
    # Assert
    assert {v.kind for v in r.violations} == {"unsupported_op"}


def test_apply_overlay_存在しないidをstrengthenした場合_unknown_idで拒否されること():
    # Arrange
    overlay = {"extends": "four-layer-delegation-readiness",
               "strengthen": {"L9": {"revise": 0.9}}}
    # Act
    r = ov.apply_overlay(four_layer(), overlay)
    # Assert
    assert {v.kind for v in r.violations} == {"unknown_id"}


def test_apply_overlay_同一overlayでaddとstrengthenを両方使った場合_両方が反映されること():
    # Arrange
    overlay = {"extends": "four-layer-delegation-readiness",
               "add": [{"id": "efficacy.E_NEW", "text": "extra efficacy question", "weight": 1.0}],
               "strengthen": {"efficacy": {"revise": 0.9}}}
    # Act
    r = ov.apply_overlay(four_layer(), overlay)
    # Assert
    assert r.ok, r.violations
    assert "efficacy.E_NEW" in _ids(r.merged)
    eff = next(i for i in r.merged["items"] if i["id"] == "efficacy")
    assert eff["revise"] == 0.9


# --- top-level / extends ----------------------------------------------------

def test_apply_overlay_extendsが対象定義名と一致しない場合_extends_mismatchで拒否されること():
    # Arrange
    overlay = {"extends": "wrong-name", "add": []}
    # Act
    r = ov.apply_overlay(four_layer(), overlay)
    # Assert
    assert {v.kind for v in r.violations} == {"extends_mismatch"}


def test_apply_overlay_未対応のtop_level_keyを指定した場合_unsupported_opで拒否されること():
    # Arrange
    overlay = {"extends": "four-layer-delegation-readiness", "delete": ["L1"]}
    # Act
    r = ov.apply_overlay(four_layer(), overlay)
    # Assert
    assert {v.kind for v in r.violations} == {"unsupported_op"}


# --- multi-overlay ----------------------------------------------------------

def test_apply_overlays_途中のoverlayが不正な場合_それ以降を適用せず停止すること(tmp_path):
    # Arrange
    good = tmp_path / "good.yaml"
    bad = tmp_path / "bad.yaml"
    after = tmp_path / "after.yaml"
    good.write_text("extends: four-layer-delegation-readiness\nadd:\n  - {id: 'L1.G1', text: g, weight: 1.0}\n")
    bad.write_text("extends: four-layer-delegation-readiness\nstrengthen:\n  L4: {revise: 0.1}\n")
    after.write_text("extends: four-layer-delegation-readiness\nadd:\n  - {id: 'L1.G2', text: g, weight: 1.0}\n")
    # Act
    r = ov.apply_overlays(four_layer(), [good, bad, after])
    # Assert
    assert not r.ok
    assert r.applied == [str(good)]           # good applied, stopped before 'after'
    assert "L1.G1" in _ids(r.merged)
    assert "L1.G2" not in _ids(r.merged)


# --- structural guarantees ---------------------------------------------------

def test_apply_overlay_overlay適用後の場合_group順序とopaque_payloadが保持されていること():
    # Arrange
    base = four_layer()
    overlay = ov.load_yaml(sample_overlay_path())
    # Act
    r = ov.apply_overlay(base, overlay)
    # Assert
    assert r.ok, r.violations
    groups = ov.group_items(r.merged)
    # group order preserved
    assert list(groups.keys()) == ["L1", "L2", "L3", "L4", "efficacy", "organization"]
    # added leaves appended to their group, base leaves kept in order
    l1_leaves = [i["id"] for i in groups["L1"]["leaves"]]
    assert l1_leaves == ["L1.Q1", "L1.Q2", "L1.Q3", "L1.Q4", "L1.MIDORI_Q5"]
    # opaque payload on the header survives untouched
    assert groups["L1"]["header"]["case_evidence"][0]["confidence"] == "observed_fact"


def test_apply_overlay_overlayを適用した場合_base定義が変更されないこと():
    # Arrange
    base = four_layer()
    snapshot = deepcopy(base)
    # Act
    ov.apply_overlay(base, {"extends": "four-layer-delegation-readiness",
                             "add": [{"id": "L1.Z", "text": "z", "weight": 1.0}]})
    # Assert
    assert base == snapshot


# --- round-trip against the real overlay sample ------------------------------

def test_apply_overlay_sample_overlayを四層定義に適用した場合_期待するidとstrengthen結果が得られること():
    # Act
    r = ov.apply_overlay(four_layer(), ov.load_yaml(sample_overlay_path()))
    # Assert
    assert r.ok, r.violations
    ids = _ids(r.merged)
    assert "L1.MIDORI_Q5" in ids and "L4.MIDORI_Q6" in ids
    l4 = next(i for i in r.merged["items"] if i["id"] == "L4")
    assert l4["revise"] == 0.8


def test_apply_overlay_high_stakes_overlayを四層定義に適用した場合_L5がハードゲートとして追加されること():
    # Act
    r = ov.apply_overlay(four_layer(), ov.load_yaml(hs_overlay_four_layer_path()))
    # Assert
    assert r.ok, r.violations
    ids = _ids(r.merged)
    assert "L5" in ids and "L5.Q1" in ids and "L5.Q4" in ids
    assert "L3.HS_Q5" in ids and "L3.HS_Q6" in ids
    l5 = next(i for i in r.merged["items"] if i["id"] == "L5")
    # hard gate: no revise band — anything below 4/4 blocks
    assert l5["pass"] == 1.0 and l5["revise"] == 1.0


def test_apply_overlay_insourcing_overlayを四層定義に適用した場合_parallel軸として追加されること():
    # Act
    r = ov.apply_overlay(four_layer(), ov.load_yaml(insourcing_overlay_path()))
    # Assert
    assert r.ok, r.violations
    ids = _ids(r.merged)
    assert "L_insourcing" in ids
    for q in ("I0", "I1", "I2", "I3", "I4"):
        assert f"L_insourcing.{q}" in ids
    axis = next(i for i in r.merged["items"] if i["id"] == "L_insourcing")
    # parallel axis (does not gate L1-L4) with a strict bar: 5/5 pass, 4/5 revise
    assert axis["role"] == "parallel"
    assert axis["pass"] == 1.0 and axis["revise"] == 0.8


def test_apply_overlay_authz_overlayを四層定義に適用した場合_capability軸とconsent軸が独立したparallel軸として追加されること():
    # Act
    r = ov.apply_overlay(four_layer(), ov.load_yaml(authz_overlay_four_layer_path()))
    # Assert
    assert r.ok, r.violations
    ids = _ids(r.merged)
    # two independent parallel axes, never merged into one score: capability
    # full and consent empty must stay distinguishable in the report.
    for axis_id, leaf_prefix in (("L_capability", "C"), ("L_consent", "S")):
        assert axis_id in ids
        for n in (1, 2, 3):
            assert f"{axis_id}.{leaf_prefix}{n}" in ids
        axis = next(i for i in r.merged["items"] if i["id"] == axis_id)
        assert axis["role"] == "parallel"
        assert axis["pass"] == 1.0 and axis["revise"] == 0.66


def test_apply_overlay_authz_overlayをtask_contractに適用した場合_boundary閾値が5に強化されること():
    # Act
    r = ov.apply_overlay(ov.load_yaml(task_contract_path()),
                         ov.load_yaml(authz_overlay_task_contract_path()))
    # Assert
    assert r.ok, r.violations
    ids = _ids(r.merged)
    assert "boundary.AZ1" in ids and "boundary.AZ2" in ids
    boundary = next(i for i in r.merged["items"] if i["id"] == "boundary")
    # Monotonicity: adding presence questions without raising the count
    # threshold makes the group relatively easier to pass. 3 base + 2 added
    # questions must not stay at "2 of 5"; this overlay requires all five.
    assert boundary["threshold"] == 5


def test_apply_overlays_authz_overlayとhigh_stakes_overlayを同時に適用した場合_idが衝突せず両方追加されること():
    """Both bundled four-layer overlays must be applicable together.

    They add sibling groups under the same ``L*`` extension point, so an id
    clash here would make the two domains mutually exclusive.
    """
    # Act
    r = ov.apply_overlays(four_layer(), [hs_overlay_four_layer_path(),
                                         authz_overlay_four_layer_path()])
    # Assert
    assert r.ok, r.violations
    ids = _ids(r.merged)
    assert {"L5", "L_capability", "L_consent"} <= set(ids)


def test_apply_overlay_unattended_overlayを四層定義に適用した場合_実行面軸と監督面軸が独立したparallel軸として追加されること():
    # Act
    r = ov.apply_overlay(four_layer(), ov.load_yaml(unattended_overlay_four_layer_path()))
    # Assert
    assert r.ok, r.violations
    ids = _ids(r.merged)
    # two independent parallel axes: a perfect kill switch must not average
    # away a missing approval fail-closed, and vice versa.
    for axis_id, leaf_prefix, count, revise in (
        ("L_unattended_surface", "U", 4, 0.75),
        ("L_unattended_supervision", "S", 3, 0.66),
    ):
        assert axis_id in ids
        for n in range(1, count + 1):
            assert f"{axis_id}.{leaf_prefix}{n}" in ids
        axis = next(i for i in r.merged["items"] if i["id"] == axis_id)
        assert axis["role"] == "parallel"
        assert axis["pass"] == 1.0 and axis["revise"] == revise


def test_apply_overlay_trajectory_overlayを四層定義に適用した場合_強制力軸と監視軸が独立したparallel軸として追加されること():
    """The enforcement floor must not be averaged away by oversight quality.

    The enforcement axis carries revise == pass == 1.0 on purpose: a single
    missing floor control (e.g. no sibling-leak test) is a BLOCK, not a
    REVISE diluted by the other three answers.
    """
    # Act
    r = ov.apply_overlay(four_layer(), ov.load_yaml(trajectory_overlay_four_layer_path()))
    # Assert
    assert r.ok, r.violations
    ids = _ids(r.merged)
    for axis_id, leaf_prefix, count, revise in (
        ("L_trajectory_enforcement", "E", 4, 1.0),
        ("L_trajectory_oversight", "O", 3, 0.66),
    ):
        assert axis_id in ids
        for n in range(1, count + 1):
            assert f"{axis_id}.{leaf_prefix}{n}" in ids
        axis = next(i for i in r.merged["items"] if i["id"] == axis_id)
        assert axis["role"] == "parallel"
        assert axis["pass"] == 1.0 and axis["revise"] == revise


def test_apply_overlay_ledger_overlayを四層定義に適用した場合_責任軸とコスト軸が独立したparallel軸として追加されること():
    """Accountability and cost are independent controls on purpose.

    Averaging them into one axis would let a complete accountability ledger
    compensate for a cost picture that is only a monthly invoice total, and
    vice versa — each gap must surface as its own axis verdict.
    """
    # Act
    r = ov.apply_overlay(four_layer(), ov.load_yaml(ledger_overlay_four_layer_path()))
    # Assert
    assert r.ok, r.violations
    ids = _ids(r.merged)
    for axis_id, leaf_prefix, count, revise in (
        ("L_ledger_accountability", "LA", 4, 0.75),
        ("L_ledger_cost", "LC", 3, 0.66),
    ):
        assert axis_id in ids
        for n in range(1, count + 1):
            assert f"{axis_id}.{leaf_prefix}{n}" in ids
        axis = next(i for i in r.merged["items"] if i["id"] == axis_id)
        assert axis["role"] == "parallel"
        assert axis["pass"] == 1.0 and axis["revise"] == revise


def test_apply_overlays_同梱の全four_layer_overlayを同時に適用した場合_idが衝突せず全軸が追加されること():
    """All six bundled four-layer overlays must be applicable together.

    They add sibling groups under the same ``L*`` extension point, so an id
    clash would make the newest axes mutually exclusive with an existing
    domain overlay.
    """
    # Act
    r = ov.apply_overlays(four_layer(), [hs_overlay_four_layer_path(),
                                         insourcing_overlay_path(),
                                         authz_overlay_four_layer_path(),
                                         unattended_overlay_four_layer_path(),
                                         trajectory_overlay_four_layer_path(),
                                         ledger_overlay_four_layer_path()])
    # Assert
    assert r.ok, r.violations
    ids = _ids(r.merged)
    assert {"L5", "L_insourcing", "L_capability", "L_consent",
            "L_unattended_surface", "L_unattended_supervision",
            "L_trajectory_enforcement", "L_trajectory_oversight",
            "L_ledger_accountability", "L_ledger_cost"} <= set(ids)


def test_apply_overlay_high_stakes_overlayをmatrix定義に適用した場合_軸の閾値と新規exampleが反映されること():
    # Act
    r = ov.apply_overlay(matrix(), ov.load_yaml(hs_overlay_matrix_path()))
    # Assert
    assert r.ok, r.violations
    for axis_id in ("verifiability", "answer_definability"):
        axis = next(i for i in r.merged["items"] if i["id"] == axis_id)
        assert axis["threshold"] == 3
    ids = _ids(r.merged)
    assert "examples.patent_classification" in ids
    assert "examples.invalidity_search_final" in ids


# --- delegation-matrix: axes / examples / regions ---------------------------
# (not exercised by the old per-DSL overlay tests, which only covered
# four-layer's layers/efficacy_axis)

def test_apply_overlay_matrix定義の既存axisに質問をaddした場合_mergeに追加されること():
    # Arrange
    overlay = {"extends": "delegation-matrix",
               "add": [{"id": "verifiability.V4", "text": "extra question"}]}
    # Act
    r = ov.apply_overlay(matrix(), overlay)
    # Assert
    assert r.ok, r.violations
    assert "verifiability.V4" in _ids(r.merged)


def test_apply_overlay_matrix定義の未知axisに質問をaddした場合_unsupported_opで拒否されること():
    # Arrange
    overlay = {"extends": "delegation-matrix",
               "add": [{"id": "novelty.N1", "text": "extra"}]}
    # Act
    r = ov.apply_overlay(matrix(), overlay)
    # Assert
    assert {v.kind for v in r.violations} == {"unsupported_op"}


def test_apply_overlay_matrix定義のthresholdをbaseより高い値でstrengthenした場合_受理されること():
    # Arrange
    overlay = {"extends": "delegation-matrix",
               "strengthen": {"verifiability": {"threshold": 3}}}
    # Act
    r = ov.apply_overlay(matrix(), overlay)
    # Assert
    assert r.ok, r.violations
    axis = next(i for i in r.merged["items"] if i["id"] == "verifiability")
    assert axis["threshold"] == 3


def test_apply_overlay_matrix定義のthresholdをbaseより低い値でstrengthenした場合_weakening_rejectedで拒否されること():
    # Arrange
    overlay = {"extends": "delegation-matrix",
               "strengthen": {"verifiability": {"threshold": 1}}}  # 2 -> 1 is weaker
    # Act
    r = ov.apply_overlay(matrix(), overlay)
    # Assert
    assert {v.kind for v in r.violations} == {"weakening_rejected"}


def test_apply_overlay_matrix定義のexamplesにexampleをaddした場合_mergeに追加されること():
    # Arrange
    overlay = {"extends": "delegation-matrix",
               "add": [{"id": "examples.acme_custom_check",
                        "judgment": "Acme custom check", "region": "green"}]}
    # Act
    r = ov.apply_overlay(matrix(), overlay)
    # Assert
    assert r.ok, r.violations
    assert "examples.acme_custom_check" in _ids(r.merged)


def test_apply_overlay_matrix定義の固定lookupであるregionsにaddした場合_unsupported_opで拒否されること():
    # Arrange
    # regions is a fixed lookup, not an extension point: overlays cannot grow it
    overlay = {"extends": "delegation-matrix",
               "add": [{"id": "regions.blue", "when": [], "action": "n/a"}]}
    # Act
    r = ov.apply_overlay(matrix(), overlay)
    # Assert
    assert {v.kind for v in r.violations} == {"unsupported_op"}


def test_group_items_matrix定義のregionsを取得した場合_順序とopaqueなwhenが保持されていること():
    # Act
    groups = ov.group_items(matrix())
    # Assert
    region_ids = [i["id"] for i in groups["regions"]["leaves"]]
    assert region_ids == ["regions.green", "regions.yellow", "regions.red"]
    green = groups["regions"]["leaves"][0]
    assert green["when"] == [{"verifiability": "high", "answer_definability": "high"}]


# --- task-contract overlay cases --------------------------------------------

def test_validate_definition_task_contract定義の場合_バリデーションエラーが出ないこと():
    # Act & Assert
    assert ov.validate_definition(task_contract()) == []


def test_apply_overlay_task_contract定義のelementに質問をaddした場合_mergeに追加されること():
    # Arrange
    overlay = {"extends": "task-contract",
               "add": [{"id": "intent.I4", "kind": "question", "text": "extra"}]}
    # Act
    r = ov.apply_overlay(task_contract(), overlay)
    # Assert
    assert r.ok, r.violations
    assert "intent.I4" in _ids(r.merged)


def test_apply_overlay_task_contract定義のthresholdをbaseより高い値でstrengthenした場合_受理されること():
    # Arrange
    overlay = {"extends": "task-contract",
               "strengthen": {"boundary": {"threshold": 3}}}
    # Act
    r = ov.apply_overlay(task_contract(), overlay)
    # Assert
    assert r.ok, r.violations


def test_apply_overlay_task_contract定義のthresholdをbaseより低い値でstrengthenした場合_weakening_rejectedで拒否されること():
    # Arrange
    overlay = {"extends": "task-contract",
               "strengthen": {"boundary": {"threshold": 1}}}  # 2 -> 1 is weaker
    # Act
    r = ov.apply_overlay(task_contract(), overlay)
    # Assert
    assert {v.kind for v in r.violations} == {"weakening_rejected"}


def test_apply_overlay_task_contract定義の拡張点でないgatesにaddした場合_拒否されること():
    # Arrange
    # gates is a lookup group, not declared extensible.
    overlay = {"extends": "task-contract",
               "add": [{"id": "gates.orange", "kind": "lookup", "when": ["otherwise"]}]}
    # Act
    r = ov.apply_overlay(task_contract(), overlay)
    # Assert
    assert not r.ok


def test_group_items_task_contract定義のgatesを取得した場合_順序とopaqueなwhenが保持されていること():
    # Act
    groups = ov.group_items(task_contract())
    # Assert
    gate_ids = [i["id"] for i in groups["gates"]["leaves"]]
    assert gate_ids == ["gates.red", "gates.yellow", "gates.green"]
    red = groups["gates"]["leaves"][0]
    assert red["when"] == ["any_element_absent", "ai_judge_without_iruler"]
    assert red["exit_code"] == 2


# --- transition-screening: axes are add-only (no threshold strengthening) ----
# The screening definition deliberately declares NO strengthen extension
# points: raising a threshold makes exposure=high harder to reach and drops
# reorganization candidates into minimal_change (a silent miss on a planning
# map). See the extension_points comment in transition-screening.yaml.

def test_apply_overlay_transition_screening定義のaxisに質問をaddした場合_mergeに追加されること():
    # Arrange
    overlay = {"extends": "transition-screening",
               "add": [{"id": "technical_exposure.E4", "text": "extra question"}]}
    # Act
    r = ov.apply_overlay(transition(), overlay)
    # Assert
    assert r.ok, r.violations
    assert "technical_exposure.E4" in _ids(r.merged)


def test_apply_overlay_transition_screening定義のexamplesにexampleをaddした場合_mergeに追加されること():
    # Arrange
    overlay = {"extends": "transition-screening",
               "add": [{"id": "examples.acme_support_desk",
                        "task_group": "Acme support desk", "type": "reorganization"}]}
    # Act
    r = ov.apply_overlay(transition(), overlay)
    # Assert
    assert r.ok, r.violations
    assert "examples.acme_support_desk" in _ids(r.merged)


def test_apply_overlay_strengthen拡張点が宣言されていないtransition_screening定義でthresholdを強化した場合_拒否されること():
    # Arrange
    # Even a "stricter" threshold is rejected: no strengthen point is declared.
    overlay = {"extends": "transition-screening",
               "strengthen": {"technical_exposure": {"threshold": 3}}}
    # Act
    r = ov.apply_overlay(transition(), overlay)
    # Assert
    assert not r.ok


def test_apply_overlay_strengthen拡張点が宣言されていないtransition_screening定義でhuman_necessity閾値を弱めた場合_拒否されること():
    # Arrange
    overlay = {"extends": "transition-screening",
               "strengthen": {"human_necessity": {"threshold": 2}}}
    # Act
    r = ov.apply_overlay(transition(), overlay)
    # Assert
    assert not r.ok


def test_apply_overlay_transition_screening定義の固定lookupであるtypesにaddした場合_拒否されること():
    # Arrange
    # types is a fixed lookup, not an extension point: overlays cannot grow it.
    overlay = {"extends": "transition-screening",
               "add": [{"id": "types.hybrid", "when": [], "action": "n/a"}]}
    # Act
    r = ov.apply_overlay(transition(), overlay)
    # Assert
    assert not r.ok


# --- patch-decision: discard_reason / bands are add-only extension points ---
# decision / reading are the record contract and the reading guidance; both
# are deliberately NOT declared in extension_points (see the comment in
# definitions/patch-decision.yaml), so overlays cannot grow them.

def test_validate_definition_patch_decision定義の場合_バリデーションエラーが出ないこと():
    # Act & Assert
    assert ov.validate_definition(patch_decision()) == []


def test_apply_overlay_patch_decision定義のdiscard_reasonに理由をaddした場合_mergeに追加されること():
    # Arrange
    overlay = {"extends": "patch-decision",
               "add": [{"id": "discard_reason.local_reason", "kind": "lookup",
                        "gate_group": "", "text": "extra", "text_ja": "追加理由"}]}
    # Act
    r = ov.apply_overlay(patch_decision(), overlay)
    # Assert
    assert r.ok, r.violations
    assert "discard_reason.local_reason" in _ids(r.merged)


def test_apply_overlay_patch_decision定義のbandsに帯をaddした場合_mergeに追加されること():
    # Arrange
    overlay = {"extends": "patch-decision",
               "add": [{"id": "bands.custom", "kind": "lookup", "applies_to": "discard_rate",
                        "low": 0.0, "high": 0.5, "label": "custom", "label_ja": "自社帯"}]}
    # Act
    r = ov.apply_overlay(patch_decision(), overlay)
    # Assert
    assert r.ok, r.violations
    assert "bands.custom" in _ids(r.merged)


def test_apply_overlay_patch_decision定義のdecisionに状態をaddした場合_unsupported_opで拒否されること():
    # Arrange
    # decision is the record contract, not declared in extension_points.
    overlay = {"extends": "patch-decision",
               "add": [{"id": "decision.withdrawn", "kind": "lookup",
                        "text": "extra state", "text_ja": "追加状態"}]}
    # Act
    r = ov.apply_overlay(patch_decision(), overlay)
    # Assert
    assert {v.kind for v in r.violations} == {"unsupported_op"}


def test_apply_overlay_patch_decision定義のreadingに読み方をaddした場合_unsupported_opで拒否されること():
    # Arrange
    # reading is the normative "how to read this" guidance, not extensible.
    overlay = {"extends": "patch-decision",
               "add": [{"id": "reading.local_side", "kind": "lookup",
                        "text": "extra reading", "text_ja": "追加の読み方"}]}
    # Act
    r = ov.apply_overlay(patch_decision(), overlay)
    # Assert
    assert {v.kind for v in r.violations} == {"unsupported_op"}


# --- risk-architecture: new scenario groups are add-able; profile/owners are not
# The {0,1,2} scale depends on the monotone two-question shape, so questions
# cannot be added to existing groups (the per-definition contract validator in
# assess_risk_architecture rejects shape breaks the generic engine lets through;
# see tests/test_assess_risk_architecture.py). Here we pin the ENGINE-level
# rules: which groups accept add / strengthen at all.


def risk_architecture() -> dict:
    return ov.load_yaml(risk_architecture_path())


def _scenario_x_items() -> list[dict]:
    items = [{"id": "scenario_x", "name": "custom", "name_ja": "自社シナリオ",
              "cluster": "X", "medium_min": 3, "high_min": 5}]
    for cap, prefix in (("detection", "D"), ("containment", "C"), ("escalation", "S")):
        for strength, n in (("weak", "1"), ("strong", "2")):
            items.append({
                "id": f"scenario_x.{prefix}{n}", "capability": cap, "strength": strength,
                "text": f"{cap} {strength}", "text_ja": f"{cap} {strength} の質問",
            })
    return items


def test_apply_overlay_risk_architecture定義に新シナリオgroup一式をaddした場合_mergeに追加されること():
    # Arrange
    overlay = {"extends": "risk-architecture", "add": _scenario_x_items()}
    # Act
    r = ov.apply_overlay(risk_architecture(), overlay)
    # Assert
    assert r.ok, r.violations
    assert "scenario_x" in _ids(r.merged)
    assert "scenario_x.S2" in _ids(r.merged)


def test_apply_overlay_risk_architecture定義のprofileに質問をaddした場合_拒否されること():
    # Arrange
    # profile is the 7-dimension scale itself; adding a question breaks it.
    overlay = {"extends": "risk-architecture",
               "add": [{"id": "profile.D8_EXTRA", "dimension": "d8", "strength": "weak",
                        "text": "extra", "text_ja": "追加次元"}]}
    # Act
    r = ov.apply_overlay(risk_architecture(), overlay)
    # Assert
    assert not r.ok


def test_apply_overlay_risk_architecture定義のownersに質問をaddした場合_拒否されること():
    # Arrange
    overlay = {"extends": "risk-architecture",
               "add": [{"id": "owners.O4", "owner_key": "extra_owner",
                        "text": "extra owner", "text_ja": "追加オーナー"}]}
    # Act
    r = ov.apply_overlay(risk_architecture(), overlay)
    # Assert
    assert not r.ok


def test_apply_overlay_risk_architecture定義でhigh_minを強化した場合_mergeに反映されること():
    # Arrange
    overlay = {"extends": "risk-architecture",
               "strengthen": {"scenario_a": {"high_min": 6}}}
    # Act
    r = ov.apply_overlay(risk_architecture(), overlay)
    # Assert
    assert r.ok, r.violations
    header = next(i for i in r.merged["items"] if i["id"] == "scenario_a")
    assert header["high_min"] == 6


def test_apply_overlay_risk_architecture定義でmedium_minを弱めた場合_拒否されること():
    # Arrange
    overlay = {"extends": "risk-architecture",
               "strengthen": {"scenario_a": {"medium_min": 2}}}
    # Act
    r = ov.apply_overlay(risk_architecture(), overlay)
    # Assert
    assert {v.kind for v in r.violations} == {"weakening_rejected"}

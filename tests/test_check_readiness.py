"""4-layer + efficacy readiness scoring tests."""
from __future__ import annotations

import textwrap

import pytest
import yaml

import overlay_scoring as ov
from adr import check_readiness as cr
from conftest import sample_business_path, four_layer_path, EXAMPLES_DIR


def ajinomoto_discovery_team_path():
    return EXAMPLES_DIR / "business" / "ajinomoto-discovery-team.csv"


def _write(tmp_path, text, name="biz.yaml"):
    p = tmp_path / name
    p.write_text(textwrap.dedent(text))
    return p


def _all_yes_answers() -> dict:
    base = yaml.safe_load(four_layer_path().read_text())
    return {item["id"]: "yes" for item in base["items"] if ov.is_leaf(item["id"], ov.separator_of(base))}


def test_check_全項目yesの場合_PASSしblocked_fromがNoneであること(tmp_path):
    # Arrange
    biz_path = tmp_path / "biz.yaml"
    biz_path.write_text(yaml.safe_dump({"target": "all-yes", "answers": _all_yes_answers()}))
    # Act
    result = cr.check(biz_path)
    # Assert
    assert result.conclusion == "PASS"
    assert cr.exit_code_for(result) == 0
    assert result.blocked_from is None


def test_check_同梱サンプルbusinessの場合_L1でBLOCKすること():
    """The bundled sample business is intentionally L4-incomplete."""
    # Act
    result = cr.check(sample_business_path())
    # Assert
    assert result.conclusion == "BLOCK"
    assert cr.exit_code_for(result) == 2
    assert result.blocked_from == "L1"  # L1 is the first non-PASS layer


def test_check_全回答なしの場合_BLOCKすること(tmp_path):
    # Arrange
    biz = _write(
        tmp_path,
        """
        target: all-no
        answers: {}
        """,
    )
    # Act
    result = cr.check(biz)
    # Assert
    assert result.conclusion == "BLOCK"


def test_check_未知の回答値の場合_unknown_idsに含まれること(tmp_path):
    # Arrange
    biz = _write(
        tmp_path,
        """
        target: unknown
        answers:
          L1.Q1: maybe
        """,
    )
    # Act
    result = cr.check(biz)
    # Assert
    l1 = next(l for l in result.layers if l.id == "L1")
    assert "L1.Q1" in l1.unknown_ids


def test_check_overlayで質問を追加した場合_追加質問がunknownとして採点されること(tmp_path):
    # Arrange
    overlay = _write(
        tmp_path,
        """
        extends: four-layer-delegation-readiness
        add:
          - id: "L1.NEW_Q"
            text: x
            weight: 1.0
        """,
        name="overlay.yaml",
    )
    biz = tmp_path / "biz.yaml"
    biz.write_text(yaml.safe_dump({"target": "with-overlay", "answers": _all_yes_answers()}))

    # Act
    result_no = cr.check(biz)
    result_ov = cr.check(biz, overlay_paths=[overlay])
    l1 = next(l for l in result_ov.layers if l.id == "L1")

    # Assert
    assert result_no.conclusion == "PASS"
    assert "L1.NEW_Q" in l1.unknown_ids


def test_check_overlayのextendsが不正な場合_OverlayErrorを送出すること(tmp_path):
    # Arrange
    overlay = _write(
        tmp_path,
        """
        extends: wrong-name
        """,
        name="overlay.yaml",
    )
    biz = _write(
        tmp_path,
        """
        target: x
        answers: {}
        """,
        name="biz.yaml",
    )
    # Act & Assert
    with pytest.raises(cr.OverlayError):
        cr.check(biz, overlay_paths=[overlay])


# --- organization axis (parallel, non-gating) --------------------------------

def test_axis_role_role指定と既定値の場合_ROLEを正しく判定すること():
    # Act
    explicit_parallel = cr.axis_role("organization", {"role": "parallel"})
    explicit_gating = cr.axis_role("X", {"role": "gating"})
    default_gating = cr.axis_role("L1", {})
    historical_parallel = cr.axis_role("efficacy", {})

    # Assert
    assert explicit_parallel == cr.ROLE_PARALLEL
    assert explicit_gating == cr.ROLE_GATING
    assert default_gating == cr.ROLE_GATING
    assert historical_parallel == cr.ROLE_PARALLEL


def test_axis_role_role値が不正な場合_ValueErrorを送出すること():
    """A role typo must not silently demote a parallel axis to a gating layer."""
    # Act & Assert
    with pytest.raises(ValueError):
        cr.axis_role("organization", {"role": "paralell"})


def test_check_定義内のroleが不正な場合_ValueErrorを送出すること(tmp_path):
    # Arrange
    defn = _write(
        tmp_path,
        """
        version: 1
        name: four-layer-delegation-readiness
        separator: "."
        items:
          - {id: "L1", name: l1, pass: 1.0, revise: 0.5}
          - {id: "L1.Q1", text: q, weight: 1.0}
          - {id: "org", name: org, role: paralell, pass: 1.0, revise: 0.5}
          - {id: "org.C1", text: c, weight: 1.0}
        """,
        name="defn.yaml",
    )
    biz = _write(tmp_path, "target: x\nanswers: {L1.Q1: yes, org.C1: yes}\n")
    # Act & Assert
    with pytest.raises(ValueError):
        cr.check(biz, definition_path=defn)


def test_check_organization軸がBLOCKの場合_gating層をblockしないこと():
    """organization BLOCK must not gate the layers (blocked_from stays None)."""
    # Act
    result = cr.check(ajinomoto_discovery_team_path())
    # Assert
    assert result.conclusion == "BLOCK"
    assert result.blocked_from is None  # all gating layers pass
    layer_ids = {l.id for l in result.layers}
    assert layer_ids == {"L1", "L2", "L3", "L4"}  # organization is NOT a gating layer
    org = next(a for a in result.parallel_axes if a.id == "organization")
    assert org.verdict == "block"
    assert {a.id for a in result.parallel_axes} == {"efficacy", "organization"}


def test_check_parallel軸に葉がない場合_評価対象から除外されること(tmp_path):
    """A parallel axis with zero leaves is unassessed, not a silent BLOCK."""
    # Arrange
    defn = _write(
        tmp_path,
        """
        version: 1
        name: four-layer-delegation-readiness
        separator: "."
        items:
          - {id: "L1", name: l1, pass: 1.0, revise: 0.5}
          - {id: "L1.Q1", text: q, weight: 1.0}
          - {id: "org", name: org, role: parallel, pass: 1.0, revise: 0.5}
        """,
        name="defn.yaml",
    )
    biz = _write(tmp_path, "target: x\nanswers: {L1.Q1: yes}\n")
    # Act
    result = cr.check(biz, definition_path=defn)
    # Assert
    assert result.conclusion == "PASS"  # empty org axis skipped, not blocking
    assert {a.id for a in result.parallel_axes} == set()


def test_check_organization軸にoverlayでadd_strengthenした場合_追加質問がunknownとして採点されること(tmp_path):
    """add/strengthen work on the organization axis just like on efficacy."""
    # Arrange
    overlay = _write(
        tmp_path,
        """
        extends: four-layer-delegation-readiness
        add:
          - id: "organization.NEW_C"
            text: extra org question
            weight: 1.0
        strengthen:
          "organization": {revise: 0.83}
        """,
        name="overlay.yaml",
    )
    # Act
    result = cr.check(ajinomoto_discovery_team_path(), overlay_paths=[overlay])
    # Assert
    org = next(a for a in result.parallel_axes if a.id == "organization")
    assert "organization.NEW_C" in org.unknown_ids  # added question is scored


# --- high-stakes domain overlay (examples/overlays/high-stakes-domain) ------

def _hs_overlay_path():
    from conftest import hs_overlay_four_layer_path
    return hs_overlay_four_layer_path()


def _merged_all_yes_answers() -> dict:
    base = yaml.safe_load(four_layer_path().read_text())
    merged = ov.apply_overlays(base, [_hs_overlay_path()]).merged
    sep = ov.separator_of(merged)
    return {item["id"]: "yes" for item in merged["items"] if ov.is_leaf(item["id"], sep)}


def test_check_high_stakesで全項目yesの場合_PASSすること(tmp_path):
    # Arrange
    biz_path = tmp_path / "biz.yaml"
    biz_path.write_text(yaml.safe_dump({"target": "hs-all-yes", "answers": _merged_all_yes_answers()}))
    # Act
    result = cr.check(biz_path, overlay_paths=[_hs_overlay_path()])
    # Assert
    assert result.conclusion == "PASS"
    assert result.blocked_from is None


def test_check_high_stakesで1問noの場合_revise帯なしでBLOCKすること(tmp_path):
    """The L5 gate has no revise band: 3/4 -> BLOCK, not REVISE."""
    # Arrange
    answers = _merged_all_yes_answers()
    answers["L5.Q4"] = "no"
    biz_path = tmp_path / "biz.yaml"
    biz_path.write_text(yaml.safe_dump({"target": "hs-one-no", "answers": answers}))
    # Act
    result = cr.check(biz_path, overlay_paths=[_hs_overlay_path()])
    # Assert
    assert result.conclusion == "BLOCK"
    assert result.blocked_from == "L5"
    l5 = next(layer for layer in result.layers if layer.id == "L5")
    assert l5.verdict == "block"


def test_check_同梱IPサンプルの場合_L5でBLOCKすること():
    # Arrange
    from conftest import sample_ip_business_path
    # Act
    result = cr.check(sample_ip_business_path(), overlay_paths=[_hs_overlay_path()])
    # Assert
    verdicts = {layer.id: layer.verdict for layer in result.layers}
    assert verdicts == {"L1": "pass", "L2": "pass", "L3": "pass", "L4": "pass", "L5": "block"}
    assert result.conclusion == "BLOCK"
    assert result.blocked_from == "L5"


# --- insourcing-judgment overlay (examples/overlays/insourcing-judgment) -----
# L_insourcing is a PARALLEL axis: it is scored alongside efficacy/organization
# and never gates L1-L4. pass 1.0 / revise 0.8 over 5 equal-weight questions ->
# 5/5 PASS, 4/5 REVISE, <=3/5 BLOCK. These fix each boundary individually.

def _insourcing_overlay_path():
    from conftest import insourcing_overlay_path
    return insourcing_overlay_path()


def _merged_all_yes_insourcing_answers() -> dict:
    base = yaml.safe_load(four_layer_path().read_text())
    merged = ov.apply_overlays(base, [_insourcing_overlay_path()]).merged
    sep = ov.separator_of(merged)
    return {item["id"]: "yes" for item in merged["items"] if ov.is_leaf(item["id"], sep)}


def _insourcing_axis(result):
    return next(a for a in result.parallel_axes if a.id == "L_insourcing")


def test_check_insourcingで全項目yesの場合_PASSすること(tmp_path):
    # Arrange
    biz_path = tmp_path / "biz.yaml"
    biz_path.write_text(yaml.safe_dump({"target": "ins-all-yes", "answers": _merged_all_yes_insourcing_answers()}))
    # Act
    result = cr.check(biz_path, overlay_paths=[_insourcing_overlay_path()])
    # Assert
    axis = _insourcing_axis(result)
    assert axis.verdict == "pass" and axis.score == 1.0
    assert result.conclusion == "PASS"
    assert result.blocked_from is None


def test_check_insourcingで1問noの場合_gatingせずREVISEすること(tmp_path):
    # Arrange
    answers = _merged_all_yes_insourcing_answers()
    answers["L_insourcing.I2"] = "no"
    biz_path = tmp_path / "biz.yaml"
    biz_path.write_text(yaml.safe_dump({"target": "ins-one-no", "answers": answers}))
    # Act
    result = cr.check(biz_path, overlay_paths=[_insourcing_overlay_path()])
    # Assert
    axis = _insourcing_axis(result)
    assert axis.verdict == "revise" and axis.score == 0.8
    assert result.conclusion == "REVISE"
    # parallel axis: every gating layer still passes, so no first gate to fix
    assert all(layer.verdict == "pass" for layer in result.layers)
    assert result.blocked_from is None


def test_check_insourcingで2問noの場合_gatingせずBLOCKすること(tmp_path):
    # Arrange
    answers = _merged_all_yes_insourcing_answers()
    answers["L_insourcing.I0"] = "no"
    answers["L_insourcing.I1"] = "no"
    biz_path = tmp_path / "biz.yaml"
    biz_path.write_text(yaml.safe_dump({"target": "ins-two-no", "answers": answers}))
    # Act
    result = cr.check(biz_path, overlay_paths=[_insourcing_overlay_path()])
    # Assert
    axis = _insourcing_axis(result)
    assert axis.verdict == "block" and axis.score == 0.6
    assert result.conclusion == "BLOCK"
    # even at BLOCK the parallel axis does not become a gate
    assert all(layer.verdict == "pass" for layer in result.layers)
    assert result.blocked_from is None


def test_check_同梱insourcingサンプルの場合_REVISEすること():
    # Arrange
    from conftest import sample_insourcing_business_path
    # Act
    result = cr.check(sample_insourcing_business_path(), overlay_paths=[_insourcing_overlay_path()])
    # Assert
    assert all(layer.verdict == "pass" for layer in result.layers)
    axis = _insourcing_axis(result)
    assert axis.verdict == "revise"
    assert axis.no_ids == ["L_insourcing.I2"]
    assert result.conclusion == "REVISE"
    assert result.blocked_from is None


# --- agent-authorization overlay (examples/overlays/agent-authorization) -----
# Two PARALLEL axes, L_capability and L_consent, scored independently: the
# whole point of the source framing is that capability and consent do not
# substitute for each other. pass 1.0 / revise 0.66 over 3 equal-weight
# questions each -> 3/3 PASS, 2/3 REVISE, <=1/3 BLOCK.

def _authz_overlay_path():
    from conftest import authz_overlay_four_layer_path
    return authz_overlay_four_layer_path()


def _merged_all_yes_authz_answers() -> dict:
    base = yaml.safe_load(four_layer_path().read_text())
    merged = ov.apply_overlays(base, [_authz_overlay_path()]).merged
    sep = ov.separator_of(merged)
    return {item["id"]: "yes" for item in merged["items"] if ov.is_leaf(item["id"], sep)}


def _authz_axis(result, axis_id):
    return next(a for a in result.parallel_axes if a.id == axis_id)


def test_check_authzで全項目yesの場合_PASSすること(tmp_path):
    # Arrange
    biz_path = tmp_path / "biz.yaml"
    biz_path.write_text(yaml.safe_dump({"target": "authz-all-yes", "answers": _merged_all_yes_authz_answers()}))
    # Act
    result = cr.check(biz_path, overlay_paths=[_authz_overlay_path()])
    # Assert
    for axis_id in ("L_capability", "L_consent"):
        axis = _authz_axis(result, axis_id)
        assert axis.verdict == "pass" and axis.score == 1.0
    assert result.conclusion == "PASS"
    assert result.blocked_from is None


def test_check_capability軸で1問noの場合_gatingせずREVISEすること(tmp_path):
    # Arrange
    answers = _merged_all_yes_authz_answers()
    answers["L_capability.C2"] = "no"
    biz_path = tmp_path / "biz.yaml"
    biz_path.write_text(yaml.safe_dump({"target": "authz-one-no", "answers": answers}))
    # Act
    result = cr.check(biz_path, overlay_paths=[_authz_overlay_path()])
    # Assert
    axis = _authz_axis(result, "L_capability")
    assert axis.verdict == "revise"
    assert _authz_axis(result, "L_consent").verdict == "pass"
    assert result.conclusion == "REVISE"
    assert all(layer.verdict == "pass" for layer in result.layers)
    assert result.blocked_from is None


def test_check_capability軸yesかつconsent軸全noの場合_相殺されずBLOCKすること(tmp_path):
    """A full capability axis must not mask an empty consent axis.

    Averaged into a single 6-question axis these answers would score 4/6 and
    land in the revise band, hiding the block. Scored as two axes, capability
    passes and consent blocks — which is the distinction the framing exists
    to preserve.
    """
    # Arrange
    answers = _merged_all_yes_authz_answers()
    for qid in ("L_consent.S1", "L_consent.S2", "L_consent.S3"):
        answers[qid] = "no"
    biz_path = tmp_path / "biz.yaml"
    biz_path.write_text(yaml.safe_dump({"target": "authz-split", "answers": answers}))
    # Act
    result = cr.check(biz_path, overlay_paths=[_authz_overlay_path()])
    # Assert
    assert _authz_axis(result, "L_capability").verdict == "pass"
    assert _authz_axis(result, "L_consent").verdict == "block"
    assert result.conclusion == "BLOCK"
    # a parallel axis drives the conclusion but never becomes a gate
    assert all(layer.verdict == "pass" for layer in result.layers)
    assert result.blocked_from is None


def test_check_同梱authzサンプルの場合_consent軸でBLOCKすること():
    # Arrange
    from conftest import sample_authz_business_path
    # Act
    result = cr.check(sample_authz_business_path(), overlay_paths=[_authz_overlay_path()])
    # Assert
    assert all(layer.verdict == "pass" for layer in result.layers)
    assert _authz_axis(result, "L_capability").verdict == "pass"
    consent = _authz_axis(result, "L_consent")
    assert consent.verdict == "block"
    assert consent.no_ids == ["L_consent.S1", "L_consent.S3"]
    assert result.conclusion == "BLOCK"
    assert result.blocked_from is None


# ---------------------------------------------------------- unattended overlay
# Threshold boundaries for the account-resident-execution overlay, pinned
# independently of the bundled sample CSVs: surface axis is 4 questions with
# revise 0.75 (one gap REVISE, two gaps BLOCK), supervision axis is 3
# questions with revise 0.66 (one gap REVISE, two gaps BLOCK).


def _unattended_overlay_path():
    from conftest import unattended_overlay_four_layer_path
    return unattended_overlay_four_layer_path()


def _merged_all_yes_unattended_answers() -> dict:
    base = yaml.safe_load(four_layer_path().read_text())
    merged = ov.apply_overlays(base, [_unattended_overlay_path()]).merged
    sep = ov.separator_of(merged)
    return {item["id"]: "yes" for item in merged["items"] if ov.is_leaf(item["id"], sep)}


def _unattended_axis(result, axis_id):
    return next(a for a in result.parallel_axes if a.id == axis_id)


def _check_unattended(tmp_path, answers: dict, target: str):
    biz_path = tmp_path / "biz.yaml"
    biz_path.write_text(yaml.safe_dump({"target": target, "answers": answers}))
    return cr.check(biz_path, overlay_paths=[_unattended_overlay_path()])


def test_check_unattendedで全項目yesの場合_PASSすること(tmp_path):
    # Arrange
    answers = _merged_all_yes_unattended_answers()
    # Act
    result = _check_unattended(tmp_path, answers, "unattended-all-yes")
    # Assert
    for axis_id in ("L_unattended_surface", "L_unattended_supervision"):
        axis = _unattended_axis(result, axis_id)
        assert axis.verdict == "pass" and axis.score == 1.0
    assert result.conclusion == "PASS"
    assert result.blocked_from is None


@pytest.mark.parametrize(
    ("axis_id", "no_ids", "verdict", "conclusion"),
    [
        # one gap = 3/4 = 0.75 hits the surface revise threshold exactly
        ("L_unattended_surface", ("U2",), "revise", "REVISE"),
        # two gaps = 2/4 = 0.5 fall below the surface revise threshold
        ("L_unattended_surface", ("U2", "U3"), "block", "BLOCK"),
        # one gap = 2/3 = 0.66... hits the supervision revise threshold
        ("L_unattended_supervision", ("S2",), "revise", "REVISE"),
        # two gaps = 1/3 fall below the supervision revise threshold
        ("L_unattended_supervision", ("S2", "S3"), "block", "BLOCK"),
    ],
    ids=[
        "実行面軸で1問noの場合_REVISEすること",
        "実行面軸で2問noの場合_BLOCKすること",
        "監督面軸で1問noの場合_REVISEすること",
        "監督面軸で2問noの場合_BLOCKすること",
    ],
)
def test_check_unattended軸の欠落数の場合_閾値どおりの判定になること(
        tmp_path, axis_id, no_ids, verdict, conclusion):
    # Arrange
    answers = _merged_all_yes_unattended_answers()
    for qid in no_ids:
        answers[f"{axis_id}.{qid}"] = "no"
    # Act
    result = _check_unattended(tmp_path, answers, f"{axis_id}-{len(no_ids)}-no")
    # Assert
    assert _unattended_axis(result, axis_id).verdict == verdict
    assert result.conclusion == conclusion
    # a parallel axis drives the conclusion but never becomes a gate
    assert all(layer.verdict == "pass" for layer in result.layers)
    assert result.blocked_from is None


def test_check_両軸に1問ずつnoの場合_軸ごと契約によりREVISEに留まること(tmp_path):
    """Cross-axis gaps do not accumulate into a BLOCK.

    The "two gaps = BLOCK" contract is per axis. One gap on each axis
    (two gaps in total) leaves both axes REVISE and the conclusion REVISE —
    an accepted limit documented in docs/14 (merging the counts would
    destroy the which-side-is-thin reading the two-axis split exists for).
    """
    # Arrange
    answers = _merged_all_yes_unattended_answers()
    answers["L_unattended_surface.U2"] = "no"
    answers["L_unattended_supervision.S2"] = "no"
    # Act
    result = _check_unattended(tmp_path, answers, "cross-axis-one-one")
    # Assert
    assert _unattended_axis(result, "L_unattended_surface").verdict == "revise"
    assert _unattended_axis(result, "L_unattended_supervision").verdict == "revise"
    assert result.conclusion == "REVISE"
    assert result.blocked_from is None


def test_check_実行面軸yesかつ監督面軸全noの場合_相殺されずBLOCKすること(tmp_path):
    """A full surface axis must not mask an empty supervision axis.

    Averaged into a single 7-question axis these answers would score 4/7 and
    the three missing supervision controls would compensate against the
    surface answers. Scored as two axes, surface passes and supervision
    blocks — the distinction this overlay's split exists to preserve.
    """
    # Arrange
    answers = _merged_all_yes_unattended_answers()
    for qid in ("L_unattended_supervision.S1", "L_unattended_supervision.S2",
                "L_unattended_supervision.S3"):
        answers[qid] = "no"
    # Act
    result = _check_unattended(tmp_path, answers, "unattended-split")
    # Assert
    assert _unattended_axis(result, "L_unattended_surface").verdict == "pass"
    assert _unattended_axis(result, "L_unattended_supervision").verdict == "block"
    assert result.conclusion == "BLOCK"
    assert all(layer.verdict == "pass" for layer in result.layers)
    assert result.blocked_from is None


def test_check_unattendedで未回答の場合_unknownが0点として分母に残ること(tmp_path):
    # Arrange: leave U2 unanswered — unknown must count against the axis
    answers = _merged_all_yes_unattended_answers()
    del answers["L_unattended_surface.U2"]
    # Act
    result = _check_unattended(tmp_path, answers, "unattended-unknown")
    # Assert
    axis = _unattended_axis(result, "L_unattended_surface")
    assert axis.verdict == "revise"
    assert "L_unattended_surface.U2" in axis.unknown_ids
    assert result.conclusion == "REVISE"


def test_check_同梱unattendedサンプル3種の場合_基盤差が判定に表面化すること():
    """Freeze the shipped comparison samples' verdicts.

    Same fictional organization, same task, three execution platforms. The
    difference shown is how far each platform's guarantees can be confirmed
    (public evidence or own measurement), surfaced by the two axes.
    """
    # Arrange
    from conftest import (
        sample_unattended_chatgpt_tasks_path,
        sample_unattended_cowork_path,
        sample_unattended_selfhosted_path,
    )
    expectations = [
        (sample_unattended_cowork_path(), "revise", "revise", "REVISE"),
        (sample_unattended_chatgpt_tasks_path(), "block", "block", "BLOCK"),
        (sample_unattended_selfhosted_path(), "pass", "block", "BLOCK"),
    ]
    for path, surface, supervision, conclusion in expectations:
        # Act
        result = cr.check(path, overlay_paths=[_unattended_overlay_path()])
        # Assert
        assert all(layer.verdict == "pass" for layer in result.layers), path.name
        assert _unattended_axis(result, "L_unattended_surface").verdict == surface, path.name
        assert _unattended_axis(result, "L_unattended_supervision").verdict == supervision, path.name
        assert result.conclusion == conclusion, path.name
        assert result.blocked_from is None, path.name

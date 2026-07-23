"""SDD task dependency graph and waves."""

from __future__ import annotations

from core.sdd.models import SpecTask
from core.sdd.task_graph import (
    build_task_graph,
    format_graph_summary,
    ready_task_ids,
)
from core.sdd.tasks import parse_tasks_markdown


def test_parse_depends_on_field():
    md = """# Tasks

- [ ] 1.1 Base
  - **assignee:** `coder`
  - **depends_on:**

- [ ] 1.2 Next
  - **assignee:** `coder`
  - **depends_on:** `1.1`

- [ ] 1.3 Multi
  - **assignee:** `main`
  - **depends_on:** 1.1, 1.2
"""
    tasks = parse_tasks_markdown(md)
    by_id = {t.id: t for t in tasks}
    assert by_id["1.1"].depends_on == []
    assert by_id["1.2"].depends_on == ["1.1"]
    assert by_id["1.3"].depends_on == ["1.1", "1.2"]


def test_infer_sequential_same_section():
    tasks = [
        SpecTask(id="1.1", text="1.1 a", assignee="coder"),
        SpecTask(id="1.2", text="1.2 b", assignee="coder"),
        SpecTask(id="2.1", text="2.1 c", assignee="coder"),
    ]
    g = build_task_graph(tasks, infer_sequential=True)
    assert g.depends_on["1.2"] == ["1.1"]
    assert g.depends_on["2.1"] == []  # different section
    assert ready_task_ids(g) == ["1.1", "2.1"]
    assert g.waves[0] == ["1.1", "2.1"]
    assert g.waves[1] == ["1.2"]


def test_explicit_depends_overrides_infer():
    tasks = [
        SpecTask(id="1.1", text="1.1 a", assignee="coder"),
        SpecTask(
            id="1.2",
            text="1.2 b",
            assignee="coder",
            depends_on=["2.1"],
        ),
        SpecTask(id="2.1", text="2.1 c", assignee="coder"),
    ]
    g = build_task_graph(tasks, infer_sequential=True)
    assert g.depends_on["1.2"] == ["2.1"]
    assert ready_task_ids(g) == ["1.1", "2.1"]


def test_done_prereq_unblocks():
    tasks = [
        SpecTask(id="1.1", text="1.1 a", done=True, assignee="coder"),
        SpecTask(
            id="1.2",
            text="1.2 b",
            assignee="coder",
            depends_on=["1.1"],
        ),
    ]
    g = build_task_graph(tasks)
    assert ready_task_ids(g) == ["1.2"]
    assert format_graph_summary(g)


def test_cycle_reported():
    tasks = [
        SpecTask(id="1.1", text="a", depends_on=["1.2"]),
        SpecTask(id="1.2", text="b", depends_on=["1.1"]),
    ]
    g = build_task_graph(tasks, infer_sequential=False)
    assert any("cycle" in e.lower() for e in g.errors)

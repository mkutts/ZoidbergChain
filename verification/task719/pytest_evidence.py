"""Record exact selected/deselected node IDs and actual outcomes without changing tests."""
import json
import os
from pathlib import Path

STATE = dict(collected=[], deselected=[], reports=[])


def pytest_collection_modifyitems(items):
    STATE['collected'] = [dict(nodeid=i.nodeid, line=i.location[1] + 1) for i in items]


def pytest_deselected(items):
    STATE['deselected'].extend(i.nodeid for i in items)


def pytest_runtest_logreport(report):
    if report.when == 'call' or report.failed or report.skipped:
        STATE['reports'].append(dict(nodeid=report.nodeid, when=report.when, outcome=report.outcome,
                                     detail=str(report.longrepr) if report.longrepr else None))


def pytest_sessionfinish(session, exitstatus):
    STATE['exitstatus'] = int(exitstatus)
    Path(os.environ['TASK719_OUTCOMES']).write_text(json.dumps(STATE, indent=2) + '\n', encoding='utf-8')

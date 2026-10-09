"""CLI:  python -m runbook_copilot.agent --env dev --namespace lab-oomkilled --incident "pod keeps restarting"

The environment decides everything: `--env dev` loads policies/dev.yaml (act) and `--env prod` loads policies/prod.yaml
(advise). The kube identity comes from --kubeconfig/--kube-context (the operator's choice), never from the model.
Exit code: 0 resolved / no_problem / advised, 1 error, 2 anything else (escalated, denied, partial, ...).
"""
from __future__ import annotations

import argparse
import sys

from ..config import get_settings
from ..llm.client import make_llm
from ..retrieval.search import Retriever
from ..telemetry import setup_telemetry
from .audit import AuditLog
from .loop import Agent
from .policy import Policy
from .runner import KubectlRunner


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m runbook_copilot.agent", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", choices=["dev", "prod"], required=True)
    ap.add_argument("--namespace", "-n", required=True)
    ap.add_argument("--incident", required=True, help="what the user sees, in their own words")
    ap.add_argument("--kubeconfig", help="kubeconfig bound to this environment's identity (see deploy/scripts/agent-access.sh)")
    ap.add_argument("--kube-context")
    ap.add_argument("--policy", help="path to a policy file (default: policies/<env>.yaml)")
    a = ap.parse_args(argv)

    s = get_settings()
    tel = setup_telemetry(s)
    runner = KubectlRunner(a.kube_context, a.kubeconfig)
    try:
        agent = Agent(Retriever.load(s), make_llm(s), Policy.load(a.policy or a.env), runner, settings=s,
                      audit=AuditLog(s.agent_audit_path), telemetry=tel, kube_context=runner.current_context())
    except (RuntimeError, FileNotFoundError) as e:  # missing kubectl, LLM key, or corpus: say so plainly
        print(f"cannot start: {e}", file=sys.stderr)
        return 1
    rep = agent.run(a.namespace, a.incident)
    print(rep.model_dump_json(indent=2))
    if rep.status in ("resolved", "no_problem", "advised"):
        return 0
    return 1 if rep.status == "error" else 2


if __name__ == "__main__":
    sys.exit(main())

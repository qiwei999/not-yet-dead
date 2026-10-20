"""File-based ninnin extraction and verification; no model call on import."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys


def main(argv=None):
    if hasattr(sys.stdout,"reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description="ninnin: evidence-based progress and direction handoff")
    sub=parser.add_subparsers(dest="command",required=True)
    extract=sub.add_parser("extract",help="Extract a portable handoff from a saved task snapshot")
    extract.add_argument("--snapshot",required=True,type=Path)
    extract.add_argument("--checkpoint",type=Path)
    extract.add_argument("--workspace",type=Path)
    extract.add_argument("--out",required=True,type=Path)
    export=sub.add_parser("export",help="Export one persisted workbench task")
    export.add_argument("--root",required=True,type=Path)
    export.add_argument("--task",required=True)
    export.add_argument("--out",required=True,type=Path)
    verify=sub.add_parser("verify",help="Verify handoff manifest and artifact checksums")
    verify.add_argument("path",type=Path)
    status=sub.add_parser("status",help="Read persisted collaboration rooms")
    status.add_argument("--root",required=True,type=Path)
    resume=sub.add_parser("resume",help="Inspect current project files and optional historical differences, read-only")
    resume.add_argument("--workspace",required=True,type=Path)
    resume.add_argument("--state",default="STATE.md")
    resume.add_argument("--recovery")
    resume.add_argument("--approvals",default="DECISIONS.md")
    resume.add_argument("--handoff",type=Path)
    resume.add_argument("--max-chars",type=int,default=8000)
    sub.add_parser("doctor",help="Check the local handoff and resume installation without model calls")
    args=parser.parse_args(argv)
    try:
        if args.command=="resume":
            from .resume import inspect_project
            result=inspect_project(args.workspace,handoff=args.handoff,state=args.state,
                                   recovery=args.recovery,approvals=args.approvals,max_chars=args.max_chars)
        elif args.command=="doctor":
            from .resume import inspect_project
            from .handoff import verify_handoff
            core=Path(__file__).absolute().parent
            required={name:(core/name).is_file() for name in ("cli.py","handoff.py","workspace.py","resume.py")}
            result={"mode":"read_only_installation_check","standalone_revision":"0.3.0",
                    "python_executable":sys.executable,"python_version":sys.version.split()[0],
                    "core_path":str(core),"required_files":required,
                    "local_handoff_available":all(required.values()),
                    "commands":["extract","export","verify","status","resume","doctor"]}
        elif args.command=="verify":
            from .handoff import verify_handoff
            result=verify_handoff(args.path)
        elif args.command=="extract":
            from .handoff import export_handoff
            snapshot=json.loads(args.snapshot.read_text(encoding="utf-8-sig"))
            checkpoint=json.loads(args.checkpoint.read_text(encoding="utf-8-sig")) if args.checkpoint else None
            result={"path":str(export_handoff(snapshot,checkpoint,args.out,workspace=args.workspace))}
        else:
            from .store import Store
            store=Store(args.root)
            if args.command=="status":
                result={"rooms":store.rooms()}
            else:
                from .handoff import export_handoff
                task=store.task(args.task)
                snap={"task":task,"events":[e for e in store.events(task["room_id"]) if e.get("task_id")==args.task]}
                result={"path":str(export_handoff(snap,store.get_checkpoint(args.task),args.out,workspace=args.root/"workspaces"/args.task))}
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (OSError,ValueError,PermissionError,KeyError) as error:
        print(json.dumps({"error":str(error),"status":"not_completed"},ensure_ascii=False),file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())

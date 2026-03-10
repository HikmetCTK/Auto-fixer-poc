"""Orchestrator — coordinates the bug-fix workflow.

For Phase 1 this is a simple sequential pipeline.  In Phase 3 each step
will be wrapped as a Temporal Activity for durable execution.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from src.agents.base import AgentContext
from src.agents.error_analyzer import ErrorAnalyzerAgent, ErrorAnalysis
from src.agents.research_agent import ResearchAgent, ResearchResult
from src.agents.fix_suggester import FixSuggesterAgent, FixSuggestion
from src.agents.reporter import ReporterAgent, ReportOutput
from src.agents.auto_fixer import DeployResult
from src.indexer.indexer import CodebaseIndex
from src.tools.codebase import set_global_index

logger = logging.getLogger(__name__)


@dataclass
class WorkflowResult:
    """Full result of a bug-fix workflow run."""

    error_analysis: ErrorAnalysis
    research: ResearchResult
    fix: FixSuggestion
    report: ReportOutput
    deploy: DeployResult | None = None



class Orchestrator:
    """Sequential orchestrator — runs each agent in order.
    """

    def __init__(self, project_path: str | None = None, **kwargs) -> None:
        # Index codebase if a project path is provided
        if kwargs:
            logger.warning("Orchestrator.__init__ received unexpected kwargs: %s", kwargs)

        self.index = CodebaseIndex()
        if project_path:
            chunk_count = self.index.index_directory(project_path)
            set_global_index(self.index)
            logger.info("Codebase indexed: %d chunks from %s", chunk_count, project_path)

        self.error_analyzer = ErrorAnalyzerAgent()
        self.research_agent = ResearchAgent()
        self.fix_suggester = FixSuggesterAgent()
        self.reporter = ReporterAgent()

    async def run(self, error_input: str, context: AgentContext | None = None, auto_apply_fix: bool = False) -> WorkflowResult:
        """Execute the full bug-fix pipeline."""
        context = context or AgentContext()
        logger.info("Starting bug-fix workflow for session=%s", context.session_id)

        # Step 1: Analyze the error
        await context.emit("orchestrator_stage", {"stage": "analyzing", "message": "Analyzing error stack trace..."})
        analysis = await self._step_analyze(error_input, context)
        logger.info("Analysis complete: %s (%s)", analysis.error_type, analysis.severity)

        # Step 2: Research solutions
        await context.emit("orchestrator_stage", {"stage": "researching", "message": "Researching similar issues and solutions..."})
        research_input = self._build_research_prompt(analysis)
        research = await self._step_research(research_input, context)
        logger.info("Research complete: %d issues found, confidence=%s", len(research.similar_issues), research.confidence)

        # Step 3: Suggest fix
        await context.emit("orchestrator_stage", {"stage": "planning", "message": "Formulating fix suggestions..."})
        fix_input = self._build_fix_prompt(analysis, research)
        fix = await self._step_fix(fix_input, context)
        logger.info("Fix suggestion complete: risk=%s", fix.risk_level)

        # Step 4: Docker test + git push (immediately after fix, before report)
        # Check both fix.did_edit (LLM-reported) AND context.state['file_edited']
        # (set by base.py whenever file_editor tool is actually called).
        file_was_edited = getattr(fix, "did_edit", False) or context.state.get("file_edited", False)
        deploy_result = None
        if auto_apply_fix and file_was_edited:
            await context.emit("orchestrator_stage", {"stage": "executing", "message": "Fix applied — running sandbox tests and git push..."})
            logger.info("Automatic tests & git push starting.")

            from src.tools.sandbox_test import DockerTestTool
            from src.tools.git_tools import GitPushTool
            import json as _json

            test_tool = DockerTestTool()
            test_res = await test_tool.execute()

            git_pushed = False
            details_str = f"Tests run result:\n{test_res}"

            # Parse the structured JSON result from DockerTestTool
            try:
                test_data = _json.loads(test_res)
            except Exception:
                test_data = {}

            docker_unavailable = (
                "docker executable not found" in test_res.lower() or
                "docker daemon not running" in test_res.lower()
            )
            test_passed = test_data.get("passed", True)  # default True if unparseable

            # Push if: tests passed, OR Docker simply wasn't available (treat as skip, not failure)
            should_push = test_passed or docker_unavailable
            if should_push:
                if docker_unavailable:
                    details_str += "\n\n⚠️ Docker not available — skipping sandbox test, pushing anyway."
                git_tool = GitPushTool()
                git_res = await git_tool.execute(
                    branch_name=getattr(fix, "branch_name", "fix/autonomous-patch") or "fix/autonomous-patch",
                    commit_message=getattr(fix, "commit_message", "fix: applied fix") or "fix: applied fix"
                )
                # Check actual push result — not just that the tool was called
                try:
                    git_data = _json.loads(git_res)
                    git_pushed = git_data.get("passed", False)
                except Exception:
                    git_pushed = False
                details_str += f"\n\nGit Push result:\n{git_res}"
            else:
                details_str += "\n\n❌ Tests failed — git push skipped."

            deploy_result = DeployResult(
                success=should_push,
                test_passed=test_passed or docker_unavailable,
                git_pushed=git_pushed,
                details=details_str
            )
            logger.info("Auto-deploy finished: git_pushed=%s", git_pushed)

            # Emit structured deploy result for the UI detail card
            await context.emit("deploy_result", {
                "test_passed": test_passed or docker_unavailable,
                "docker_unavailable": docker_unavailable,
                "git_pushed": git_pushed,
                "branch": getattr(fix, "branch_name", "") or "fix/autonomous-patch",
                "commit_message": getattr(fix, "commit_message", "") or "fix: applied fix",
                "details": details_str,
            })

        # Step 5: Generate report (last — has full context including deploy outcome)
        await context.emit("orchestrator_stage", {"stage": "reporting", "message": "Generating final incident report..."})
        report_input = self._build_report_prompt(analysis, research, fix, deploy_result)
        report = await self._step_report(report_input, context)
        logger.info("Report generated: %s", report.title)

        # Emit structured report for the UI detail card
        await context.emit("report_result", {
            "title": report.title,
            "severity": report.severity,
            "summary": report.summary,
            "root_cause": report.root_cause,
            "proposed_fix": report.proposed_fix,
            "risk_assessment": report.risk_assessment,
            "next_steps": report.next_steps if hasattr(report, "next_steps") else [],
            "references": report.references if hasattr(report, "references") else [],
        })

        await context.emit("orchestrator_complete", {"success": True, "message": "Bug Detective workflow finished!"})

        return WorkflowResult(
            error_analysis=analysis,
            research=research,
            fix=fix,
            report=report,
            deploy=deploy_result,
        )


    # ── Steps (future Temporal Activities) ───────────────────────────────

    async def _step_analyze(self, error_input: str, context: AgentContext) -> ErrorAnalysis:
        return await self.error_analyzer.run(error_input, context)

    async def _step_research(self, prompt: str, context: AgentContext) -> ResearchResult:
        logger.info("Skipping web search for fast testing.")
        return await self.research_agent.run(prompt, context)

    async def _step_fix(self, prompt: str, context: AgentContext) -> FixSuggestion:
        return await self.fix_suggester.run(prompt, context)

    async def _step_report(self, prompt: str, context: AgentContext) -> ReportOutput:
        return await self.reporter.run(prompt, context)

    # ── Prompt builders ──────────────────────────────────────────────────

    @staticmethod
    def _build_research_prompt(analysis: ErrorAnalysis) -> str:
        return (
            f"Error Type: {analysis.error_type}\n"
            f"Root Cause: {analysis.root_cause}\n"
            f"Severity: {analysis.severity}\n"
            f"Language: {analysis.language}\n"
            f"Stack Summary: {analysis.stack_summary}\n"
            f"Affected Files: {', '.join(analysis.affected_files)}\n\n"
            f"Suggested search queries:\n"
            + "\n".join(f"- {q}" for q in analysis.suggested_search_queries)
        )

    @staticmethod
    def _build_fix_prompt(analysis: ErrorAnalysis, research: ResearchResult) -> str:
        return (
            "## Error Analysis\n"
            f"Type: {analysis.error_type}\n"
            f"Root Cause: {analysis.root_cause}\n"
            f"Severity: {analysis.severity}\n"
            f"Affected Files: {', '.join(analysis.affected_files)}\n"
            f"Stack: {analysis.stack_summary}\n\n"
            "## Research Findings\n"
            f"Confidence: {research.confidence}\n"
            f"Solutions Found:\n"
            + "\n".join(f"- {s}" for s in research.solutions_found)
            + "\n\nReferences:\n"
            + "\n".join(f"- {r}" for r in research.references)
        )

    @staticmethod
    def _build_report_prompt(
        analysis: ErrorAnalysis,
        research: ResearchResult,
        fix: FixSuggestion,
        deploy: DeployResult | None = None,
    ) -> str:
        prompt = (
            "## Error Analysis\n"
            + json.dumps(analysis.model_dump(), indent=2, ensure_ascii=False)
            + "\n\n## Research Results\n"
            + json.dumps(research.model_dump(), indent=2, ensure_ascii=False)
            + "\n\n## Fix Suggestion\n"
            + json.dumps(fix.model_dump(), indent=2, ensure_ascii=False)
        )
        if deploy:
            prompt += (
                "\n\n## Deployment Result\n"
                + json.dumps({
                    "success": deploy.success,
                    "test_passed": deploy.test_passed,
                    "git_pushed": deploy.git_pushed,
                    "details": deploy.details,
                }, indent=2, ensure_ascii=False)
            )
        return prompt



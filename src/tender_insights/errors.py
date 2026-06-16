from __future__ import annotations


class TenderInsightsError(Exception):
    """Base error for tender_insights."""


class WorkspaceResolveError(TenderInsightsError):
    pass


class AnalysisError(TenderInsightsError):
    pass


class LLMExtractionError(AnalysisError):
    pass

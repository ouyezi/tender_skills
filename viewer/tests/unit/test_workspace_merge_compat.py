from tender_insights.common.workspace_merge import merge_workspaces, validate_merged_workspace

from viewer.services.workspace_merge import merge_workspaces as viewer_merge
from viewer.services.workspace_merge import validate_merged_workspace as viewer_validate


def test_viewer_reexports_workspace_merge() -> None:
    assert viewer_merge is merge_workspaces
    assert viewer_validate is validate_merged_workspace

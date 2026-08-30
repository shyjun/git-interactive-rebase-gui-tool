# Re-export all public and private symbols from sub-modules so that
# ``from lib.git_helpers import X`` continues to work unchanged.

from .core import (
    _parse_log_records,
    _attach_full_messages,
    _parse_reflog_records,
    _parse_stash_records,
    _git_capture,
    _pad_diff_separators,
)

from .history import (
    get_git_history,
    get_git_history_fast,
    get_commit_stats,
    get_branch_history,
    get_file_history,
    get_reflog_history,
    get_tags_history,
    get_stash_history,
)

from .branches import (
    get_current_branch,
    get_local_branches_map,
    get_tags_map,
    get_head_sha,
    get_full_head_sha,
    get_root_commit,
    get_recent_history_start,
    get_branch_base_info,
    commit_exists,
    branch_exists,
    normalize_branch_ref,
    get_branch_names,
    resolve_ref,
)

from .commits import (
    get_commit_diff,
    get_full_commit_message,
    get_commit_subject,
    get_commit_metadata_and_message,
    get_commit_metadata,
    get_commit_files,
    get_commit_file_stats,
    get_commit_files_with_status,
    get_rename_diff_in_commit,
    get_file_diff_only_in_commit,
)

from .diffs import (
    get_merge_base,
    get_diff_between,
    get_files_between,
    get_file_diff_between,
    get_file_stats_between,
    get_unstaged_diff,
    get_unstaged_file_stats,
    get_unstaged_file_diff,
    get_difftool_name,
    is_file_unchanged_between,
    is_file_working_tree_clean,
    run_difftool_temp_files,
    run_difftool_direct,
    run_configured_difftool,
)

from .stash import (
    STASH_NOTHING_STASHED,
    stash_changes,
    discard_changes,
    get_stash_subject,
    stash_pop,
    stash_pop_can_apply,
    get_stash_status,
    _stash_index,
    stash_apply,
    stash_drop,
    _rollback_merge,
    merge_into_stash,
)

from .status import (
    has_uncommitted_changes,
    cherry_pick_in_progress,
    rebase_in_progress,
    classify_cherry_pick_failure,
    classify_tracked_changes,
    get_unstaged_files,
)

from .commit_ops import (
    commit_file,
    get_revert_commit_message,
    bulk_commit_all,
    amend_with_head,
    stage_files,
    commit_staged,
    amend_staged,
    apply_patch_to_index,
    _parse_patch_commit_message,
    _count_format_patch_sections,
    apply_patch_file,
)

from .update import (
    GIT_REPO_URL,
    _run_capture,
    _is_git_install,
    _read_version_sha,
    _write_app_version,
    _detect_default_branch,
    build_update_command,
    perform_self_update,
)

from .blame import (
    _parse_blame_porcelain,
    get_git_blame,
)

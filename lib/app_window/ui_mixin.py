from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QFont, QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QSplitter, QCheckBox, QToolButton, QMenu,
    QWidgetAction, QRadioButton, QGroupBox, QSizePolicy,
    QStatusBar, QListWidget, QListWidgetItem, QTabWidget, QTextEdit, QPushButton,
)
from lib.app_window.commit_list import CommitListWidget
from lib.app_window.delegates import CommitItemDelegate
from lib.app_window.helpers import MATCH_ROLE, _diff_search_matches
from lib.widgets import (
    DiffView, DiffSearchBar, DiffHighlighter, StatsItemDelegate,
    FILE_ENTRY_ROLE, BrowseDimOverlay,
)
from lib.git_helpers import (
    get_commit_files_with_status, get_commit_diff, get_commit_metadata_and_message,
    get_file_diff_only_in_commit, get_commit_file_stats,
)


class UIMixin:
    """setup_ui and related UI methods for GitInteractiveRebaseApp."""

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Use our custom list widget
        self.list_widget = CommitListWidget(self)
        self.list_widget.setItemDelegate(CommitItemDelegate(self.list_widget))
        self.update_font()
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        if self.browse_reflog or self.browse_tags:
            self.list_widget.customContextMenuRequested.connect(self.show_reflog_context_menu)
        elif self.browse_stash:
            self.list_widget.customContextMenuRequested.connect(self.show_stash_context_menu)
        elif self.browse_mode:
            self.list_widget.customContextMenuRequested.connect(self.show_browse_context_menu)
        else:
            self.list_widget.customContextMenuRequested.connect(self.show_context_menu)

        # Search / Filter Bar row
        search_row_widget = QWidget()
        search_row_layout = QHBoxLayout(search_row_widget)
        search_row_layout.setContentsMargins(0, 0, 0, 0)
        search_row_layout.setSpacing(4)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search commits (SHA or Message)...")
        self.search_edit.setToolTip("Search commits by SHA or message.")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self.filter_commits)
        search_row_layout.addWidget(self.search_edit, 1)  # stretch to fill

        # Search Options dropdown (HOW to search: Match Case / Whole Word / Display Only Matching)
        self.search_options_btn = QToolButton()
        self.search_options_btn.setText("Search Options ▼")
        self.search_options_btn.setToolTip("Search options: Match Case, Whole Word, Display Only Matching")
        self.search_options_btn.setPopupMode(QToolButton.InstantPopup)
        self.search_options_btn.setMinimumHeight(28)
        # The text already carries a "▼", so hide Qt's extra menu indicator at
        # the bottom-right of the button.
        self.search_options_btn.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0px; }")
        self.search_options_menu = QMenu(self)
        self.search_match_case_action = QAction("Match Case", self)
        self.search_match_case_action.setCheckable(True)
        self.search_match_case_action.setToolTip("Make search case-sensitive")
        self.search_whole_word_action = QAction("Whole Word", self)
        self.search_whole_word_action.setCheckable(True)
        self.search_whole_word_action.setToolTip("Match whole words only")
        self.search_display_only_action = QAction("Display Only Matching", self)
        self.search_display_only_action.setCheckable(True)
        self.search_display_only_action.setToolTip("Hide commits that do not match the search")
        self.search_options_menu.addAction(self.search_match_case_action)
        self.search_options_menu.addAction(self.search_whole_word_action)
        self.search_options_menu.addAction(self.search_display_only_action)
        self.search_options_btn.setMenu(self.search_options_menu)
        self.search_match_case_action.toggled.connect(self._on_search_option_changed)
        self.search_whole_word_action.toggled.connect(self._on_search_option_changed)
        self.search_display_only_action.toggled.connect(self._on_search_option_changed)
        search_row_layout.addWidget(self.search_options_btn)

        # Compact filter controls: "Filter:" label + three checkboxes
        filter_label = QLabel("Filter:")
        filter_label.setStyleSheet("font-size: 11px; color: gray;")
        search_row_layout.addWidget(filter_label)

        self.filter_by_files_cb = QCheckBox("Filenames")
        self.filter_by_files_cb.setChecked(False)
        self.filter_by_files_cb.setToolTip("Filter commits by modified filenames")
        self.filter_by_files_cb.stateChanged.connect(lambda: self.filter_commits(self.search_edit.text()))
        search_row_layout.addWidget(self.filter_by_files_cb)

        self.filter_by_diff_cb = QCheckBox("Diff")
        self.filter_by_diff_cb.setChecked(False)
        self.filter_by_diff_cb.setToolTip("Filter commits by diff content (min 3 chars, debounced)")
        self.filter_by_diff_cb.stateChanged.connect(lambda: self.filter_commits(self.search_edit.text()))
        search_row_layout.addWidget(self.filter_by_diff_cb)

        self.filter_by_author_cb = QCheckBox("Author")
        self.filter_by_author_cb.setChecked(False)
        self.filter_by_author_cb.setToolTip("Filter commits by author name or email")
        self.filter_by_author_cb.stateChanged.connect(lambda: self.filter_commits(self.search_edit.text()))
        search_row_layout.addWidget(self.filter_by_author_cb)

        # Inline status label shown during diff search (timer and style constants
        # live in CommitFilterController).
        self._diff_status_label = QLabel("Searching diffs...")
        self._diff_status_label.setVisible(False)
        search_row_layout.addWidget(self._diff_status_label)

        layout.addWidget(search_row_widget)

        # Main Splitter
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.list_widget.setMinimumWidth(150)

        # Insert Left Panel logic embedding explicit Checkboxes
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addWidget(self.list_widget, 1)

        self.main_splitter.addWidget(left_panel)

        # Right Side Panel
        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Right Side Splitter (Vertical)
        self.right_splitter = QSplitter(Qt.Vertical)

        # Top half: Header + Message
        self.right_top_widget = QWidget()
        right_top_layout = QVBoxLayout(self.right_top_widget)
        right_top_layout.setContentsMargins(0, 0, 0, 0)

        self.side_commit_label = QLabel("Select a commit to view details")
        self.side_commit_label.setTextFormat(Qt.RichText)
        right_top_layout.addWidget(self.side_commit_label)

        self.side_commit_msg = QTextEdit()
        self.side_commit_msg.setReadOnly(True)
        self.side_commit_msg.setMinimumHeight(60)
        right_top_layout.addWidget(self.side_commit_msg)

        self.right_splitter.addWidget(self.right_top_widget)

        # Bottom half: Diff Tab Widget
        self.diff_tab_widget = QTabWidget()
        self.diff_tab_widget.setMinimumHeight(150)

        # Page 0: Plain Diff
        plain_diff_widget = QWidget()
        plain_diff_layout = QVBoxLayout(plain_diff_widget)
        plain_diff_layout.setContentsMargins(0, 0, 0, 0)
        plain_diff_layout.setSpacing(0)

        self.side_diff_view = DiffView()
        self.side_diff_view.setReadOnly(True)

        self.plain_diff_search = DiffSearchBar(target_view=self.side_diff_view, parent=plain_diff_widget)
        # Search bar is visible by default now as requested

        plain_diff_layout.addWidget(self.plain_diff_search)
        plain_diff_layout.addWidget(self.side_diff_view)

        self.diff_tab_widget.addTab(plain_diff_widget, "Plain Diff")

        # Page 1: Filewise Diff
        filewise_widget = QWidget()
        filewise_layout = QVBoxLayout(filewise_widget)
        filewise_layout.setContentsMargins(0, 0, 0, 0)

        self.filewise_splitter = QSplitter(Qt.Vertical)

        # File list
        self.filewise_file_list = QListWidget()
        self.filewise_file_list.setMinimumHeight(60)
        self.filewise_file_list.currentTextChanged.connect(self.on_filewise_file_selected)
        self.filewise_file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.filewise_file_list.customContextMenuRequested.connect(self.show_filewise_context_menu)
        # Install stats delegate (colors updated when theme changes)
        colors = self.current_theme_colors if hasattr(self, 'current_theme_colors') else {"added": "#22863a", "removed": "#cb2431"}
        self.filewise_stats_delegate = StatsItemDelegate(
            added_color=colors.get("added", "#22863a"),
            removed_color=colors.get("removed", "#cb2431"),
            parent=self.filewise_file_list
        )
        self.filewise_file_list.setItemDelegate(self.filewise_stats_delegate)

        # File diff
        self.filewise_diff_view = DiffView()
        self.filewise_diff_view.setReadOnly(True)
        self.filewise_diff_view.setMinimumHeight(100)

        # Apply highlighter
        self.filewise_highlighter = DiffHighlighter(self.filewise_diff_view.document())

        filewise_right_widget = QWidget()
        filewise_right_layout = QVBoxLayout(filewise_right_widget)
        filewise_right_layout.setContentsMargins(0, 0, 0, 0)
        filewise_right_layout.setSpacing(0)

        self.filewise_diff_search = DiffSearchBar(target_view=self.filewise_diff_view, parent=filewise_right_widget)

        filewise_right_layout.addWidget(self.filewise_diff_search)
        filewise_right_layout.addWidget(self.filewise_diff_view)

        self.filewise_splitter.addWidget(self.filewise_file_list)
        self.filewise_splitter.addWidget(filewise_right_widget)
        self.filewise_splitter.setCollapsible(0, False)
        self.filewise_splitter.setCollapsible(1, False)
        self.filewise_splitter.setSizes([100, 300]) # default split

        filewise_layout.addWidget(self.filewise_splitter)
        # Keep a strong reference: in file-log mode the tab page is not added to
        # the tab widget, so it would otherwise be garbage-collected.
        self.filewise_widget = filewise_widget
        if not self.browse_file:
            self.diff_tab_widget.addTab(filewise_widget, "File-wise Diff")

        self.right_splitter.addWidget(self.diff_tab_widget)

        # Determine highlighting colors and initialize highlighter
        colors = self.current_theme_colors if hasattr(self, 'current_theme_colors') else {"added": "#a6e22e", "removed": "#f92672", "header": "#66d9ef", "separator": "#444444"}
        self.side_diff_highlighter = DiffHighlighter(self.side_diff_view.document(),
                                                   added_color=colors["added"],
                                                   removed_color=colors["removed"],
                                                   header_color=colors["header"])
        self.side_diff_view.set_separator_color(colors["separator"])

        # Add the vertical splitter to the right panel's layout
        right_layout.addWidget(self.right_splitter)

        # Set initial split sizes for top (message) and bottom (diff)
        self.right_splitter.setCollapsible(0, False)
        self.right_splitter.setCollapsible(1, False)
        self.right_splitter.setSizes([150, 650])

        self.right_panel.setMinimumWidth(150)

        self.right_panel.setVisible(not (self.browse_reflog or self.browse_tags))

        self.main_splitter.addWidget(self.right_panel)
        # default split ratio: history 60%, diff 40%
        self.main_splitter.setSizes([600, 400])

        layout.addWidget(self.main_splitter, 1)

        # In browse (read-only) mode use only the right-side pane for details;
        # no commit-viewer dialog on double-click. In reflog mode, double-click
        # opens the selected entry's commit history viewer.
        if self.browse_reflog or self.browse_tags:
            self.list_widget.itemDoubleClicked.connect(self.handle_reflog_show_log)
        elif not self.browse_mode:
            self.list_widget.itemDoubleClicked.connect(self.view_commit)
        self.list_widget.itemSelectionChanged.connect(self.on_selection_changed)

        self.diff_tab_widget.currentChanged.connect(self.on_diff_tab_changed)

        self.update_window_title()

        # Top Control Bar (single row of buttons)
        controls_layout = QHBoxLayout()
        controls_layout.setAlignment(Qt.AlignTop)

        # Theme dropdown menu button
        self.theme_menu_btn = QPushButton("Theme")
        self.theme_menu_btn.setToolTip("Switch between Dark and Light theme.")
        self._set_theme_icon(self.theme_menu_btn)
        theme_menu = QMenu(self.theme_menu_btn)
        self.dark_radio = QRadioButton("Dark Theme")
        self.light_radio = QRadioButton("Light Theme")
        self.dark_radio.toggled.connect(lambda: self.on_theme_toggled())
        self.light_radio.toggled.connect(lambda: self.on_theme_toggled())
        dark_action = QWidgetAction(theme_menu)
        dark_action.setDefaultWidget(self.dark_radio)
        light_action = QWidgetAction(theme_menu)
        light_action.setDefaultWidget(self.light_radio)
        theme_menu.addAction(dark_action)
        theme_menu.addAction(light_action)
        self.theme_menu_btn.setMenu(theme_menu)

        self.exit_viewer_mode_btn = QPushButton("Exit Viewer Mode")
        self.exit_viewer_mode_btn.setToolTip("Re-enable history-modifying operations.")
        self._set_exit_viewer_mode_icon(self.exit_viewer_mode_btn)
        self.exit_viewer_mode_btn.setVisible(self.viewer_mode and not self.browse_mode)
        self.rescan_btn = QPushButton("Rescan Repo")
        self.rescan_btn.setToolTip("Re-scan the repository and rebuild the commit list.")
        self._set_rescan_icon(self.rescan_btn)
        self.repo_btn = QPushButton("Repo")
        self.repo_btn.setToolTip("Repository actions: PR diff, cherry-pick, browse branch.")
        self.repo_btn.setMenu(self._build_repo_menu())
        self._set_repo_icon(self.repo_btn)
        self.pop_stash_btn = QPushButton("Pop app created stash")
        self.pop_stash_btn.setToolTip("Pop the app-created stash (git stash pop).")
        self._set_pop_stash_icon(self.pop_stash_btn)
        self.pop_stash_btn.setVisible(False)
        self.undo_btn = QPushButton("Undo")
        self.undo_btn.setToolTip("Undo the last operation (Ctrl+Z).")
        self._set_undo_icon(self.undo_btn)
        self.undo_btn.setEnabled(False)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setToolTip("Reload the commit history from git.")
        self._set_refresh_icon(self.refresh_btn)
        self.exit_btn = QPushButton("Exit")
        self.exit_btn.setToolTip("Close the application.")
        self._set_exit_icon(self.exit_btn)
        self.exit_btn.setStyleSheet("color: red; font-weight: bold;")

        self.failsafe_btn = QPushButton("")
        self.failsafe_btn.setToolTip("Reset hard to START_TIME_HEAD.")
        self.best_commit_btn = QPushButton("Reset Hard to BEST_COMMITID (Not Set)")
        self.best_commit_btn.setToolTip("Reset hard to the marked BEST_COMMITID.")
        self.best_commit_btn.setEnabled(False)
        self.custom_reset_btn = QPushButton("Enter commit id to reset hard to")
        self.custom_reset_btn.setToolTip("Reset hard to a commit id you enter.")

        for btn in [self.exit_viewer_mode_btn, self.rescan_btn, self.repo_btn, self.pop_stash_btn, self.undo_btn, self.refresh_btn, self.exit_btn, self.theme_menu_btn]:
            btn.setMinimumHeight(40)
            btn.setMinimumWidth(100)
        self.failsafe_btn.setMinimumHeight(40)
        self.best_commit_btn.setMinimumHeight(40)
        self.custom_reset_btn.setMinimumHeight(40)

        self.exit_viewer_mode_btn.clicked.connect(self.handle_exit_viewer_mode)
        self.rescan_btn.clicked.connect(self.handle_rescan_repo)
        self.pop_stash_btn.clicked.connect(self.handle_pop_managed_stash)
        self.undo_btn.clicked.connect(self.handle_undo)
        self.refresh_btn.clicked.connect(self.handle_manual_refresh)
        self.failsafe_btn.clicked.connect(self.handle_failsafe_reset)
        self.best_commit_btn.clicked.connect(self.handle_best_commit_reset)
        self.custom_reset_btn.clicked.connect(self.handle_custom_reset)
        self.exit_btn.clicked.connect(self.close)

        # Single row of main buttons
        controls_layout.addWidget(self.theme_menu_btn)
        self.browse_select_btn = QPushButton("Select commits")
        self.browse_select_btn.setToolTip("Enter checkbox selection mode on the commit list.")
        self.browse_select_btn.clicked.connect(self.enter_browse_multi_select)
        self.browse_cancel_select_btn = QPushButton("Cancel selection")
        self.browse_cancel_select_btn.setToolTip("Exit checkbox selection mode.")
        self.browse_cancel_select_btn.setEnabled(False)
        self.browse_cancel_select_btn.clicked.connect(self.exit_browse_multi_select)
        for btn in [self.browse_select_btn, self.browse_cancel_select_btn]:
            btn.setMinimumHeight(40)
            btn.setMinimumWidth(100)
            btn.setVisible(bool(self.browse_branch))
        controls_layout.addWidget(self.browse_select_btn)
        controls_layout.addWidget(self.browse_cancel_select_btn)
        self.reflog_copy_sha_btn = QPushButton("Copy SHA to clipboard")
        self.reflog_copy_sha_btn.setToolTip("Copy the selected reflog entry's SHA to the clipboard.")
        self.reflog_copy_sha_btn.clicked.connect(self.handle_reflog_copy_sha)
        self.reflog_show_log_btn = QPushButton("Show log")
        self.reflog_show_log_btn.setToolTip("Open a read-only history viewer for the selected reflog entry's commit.")
        self.reflog_show_log_btn.clicked.connect(self.handle_reflog_show_log)
        for btn in [self.reflog_copy_sha_btn, self.reflog_show_log_btn]:
            btn.setMinimumHeight(40)
            btn.setMinimumWidth(100)
            btn.setVisible(bool(self.browse_reflog or self.browse_tags))
        controls_layout.addWidget(self.reflog_copy_sha_btn)
        controls_layout.addWidget(self.reflog_show_log_btn)
        self.stash_copy_sha_btn = QPushButton("Copy")
        self.stash_copy_sha_btn.setToolTip("Copy the selected stash's SHA to the clipboard.")
        self.stash_copy_sha_btn.clicked.connect(self.handle_stash_copy_sha)
        self.stash_apply_keep_btn = QPushButton("Apply + Keep")
        self.stash_apply_keep_btn.setToolTip("Apply the selected stash and keep it in the list.")
        self.stash_apply_keep_btn.clicked.connect(self.handle_stash_apply_keep_btn)
        self.stash_apply_drop_btn = QPushButton("Apply + Drop")
        self.stash_apply_drop_btn.setToolTip("Apply the selected stash and drop it after a successful apply.")
        self.stash_apply_drop_btn.clicked.connect(self.handle_stash_apply_drop_btn)
        self.stash_drop_btn = QPushButton("Drop")
        self.stash_drop_btn.setToolTip("Drop the selected stash (asks for confirmation).")
        self.stash_drop_btn.clicked.connect(self.handle_stash_drop_btn)
        for btn in [self.stash_copy_sha_btn, self.stash_apply_keep_btn,
                    self.stash_apply_drop_btn, self.stash_drop_btn]:
            btn.setMinimumHeight(40)
            btn.setMinimumWidth(100)
            btn.setVisible(bool(self.browse_stash))
        controls_layout.addWidget(self.stash_copy_sha_btn)
        controls_layout.addWidget(self.stash_apply_keep_btn)
        controls_layout.addWidget(self.stash_apply_drop_btn)
        controls_layout.addWidget(self.stash_drop_btn)
        controls_layout.addStretch()
        controls_layout.addWidget(self.pop_stash_btn)
        controls_layout.addWidget(self.repo_btn)
        controls_layout.addWidget(self.exit_viewer_mode_btn)
        self.browse_cherry_pick_btn = QPushButton("Cherry-pick selected commit(s)")
        self.browse_cherry_pick_btn.setToolTip(
            "Cherry-pick the currently selected commit (single) or the checked "
            "commits (in multi-select mode).")
        self.browse_cherry_pick_btn.clicked.connect(self.handle_browse_cherry_pick)
        self.browse_cherry_pick_btn.setMinimumHeight(40)
        self.browse_cherry_pick_btn.setMinimumWidth(100)
        self.browse_cherry_pick_btn.setVisible(bool(self.browse_branch))
        controls_layout.addWidget(self.browse_cherry_pick_btn)
        controls_layout.addWidget(self.rescan_btn)
        controls_layout.addWidget(self.undo_btn)
        controls_layout.addWidget(self.refresh_btn)
        controls_layout.addWidget(self.exit_btn)

        if self.browse_mode:
            for btn in [self.theme_menu_btn, self.repo_btn, self.rescan_btn, self.undo_btn]:
                btn.setVisible(False)

        layout.addLayout(controls_layout)

        # Add failsafe options as a distinct row below the other controls
        self.failsafe_group = QGroupBox("Fail-safe")
        self.failsafe_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        failsafe_layout = QHBoxLayout()
        failsafe_layout.addWidget(self.failsafe_btn)
        failsafe_layout.addWidget(self.best_commit_btn)
        failsafe_layout.addWidget(self.custom_reset_btn)
        self.failsafe_group.setLayout(failsafe_layout)
        layout.addWidget(self.failsafe_group)
        self.failsafe_group.setVisible(not self.browse_mode)

        # Squash multiple commits group
        self.multi_select_mode = False
        self.squash_group = QGroupBox("Select multiple commits")
        self.squash_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        squash_layout = QHBoxLayout()
        self.multi_select_btn = QPushButton("Select multiple commits")
        self.multi_select_btn.setToolTip("Select multiple commits.")
        self.perform_action_btn = QPushButton("Perform action on selected commits")
        self.perform_action_btn.setToolTip("Choose an action to apply to the selected commits.")
        self.perform_action_menu = QMenu(self)
        self.squash_selected_action = QAction("Squash selected commits", self)
        self.squash_selected_action.setToolTip("Squash the selected commits into one.")
        self.squash_selected_action.triggered.connect(self.handle_squash_selected)
        self.mark_selected_action = QAction("Mark selected commits", self)
        self.mark_selected_action.setToolTip("Mark all the selected commits.")
        self.mark_selected_action.triggered.connect(self.handle_mark_selected)
        self.drop_selected_action = QAction("Drop selected commits", self)
        self.drop_selected_action.setToolTip("Drop the selected commits.")
        self.drop_selected_action.triggered.connect(self.handle_drop_selected)
        self.move_selected_action = QAction("Move selected commits", self)
        self.move_selected_action.setToolTip("Drag the selected commits to a new position to reorder them.")
        self.move_selected_action.triggered.connect(self.handle_move_selected_info)
        self.perform_action_menu.addAction(self.squash_selected_action)
        self.perform_action_menu.addAction(self.mark_selected_action)
        self.perform_action_menu.addAction(self.drop_selected_action)
        self.perform_action_menu.addAction(self.move_selected_action)
        self.perform_action_menu.addSeparator()

        self.create_patch_menu = QMenu("Create patch(s) from selected commits", self)
        self.create_patch_menu.setToolTip("Generate patch files from the selected commits.")
        self.create_patch_consolidated_action = QAction("Consolidated single patch", self)
        self.create_patch_consolidated_action.setToolTip("Combine all selected commits into one unified-diff patch.")
        self.create_patch_consolidated_action.triggered.connect(
            lambda: self.handle_create_patch_selected(consolidated=True))
        self.create_patch_multiple_action = QAction("Multiple patches", self)
        self.create_patch_multiple_action.setToolTip("Create one format-patch file per selected commit.")
        self.create_patch_multiple_action.triggered.connect(
            lambda: self.handle_create_patch_selected(consolidated=False))
        self.create_patch_menu.addAction(self.create_patch_consolidated_action)
        self.create_patch_menu.addAction(self.create_patch_multiple_action)
        self.perform_action_menu.addMenu(self.create_patch_menu)
        self.perform_action_menu.addSeparator()
        self.difftool_selected_action = QAction("Git Difftool (requires exactly 2 commits)", self)
        self.difftool_selected_action.setToolTip("Run 'git difftool' between the two selected commits.")
        self.difftool_selected_action.triggered.connect(self.handle_difftool_selected)
        self.perform_action_menu.addAction(self.difftool_selected_action)
        self.perform_action_btn.setMenu(self.perform_action_menu)
        self.cancel_multi_btn = QPushButton("Cancel multiple selection")
        self.cancel_multi_btn.setToolTip("Cancel multi-select mode.")
        self.perform_action_btn.setEnabled(False)
        self.cancel_multi_btn.setEnabled(False)
        for btn in [self.multi_select_btn, self.perform_action_btn, self.cancel_multi_btn]:
            btn.setMinimumHeight(40)
        self.multi_select_btn.clicked.connect(self.enter_multi_select_mode)
        self.cancel_multi_btn.clicked.connect(self.handle_cancel_multi_select)
        squash_layout.addWidget(self.multi_select_btn)
        squash_layout.addWidget(self.perform_action_btn)
        squash_layout.addWidget(self.cancel_multi_btn)
        self.squash_group.setLayout(squash_layout)
        layout.addWidget(self.squash_group)

        # Origin group box
        self.origin_group = QGroupBox("Origin")
        self.origin_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        origin_layout = QHBoxLayout()
        self.fetch_btn = QPushButton("git fetch")
        self.fetch_btn.setToolTip("git fetch from the remote.")
        self.reset_origin_btn = QPushButton("git reset --hard origin")
        self.reset_origin_btn.setToolTip("Reset hard to the remote-tracking branch.")
        self.push_force_btn = QPushButton("git push --force")
        self.push_force_btn.setToolTip("Force-push the branch to the remote.")
        for btn in [self.fetch_btn, self.reset_origin_btn, self.push_force_btn]:
            btn.setMinimumHeight(40)
            btn.setMinimumWidth(120)
        self.fetch_btn.clicked.connect(self.handle_git_fetch)
        self.reset_origin_btn.clicked.connect(self.handle_git_reset_hard_origin)
        self.push_force_btn.clicked.connect(self.handle_git_push_force)
        origin_layout.addWidget(self.fetch_btn)
        origin_layout.addWidget(self.reset_origin_btn)
        origin_layout.addWidget(self.push_force_btn)
        self.origin_group.setLayout(origin_layout)
        layout.addWidget(self.origin_group)

        # Rebase group box
        self.rebase_group = QGroupBox("Rebase")
        self.rebase_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        rebase_layout = QHBoxLayout()
        self.rebase_master_btn = QPushButton("git rebase master")
        self.rebase_master_btn.setToolTip("Rebase the current branch onto master.")
        self.rebase_main_btn = QPushButton("git rebase main")
        self.rebase_main_btn.setToolTip("Rebase the current branch onto main.")
        self.rebase_custom_btn = QPushButton("Enter branch/sha to rebase on top of")
        self.rebase_custom_btn.setToolTip("Rebase onto a branch/sha you enter.")
        for btn in [self.rebase_master_btn, self.rebase_main_btn, self.rebase_custom_btn]:
            btn.setMinimumHeight(40)
            btn.setMinimumWidth(120)
        self.rebase_master_btn.clicked.connect(self.handle_git_rebase_master)
        self.rebase_main_btn.clicked.connect(self.handle_git_rebase_main)
        self.rebase_custom_btn.clicked.connect(self.handle_git_rebase_custom)
        rebase_layout.addWidget(self.rebase_master_btn)
        rebase_layout.addWidget(self.rebase_main_btn)
        rebase_layout.addWidget(self.rebase_custom_btn)
        self.rebase_group.setLayout(rebase_layout)
        layout.addWidget(self.rebase_group)

        # ── Status Bar ──
        status_bar = self.statusBar()
        status_widget = QWidget()
        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(4, 0, 4, 0)
        status_layout.setSpacing(6)

        # Zoom controls
        zoom_label = QLabel("Zoom:")
        self.sb_zoom_out_btn = QPushButton("–")
        self.sb_zoom_out_btn.setFixedSize(26, 22)
        self.sb_zoom_out_btn.setToolTip("Zoom out.")
        self.sb_zoom_out_btn.setStyleSheet("padding: 0px;")
        self.zoom_percent_label = QLabel("100%")
        self.zoom_percent_label.setFixedWidth(40)
        self.zoom_percent_label.setAlignment(Qt.AlignCenter)
        self.sb_zoom_in_btn = QPushButton("+")
        self.sb_zoom_in_btn.setFixedSize(26, 22)
        self.sb_zoom_in_btn.setToolTip("Zoom in.")
        self.sb_zoom_in_btn.setStyleSheet("padding: 0px;")
        self.sb_zoom_in_btn.clicked.connect(self.handle_zoom_in)
        self.sb_zoom_out_btn.clicked.connect(self.handle_zoom_out)

        status_layout.addWidget(zoom_label)
        status_layout.addWidget(self.sb_zoom_out_btn)
        status_layout.addWidget(self.zoom_percent_label)
        status_layout.addWidget(self.sb_zoom_in_btn)

        if self.browse_mode:
            for w in [zoom_label, self.sb_zoom_out_btn, self.zoom_percent_label,
                      self.sb_zoom_in_btn]:
                w.setVisible(False)

        sep1 = QLabel("|")
        sep1.setStyleSheet("color: gray;")
        status_layout.addWidget(sep1)
        if self.browse_mode:
            sep1.setVisible(False)

        # Configure button replaces the visibility checkboxes (origin, rebase,
        # squash, local branches, stats, date) with a Show/Hide menu.
        self.configure_btn = QPushButton("Configure")
        self.configure_btn.setToolTip("Configure which controls are visible.")
        self.configure_btn.setStyleSheet("padding: 0px 8px;")
        self.configure_btn.setFixedHeight(22)
        self._set_configure_icon(self.configure_btn)
        self.configure_btn.clicked.connect(self._show_configure_menu)

        self.configure_menu = self._build_configure_menu()
        if self.browse_mode:
            for action in [self.show_origin_action, self.show_rebase_action,
                           self.show_squash_action]:
                action.setEnabled(False)

        self.always_on_top_cb = QCheckBox("Always On Top")
        self.always_on_top_cb.setToolTip("Keep the window on top.")
        self.always_on_top_cb.toggled.connect(self._on_always_on_top_toggled)
        status_layout.addWidget(self.always_on_top_cb)

        sep_ontop = QLabel("|")
        sep_ontop.setStyleSheet("color: gray;")
        status_layout.addWidget(sep_ontop)

        status_layout.addStretch()

        sep3 = QLabel("|")
        sep3.setStyleSheet("color: gray;")
        status_layout.addWidget(sep3)

        status_layout.addWidget(self.configure_btn)

        sep_configure = QLabel("|")
        sep_configure.setStyleSheet("color: gray;")
        status_layout.addWidget(sep_configure)

        self.total_commits_label = QLabel("Total: 0")
        self.total_commits_label.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(self.total_commits_label)

        sep4 = QLabel("|")
        sep4.setStyleSheet("color: gray;")
        status_layout.addWidget(sep4)

        self.showing_commits_label = QLabel("Showing: 0")
        self.showing_commits_label.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(self.showing_commits_label)

        self.sep_merge = QLabel("|")
        self.sep_merge.setStyleSheet("color: gray;")
        self.sep_merge.setVisible(False)
        status_layout.addWidget(self.sep_merge)

        self.merge_commits_label = QLabel("Merge: 0")
        self.merge_commits_label.setStyleSheet("font-weight: bold;")
        self.merge_commits_label.setVisible(False)
        status_layout.addWidget(self.merge_commits_label)

        status_bar.addPermanentWidget(status_widget, 1)


        # Keyboard Shortcuts
        self.slash_shortcut = QShortcut(QKeySequence("/"), self)
        self.slash_shortcut.activated.connect(self.handle_slash_shortcut)

        self.esc_shortcut = QShortcut(QKeySequence("Esc"), self)
        self.esc_shortcut.activated.connect(self.handle_esc_shortcut)

        self.f5_shortcut = QShortcut(QKeySequence("F5"), self)
        self.f5_shortcut.activated.connect(self.handle_manual_refresh)

        self.ctrl_f_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.ctrl_f_shortcut.activated.connect(self.show_search_bar)

        self.ctrl_q_shortcut = QShortcut(QKeySequence("Ctrl+Q"), self)
        self.ctrl_q_shortcut.activated.connect(self.close)

        self.ctrl_z_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.ctrl_z_shortcut.activated.connect(self.handle_undo_shortcut)

        # A grey veil over the whole browse window marks it as a read-only viewer.
        self._browse_overlay = None
        if self.browse_mode:
            self._browse_overlay = BrowseDimOverlay(self, self.is_dark_theme)
            self._browse_overlay.raise_()

        # Create the commit-list filter controller.
        from lib.commit_filter_controller import CommitFilterController
        self._filter_controller = CommitFilterController(
            self, self.list_widget, self.commit_cache, self.repo_path,
            self.search_edit, self.filter_by_files_cb, self.filter_by_diff_cb,
            self.filter_by_author_cb, self._diff_status_label,
            self.showing_commits_label, self.sep_merge, self.merge_commits_label,
            MATCH_ROLE, _diff_search_matches, get_commit_files_with_status,
            get_commit_diff, self.settings, self._sk)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, '_browse_overlay', None) is not None:
            self._browse_overlay.setGeometry(self.rect())

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, '_browse_overlay', None) is not None:
            self._browse_overlay.setGeometry(self.rect())
            self._browse_overlay.raise_()

"""Modal dialog components.

This package contains reusable dialog windows for:
- Game completion: GameOverDialog
- Session management: ResumeSessionDialog
- Data loss prevention: UnsavedWarningDialog
- Interventions: EditScoreDialog, ForceSideOutDialog, AddCommentDialog
- Export completion: ExportCompleteDialog
- Export progress: ExportProgressDialog
- Configuration: ConfigDialog
- Frame selection: FrameSelectorDialog
- Player names: PlayerNamesDialog
- New game: NewGameConfirmDialog
- Auto-edit pipeline progress: AutoEditProgressDialog
- Human-in-the-loop retraining: RetrainProgressDialog, RetrainResultDialog
"""

from src.ui.dialogs.game_over import GameOverDialog, GameOverResult
from src.ui.dialogs.resume_session import (
    ResumeSessionDialog,
    ResumeSessionResult,
    SessionDetails,
)
from src.ui.dialogs.unsaved_warning import UnsavedWarningDialog, UnsavedWarningResult
from src.ui.dialogs.edit_score import EditScoreDialog, EditScoreResult
from src.ui.dialogs.force_sideout import ForceSideOutDialog, ForceSideOutResult
from src.ui.dialogs.frame_selector_dialog import FrameSelectorDialog
from src.ui.dialogs.add_comment import AddCommentDialog, AddCommentResult
from src.ui.dialogs.export_complete import ExportCompleteDialog, ExportCompleteResult
from src.ui.dialogs.export_progress import (
    ExportProgressDialog,
    ExportProgressResult,
    FFmpegWorker,
)
from src.ui.dialogs.config_dialog import ConfigDialog, ConfigDialogResult
from src.ui.dialogs.player_names import PlayerNamesDialog, PlayerNamesResult
from src.ui.dialogs.new_game_confirm import (
    NewGameConfirmDialog,
    NewGameResult,
    NewGameSettings,
)
from src.ui.dialogs.auto_edit_progress import (
    AutoEditProgressDialog,
    AutoEditWorker,
)
from src.ui.dialogs.retrain_dialog import (
    RetrainProgressDialog,
    RetrainResultDialog,
    decide_default_apply,
    format_result_text,
)

__all__ = [
    # Game Over Dialog
    "GameOverDialog",
    "GameOverResult",
    # Resume Session Dialog
    "ResumeSessionDialog",
    "ResumeSessionResult",
    "SessionDetails",
    # Unsaved Warning Dialog
    "UnsavedWarningDialog",
    "UnsavedWarningResult",
    # Edit Score Dialog
    "EditScoreDialog",
    "EditScoreResult",
    # Force Side-Out Dialog
    "ForceSideOutDialog",
    "ForceSideOutResult",
    # Frame Selector Dialog
    "FrameSelectorDialog",
    # Add Comment Dialog
    "AddCommentDialog",
    "AddCommentResult",
    # Export Complete Dialog
    "ExportCompleteDialog",
    "ExportCompleteResult",
    # Export Progress Dialog
    "ExportProgressDialog",
    "ExportProgressResult",
    "FFmpegWorker",
    # Config Dialog
    "ConfigDialog",
    "ConfigDialogResult",
    # Player Names Dialog
    "PlayerNamesDialog",
    "PlayerNamesResult",
    # New Game Confirm Dialog
    "NewGameConfirmDialog",
    "NewGameResult",
    "NewGameSettings",
    # Auto-Edit Progress Dialog
    "AutoEditProgressDialog",
    "AutoEditWorker",
    # Retrain Rally Detector Dialog
    "RetrainProgressDialog",
    "RetrainResultDialog",
    "decide_default_apply",
    "format_result_text",
]

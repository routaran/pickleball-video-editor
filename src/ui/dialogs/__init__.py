"""Modal dialog components.

This package contains reusable dialog windows for:
- Game completion: GameOverDialog
- Session management: ResumeSessionDialog
- Data loss prevention: UnsavedWarningDialog
- Interventions: EditScoreDialog, ForceSideOutDialog, AddCommentDialog
- Export completion: ExportCompleteDialog
- Export progress: ExportProgressDialog
- Configuration: ConfigDialog
- Player names: PlayerNamesDialog
- New game: NewGameConfirmDialog
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
]

"""Status overlay widget that displays game status on top of the video player.

This widget overlays the video player showing:
- Status indicator (dot + text: IN RALLY / WAITING)
- Current score (e.g., "7-5-2")
- Server information (e.g., "Team 1 (John) #2")

Layout:
    ┌───────────────────────────────────────────────────────────┐
    │  ● IN RALLY    Score: 7-5-2    Server: Team 1 (John) #2  │
    └───────────────────────────────────────────────────────────┘

Visual Design:
- Semi-transparent background: rgba(26, 29, 35, 0.85)
- Border: 1px solid rgba(255,255,255,0.1)
- Border-radius: 6px
- Padding: 8px 16px
- Status dot: 8px diameter, green (in rally) or amber (waiting)
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel

from src.ui.styles.colors import BG_PRIMARY, RALLY_START, TEXT_PRIMARY, TEXT_WARNING, Colors
from src.ui.styles.fonts import SPACE_MD, SPACE_SM, Fonts, RADIUS_MD


class StatusOverlay(QFrame):
    """Semi-transparent overlay displaying current game status.

    This widget is designed to be positioned on top of the video player
    using absolute positioning or a stacked layout.

    The overlay shows three pieces of information:
    1. Rally status (WAITING or IN RALLY) with colored dot indicator
    2. Current score in large tabular numerals
    3. Server information (team, player name, server number)

    Example:
        ```python
        overlay = StatusOverlay()
        overlay.update_display(
            in_rally=True,
            score="7-5-2",
            server_info="Team 1 (John) #2"
        )
        ```
    """

    def __init__(self, parent=None):
        """Initialize the status overlay widget.

        Args:
            parent: Parent widget (typically the video player container)
        """
        super().__init__(parent)

        # Configure the frame as an overlay
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setObjectName("status_overlay")

        # Track compact mode state
        self._compact_mode = False

        # Initialize child widgets
        self._status_dot = QLabel()
        self._status_text = QLabel("WAITING")
        self._score_label = QLabel("Score:")
        self._score_value = QLabel("0-0-2")
        self._server_label = QLabel("Server:")
        self._server_value = QLabel("Team 1 #1")

        # Setup UI
        self._setup_ui()
        self._apply_styles()

        # Set initial state
        self.set_status(in_rally=False)

    def _setup_ui(self) -> None:
        """Configure the layout and widget hierarchy."""
        # Create horizontal layout with padding
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_MD, SPACE_SM, SPACE_MD, SPACE_SM)
        layout.setSpacing(SPACE_MD)

        # Status section (dot + text)
        self._status_dot.setFixedSize(8, 8)
        self._status_dot.setObjectName("status_dot")
        layout.addWidget(self._status_dot)

        self._status_text.setObjectName("status_text")
        layout.addWidget(self._status_text)

        # Add some spacing between sections
        layout.addSpacing(SPACE_MD)

        # Score section (label + value)
        self._score_label.setObjectName("score_label")
        layout.addWidget(self._score_label)

        self._score_value.setObjectName("score_value")
        layout.addWidget(self._score_value)

        # Add spacing
        layout.addSpacing(SPACE_MD)

        # Server section (label + value)
        self._server_label.setObjectName("server_label")
        layout.addWidget(self._server_label)

        self._server_value.setObjectName("server_value")
        layout.addWidget(self._server_value)

        # Push everything to the left
        layout.addStretch()

    def _apply_styles(self) -> None:
        """Apply styling to the overlay and child widgets."""
        # Background: semi-transparent primary background
        bg_rgba = Colors.to_rgba(BG_PRIMARY, 0.85)

        # Create stylesheet
        stylesheet = f"""
            QFrame#status_overlay {{
                background-color: {bg_rgba};
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: {RADIUS_MD}px;
            }}

            QLabel#status_dot {{
                border-radius: 4px;
                background-color: {TEXT_WARNING};
            }}

            QLabel#status_text {{
                color: {TEXT_PRIMARY};
                font-weight: 600;
            }}

            QLabel#score_label,
            QLabel#server_label {{
                color: {TEXT_PRIMARY};
            }}

            QLabel#score_value {{
                color: {TEXT_PRIMARY};
                font-weight: 700;
            }}

            QLabel#server_value {{
                color: {TEXT_PRIMARY};
            }}
        """

        self.setStyleSheet(stylesheet)

        # Apply fonts
        # Status text: body font, medium weight
        status_font = Fonts.body(size=14, weight=500)
        self._status_text.setFont(status_font)

        # Score label: body font, regular
        label_font = Fonts.label()
        self._score_label.setFont(label_font)
        self._server_label.setFont(label_font)

        # Score value: display font (monospace, bold, tabular) - LARGER
        score_font = Fonts.display(size=24, weight=700, tabular=True)
        self._score_value.setFont(score_font)

        # Server value: body font, regular
        server_font = Fonts.body(size=14, weight=400)
        self._server_value.setFont(server_font)

    def set_status(self, in_rally: bool) -> None:
        """Update status dot and text (WAITING or IN RALLY).

        Args:
            in_rally: True if currently in a rally, False if waiting
        """
        if in_rally:
            # Green dot for "IN RALLY"
            self._status_dot.setStyleSheet(f"""
                QLabel#status_dot {{
                    border-radius: 4px;
                    background-color: {RALLY_START};
                }}
            """)
            self._status_text.setText("IN RALLY")
        else:
            # Amber/warning color for "WAITING"
            self._status_dot.setStyleSheet(f"""
                QLabel#status_dot {{
                    border-radius: 4px;
                    background-color: {TEXT_WARNING};
                }}
            """)
            self._status_text.setText("WAITING")

    def set_score(self, score_text: str) -> None:
        """Update score display.

        Args:
            score_text: Score string (e.g., "7-5-2" for doubles, "7-5" for singles)
        """
        self._score_value.setText(score_text)

    def set_server_info(self, server_info: str) -> None:
        """Update server information display.

        Args:
            server_info: Server description (e.g., "Team 1 (John) #2")
        """
        self._server_value.setText(server_info)

    def update_display(self, in_rally: bool, score: str, server_info: str) -> None:
        """Update all status fields at once.

        This is the preferred method for updating the overlay as it's more
        efficient than calling individual setters.

        Args:
            in_rally: True if currently in a rally
            score: Score string (e.g., "7-5-2")
            server_info: Server description (e.g., "Team 1 (John) #2")

        Example:
            ```python
            overlay.update_display(
                in_rally=True,
                score="7-5-2",
                server_info="Team 1 (Alice) #1"
            )
            ```
        """
        self.set_status(in_rally)
        self.set_score(score)
        self.set_server_info(server_info)

    def set_compact_mode(self, compact: bool) -> None:
        """Apply compact or normal mode styling.

        In compact mode (window < 950px width), font sizes are reduced:
        - Score value: 18px instead of 24px
        - Labels: 11px instead of 13px
        - Status and server text: 12px instead of 14px

        Args:
            compact: True for smaller fonts (window < 950px width)
        """
        if compact == self._compact_mode:
            return  # No change needed

        self._compact_mode = compact

        # Scale score value (most prominent element)
        score_size = 18 if compact else 24
        self._score_value.setFont(Fonts.display(size=score_size, weight=700, tabular=True))

        # Scale labels
        label_size = 11 if compact else 13
        label_font = Fonts.body(size=label_size, weight=400)
        self._score_label.setFont(label_font)
        self._server_label.setFont(label_font)

        # Scale status and server text
        text_size = 12 if compact else 14
        self._status_text.setFont(Fonts.body(size=text_size, weight=500))
        self._server_value.setFont(Fonts.body(size=text_size, weight=400))

        # Resize widget to fit new font sizes
        self.adjustSize()


__all__ = ["StatusOverlay"]

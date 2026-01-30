"""Forge TUI widgets."""
try:
    from forge.widgets.chat_display import ChatDisplay
    from forge.widgets.file_autocomplete import FileAutoComplete, FileInput
    from forge.widgets.status_bar import StatusBar
    __all__ = ["ChatDisplay", "FileAutoComplete", "FileInput", "StatusBar"]
except ImportError:
    # Textual not installed - widgets unavailable
    __all__ = []

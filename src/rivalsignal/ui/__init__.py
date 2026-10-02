"""Rerunnable UI; page configuration belongs to the host."""
from rivalsignal import __version__
from rivalsignal.ui import signal_theme
from rivalsignal.ui.app import render

APP_INFO = {"product": "Rival Signal", "version": __version__, "repo": "competitor-analysis", "slug": "rival"}
__all__ = ["APP_INFO", "render", "signal_theme"]

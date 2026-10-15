"""File in/out on Android: pick files with the system picker, export to the gallery.

Two layers, both wrapped so a failure can never take the app down:

* ``androidstorage4kivy`` (the Android-for-Python helper) does the real work on a
  device - the system chooser for input, MediaStore for output, the share sheet
  for sending files to Telegram/WhatsApp.
* without it (desktop test runs, or an exotic device) files are copied into a
  normal folder and the UI simply shows where they went.
"""
from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger("easywalp.android.storage")

PICK_IMAGE = "image/*"
PICK_PSD = "*/*"


class Storage:
    """Small facade over the Android storage APIs with graceful degradation."""

    def __init__(self) -> None:
        self._shared = None
        self._chooser = None
        self._sheet = None
        self.error = ""
        if not _on_android():
            self.error = "desktop"
            return
        try:
            from androidstorage4kivy import Chooser, SharedStorage, ShareSheet

            self._shared = SharedStorage()
            self._chooser = Chooser()
            self._sheet = ShareSheet()
        except Exception as e:  # noqa: BLE001 - keep the app usable without it
            self.error = str(e)
            log.warning("androidstorage4kivy unavailable: %s", e)

    # ------------------------------------------------------------------ info
    @property
    def rich(self) -> bool:
        """True when the gallery export + share sheet are available."""
        return self._shared is not None

    # ----------------------------------------------------------------- picking
    def pick_file(
        self,
        mime: str,
        on_picked: Callable[[Path | None, str], None],
        *,
        title: str = "",
        filetypes: list[tuple[str, list[str]]] | None = None,
    ) -> None:
        """Ask the user for a file; ``on_picked(path, error)`` runs on the UI thread later.

        On Android the picker returns a content URI which is copied into EasyWalp's
        private cache first - the pipeline needs a real filesystem path (the engine
        reads files itself).
        """
        if self._chooser is not None and self._shared is not None:
            self._chooser.callback = lambda uris: self._on_uris(uris, on_picked)
            try:
                self._chooser.choose_content(mime)
            except Exception as e:  # noqa: BLE001
                log.exception("chooser failed")
                on_picked(None, str(e))
            return
        _desktop_pick(on_picked, title=title, filetypes=filetypes or [])

    def _on_uris(self, uris: list, on_picked: Callable[[Path | None, str], None]) -> None:
        if not uris:
            on_picked(None, "cancelled")
            return
        try:
            private = self._shared.copy_from_shared(uris[0])
        except Exception as e:  # noqa: BLE001
            log.exception("copy_from_shared failed")
            on_picked(None, str(e))
            return
        if not private:
            on_picked(None, "the picked file could not be copied into the app")
            return
        on_picked(Path(str(private)), "")

    # ---------------------------------------------------------------- exporting
    def export(self, files: list[Path], *, subfolder: str = "") -> tuple[list[str], str]:
        """Put finished JPGs somewhere the user can see them.

        Returns ``(handles, error)`` where *handles* are MediaStore URIs on Android
        (used for sharing) or plain paths in the fallback folder.
        """
        files = [Path(f) for f in files if Path(f).is_file()]
        if not files:
            return [], "nothing to export"
        if self._shared is not None:
            handles: list[str] = []
            errors: list[str] = []
            for path in files:
                rel = f"{subfolder}/{path.name}" if subfolder else path.name
                try:
                    handle = self._shared.copy_to_shared(str(path), collection="Pictures", filepath=rel)
                except Exception as e:  # noqa: BLE001
                    log.exception("copy_to_shared failed")
                    handle = None
                    errors.append(str(e))
                if handle:
                    handles.append(str(handle))
                else:
                    errors.append(path.name)
            if handles:
                return handles, ""
            return [], "the gallery export failed: " + ", ".join(errors[:3])
        # Fallback: a plain folder (device without the helper, or a desktop run).
        try:
            target = fallback_export_dir() / subfolder if subfolder else fallback_export_dir()
            target.mkdir(parents=True, exist_ok=True)
            out: list[str] = []
            for path in files:
                dest = target / path.name
                shutil.copyfile(path, dest)
                out.append(str(dest))
            return out, ""
        except OSError as e:
            return [], str(e)

    def share(self, handles: list[str], *, text: str = "") -> str:
        """Share exported files (or the code) through the Android share sheet."""
        if self._sheet is None:
            return "sharing is not available in this build"
        try:
            files = [h for h in handles if h and not h.startswith("/")]
            if files:
                self._sheet.share_file_list(files)
            elif text:
                self._sheet.share_plain_text(text)
            else:
                return "nothing to share"
            return ""
        except Exception as e:  # noqa: BLE001
            log.exception("share failed")
            return str(e)

    def view(self, handle: str) -> str:
        if self._sheet is None or not handle:
            return "opening files is not available in this build"
        try:
            self._sheet.view_file(handle)
            return ""
        except Exception as e:  # noqa: BLE001
            return str(e)


def fallback_export_dir() -> Path:
    """Where exports go when the MediaStore helper is unavailable."""
    try:
        from easywalp import paths

        if paths.is_android():
            from .platform import external_files_dir

            ext = external_files_dir()
            if ext is not None:
                return ext / "EasyWalp"
        return paths.data_dir() / "out"
    except Exception:  # noqa: BLE001
        return Path.home() / "EasyWalp"


def _on_android() -> bool:
    try:
        from easywalp import paths

        return paths.is_android()
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------- desktop picker
def _desktop_pick(
    on_picked: Callable[[Path | None, str], None], *, title: str, filetypes: list[tuple[str, list[str]]]
) -> None:
    """A Kivy file browser for desktop test runs of the Android UI."""
    try:
        from kivy.uix.filechooser import FileChooserListView
        from kivy.uix.popup import Popup

        from .ui.theme import tr

        chooser = FileChooserListView(path=str(Path.home()), filters=[f"*.{f}" for _l, exts in filetypes for f in exts])

        popup = Popup(title=title or tr("and.chooseFile"), content=chooser, size_hint=(0.9, 0.9))

        def _chosen(_chooser, selection, _touch):
            if selection:
                popup.dismiss()
                on_picked(Path(selection[0]), "")

        chooser.bind(on_submit=_chosen)
        popup.open()
    except Exception as e:  # noqa: BLE001 - headless runs have no window
        on_picked(None, str(e))

"""System tray icon (XApp on Cinnamon/Mint, falling back to AppIndicator or GtkStatusIcon)."""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

ICON = "applets-screenshooter"


class Tray:
    def __init__(self, app, menu_builder):
        self.app, self.build = app, menu_builder
        self.kind = None
        self.icon = None
        self._make()

    def _make(self):
        try:
            gi.require_version("XApp", "1.0")
            from gi.repository import XApp
            self.icon = XApp.StatusIcon()
            self.icon.set_name("mintshare")
            self.icon.set_icon_name(ICON)
            self.icon.set_tooltip_text("MintShare")
            self.icon.connect("activate", lambda *a: self.app.show_main())
            self.menu = self.build()
            self.icon.set_secondary_menu(self.menu)
            self.kind = "xapp"
            return
        except (ValueError, ImportError, AttributeError):
            pass
        for ns in ("AyatanaAppIndicator3", "AppIndicator3"):
            try:
                gi.require_version(ns, "0.1")
                mod = getattr(__import__("gi.repository", fromlist=[ns]), ns)
                self._ind_mod = mod
                self.icon = mod.Indicator.new("mintshare", ICON, mod.IndicatorCategory.APPLICATION_STATUS)
                self.icon.set_status(mod.IndicatorStatus.ACTIVE)
                self.menu = self.build()
                self.icon.set_menu(self.menu)
                self.kind = "appindicator"
                return
            except (ValueError, ImportError, AttributeError):
                continue
        self.icon = Gtk.StatusIcon()
        self.icon.set_from_icon_name(ICON)
        self.icon.set_tooltip_text("MintShare")
        self.menu = self.build()
        self.icon.connect("activate", lambda *a: self.app.show_main())
        self.icon.connect("popup-menu", lambda i, b, t: self.menu.popup(None, None, Gtk.StatusIcon.position_menu, i, b, t))
        self.kind = "gtk"

    def rebuild(self):
        self.menu = self.build()
        if self.kind == "xapp":
            self.icon.set_secondary_menu(self.menu)
        elif self.kind == "appindicator":
            self.icon.set_menu(self.menu)

    def set_recording(self, on):
        name = "media-record" if on else ICON
        if self.kind in ("xapp",):
            self.icon.set_icon_name(name)
        elif self.kind == "appindicator":
            self.icon.set_icon(name)
        else:
            self.icon.set_from_icon_name(name)

    def destroy(self):
        try:
            if self.kind == "xapp":
                self.icon.set_visible(False)
            elif self.kind == "appindicator":
                self.icon.set_status(self._ind_mod.IndicatorStatus.PASSIVE)
            else:
                self.icon.set_visible(False)
        except Exception:
            pass
